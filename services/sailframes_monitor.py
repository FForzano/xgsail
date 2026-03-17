#!/usr/bin/env python3
"""
SailFrames Monitor Service
Monitors system health: CPU temp, battery level, disk usage, sensor status.
Provides a local web dashboard on port 8080.
Triggers clean shutdown on low battery.
"""

import os
import sys
import csv
import time
import signal
import logging
import threading
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psutil
from flask import Flask, jsonify, render_template_string, request
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [MONITOR] %(levelname)s %(message)s'
)
logger = logging.getLogger('sailframes.monitor')

running = True

def signal_handler(sig, frame):
    global running
    logger.info("Shutdown signal received")
    running = False

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def load_config():
    config_paths = [
        '/etc/sailframes/sailframes.yaml',
        os.path.join(os.path.dirname(__file__), '..', 'config', 'sailframes.yaml')
    ]
    for path in config_paths:
        if os.path.exists(path):
            with open(path) as f:
                return yaml.safe_load(f)
    logger.error("No config file found")
    sys.exit(1)


def get_cpu_temp():
    """Read Pi CPU temperature."""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def get_battery_info():
    """
    Read battery status from Waveshare UPS HAT (D) via I2C.
    - INA219 at 0x43: voltage/current monitoring
    - Battery percentage calculated from output voltage:
      - Full (charging): ~4.2V output
      - Empty (shutdown): ~3.4V output
    """
    INA219_ADDR = 0x43
    REG_BUS_VOLTAGE = 0x02
    REG_SHUNT_VOLTAGE = 0x01
    SHUNT_OHMS = 0.1

    # Output voltage range observed on UPS HAT (D)
    VOUT_FULL = 4.2   # Output voltage when fully charged
    VOUT_EMPTY = 3.4  # Output voltage when battery depleted

    try:
        import smbus2
        bus = smbus2.SMBus(1)

        # Read output voltage from INA219
        raw_bus = bus.read_word_data(INA219_ADDR, REG_BUS_VOLTAGE)
        raw_bus = ((raw_bus & 0xFF) << 8) | ((raw_bus >> 8) & 0xFF)
        voltage = (raw_bus >> 3) * 0.004

        # Read current from INA219 shunt
        raw_shunt = bus.read_word_data(INA219_ADDR, REG_SHUNT_VOLTAGE)
        raw_shunt = ((raw_shunt & 0xFF) << 8) | ((raw_shunt >> 8) & 0xFF)
        if raw_shunt > 32767:
            raw_shunt -= 65536
        shunt_mv = raw_shunt * 0.01
        current_ma = shunt_mv / SHUNT_OHMS

        bus.close()

        # Calculate battery percentage from output voltage
        percent = (voltage - VOUT_EMPTY) / (VOUT_FULL - VOUT_EMPTY) * 100.0
        percent = max(0, min(100, percent))

        # Charging detection: current is negative when USB powers system and charges battery
        # Positive current = discharging (battery powering Pi)
        # Negative current = charging (USB powering Pi + charging battery)
        charging = current_ma < 0

        return {
            'voltage': round(voltage, 2),
            'percent': round(percent, 1),
            'current_ma': round(current_ma, 0),
            'charging': charging,
        }
    except Exception as e:
        logger.debug(f"Battery read error: {e}")
        return {'voltage': None, 'percent': None, 'current_ma': None, 'charging': None}


def get_disk_usage(mount_point):
    """Get disk usage for data storage."""
    try:
        usage = psutil.disk_usage(mount_point)
        return {
            'total_gb': round(usage.total / (1024**3), 1),
            'used_gb': round(usage.used / (1024**3), 1),
            'free_gb': round(usage.free / (1024**3), 1),
            'percent': usage.percent,
        }
    except Exception:
        return {'total_gb': 0, 'used_gb': 0, 'free_gb': 0, 'percent': 0}


def check_service_status(service_name):
    """Check if a systemd service is running."""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == 'active'
    except Exception:
        return False


def get_latest_gps():
    """Get latest GPS data from most recent CSV file with detailed metrics."""
    try:
        data_dir = Path('/mnt/sailframes-data')
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        gps_dir = data_dir / today / 'gps'

        if not gps_dir.exists():
            return None

        # Find most recent CSV
        csv_files = sorted(gps_dir.glob('track_*.csv'), reverse=True)
        if not csv_files:
            return None

        # Read last lines for stats
        with open(csv_files[0], 'r') as f:
            lines = f.readlines()
            if len(lines) < 2:
                return None
            last_line = lines[-1].strip()
            # Get recent lines for stats (last 60 = ~1 minute at 1Hz)
            recent_lines = lines[-61:] if len(lines) > 60 else lines[1:]

        # Parse CSV line
        parts = last_line.split(',')
        if len(parts) < 10:
            return None

        # Fix quality descriptions with detailed explanations
        fix_info = {
            0: {'name': 'No Fix', 'accuracy_m': None, 'desc': 'No satellite signal received'},
            1: {'name': 'GPS (SPS)', 'accuracy_m': 2.5, 'desc': 'Standard Positioning Service - civilian GPS'},
            2: {'name': 'DGPS', 'accuracy_m': 1.0, 'desc': 'Differential GPS - uses SBAS corrections (WAAS/EGNOS)'},
            4: {'name': 'RTK Fixed', 'accuracy_m': 0.02, 'desc': 'Real-Time Kinematic - centimeter-level accuracy'},
            5: {'name': 'RTK Float', 'accuracy_m': 0.5, 'desc': 'RTK converging - decimeter accuracy, improving'},
            6: {'name': 'Dead Reckoning', 'accuracy_m': 10.0, 'desc': 'Estimated position based on last known + motion'},
        }

        fix_quality = int(parts[7]) if parts[7] else 0
        speed_knots = float(parts[4]) if parts[4] else 0
        hdop = float(parts[9]) if parts[9] else 99
        satellites = int(parts[8]) if parts[8] else 0

        # Calculate estimated accuracy
        # Base accuracy depends on fix type, multiplied by HDOP
        base_accuracy = fix_info.get(fix_quality, {}).get('accuracy_m', 5.0)
        if base_accuracy:
            estimated_accuracy_m = base_accuracy * hdop
            estimated_accuracy_cm = int(estimated_accuracy_m * 100)
        else:
            estimated_accuracy_m = None
            estimated_accuracy_cm = None

        # HDOP quality rating
        if hdop < 1:
            hdop_rating = 'Ideal'
            hdop_desc = 'Highest precision, satellites well distributed'
        elif hdop < 2:
            hdop_rating = 'Excellent'
            hdop_desc = 'Very high precision positioning'
        elif hdop < 5:
            hdop_rating = 'Good'
            hdop_desc = 'Good for most navigation'
        elif hdop < 10:
            hdop_rating = 'Moderate'
            hdop_desc = 'Fair accuracy, some satellites blocked'
        elif hdop < 20:
            hdop_rating = 'Fair'
            hdop_desc = 'Low accuracy, poor satellite geometry'
        else:
            hdop_rating = 'Poor'
            hdop_desc = 'Position unreliable'

        # Calculate statistics from recent data
        recent_hdops = []
        recent_sats = []
        for line in recent_lines:
            if line.startswith('utc') or line.startswith('20'):
                p = line.strip().split(',')
                if len(p) >= 10 and p[9]:
                    try:
                        recent_hdops.append(float(p[9]))
                        recent_sats.append(int(p[8]))
                    except:
                        pass

        avg_hdop = sum(recent_hdops) / len(recent_hdops) if recent_hdops else hdop
        min_hdop = min(recent_hdops) if recent_hdops else hdop
        max_hdop = max(recent_hdops) if recent_hdops else hdop
        avg_sats = sum(recent_sats) / len(recent_sats) if recent_sats else satellites

        # Get total points logged today
        total_points = len(lines) - 1  # Minus header

        return {
            # Position
            'latitude': float(parts[1]) if parts[1] else None,
            'longitude': float(parts[2]) if parts[2] else None,
            'altitude_m': float(parts[3]) if parts[3] else None,

            # Speed (multiple units)
            'speed_knots': round(speed_knots, 2),
            'speed_mph': round(speed_knots * 1.15078, 2),
            'speed_kmh': round(speed_knots * 1.852, 2),
            'speed_mps': round(speed_knots * 0.514444, 3),

            # Course
            'course_deg': float(parts[6]) if parts[6] else None,

            # Fix info
            'fix_quality': fix_quality,
            'fix_type': fix_info.get(fix_quality, {}).get('name', f'Unknown ({fix_quality})'),
            'fix_desc': fix_info.get(fix_quality, {}).get('desc', ''),

            # Satellites
            'satellites': satellites,
            'satellites_avg': round(avg_sats, 1),

            # Precision
            'hdop': round(hdop, 2),
            'hdop_rating': hdop_rating,
            'hdop_desc': hdop_desc,
            'hdop_avg': round(avg_hdop, 2),
            'hdop_min': round(min_hdop, 2),
            'hdop_max': round(max_hdop, 2),

            # Estimated accuracy
            'accuracy_m': round(estimated_accuracy_m, 2) if estimated_accuracy_m else None,
            'accuracy_cm': estimated_accuracy_cm,
            'accuracy_rating': hdop_rating,

            # Stats
            'total_points_today': total_points,
            'sample_rate_hz': 10,  # From config
            'timestamp': parts[0],
            'gps_time': parts[10] if len(parts) > 10 else '',
        }
    except Exception as e:
        logger.debug(f"GPS read error: {e}")
        return None


# ── System state (shared between monitor thread and web server) ──
system_state = {
    'device_id': '',
    'uptime_sec': 0,
    'cpu_temp_c': None,
    'cpu_percent': 0,
    'ram_percent': 0,
    'battery': {},
    'disk': {},
    'gps': {},
    'services': {},
    'last_update': '',
}


def monitor_loop(config):
    """Background thread that collects system stats."""
    global system_state, running

    monitor_config = config['monitor']
    interval = monitor_config['stats_interval_sec']
    shutdown_percent = monitor_config['battery_shutdown_percent']
    data_mount = config['storage']['ssd_mount']

    system_state['device_id'] = config['device']['id']

    while running:
        system_state['cpu_temp_c'] = get_cpu_temp()
        system_state['cpu_percent'] = psutil.cpu_percent(interval=1)
        system_state['ram_percent'] = psutil.virtual_memory().percent
        system_state['battery'] = get_battery_info()
        system_state['disk'] = get_disk_usage(data_mount)
        system_state['gps'] = get_latest_gps() or {}
        system_state['uptime_sec'] = int(time.monotonic())
        system_state['last_update'] = datetime.now(timezone.utc).isoformat()

        # Check service status
        system_state['services'] = {
            'gps': check_service_status('sailframes-gps'),
            'imu': check_service_status('sailframes-imu'),
            'pressure': check_service_status('sailframes-pressure'),
            'wind': check_service_status('sailframes-wind'),
            'camera': check_service_status('sailframes-camera'),
        }

        # Low battery shutdown - only if batteries are actually present
        # (voltage > 5V means batteries installed, not just HAT with no/dead batteries)
        battery_pct = system_state['battery'].get('percent')
        battery_voltage = system_state['battery'].get('voltage')
        if (battery_pct is not None and battery_voltage is not None
            and battery_voltage > 5.0 and battery_pct < shutdown_percent):
            logger.warning(f"Battery at {battery_pct}% ({battery_voltage}V)! Initiating clean shutdown.")
            subprocess.run(['sudo', 'shutdown', '-h', 'now'])
            running = False
            return

        # Log summary periodically
        logger.info(
            f"CPU={system_state['cpu_temp_c']}°C "
            f"RAM={system_state['ram_percent']}% "
            f"Disk={system_state['disk'].get('free_gb', '?')}GB free "
            f"Batt={battery_pct or '?'}%"
        )

        time.sleep(interval)


# ── Web Dashboard ──
app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SailFrames - {{ state.device_id }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="5">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: #0a1628; color: #e0e8f0; padding: 16px; }
        h1 { color: #4fc3f7; margin-bottom: 16px; font-size: 24px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .card { background: #1a2a40; border-radius: 8px; padding: 14px; }
        .card h2 { font-size: 13px; color: #78909c; text-transform: uppercase; margin-bottom: 8px; }
        .value { font-size: 28px; font-weight: 700; color: #fff; }
        .unit { font-size: 14px; color: #78909c; }
        .status { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 4px; margin-right: 8px; min-width: 36px; text-align: center; }
        .status.on { background: #1976d2; color: #fff; }
        .status.off { background: #455a64; color: #90a4ae; }
        .sub { font-size: 13px; color: #90a4ae; margin-top: 6px; }
        .charging { color: #1976d2; }
        .discharging { color: #ff9800; }
        .services { margin-top: 12px; }
        .svc-row { padding: 6px 0; font-size: 14px; border-bottom: 1px solid #233; }
        .updated { font-size: 11px; color: #546e7a; margin-top: 12px; text-align: center; }
    </style>
</head>
<body>
    <h1>⛵ SailFrames {{ state.device_id }}</h1>
    <div class="grid">
        <div class="card">
            <h2>CPU Temp</h2>
            <div class="value">{{ state.cpu_temp_c or '—' }}<span class="unit">°C</span></div>
        </div>
        <div class="card">
            <h2>Battery {% if state.battery.charging %}<span class="charging">⚡</span>{% endif %}</h2>
            <div class="value">{{ state.battery.percent or '—' }}<span class="unit">%</span></div>
            <div class="sub">{{ state.battery.voltage or '—' }}V · {{ state.battery.current_ma or '—' }}mA · {% if state.battery.charging %}<span class="charging">Charging</span>{% else %}<span class="discharging">On Battery</span>{% endif %}</div>
        </div>
        <div class="card">
            <h2>Disk Free</h2>
            <div class="value">{{ state.disk.free_gb or '—' }}<span class="unit">GB</span></div>
        </div>
        <div class="card">
            <h2>RAM</h2>
            <div class="value">{{ state.ram_percent or '—' }}<span class="unit">%</span></div>
        </div>
    </div>

    <!-- GPS Section -->
    {% if state.gps %}
    <div class="card" style="margin-top: 12px;">
        <h2>📍 GPS — {{ state.gps.fix_type }} ({{ state.gps.satellites }} sats) · ±{{ state.gps.accuracy_cm or '?' }}cm</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px;">
            <div>
                <div style="font-size: 11px; color: #78909c;">POSITION</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.6f"|format(state.gps.latitude) }}, {{ "%.6f"|format(state.gps.longitude) }}</div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">ACCURACY</div>
                <div style="font-size: 14px; font-weight: 600;">±{{ state.gps.accuracy_cm }}cm ({{ state.gps.hdop_rating }})</div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">SPEED</div>
                <div style="font-size: 14px; font-weight: 600;">{{ state.gps.speed_knots }} kts · {{ state.gps.speed_mph }} mph</div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">ALTITUDE</div>
                <div style="font-size: 14px; font-weight: 600;">{{ state.gps.altitude_m|round(1) }} m</div>
            </div>
        </div>
        <div style="margin-top: 10px; display: flex; gap: 16px; font-size: 12px;">
            <a href="/gps" style="color: #4fc3f7;">📊 GPS Details</a>
            <a href="https://www.google.com/maps?q={{ state.gps.latitude }},{{ state.gps.longitude }}" target="_blank" style="color: #4fc3f7;">🗺 Open Map ↗</a>
        </div>
    </div>
    {% else %}
    <div class="card" style="margin-top: 12px;">
        <h2>📍 GPS</h2>
        <div style="color: #78909c; font-style: italic;">No GPS fix — waiting for satellites...</div>
        <div style="margin-top: 8px;"><a href="/gps" style="color: #4fc3f7; font-size: 12px;">📊 GPS Details</a></div>
    </div>
    {% endif %}

    <div class="card services" style="margin-top: 12px;">
        <h2>Sensor Services</h2>
        {% for name, active in state.services.items() %}
        <div class="svc-row">
            <span class="status {{ 'on' if active else 'off' }}">{{ '✓ ON' if active else '✗ OFF' }}</span>
            {{ name }}
        </div>
        {% endfor %}
    </div>
    <div class="updated">Updated {{ state.last_update }}</div>
    <div style="text-align: center; margin-top: 12px; display: flex; gap: 20px; justify-content: center;">
        <a href="/gps" style="color: #4fc3f7; font-size: 13px;">📍 GPS Details</a>
        <a href="/battery" style="color: #4fc3f7; font-size: 13px;">🔋 Battery History</a>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML, state=system_state)

@app.route('/api/status')
def api_status():
    return jsonify(system_state)


# ── GPS Details Page ──
GPS_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>GPS Details - SailFrames</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="5">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: #0a1628; color: #e0e8f0; padding: 16px; line-height: 1.5; }
        h1 { color: #4fc3f7; margin-bottom: 8px; font-size: 24px; }
        h2 { color: #78909c; font-size: 14px; text-transform: uppercase; margin: 20px 0 10px; }
        h3 { color: #4fc3f7; font-size: 16px; margin: 16px 0 8px; }
        a { color: #4fc3f7; text-decoration: none; }
        .nav { margin-bottom: 16px; font-size: 14px; }
        .card { background: #1a2a40; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
        .metric { background: #0d1929; border-radius: 6px; padding: 12px; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 700; color: #fff; }
        .metric-label { font-size: 11px; color: #78909c; text-transform: uppercase; margin-top: 4px; }
        .metric-sub { font-size: 11px; color: #546e7a; margin-top: 2px; }
        .big-metric { grid-column: span 2; }
        .big-metric .metric-value { font-size: 32px; }
        .info-box { background: #0d1929; border-radius: 6px; padding: 12px; margin: 8px 0; font-size: 13px; }
        .info-box strong { color: #4fc3f7; }
        .fix-badge { display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: 600; font-size: 14px; }
        .fix-dgps { background: #1565c0; color: #fff; }
        .fix-rtk-fixed { background: #2e7d32; color: #fff; }
        .fix-rtk-float { background: #f9a825; color: #000; }
        .fix-gps { background: #455a64; color: #fff; }
        .fix-none { background: #c62828; color: #fff; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #233; }
        th { color: #78909c; font-weight: 500; }
        .edu { font-size: 13px; color: #90a4ae; }
        .edu p { margin: 8px 0; }
        .highlight { color: #4fc3f7; font-weight: 600; }
        .coord { font-family: monospace; font-size: 16px; }
    </style>
</head>
<body>
    <div class="nav"><a href="/">← Back to Dashboard</a></div>
    <h1>📍 GPS Details — ZED-F9P</h1>

    {% if gps %}
    <!-- Current Fix Status -->
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div>
                <span class="fix-badge fix-{{ gps.fix_type|lower|replace(' ', '-')|replace('(', '')|replace(')', '') }}">{{ gps.fix_type }}</span>
                <span style="margin-left: 12px; font-size: 14px;">{{ gps.satellites }} satellites · HDOP {{ gps.hdop }}</span>
            </div>
            <div style="font-size: 24px; font-weight: 700;">
                ±{{ gps.accuracy_cm }}<span style="font-size: 14px; color: #78909c;">cm</span>
            </div>
        </div>
        <div class="info-box">
            <strong>{{ gps.fix_type }}:</strong> {{ gps.fix_desc }}
        </div>
    </div>

    <!-- Position -->
    <h2>Position</h2>
    <div class="card">
        <div class="grid">
            <div class="metric big-metric">
                <div class="metric-value coord">{{ "%.8f"|format(gps.latitude) }}°</div>
                <div class="metric-label">Latitude</div>
                <div class="metric-sub">{{ "N" if gps.latitude >= 0 else "S" }} {{ "%d°%d'%.2f''"|format(gps.latitude|abs|int, ((gps.latitude|abs % 1) * 60)|int, ((gps.latitude|abs * 60) % 1) * 60) }}</div>
            </div>
            <div class="metric big-metric">
                <div class="metric-value coord">{{ "%.8f"|format(gps.longitude) }}°</div>
                <div class="metric-label">Longitude</div>
                <div class="metric-sub">{{ "E" if gps.longitude >= 0 else "W" }} {{ "%d°%d'%.2f''"|format(gps.longitude|abs|int, ((gps.longitude|abs % 1) * 60)|int, ((gps.longitude|abs * 60) % 1) * 60) }}</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.altitude_m|round(1) }}</div>
                <div class="metric-label">Altitude (m)</div>
                <div class="metric-sub">{{ (gps.altitude_m * 3.28084)|round(1) }} ft</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.course_deg|round(0)|int if gps.course_deg else '—' }}°</div>
                <div class="metric-label">Course</div>
                <div class="metric-sub">True North</div>
            </div>
        </div>
        <div style="margin-top: 12px; text-align: center;">
            <a href="https://www.google.com/maps?q={{ gps.latitude }},{{ gps.longitude }}&z=18" target="_blank" style="font-size: 14px;">🗺 Open in Google Maps ↗</a>
        </div>
    </div>

    <!-- Speed -->
    <h2>Speed</h2>
    <div class="card">
        <div class="grid">
            <div class="metric">
                <div class="metric-value">{{ gps.speed_knots }}</div>
                <div class="metric-label">Knots</div>
                <div class="metric-sub">Nautical</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.speed_mph }}</div>
                <div class="metric-label">MPH</div>
                <div class="metric-sub">Statute</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.speed_kmh }}</div>
                <div class="metric-label">km/h</div>
                <div class="metric-sub">Metric</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.speed_mps }}</div>
                <div class="metric-label">m/s</div>
                <div class="metric-sub">SI Unit</div>
            </div>
        </div>
    </div>

    <!-- Accuracy & Precision -->
    <h2>Accuracy & Precision</h2>
    <div class="card">
        <div class="grid">
            <div class="metric big-metric">
                <div class="metric-value">±{{ gps.accuracy_cm }}<span style="font-size: 14px;">cm</span></div>
                <div class="metric-label">Estimated Accuracy</div>
                <div class="metric-sub">{{ gps.accuracy_m }}m · {{ gps.hdop_rating }}</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.hdop }}</div>
                <div class="metric-label">HDOP</div>
                <div class="metric-sub">{{ gps.hdop_rating }}</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.hdop_min }}</div>
                <div class="metric-label">HDOP Min</div>
                <div class="metric-sub">Last minute</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.hdop_max }}</div>
                <div class="metric-label">HDOP Max</div>
                <div class="metric-sub">Last minute</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.satellites }}</div>
                <div class="metric-label">Satellites</div>
                <div class="metric-sub">In use now</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.satellites_avg }}</div>
                <div class="metric-label">Avg Satellites</div>
                <div class="metric-sub">Last minute</div>
            </div>
        </div>
        <div class="info-box">
            <strong>HDOP {{ gps.hdop }} ({{ gps.hdop_rating }}):</strong> {{ gps.hdop_desc }}
        </div>
    </div>

    <!-- Session Stats -->
    <h2>Today's Session</h2>
    <div class="card">
        <div class="grid">
            <div class="metric">
                <div class="metric-value">{{ "{:,}".format(gps.total_points_today) }}</div>
                <div class="metric-label">Points Logged</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ gps.sample_rate_hz }}</div>
                <div class="metric-label">Sample Rate Hz</div>
            </div>
        </div>
    </div>
    {% else %}
    <div class="card">
        <div style="text-align: center; padding: 20px; color: #78909c;">
            <div style="font-size: 48px; margin-bottom: 12px;">📡</div>
            <div style="font-size: 18px;">Waiting for GPS fix...</div>
            <div style="margin-top: 8px;">Make sure antenna has clear sky view</div>
        </div>
    </div>
    {% endif %}

    <!-- Education Section -->
    <h2>Understanding GPS</h2>

    <div class="card">
        <h3>🛰️ Fix Types Explained</h3>
        <table>
            <tr><th>Fix Type</th><th>Accuracy</th><th>Description</th></tr>
            <tr>
                <td><span class="fix-badge fix-gps" style="font-size: 11px;">GPS (SPS)</span></td>
                <td>~2.5m</td>
                <td>Standard Positioning Service. Basic civilian GPS using L1 C/A signal. Affected by ionospheric delays, multipath, and satellite geometry.</td>
            </tr>
            <tr>
                <td><span class="fix-badge fix-dgps" style="font-size: 11px;">DGPS</span></td>
                <td>~1m</td>
                <td><strong>Differential GPS.</strong> Uses SBAS corrections (WAAS in USA, EGNOS in Europe) broadcast from geostationary satellites. Corrects atmospheric delays. Your ZED-F9P receives these automatically!</td>
            </tr>
            <tr>
                <td><span class="fix-badge fix-rtk-float" style="font-size: 11px;">RTK Float</span></td>
                <td>~50cm</td>
                <td><strong>Real-Time Kinematic (converging).</strong> Receiving corrections from a base station but hasn't achieved integer ambiguity resolution. Accuracy improving toward fixed.</td>
            </tr>
            <tr>
                <td><span class="fix-badge fix-rtk-fixed" style="font-size: 11px;">RTK Fixed</span></td>
                <td>~2cm</td>
                <td><strong>RTK with integer ambiguity resolved.</strong> Centimeter-level accuracy! Requires corrections from a nearby base station (NTRIP/CORS). The holy grail of GPS.</td>
            </tr>
        </table>
    </div>

    <div class="card">
        <h3>📊 HDOP (Horizontal Dilution of Precision)</h3>
        <div class="edu">
            <p>HDOP measures how satellite geometry affects position accuracy. Lower is better.</p>
            <p>The GPS receiver calculates position by measuring distances to multiple satellites. If satellites are clustered together in the sky, small measurement errors cause large position errors. If satellites are spread out evenly, errors cancel out.</p>
        </div>
        <table>
            <tr><th>HDOP</th><th>Rating</th><th>Meaning</th></tr>
            <tr><td>&lt;1</td><td class="highlight">Ideal</td><td>Highest possible precision. Satellites perfectly distributed across the sky.</td></tr>
            <tr><td>1-2</td><td class="highlight">Excellent</td><td>Very high precision. Great for surveying and precision navigation.</td></tr>
            <tr><td>2-5</td><td>Good</td><td>Good for most navigation. Acceptable for general use.</td></tr>
            <tr><td>5-10</td><td>Moderate</td><td>Position usable but degraded. Some satellites may be blocked.</td></tr>
            <tr><td>10-20</td><td>Fair</td><td>Low confidence. Consider waiting for better geometry.</td></tr>
            <tr><td>&gt;20</td><td>Poor</td><td>Position unreliable. Significant obstructions or few satellites.</td></tr>
        </table>
        <div class="info-box">
            <strong>Accuracy Formula:</strong> Estimated accuracy ≈ Base accuracy × HDOP<br>
            Example: DGPS (1m base) × HDOP 0.5 = <strong>0.5m (50cm) accuracy</strong>
        </div>
    </div>

    <div class="card">
        <h3>📡 Your ZED-F9P Receiver</h3>
        <div class="edu">
            <p>The <strong>u-blox ZED-F9P</strong> is a high-precision GNSS module capable of:</p>
        </div>
        <table>
            <tr><th>Feature</th><th>Specification</th></tr>
            <tr><td>Constellations</td><td>GPS, GLONASS, Galileo, BeiDou (184 channels)</td></tr>
            <tr><td>Frequencies</td><td>L1 + L2 (dual-band for better accuracy)</td></tr>
            <tr><td>Standard Accuracy</td><td>~1m CEP (with SBAS/DGPS)</td></tr>
            <tr><td>RTK Accuracy</td><td>1cm + 1ppm CEP (with corrections)</td></tr>
            <tr><td>Update Rate</td><td>Up to 25Hz (currently: {{ gps.sample_rate_hz if gps else 10 }}Hz)</td></tr>
            <tr><td>Time to First Fix</td><td>Cold: 24s, Hot: 2s</td></tr>
            <tr><td>RTK Convergence</td><td>&lt;10 seconds to fixed</td></tr>
        </table>
    </div>

    <div class="card">
        <h3>🎯 Improving Accuracy</h3>
        <div class="edu">
            <p><strong>Current setup (DGPS ~1m):</strong> You're already getting SBAS corrections automatically.</p>
            <p><strong>To achieve RTK (~2cm):</strong></p>
            <ol style="margin-left: 20px; margin-top: 8px;">
                <li>Subscribe to an NTRIP service (free or paid CORS network)</li>
                <li>Configure ZED-F9P to receive RTCM corrections via USB or UART</li>
                <li>Use a nearby base station (&lt;35km for best results)</li>
            </ol>
            <p style="margin-top: 12px;"><strong>Free NTRIP sources:</strong></p>
            <ul style="margin-left: 20px;">
                <li>RTK2GO.com - Community-operated casters</li>
                <li>State DOT CORS networks (varies by state)</li>
                <li>UNAVCO - Academic research network</li>
            </ul>
        </div>
    </div>

    <div class="card">
        <h3>🔢 Coordinate Precision</h3>
        <div class="edu">
            <p>Each decimal place in latitude/longitude represents different precision:</p>
        </div>
        <table>
            <tr><th>Decimals</th><th>Precision</th><th>Use Case</th></tr>
            <tr><td>4 (0.0001°)</td><td>~11m</td><td>City block level</td></tr>
            <tr><td>5 (0.00001°)</td><td>~1.1m</td><td>Individual trees, parked cars</td></tr>
            <tr><td>6 (0.000001°)</td><td>~11cm</td><td>Surveying, precision agriculture</td></tr>
            <tr><td>7 (0.0000001°)</td><td>~1.1cm</td><td>RTK applications, construction</td></tr>
            <tr><td>8 (0.00000001°)</td><td>~1.1mm</td><td>Theoretical (beyond GPS capability)</td></tr>
        </table>
        <div class="info-box">
            Your ZED-F9P outputs <strong>8 decimal places</strong>. With RTK, you can actually use 7 of them meaningfully!
        </div>
    </div>

    <div class="card">
        <h3>⚡ ZED-F9P LED Guide</h3>
        <table>
            <tr><th>LED</th><th>Color</th><th>Off</th><th>Blinking</th><th>Solid</th></tr>
            <tr><td><strong>PWR</strong></td><td>Red</td><td>No power</td><td>—</td><td>Power OK</td></tr>
            <tr><td><strong>PPS</strong></td><td>Blue</td><td>No fix</td><td>1Hz = Valid fix</td><td>—</td></tr>
            <tr><td><strong>RTK</strong></td><td>Green</td><td>No RTK</td><td>RTK Float</td><td>RTK Fixed ✓</td></tr>
            <tr><td><strong>GEO</strong></td><td>Yellow</td><td>Normal</td><td>Geofence event</td><td>Inside fence</td></tr>
        </table>
    </div>

</body>
</html>
"""


@app.route('/gps')
def gps_page():
    """Detailed GPS information page."""
    gps_data = get_latest_gps()
    return render_template_string(GPS_PAGE_HTML, gps=gps_data)


# ── Battery History API ──
BATTERY_DATA_DIR = Path('/mnt/sailframes-data/battery')


def format_time_ny(iso_time):
    """Convert ISO UTC time to New York time formatted string."""
    try:
        # Parse ISO format
        dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        # Convert to New York timezone
        ny_tz = ZoneInfo('America/New_York')
        dt_ny = dt.astimezone(ny_tz)
        return dt_ny.strftime('%Y-%m-%d %I:%M %p')
    except Exception:
        return iso_time[:16].replace('T', ' ')


def get_battery_sessions(limit=20):
    """Get list of battery discharge sessions."""
    sessions_file = BATTERY_DATA_DIR / 'sessions.csv'
    if not sessions_file.exists():
        return []

    sessions = []
    with open(sessions_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Add formatted times in New York timezone
            row['start_time_ny'] = format_time_ny(row['start_time'])
            row['end_time_ny'] = format_time_ny(row['end_time'])
            # Round duration to int
            row['duration_minutes'] = round(float(row['duration_minutes']))
            sessions.append(row)

    # Return most recent first
    sessions.reverse()
    return sessions[:limit]


def get_session_data(session_id):
    """Get detailed data for a specific session."""
    log_file = BATTERY_DATA_DIR / f'session_{session_id}.csv'
    process_file = BATTERY_DATA_DIR / f'processes_{session_id}.csv'

    data = {'samples': [], 'processes': {}}

    if log_file.exists():
        with open(log_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data['samples'].append(row)

    if process_file.exists():
        with open(process_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['name']
                if name not in data['processes']:
                    data['processes'][name] = {'total_cpu': 0, 'samples': 0}
                data['processes'][name]['total_cpu'] += float(row['cpu_percent'])
                data['processes'][name]['samples'] += 1

        # Calculate average CPU per process and add descriptions
        for name, stats in data['processes'].items():
            stats['avg_cpu'] = round(stats['total_cpu'] / stats['samples'], 1) if stats['samples'] > 0 else 0
            stats['description'] = get_process_description(name)

        # Sort by total CPU usage - show top 25
        data['top_processes'] = sorted(
            [{'name': k, **v} for k, v in data['processes'].items()],
            key=lambda x: x['total_cpu'],
            reverse=True
        )[:25]

    return data


# Process descriptions - what each process does and its origin
PROCESS_DESCRIPTIONS = {
    # System core (Raspberry Pi OS)
    'systemd': ('Init system', 'Core', 'Main system and service manager'),
    'systemd-journald': ('System logger', 'Core', 'Collects and stores logs'),
    'systemd-udevd': ('Device manager', 'Core', 'Handles hardware events'),
    'systemd-logind': ('Login manager', 'Core', 'Manages user sessions'),
    'systemd-timesyncd': ('Time sync', 'Core', 'Synchronizes system clock'),
    'dbus-daemon': ('Message bus', 'Core', 'Inter-process communication'),
    'dbus-broker': ('Message bus', 'Core', 'Modern D-Bus implementation'),

    # Desktop environment (Wayland/Wayfire)
    'labwc': ('Compositor', 'Desktop', 'Wayland window compositor'),
    'wayfire': ('Compositor', 'Desktop', 'Wayland compositor (alternative)'),
    'wf-panel-pi': ('Panel', 'Desktop', 'Desktop taskbar/panel'),
    'wireplumber': ('Audio routing', 'Desktop', 'PipeWire session manager'),
    'pipewire': ('Audio server', 'Desktop', 'Modern audio/video server'),
    'pipewire-pulse': ('PulseAudio compat', 'Desktop', 'PulseAudio compatibility'),
    'xdg-desktop-portal': ('Desktop portal', 'Desktop', 'App sandboxing support'),
    'pcmanfm': ('File manager', 'Desktop', 'Lightweight file manager'),
    'lxpolkit': ('Auth agent', 'Desktop', 'Policy kit authentication'),
    'lxsession': ('Session manager', 'Desktop', 'LXDE session manager'),
    'openbox': ('Window manager', 'Desktop', 'X11 window manager'),
    'mutter': ('Window manager', 'Desktop', 'GNOME window manager'),

    # Browsers
    'chromium': ('Web browser', 'Added', 'Chromium browser - HIGH POWER'),
    'chromium-browser': ('Web browser', 'Added', 'Chromium browser - HIGH POWER'),
    'chrome': ('Web browser', 'Added', 'Chrome browser - HIGH POWER'),
    'firefox': ('Web browser', 'Added', 'Firefox browser - HIGH POWER'),
    'firefox-esr': ('Web browser', 'Added', 'Firefox ESR - HIGH POWER'),

    # SailFrames services
    'sailframes_monitor': ('SailFrames', 'SailFrames', 'System monitoring dashboard'),
    'sailframes_gps': ('SailFrames', 'SailFrames', 'GPS sensor service'),
    'sailframes_imu': ('SailFrames', 'SailFrames', 'IMU sensor service'),
    'sailframes_pressure': ('SailFrames', 'SailFrames', 'Pressure sensor service'),
    'sailframes_wind': ('SailFrames', 'SailFrames', 'Wind sensor (BLE) service'),
    'sailframes_camera': ('SailFrames', 'SailFrames', 'Camera recording service'),
    'sailframes_battery': ('SailFrames', 'SailFrames', 'Battery logging service'),
    'power-manager': ('SailFrames', 'SailFrames', 'Power management daemon'),

    # Monitoring tools
    'netdata': ('Monitoring', 'Added', 'Real-time system monitoring'),
    'apps.plugin': ('Netdata plugin', 'Added', 'Netdata application monitor'),
    'proc.plugin': ('Netdata plugin', 'Added', 'Netdata process monitor'),
    'go.d.plugin': ('Netdata plugin', 'Added', 'Netdata Go collectors'),
    'cgroups.plugin': ('Netdata plugin', 'Added', 'Netdata cgroup monitor'),
    'ebpf.plugin': ('Netdata plugin', 'Added', 'Netdata eBPF monitor'),

    # Network services
    'NetworkManager': ('Network', 'Core', 'Network connection manager'),
    'wpa_supplicant': ('WiFi', 'Core', 'WiFi authentication'),
    'dhcpcd': ('DHCP client', 'Core', 'IP address management'),
    'avahi-daemon': ('mDNS', 'Core', 'Local network discovery'),
    'sshd': ('SSH server', 'Core', 'Remote access server'),
    'ssh': ('SSH client', 'Core', 'Remote access client'),

    # Bluetooth
    'bluetoothd': ('Bluetooth', 'Core', 'Bluetooth daemon'),
    'bt-adapter': ('Bluetooth', 'Core', 'Bluetooth adapter control'),

    # Python processes
    'python3': ('Python', 'Varies', 'Python interpreter - check parent'),
    'python': ('Python', 'Varies', 'Python interpreter - check parent'),

    # Hardware/GPU
    'Xorg': ('X server', 'Desktop', 'X11 display server'),
    'Xwayland': ('X compat', 'Desktop', 'X11 apps on Wayland'),

    # Camera/Video
    'libcamera-vid': ('Camera', 'Added', 'Camera video capture'),
    'libcamera-still': ('Camera', 'Added', 'Camera still capture'),
    'rpicam-vid': ('Camera', 'Added', 'Pi camera video'),
    'ffmpeg': ('Video encode', 'Added', 'Video encoding/streaming'),
    'gstreamer': ('Media', 'Added', 'Media framework'),

    # Other common
    'cron': ('Scheduler', 'Core', 'Task scheduler'),
    'rsyslogd': ('Logging', 'Core', 'System logging'),
    'polkitd': ('Auth', 'Core', 'Authorization framework'),
    'udisksd': ('Disks', 'Core', 'Disk management'),
    'accounts-daemon': ('Accounts', 'Core', 'User account service'),
    'gpsd': ('GPS daemon', 'Added', 'GPS device service'),
    'cups': ('Printing', 'Added', 'Print server - can disable'),
    'cupsd': ('Printing', 'Added', 'Print server - can disable'),
}


def get_process_description(name):
    """Get description for a process."""
    # Direct match
    if name in PROCESS_DESCRIPTIONS:
        return PROCESS_DESCRIPTIONS[name]

    # Partial matches
    name_lower = name.lower()
    for key, value in PROCESS_DESCRIPTIONS.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return value

    # Check for sailframes processes
    if 'sailframes' in name_lower:
        return ('SailFrames', 'SailFrames', 'SailFrames service')

    # Check for common patterns
    if 'plugin' in name_lower:
        return ('Plugin', 'Added', 'Extension/plugin process')
    if 'kworker' in name_lower:
        return ('Kernel', 'Core', 'Kernel worker thread')
    if 'irq/' in name_lower:
        return ('Kernel', 'Core', 'Interrupt handler')

    return ('Unknown', 'Unknown', 'Process not recognized')


@app.route('/api/battery/sessions')
def api_battery_sessions():
    """Get list of battery sessions."""
    return jsonify(get_battery_sessions())


@app.route('/api/battery/session/<session_id>')
def api_battery_session(session_id):
    """Get detailed data for a session."""
    return jsonify(get_session_data(session_id))


BATTERY_HISTORY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Battery History - SailFrames</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: #0a1628; color: #e0e8f0; padding: 16px; }
        h1 { color: #4fc3f7; margin-bottom: 8px; font-size: 24px; }
        h2 { color: #78909c; font-size: 16px; margin: 16px 0 8px; }
        a { color: #4fc3f7; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .nav { margin-bottom: 16px; font-size: 14px; }
        .card { background: #1a2a40; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
        .session { display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #233; }
        .session:last-child { border-bottom: none; }
        .session:hover { background: #233; cursor: pointer; }
        .session-date { font-weight: 600; }
        .session-stats { font-size: 13px; color: #90a4ae; }
        .stat { display: inline-block; margin-right: 16px; }
        .stat-value { color: #fff; font-weight: 600; }
        .no-data { color: #546e7a; font-style: italic; padding: 20px; text-align: center; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #233; }
        th { color: #78909c; font-weight: 500; }
        .chart { height: 200px; background: #0d1929; border-radius: 4px; margin: 12px 0; position: relative; }
        .chart-bar { position: absolute; bottom: 0; background: #4fc3f7; min-width: 2px; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; }
        .summary-item { text-align: center; }
        .summary-value { font-size: 24px; font-weight: 700; color: #fff; }
        .summary-label { font-size: 12px; color: #78909c; }
        .tag { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500; }
        .tag-core { background: #1565c0; color: #fff; }
        .tag-desktop { background: #6a1b9a; color: #fff; }
        .tag-sailframes { background: #00695c; color: #fff; }
        .tag-added { background: #e65100; color: #fff; }
        .tag-varies { background: #455a64; color: #fff; }
        .tag-unknown { background: #37474f; color: #90a4ae; }
    </style>
</head>
<body>
    <div class="nav"><a href="/">← Back to Dashboard</a></div>
    <h1>🔋 Battery History</h1>

    {% if session %}
    <h2>{{ session.start_time_ny }} → {{ session.end_time_ny }}</h2>
    <div class="card">
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-value">{{ session.duration_minutes }}m</div>
                <div class="summary-label">Duration</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ session.percent_used }}%</div>
                <div class="summary-label">Battery Used</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ session.start_percent }}%</div>
                <div class="summary-label">Start</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ session.end_percent }}%</div>
                <div class="summary-label">End</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ session.total_power_mwh }}</div>
                <div class="summary-label">mWh Used</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ session.max_current_ma }}</div>
                <div class="summary-label">Peak mA</div>
            </div>
        </div>
    </div>

    {% if top_processes %}
    <h2>Top Power Consumers</h2>
    <div class="card">
        <table>
            <tr><th>Process</th><th>Type</th><th>Description</th><th>Avg CPU %</th><th>Total CPU</th></tr>
            {% for proc in top_processes %}
            <tr>
                <td><strong>{{ proc.name }}</strong></td>
                <td><span class="tag tag-{{ proc.description[1]|lower|replace(' ', '') }}">{{ proc.description[1] }}</span></td>
                <td style="font-size: 12px; color: #90a4ae;">{{ proc.description[2] }}</td>
                <td>{{ proc.avg_cpu }}%</td>
                <td>{{ proc.total_cpu|round(1) }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    <div style="margin-top: 12px; font-size: 12px; color: #78909c;">
        <strong>Type Legend:</strong>
        <span class="tag tag-core">Core</span> = Essential system service
        <span class="tag tag-desktop">Desktop</span> = GUI/Desktop environment
        <span class="tag tag-sailframes">SailFrames</span> = Our services
        <span class="tag tag-added">Added</span> = Optional/installable
    </div>
    {% endif %}

    <p style="margin-top: 12px;"><a href="/battery">← All Sessions</a></p>

    {% else %}
    <h2>Discharge Sessions</h2>
    <div class="card">
        {% if sessions %}
        {% for s in sessions %}
        <div class="session" onclick="location.href='/battery/{{ s.session_id }}'">
            <div>
                <div class="session-date">{{ s.start_time_ny }}</div>
                <div class="session-stats">
                    <span class="stat"><span class="stat-value">{{ s.duration_minutes }}m</span> duration</span>
                    <span class="stat"><span class="stat-value">{{ s.percent_used }}%</span> used</span>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 18px; font-weight: 600;">{{ s.start_percent }}% → {{ s.end_percent }}%</div>
                <div class="session-stats">{{ s.total_power_mwh }} mWh</div>
            </div>
        </div>
        {% endfor %}
        {% else %}
        <div class="no-data">No battery sessions recorded yet.<br>Unplug USB-C to start tracking.</div>
        {% endif %}
    </div>
    {% endif %}
</body>
</html>
"""


@app.route('/battery')
def battery_history():
    """Battery history dashboard."""
    sessions = get_battery_sessions()
    return render_template_string(BATTERY_HISTORY_HTML, sessions=sessions, session=None, top_processes=None)


@app.route('/battery/<session_id>')
def battery_session_detail(session_id):
    """Detailed view of a battery session."""
    sessions = get_battery_sessions(limit=100)
    session = next((s for s in sessions if s['session_id'] == session_id), None)
    if not session:
        return "Session not found", 404

    data = get_session_data(session_id)
    return render_template_string(
        BATTERY_HISTORY_HTML,
        sessions=None,
        session=session,
        top_processes=data.get('top_processes', [])
    )


def run(config):
    monitor_config = config['monitor']
    port = monitor_config['web_port']

    # Start monitor thread
    monitor_thread = threading.Thread(target=monitor_loop, args=(config,), daemon=True)
    monitor_thread.start()
    logger.info("Monitor thread started")

    # Start web dashboard
    logger.info(f"Dashboard at http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    config = load_config()
    if not config['monitor']['enabled']:
        logger.info("Monitor disabled in config, exiting")
        sys.exit(0)
    run(config)
