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
import json
import time
import signal
import logging
import threading
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psutil
from flask import Flask, jsonify, render_template_string, request, send_file
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

        # Estimate remaining/charging time (UPS HAT D has 2x 18650)
        # Conservative estimate: 3000mAh usable (accounting for cutoff voltage and efficiency)
        BATTERY_CAPACITY_MAH = 3000
        # Minimum realistic current draw for Pi 5 with services running
        MIN_DISCHARGE_MA = 200
        remaining_hours = None
        remaining_str = None
        empty_time = None
        charge_hours = None
        charge_str = None
        full_time = None

        from datetime import timedelta

        if not charging and current_ma > 10:  # Discharging with meaningful current
            # Use the higher of actual current or minimum realistic draw
            # (low readings may indicate USB-C hybrid mode)
            effective_current = max(current_ma, MIN_DISCHARGE_MA)
            remaining_mah = (percent / 100.0) * BATTERY_CAPACITY_MAH
            remaining_hours = remaining_mah / effective_current
            hours = int(remaining_hours)
            minutes = int((remaining_hours - hours) * 60)
            remaining_str = f"{hours}h {minutes}m"

            # Calculate estimated empty time
            empty_dt = datetime.now() + timedelta(hours=remaining_hours)
            empty_time = empty_dt.strftime('%I:%M %p')

        elif charging and current_ma < -10 and percent < 100:  # Charging with meaningful current
            # current_ma is negative when charging, so use absolute value
            charge_current = abs(current_ma)
            remaining_to_full = ((100 - percent) / 100.0) * BATTERY_CAPACITY_MAH
            charge_hours = remaining_to_full / charge_current
            hours = int(charge_hours)
            minutes = int((charge_hours - hours) * 60)
            charge_str = f"{hours}h {minutes}m"

            # Calculate estimated full time
            full_dt = datetime.now() + timedelta(hours=charge_hours)
            full_time = full_dt.strftime('%I:%M %p')

        return {
            'voltage': round(voltage, 2),
            'percent': round(percent, 1),
            'current_ma': round(current_ma, 0),
            'charging': charging,
            'remaining_hours': round(remaining_hours, 1) if remaining_hours else None,
            'remaining_str': remaining_str,
            'empty_time': empty_time,
            'charge_hours': round(charge_hours, 1) if charge_hours else None,
            'charge_str': charge_str,
            'full_time': full_time,
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


def get_wind_status():
    """Read current wind data from status file written by wind service."""
    status_file = Path('/tmp/sailframes-wind-status.json')
    try:
        if not status_file.exists():
            return None

        with open(status_file, 'r') as f:
            data = json.load(f)

        # Check if data is stale (older than 10 seconds)
        if data.get('timestamp'):
            ts = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > 10:
                data['connected'] = False

        return data
    except Exception:
        return None


def get_imu_status():
    """Read current IMU data from status file written by IMU service."""
    status_file = Path('/tmp/sailframes-imu-status.json')
    try:
        if not status_file.exists():
            return None

        with open(status_file, 'r') as f:
            data = json.load(f)

        # Check if data is stale (older than 2 seconds for 50Hz sensor)
        if data.get('timestamp'):
            ts = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > 2:
                data['connected'] = False

        return data
    except Exception:
        return None


def get_pressure_status():
    """Read current pressure data from status file written by pressure service."""
    status_file = Path('/tmp/sailframes-pressure-status.json')
    try:
        if not status_file.exists():
            return None

        with open(status_file, 'r') as f:
            data = json.load(f)

        # Check if data is stale (older than 5 seconds for 1Hz sensor)
        if data.get('timestamp'):
            ts = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > 5:
                data['connected'] = False

        return data
    except Exception:
        return None


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
        system_state['wind'] = get_wind_status() or {}
        system_state['imu'] = get_imu_status() or {}
        system_state['pressure'] = get_pressure_status() or {}
        system_state['uptime_sec'] = int(time.monotonic())
        system_state['last_update'] = datetime.now(timezone.utc).isoformat()

        # Check service status
        system_state['services'] = {
            'gps': check_service_status('sailframes-gps'),
            'imu': check_service_status('sailframes-imu'),
            'pressure': check_service_status('sailframes-pressure'),
            'wind': check_service_status('sailframes-wind'),
        }
        # Track cameras separately for individual control
        system_state['cameras'] = {
            'cockpit': check_service_status('sailframes-camera-cockpit'),
            'sails': check_service_status('sailframes-camera-sails'),
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
            {% if state.battery.remaining_str and not state.battery.charging %}
            <div class="sub" style="margin-top: 4px; color: #ff9800;">~{{ state.battery.remaining_str }} remaining · empty ~{{ state.battery.empty_time }}</div>
            {% elif state.battery.charge_str and state.battery.charging %}
            <div class="sub" style="margin-top: 4px; color: #1976d2;">~{{ state.battery.charge_str }} to full · ready ~{{ state.battery.full_time }}</div>
            {% endif %}
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

    <!-- Wind Section -->
    {% if state.wind and state.wind.connected %}
    <div class="card" style="margin-top: 12px;">
        <h2>💨 Wind — {{ state.wind.device_name or 'Connected' }}</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px;">
            <div>
                <div style="font-size: 11px; color: #78909c;">APPARENT WIND SPEED</div>
                <div style="font-size: 24px; font-weight: 700; color: #4fc3f7;">{{ "%.1f"|format(state.wind.speed_knots or 0) }} <span style="font-size: 14px; font-weight: 400;">kts</span></div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">APPARENT WIND ANGLE</div>
                <div style="font-size: 24px; font-weight: 700; color: #4fc3f7;">{{ state.wind.angle_deg or 0 }}°</div>
            </div>
            {% if state.wind.compass_deg is not none %}
            <div>
                <div style="font-size: 11px; color: #78909c;">COMPASS HEADING</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.1f"|format(state.wind.compass_deg) }}°</div>
            </div>
            {% endif %}
            {% if state.wind.temperature is not none %}
            <div>
                <div style="font-size: 11px; color: #78909c;">TEMPERATURE</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.1f"|format(state.wind.temperature) }}°C</div>
            </div>
            {% endif %}
            {% if state.wind.roll_deg is not none %}
            <div>
                <div style="font-size: 11px; color: #78909c;">ROLL</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.1f"|format(state.wind.roll_deg) }}°</div>
            </div>
            {% endif %}
            {% if state.wind.pitch_deg is not none %}
            <div>
                <div style="font-size: 11px; color: #78909c;">PITCH</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.1f"|format(state.wind.pitch_deg) }}°</div>
            </div>
            {% endif %}
            {% if state.wind.rate_of_turn is not none %}
            <div>
                <div style="font-size: 11px; color: #78909c;">RATE OF TURN</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.1f"|format(state.wind.rate_of_turn) }}°/s</div>
            </div>
            {% endif %}
            {% if state.wind.battery is not none %}
            <div>
                <div style="font-size: 11px; color: #78909c;">BATTERY</div>
                <div style="font-size: 14px; font-weight: 600;">{{ state.wind.battery }}%</div>
            </div>
            {% endif %}
            {% if state.wind.compass_cal is not none %}
            <div>
                <div style="font-size: 11px; color: #78909c;">COMPASS CAL</div>
                <div style="font-size: 14px; font-weight: 600;">{{ state.wind.compass_cal }}</div>
            </div>
            {% endif %}
        </div>
    </div>
    {% else %}
    <div class="card" style="margin-top: 12px;">
        <h2>💨 Wind</h2>
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="color: #78909c; font-style: italic;">
                {% if state.services.wind %}
                Searching for sensor...
                {% else %}
                Wind service not running
                {% endif %}
            </div>
            <button onclick="scanBluetooth()" style="
                background: #1976d2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                cursor: pointer;
            ">Scan Bluetooth</button>
        </div>
    </div>
    {% endif %}

    <!-- IMU Section -->
    {% if state.imu and state.imu.connected %}
    <div class="card" style="margin-top: 12px;">
        <h2>🧭 IMU — BNO085</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 8px;">
            <div>
                <div style="font-size: 11px; color: #78909c;">HEADING</div>
                <div style="font-size: 24px; font-weight: 700; color: #4fc3f7;">{{ "%.1f"|format(state.imu.heading_deg or 0) }}°</div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">HEEL</div>
                <div style="font-size: 24px; font-weight: 700; {% if state.imu.heel_deg and state.imu.heel_deg|abs > 25 %}color: #ff9800;{% else %}color: #4fc3f7;{% endif %}">
                    {{ "%.1f"|format(state.imu.heel_deg or 0) }}°
                    <span style="font-size: 12px; font-weight: 400; color: #78909c;">{{ 'STBD' if state.imu.heel_deg and state.imu.heel_deg > 0 else 'PORT' if state.imu.heel_deg and state.imu.heel_deg < 0 else '' }}</span>
                </div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">PITCH</div>
                <div style="font-size: 24px; font-weight: 700; color: #4fc3f7;">{{ "%.1f"|format(state.imu.pitch_deg or 0) }}°
                    <span style="font-size: 12px; font-weight: 400; color: #78909c;">{{ 'BOW UP' if state.imu.pitch_deg and state.imu.pitch_deg > 0 else 'BOW DN' if state.imu.pitch_deg and state.imu.pitch_deg < 0 else '' }}</span>
                </div>
            </div>
        </div>
        <!-- Linear Acceleration -->
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #233;">
            <div>
                <div style="font-size: 11px; color: #78909c;">ACCEL X (FWD)</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.2f"|format(state.imu.accel_x_mps2 or 0) }} <span style="color: #78909c;">m/s²</span></div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">ACCEL Y (STBD)</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.2f"|format(state.imu.accel_y_mps2 or 0) }} <span style="color: #78909c;">m/s²</span></div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">ACCEL Z (DOWN)</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.2f"|format(state.imu.accel_z_mps2 or 0) }} <span style="color: #78909c;">m/s²</span></div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">TOTAL ACCEL</div>
                <div style="font-size: 14px; font-weight: 600;">{{ "%.2f"|format(state.imu.accel_magnitude_mps2 or 0) }} <span style="color: #78909c;">m/s²</span></div>
            </div>
        </div>
        <!-- Quaternion (advanced) -->
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #233;">
            <div>
                <div style="font-size: 10px; color: #546e7a;">QUAT I</div>
                <div style="font-size: 12px; font-family: monospace;">{{ "%.4f"|format(state.imu.quat_i or 0) }}</div>
            </div>
            <div>
                <div style="font-size: 10px; color: #546e7a;">QUAT J</div>
                <div style="font-size: 12px; font-family: monospace;">{{ "%.4f"|format(state.imu.quat_j or 0) }}</div>
            </div>
            <div>
                <div style="font-size: 10px; color: #546e7a;">QUAT K</div>
                <div style="font-size: 12px; font-family: monospace;">{{ "%.4f"|format(state.imu.quat_k or 0) }}</div>
            </div>
            <div>
                <div style="font-size: 10px; color: #546e7a;">QUAT REAL</div>
                <div style="font-size: 12px; font-family: monospace;">{{ "%.4f"|format(state.imu.quat_real or 0) }}</div>
            </div>
        </div>
        {% if state.imu.accuracy_rad is not none %}
        <div style="margin-top: 8px; font-size: 11px; color: #546e7a;">
            Accuracy: {{ "%.4f"|format(state.imu.accuracy_rad) }} rad
        </div>
        {% endif %}
        <!-- Calibration -->
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #233; display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size: 12px; color: #78909c;">
                {% if state.imu.heel_offset or state.imu.pitch_offset %}
                Calibrated: heel {{ "%.1f"|format(state.imu.heel_offset or 0) }}°, pitch {{ "%.1f"|format(state.imu.pitch_offset or 0) }}° offset
                {% else %}
                Not calibrated (raw values)
                {% endif %}
            </div>
            <button onclick="calibrateIMU()" id="btn-imu-cal" style="
                background: #1976d2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                cursor: pointer;
            ">Zero Heel/Pitch</button>
        </div>
    </div>
    {% else %}
    <div class="card" style="margin-top: 12px;">
        <h2>🧭 IMU</h2>
        <div style="color: #78909c; font-style: italic;">
            {% if state.services.imu %}
            Initializing BNO085...
            {% else %}
            IMU service not running
            {% endif %}
        </div>
    </div>
    {% endif %}

    <!-- Pressure Section -->
    {% if state.pressure and state.pressure.connected %}
    <div class="card" style="margin-top: 12px;">
        <h2>🌡️ Pressure — DPS310</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px;">
            <div>
                <div style="font-size: 11px; color: #78909c;">BAROMETRIC PRESSURE</div>
                <div style="font-size: 24px; font-weight: 700; color: #4fc3f7;">{{ "%.1f"|format(state.pressure.pressure_hpa or 0) }} <span style="font-size: 14px; font-weight: 400;">hPa</span></div>
                <div style="font-size: 12px; color: #78909c;">{{ state.pressure.pressure_inhg }} inHg</div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">SEA LEVEL PRESSURE</div>
                <div style="font-size: 24px; font-weight: 700; color: #4fc3f7;">{{ "%.1f"|format(state.pressure.sea_level_hpa or 0) }} <span style="font-size: 14px; font-weight: 400;">hPa</span></div>
                <div style="font-size: 12px; color: #78909c;">{{ state.pressure.sea_level_inhg }} inHg</div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">TEMPERATURE</div>
                <div style="font-size: 24px; font-weight: 700; color: #4fc3f7;">{{ "%.1f"|format(state.pressure.temperature_c or 0) }}°<span style="font-size: 14px; font-weight: 400;">C</span></div>
                <div style="font-size: 12px; color: #78909c;">{{ "%.1f"|format(state.pressure.temperature_f or 0) }}°F</div>
            </div>
            <div>
                <div style="font-size: 11px; color: #78909c;">10-MIN TREND</div>
                {% if state.pressure.trend_hpa is not none %}
                <div style="font-size: 24px; font-weight: 700; {% if state.pressure.trend_hpa > 0 %}color: #4caf50;{% elif state.pressure.trend_hpa < 0 %}color: #ff9800;{% else %}color: #4fc3f7;{% endif %}">
                    {{ '+' if state.pressure.trend_hpa > 0 else '' }}{{ "%.2f"|format(state.pressure.trend_hpa) }} <span style="font-size: 14px; font-weight: 400;">hPa</span>
                </div>
                <div style="font-size: 12px; color: #78909c;">{{ state.pressure.trend_desc or 'Calculating...' }}</div>
                {% else %}
                <div style="font-size: 14px; color: #78909c; font-style: italic;">Collecting data...</div>
                <div style="font-size: 11px; color: #546e7a;">Need 10 min of readings</div>
                {% endif %}
            </div>
        </div>
    </div>
    {% else %}
    <div class="card" style="margin-top: 12px;">
        <h2>🌡️ Pressure</h2>
        <div style="color: #78909c; font-style: italic;">
            {% if state.services.pressure %}
            Initializing DPS310...
            {% else %}
            Pressure service not running
            {% endif %}
        </div>
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

    <!-- Camera Control -->
    <div class="card" style="margin-top: 12px;">
        <h2>Camera Control</h2>
        <div style="display: flex; flex-direction: column; gap: 12px;">
            <!-- Cockpit Camera -->
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="width: 80px; font-size: 14px; font-weight: 600;">Cockpit</div>
                <div style="flex: 1; font-size: 14px;">
                    {% if state.cameras.cockpit %}
                    <span style="color: #4caf50;">● Recording</span>
                    {% else %}
                    <span style="color: #78909c;">○ Stopped</span>
                    {% endif %}
                </div>
                <button id="btn-cockpit" onclick="toggleCamera('cockpit')" style="
                    background: {% if state.cameras.cockpit %}#c62828{% else %}#1976d2{% endif %};
                    color: white; border: none; padding: 8px 16px; border-radius: 6px;
                    font-size: 13px; font-weight: 600; cursor: pointer; min-width: 100px;
                ">{% if state.cameras.cockpit %}Stop{% else %}Record{% endif %}</button>
            </div>
            <!-- Sails Camera -->
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="width: 80px; font-size: 14px; font-weight: 600;">Sails</div>
                <div style="flex: 1; font-size: 14px;">
                    {% if state.cameras.sails %}
                    <span style="color: #4caf50;">● Recording</span>
                    {% else %}
                    <span style="color: #78909c;">○ Stopped</span>
                    {% endif %}
                </div>
                <button id="btn-sails" onclick="toggleCamera('sails')" style="
                    background: {% if state.cameras.sails %}#c62828{% else %}#1976d2{% endif %};
                    color: white; border: none; padding: 8px 16px; border-radius: 6px;
                    font-size: 13px; font-weight: 600; cursor: pointer; min-width: 100px;
                ">{% if state.cameras.sails %}Stop{% else %}Record{% endif %}</button>
            </div>
        </div>
    </div>

    <!-- WiFi Mode -->
    <div class="card" style="margin-top: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h2 style="margin: 0;">📶 WiFi Mode</h2>
                <div id="wifi-status" style="font-size: 12px; color: #78909c; margin-top: 4px;">Loading...</div>
            </div>
            <div style="display: flex; align-items: center; gap: 12px;">
                <span id="wifi-mode-label" style="font-size: 13px; color: #78909c;">Client</span>
                <label style="position: relative; display: inline-block; width: 50px; height: 26px;">
                    <input type="checkbox" id="wifi-toggle" onchange="toggleWiFi()" style="opacity: 0; width: 0; height: 0;">
                    <span style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #455a64; transition: .3s; border-radius: 26px;"></span>
                    <span id="wifi-slider" style="position: absolute; content: ''; height: 20px; width: 20px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%;"></span>
                </label>
                <span style="font-size: 13px; color: #4fc3f7;">AP</span>
            </div>
        </div>
        <div id="wifi-details" style="margin-top: 8px; font-size: 12px; color: #546e7a;"></div>
    </div>

    <!-- System / Shutdown -->
    <div class="card" style="margin-top: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h2 style="margin: 0;">System</h2>
                <div style="font-size: 12px; color: #78909c; margin-top: 4px;">Uptime: {{ (state.uptime_sec // 3600) }}h {{ ((state.uptime_sec % 3600) // 60) }}m</div>
            </div>
            <button onclick="confirmShutdown()" style="
                background: #c62828;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
            ">Shutdown</button>
        </div>
    </div>

    <!-- Shutdown confirmation modal -->
    <div id="shutdown-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 100;">
        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #1a2a40; padding: 24px; border-radius: 8px; text-align: center; max-width: 320px;">
            <div style="font-size: 18px; margin-bottom: 12px;">Shutdown SailFrames?</div>
            <div style="color: #78909c; font-size: 13px; margin-bottom: 16px;">
                All recordings will stop. You'll need physical access to power it back on.
            </div>
            <div id="shutdown-status" style="color: #4caf50; font-size: 14px; margin-bottom: 16px; display: none;"></div>
            <div style="display: flex; gap: 12px; justify-content: center;">
                <button onclick="closeShutdownModal()" style="background: #455a64; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; cursor: pointer;">Cancel</button>
                <button id="shutdown-btn" onclick="doShutdown()" style="background: #c62828; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;">Shutdown</button>
            </div>
        </div>
    </div>

    <!-- Bluetooth scan modal -->
    <div id="bt-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 100;">
        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #1a2a40; padding: 24px; border-radius: 8px; max-width: 400px; width: 90%;">
            <div style="font-size: 18px; margin-bottom: 12px;">Bluetooth Wind Sensors</div>
            <div id="bt-status" style="color: #78909c; font-size: 13px; margin-bottom: 12px;">Scanning for devices...</div>
            <div id="bt-devices" style="max-height: 300px; overflow-y: auto;"></div>
            <div style="display: flex; gap: 12px; justify-content: center; margin-top: 16px;">
                <button onclick="closeBtModal()" style="background: #455a64; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; cursor: pointer;">Close</button>
                <button id="bt-rescan" onclick="scanBluetooth()" style="background: #1976d2; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; cursor: pointer;">Rescan</button>
            </div>
        </div>
    </div>

    <div class="updated">Updated {{ state.last_update }}</div>
    <div style="text-align: center; margin-top: 12px; display: flex; gap: 20px; justify-content: center;">
        <a href="/gps" style="color: #4fc3f7; font-size: 13px;">📍 GPS Details</a>
        <a href="/battery" style="color: #4fc3f7; font-size: 13px;">🔋 Battery History</a>
        <a href="/video" style="color: #4fc3f7; font-size: 13px;">🎬 Video Review</a>
    </div>

    <script>
    function toggleCamera(camera) {
        const btn = document.getElementById('btn-' + camera);
        const isRecording = btn.textContent.trim() === 'Stop';
        const action = isRecording ? 'stop' : 'start';

        btn.disabled = true;
        btn.textContent = isRecording ? 'Stopping...' : 'Starting...';

        fetch('/api/camera/' + camera + '/' + action, { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                    btn.disabled = false;
                    btn.textContent = isRecording ? 'Stop' : 'Record';
                }
            })
            .catch(e => {
                alert('Error: ' + e);
                btn.disabled = false;
            });
    }

    function confirmShutdown() {
        document.getElementById('shutdown-modal').style.display = 'block';
        document.getElementById('shutdown-status').style.display = 'none';
        document.getElementById('shutdown-btn').disabled = false;
    }

    function closeShutdownModal() {
        document.getElementById('shutdown-modal').style.display = 'none';
    }

    function doShutdown() {
        const btn = document.getElementById('shutdown-btn');
        const status = document.getElementById('shutdown-status');

        btn.disabled = true;
        btn.textContent = 'Shutting down...';

        fetch('/api/system/shutdown', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    status.style.display = 'block';
                    status.innerHTML = '✓ Shutdown initiated.<br>Safe to turn off in 10 seconds.';
                    btn.style.display = 'none';
                } else {
                    alert('Error: ' + (data.error || 'Shutdown failed'));
                    btn.disabled = false;
                    btn.textContent = 'Shutdown';
                }
            })
            .catch(e => {
                alert('Error: ' + e);
                btn.disabled = false;
                btn.textContent = 'Shutdown';
            });
    }

    function scanBluetooth() {
        document.getElementById('bt-modal').style.display = 'block';
        document.getElementById('bt-status').textContent = 'Scanning for devices (30s)...';
        document.getElementById('bt-devices').innerHTML = '';
        document.getElementById('bt-rescan').disabled = true;

        fetch('/api/bluetooth/scan', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                document.getElementById('bt-rescan').disabled = false;
                if (data.devices && data.devices.length > 0) {
                    document.getElementById('bt-status').textContent = 'Found ' + data.devices.length + ' device(s):';
                    let html = '';
                    data.devices.forEach(d => {
                        const isWind = d.is_wind_sensor;
                        const bg = isWind ? '#1a3a2a' : '#1a2a40';
                        const border = isWind ? '1px solid #4caf50' : '1px solid #333';
                        html += '<div style="padding: 10px; margin: 8px 0; background: ' + bg + '; border: ' + border + '; border-radius: 6px;">';
                        html += '<div style="font-weight: 600;">' + (d.name || 'Unknown') + (isWind ? ' <span style="color: #4caf50;">✓ Wind</span>' : '') + '</div>';
                        html += '<div style="font-size: 12px; color: #78909c;">' + d.address + ' · RSSI: ' + d.rssi + '</div>';
                        if (isWind) {
                            html += '<button onclick="pairWind(\'' + d.address + '\')" style="margin-top: 8px; background: #1976d2; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer;">Set as Wind Sensor</button>';
                        }
                        html += '</div>';
                    });
                    document.getElementById('bt-devices').innerHTML = html;
                } else {
                    document.getElementById('bt-status').textContent = 'No devices found. Make sure sensor is on and nearby.';
                }
            })
            .catch(e => {
                document.getElementById('bt-rescan').disabled = false;
                document.getElementById('bt-status').textContent = 'Scan error: ' + e;
            });
    }

    function closeBtModal() {
        document.getElementById('bt-modal').style.display = 'none';
    }

    function pairWind(address) {
        fetch('/api/bluetooth/set-wind', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({address: address})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                alert('Wind sensor MAC saved! Restart wind service to connect.');
                closeBtModal();
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Failed to save'));
            }
        })
        .catch(e => alert('Error: ' + e));
    }

    function calibrateIMU() {
        if (!confirm('Zero heel and pitch at current position?\\n\\nMake sure the boat is level at the dock.')) {
            return;
        }
        const btn = document.getElementById('btn-imu-cal');
        btn.disabled = true;
        btn.textContent = 'Calibrating...';

        fetch('/api/imu/calibrate', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    alert('IMU calibrated!\\nHeel offset: ' + data.heel_offset.toFixed(1) + '°\\nPitch offset: ' + data.pitch_offset.toFixed(1) + '°');
                    location.reload();
                } else {
                    alert('Calibration failed: ' + (data.error || 'Unknown error'));
                    btn.disabled = false;
                    btn.textContent = 'Zero Heel/Pitch';
                }
            })
            .catch(e => {
                alert('Error: ' + e);
                btn.disabled = false;
                btn.textContent = 'Zero Heel/Pitch';
            });
    }

    // WiFi Mode Toggle
    function loadWiFiStatus() {
        fetch('/api/wifi/status')
            .then(r => r.json())
            .then(data => {
                const toggle = document.getElementById('wifi-toggle');
                const slider = document.getElementById('wifi-slider');
                const label = document.getElementById('wifi-mode-label');
                const status = document.getElementById('wifi-status');
                const details = document.getElementById('wifi-details');

                const isAP = data.current_mode === 'ap';
                toggle.checked = isAP;

                // Update slider position
                slider.style.transform = isAP ? 'translateX(24px)' : 'translateX(0)';
                slider.parentElement.previousElementSibling.style.backgroundColor = isAP ? '#1976d2' : '#455a64';

                // Update labels
                label.textContent = isAP ? 'AP' : 'Client';
                label.style.color = isAP ? '#78909c' : '#78909c';

                if (isAP) {
                    status.textContent = 'Access Point: ' + data.ap_ssid;
                    details.innerHTML = 'SSID: <strong>' + data.ap_ssid + '</strong> · Password: <strong>' + data.ap_password + '</strong> · IP: 192.168.4.1';
                } else {
                    status.textContent = 'Connected to: ' + (data.connection || data.client_ssid);
                    details.innerHTML = 'IP: <strong>' + (data.ip_address || 'obtaining...') + '</strong>';
                }

                if (data.saved_mode !== data.current_mode) {
                    details.innerHTML += ' <span style="color: #ff9800;">(boot: ' + data.saved_mode + ')</span>';
                }
            })
            .catch(e => {
                document.getElementById('wifi-status').textContent = 'Error loading WiFi status';
            });
    }

    function toggleWiFi() {
        const toggle = document.getElementById('wifi-toggle');
        const newMode = toggle.checked ? 'ap' : 'client';

        document.getElementById('wifi-status').textContent = 'Switching to ' + (newMode === 'ap' ? 'Access Point' : 'Client') + ' mode...';

        fetch('/api/wifi/mode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: newMode})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                if (newMode === 'ap') {
                    alert('Switched to Access Point mode!\\n\\nSSID: s1\\nPassword: hello\\nIP: 192.168.4.1\\n\\nConnect to the s1 WiFi network to access dashboard.');
                } else {
                    alert('Switched to Client mode!\\n\\nConnecting to Home-IOT...\\nPage will reload when connected.');
                }
                setTimeout(() => location.reload(), 2000);
            } else {
                alert('WiFi switch failed: ' + (data.error || 'Unknown error'));
                loadWiFiStatus();  // Reload to get correct state
            }
        })
        .catch(e => {
            alert('WiFi switch error: ' + e);
            loadWiFiStatus();
        });
    }

    // Load WiFi status on page load
    document.addEventListener('DOMContentLoaded', loadWiFiStatus);
    </script>
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


def get_active_session():
    """Check if there's an active battery session (not yet in sessions.csv)."""
    if not BATTERY_DATA_DIR.exists():
        return None

    # Get session IDs from sessions.csv
    completed_ids = set()
    sessions_file = BATTERY_DATA_DIR / 'sessions.csv'
    if sessions_file.exists():
        with open(sessions_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed_ids.add(row['session_id'])

    # Find session files that aren't in completed sessions
    for session_file in sorted(BATTERY_DATA_DIR.glob('session_*.csv'), reverse=True):
        session_id = session_file.stem.replace('session_', '')
        if session_id not in completed_ids:
            # Found an active session - read its data
            samples = []
            with open(session_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    samples.append(row)

            if not samples:
                continue

            # Calculate session stats from samples
            first = samples[0]
            last = samples[-1]
            start_time = datetime.fromisoformat(first['timestamp'].replace('Z', '+00:00'))
            last_time = datetime.fromisoformat(last['timestamp'].replace('Z', '+00:00'))
            duration = last_time - start_time

            # Check if file was modified recently (within 2 minutes) to determine if truly active
            file_mtime = datetime.fromtimestamp(session_file.stat().st_mtime, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            is_stale = (now - file_mtime).total_seconds() > 120

            return {
                'session_id': session_id,
                'start_time_ny': format_time_ny(first['timestamp']),
                'end_time_ny': format_time_ny(last['timestamp']),
                'duration_minutes': round(duration.total_seconds() / 60),
                'start_percent': float(first['percent']),
                'current_percent': float(last['percent']),
                'percent_used': round(float(first['percent']) - float(last['percent']), 1),
                'sample_count': len(samples),
                'current_voltage': float(last['voltage']),
                'current_ma': float(last['current_ma']),
                'is_stale': is_stale,  # True if session was interrupted (not actively updating)
            }

    return None


def finalize_orphan_session(session_id):
    """Finalize an orphan session by adding it to sessions.csv."""
    session_file = BATTERY_DATA_DIR / f'session_{session_id}.csv'
    process_file = BATTERY_DATA_DIR / f'processes_{session_id}.csv'

    if not session_file.exists():
        return False

    # Read session data
    samples = []
    with open(session_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append(row)

    if len(samples) < 2:
        return False

    # Calculate stats
    first = samples[0]
    last = samples[-1]
    start_time = datetime.fromisoformat(first['timestamp'].replace('Z', '+00:00'))
    end_time = datetime.fromisoformat(last['timestamp'].replace('Z', '+00:00'))
    duration = end_time - start_time

    # Calculate power usage
    total_power_mwh = 0
    max_current = 0
    min_voltage = float(first['voltage'])
    for sample in samples:
        power_mw = float(sample['voltage']) * abs(float(sample['current_ma']))
        total_power_mwh += power_mw * (30 / 3600)  # 30 second intervals
        max_current = max(max_current, float(sample['current_ma']))
        min_voltage = min(min_voltage, float(sample['voltage']))

    summary = {
        'session_id': session_id,
        'start_time': first['timestamp'],
        'end_time': last['timestamp'],
        'duration_minutes': round(duration.total_seconds() / 60, 1),
        'start_percent': float(first['percent']),
        'end_percent': float(last['percent']),
        'percent_used': round(float(first['percent']) - float(last['percent']), 1),
        'start_voltage': float(first['voltage']),
        'end_voltage': float(last['voltage']),
        'min_voltage': min_voltage,
        'max_current_ma': round(max_current, 1),
        'total_power_mwh': round(total_power_mwh, 1),
        'sample_count': len(samples),
    }

    # Append to sessions.csv
    sessions_file = BATTERY_DATA_DIR / 'sessions.csv'
    write_header = not sessions_file.exists()

    with open(sessions_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=summary.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(summary)

    return True


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


# ── Video Management ──

def get_video_list(data_dir, date_filter=None):
    """Get list of all recorded videos with metadata."""
    data_path = Path(data_dir)
    videos = []

    # Get all date directories or filter to specific date
    if date_filter:
        date_dirs = [data_path / date_filter]
    else:
        date_dirs = sorted(data_path.glob('20??-??-??'), reverse=True)

    for date_dir in date_dirs:
        video_dir = date_dir / 'video'
        if not video_dir.exists():
            continue

        # Scan both camera subdirectories and root video directory (for old videos)
        video_locations = [
            (video_dir / 'cockpit', 'cockpit'),
            (video_dir / 'sails', 'sails'),
            (video_dir, None),  # Root for old videos (cockpit_*.mp4)
        ]

        for scan_dir, camera_id in video_locations:
            if not scan_dir.exists():
                continue

            for video_file in scan_dir.glob('*.mp4'):
                # Skip if this is the root dir and file is in a subdirectory
                if camera_id is None and video_file.parent != video_dir:
                    continue

                try:
                    stat = video_file.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    # Estimate duration: ~8 Mbps = ~1 MB/s
                    duration_sec = int(size_mb)

                    # Detect camera from filename if not in subdirectory
                    detected_camera = camera_id
                    if detected_camera is None:
                        if video_file.name.startswith('cockpit_'):
                            detected_camera = 'cockpit'
                        elif video_file.name.startswith('sails_'):
                            detected_camera = 'sails'
                        else:
                            detected_camera = 'unknown'

                    videos.append({
                        'filename': video_file.name,
                        'filepath': str(video_file.relative_to(data_path)),
                        'date': date_dir.name,
                        'camera': detected_camera,
                        'size_mb': round(size_mb, 1),
                        'size_bytes': stat.st_size,
                        'duration_sec': duration_sec,
                        'duration_str': f"{duration_sec // 60}:{duration_sec % 60:02d}",
                        'created': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                except Exception:
                    pass

    # Sort by created time descending
    videos.sort(key=lambda x: x['created'], reverse=True)
    return videos


def get_video_dates(data_dir):
    """Get list of dates that have videos."""
    data_path = Path(data_dir)
    dates = []

    for date_dir in sorted(data_path.glob('20??-??-??'), reverse=True):
        video_dir = date_dir / 'video'
        if video_dir.exists():
            video_count = len(list(video_dir.glob('*.mp4')))
            if video_count > 0:
                dates.append({
                    'date': date_dir.name,
                    'video_count': video_count
                })

    return dates


def validate_video_path(data_dir, filepath):
    """Security: validate that filepath is within data_dir and is a video file."""
    data_path = Path(data_dir).resolve()
    try:
        video_path = (data_path / filepath).resolve()
        # Ensure path is within data directory
        if not str(video_path).startswith(str(data_path)):
            return None
        # Ensure it's an MP4 file
        if video_path.suffix.lower() != '.mp4':
            return None
        # Ensure file exists
        if not video_path.exists():
            return None
        return video_path
    except Exception:
        return None


@app.route('/api/battery/sessions')
def api_battery_sessions():
    """Get list of battery sessions."""
    return jsonify(get_battery_sessions())


@app.route('/api/battery/session/<session_id>')
def api_battery_session(session_id):
    """Get detailed data for a session."""
    return jsonify(get_session_data(session_id))


@app.route('/api/battery/finalize', methods=['POST'])
def api_finalize_session():
    """Finalize an orphan battery session."""
    data = request.get_json() or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'error': 'session_id required'}), 400

    if finalize_orphan_session(session_id):
        return jsonify({'success': True, 'message': f'Session {session_id} finalized'})
    return jsonify({'error': 'Failed to finalize session'}), 500


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
    {% if active_session %}
    {% if active_session.is_stale %}
    <h2 style="color: #ffb74d;">⚠ Interrupted Session</h2>
    <div class="card" style="border: 2px solid #ffb74d;">
    {% else %}
    <h2 style="color: #66bb6a;">⚡ Active Session (On Battery)</h2>
    <div class="card" style="border: 2px solid #66bb6a;">
    {% endif %}
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-value">{{ active_session.duration_minutes }}m</div>
                <div class="summary-label">Duration</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ active_session.percent_used }}%</div>
                <div class="summary-label">Battery Used</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ active_session.start_percent|round|int }}%</div>
                <div class="summary-label">Start</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ active_session.current_percent|round|int }}%</div>
                <div class="summary-label">End</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ active_session.current_ma|round|int }}</div>
                <div class="summary-label">mA Draw</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{{ active_session.sample_count }}</div>
                <div class="summary-label">Samples</div>
            </div>
        </div>
        {% if active_session.is_stale %}
        <div style="margin-top: 12px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 12px; color: #90a4ae;">
                {{ active_session.start_time_ny }} → {{ active_session.end_time_ny }} · Session ended by shutdown/restart
            </span>
            <button onclick="finalizeSession('{{ active_session.session_id }}')"
                    style="background: #1976d2; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px;">
                Save to History
            </button>
        </div>
        {% else %}
        <div style="margin-top: 12px; font-size: 12px; color: #90a4ae;">
            Started: {{ active_session.start_time_ny }} · Session will be saved when USB-C is connected
        </div>
        {% endif %}
    </div>
    {% endif %}

    <h2>Completed Sessions</h2>
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
        <div class="no-data">No completed battery sessions yet.<br>Sessions are saved when USB-C is reconnected.</div>
        {% endif %}
    </div>
    {% endif %}

    <script>
    function finalizeSession(sessionId) {
        fetch('/api/battery/finalize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({session_id: sessionId})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(e => alert('Error: ' + e));
    }
    </script>
</body>
</html>
"""


@app.route('/battery')
def battery_history():
    """Battery history dashboard."""
    sessions = get_battery_sessions()
    active = get_active_session()
    return render_template_string(BATTERY_HISTORY_HTML, sessions=sessions, session=None, top_processes=None, active_session=active)


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
        active_session=None,
        top_processes=data.get('top_processes', [])
    )


# ── Video Review Page ──

VIDEO_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Video Review - SailFrames</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: #0a1628; color: #e0e8f0; padding: 16px; }
        h1 { color: #4fc3f7; margin-bottom: 8px; font-size: 24px; }
        h2 { color: #78909c; font-size: 14px; text-transform: uppercase; margin: 16px 0 8px; }
        a { color: #4fc3f7; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .nav { margin-bottom: 16px; font-size: 14px; }
        .card { background: #1a2a40; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
        .date-nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
        .date-btn { background: #233; color: #e0e8f0; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .date-btn.active { background: #1976d2; color: white; }
        .date-btn:hover { background: #344; }
        .video-item { display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #233; }
        .video-item:last-child { border-bottom: none; }
        .video-item:hover { background: #233; }
        .video-name { font-weight: 600; font-size: 14px; }
        .video-meta { font-size: 12px; color: #78909c; margin-top: 4px; }
        .video-actions { display: flex; gap: 8px; }
        .btn { padding: 6px 12px; border-radius: 4px; border: none; font-size: 12px; cursor: pointer; }
        .btn-play { background: #1976d2; color: white; }
        .btn-delete { background: #455a64; color: #e0e8f0; }
        .btn-delete:hover { background: #c62828; }
        .no-videos { color: #546e7a; font-style: italic; padding: 20px; text-align: center; }
        .video-player { margin: 16px 0; }
        .video-player video { width: 100%; max-height: 60vh; background: #000; border-radius: 8px; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 100; }
        .modal-content { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #1a2a40; padding: 24px; border-radius: 8px; text-align: center; }
        .modal-buttons { margin-top: 16px; display: flex; gap: 12px; justify-content: center; }
        .summary { display: flex; gap: 24px; margin-bottom: 16px; font-size: 14px; }
        .summary-item { }
        .summary-value { font-size: 20px; font-weight: 700; color: #fff; }
        .summary-label { font-size: 11px; color: #78909c; }
    </style>
</head>
<body>
    <div class="nav"><a href="/">&larr; Back to Dashboard</a></div>
    <h1>Video Review</h1>

    <div class="summary">
        <div class="summary-item">
            <div class="summary-value">{{ total_videos }}</div>
            <div class="summary-label">Total Videos</div>
        </div>
        <div class="summary-item">
            <div class="summary-value">{{ total_size_gb }}GB</div>
            <div class="summary-label">Total Size</div>
        </div>
        <div class="summary-item">
            <div class="summary-value">{{ total_duration }}</div>
            <div class="summary-label">Total Duration</div>
        </div>
    </div>

    <div class="date-nav">
        <button class="date-btn {% if not selected_date %}active{% endif %}" onclick="location.href='/video'">All</button>
        {% for d in dates %}
        <button class="date-btn {% if selected_date == d.date %}active{% endif %}" onclick="location.href='/video?date={{ d.date }}'">{{ d.date }} ({{ d.video_count }})</button>
        {% endfor %}
        {% if selected_date and videos %}
        <button class="btn-delete" style="margin-left: auto; padding: 8px 16px;" onclick="confirmDeleteAll('{{ selected_date }}', {{ videos|length }})">Delete All {{ selected_date }}</button>
        {% endif %}
    </div>

    <div id="player-container" class="video-player" style="display: none;">
        <video id="video-player" controls></video>
        <div style="margin-top: 8px; font-size: 14px;">
            <span id="player-filename"></span>
            <button onclick="closePlayer()" style="float: right; background: #455a64; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer;">Close</button>
        </div>
    </div>

    <div class="card">
        <div class="video-list">
            {% if videos %}
            {% for v in videos %}
            <div class="video-item" id="video-{{ loop.index }}">
                <div>
                    <div class="video-name">
                        <span style="display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-right: 8px; background: {% if v.camera == 'cockpit' %}#1976d2{% elif v.camera == 'sails' %}#00796b{% else %}#455a64{% endif %}; color: white;">{{ v.camera|upper }}</span>
                        {{ v.filename }}
                    </div>
                    <div class="video-meta">{{ v.date }} | {{ v.size_mb }}MB | ~{{ v.duration_str }}</div>
                </div>
                <div class="video-actions">
                    <button class="btn btn-play" onclick="playVideo('{{ v.filepath }}', '{{ v.filename }}')">Play</button>
                    <button class="btn btn-delete" onclick="confirmDelete('{{ v.filepath }}', '{{ v.filename }}')">Delete</button>
                </div>
            </div>
            {% endfor %}
            {% else %}
            <div class="no-videos">No videos found{% if selected_date %} for {{ selected_date }}{% endif %}.</div>
            {% endif %}
        </div>
    </div>

    <!-- Delete confirmation modal -->
    <div id="delete-modal" class="modal">
        <div class="modal-content">
            <div style="font-size: 18px; margin-bottom: 8px;">Delete Video?</div>
            <div id="delete-filename" style="color: #78909c;"></div>
            <div class="modal-buttons">
                <button class="btn" style="background: #455a64; color: white;" onclick="closeDeleteModal()">Cancel</button>
                <button class="btn" style="background: #c62828; color: white;" onclick="doDelete()">Delete</button>
            </div>
        </div>
    </div>

    <!-- Delete All confirmation modal -->
    <div id="delete-all-modal" class="modal">
        <div class="modal-content">
            <div style="font-size: 18px; margin-bottom: 8px;">Delete All Videos?</div>
            <div id="delete-all-info" style="color: #78909c;"></div>
            <div class="modal-buttons">
                <button class="btn" style="background: #455a64; color: white;" onclick="closeDeleteAllModal()">Cancel</button>
                <button class="btn" style="background: #c62828; color: white;" onclick="doDeleteAll()">Delete All</button>
            </div>
        </div>
    </div>

    <script>
        let deleteFilepath = null;
        let deleteAllDate = null;

        function playVideo(filepath, filename) {
            const player = document.getElementById('video-player');
            const container = document.getElementById('player-container');
            document.getElementById('player-filename').textContent = filename;
            player.src = '/video/stream/' + filepath;
            container.style.display = 'block';
            player.play();
            container.scrollIntoView({ behavior: 'smooth' });
        }

        function closePlayer() {
            const player = document.getElementById('video-player');
            player.pause();
            player.src = '';
            document.getElementById('player-container').style.display = 'none';
        }

        function confirmDelete(filepath, filename) {
            deleteFilepath = filepath;
            document.getElementById('delete-filename').textContent = filename;
            document.getElementById('delete-modal').style.display = 'block';
        }

        function closeDeleteModal() {
            document.getElementById('delete-modal').style.display = 'none';
            deleteFilepath = null;
        }

        function doDelete() {
            if (!deleteFilepath) return;

            fetch('/api/video/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: deleteFilepath })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.error || 'Delete failed'));
                }
                closeDeleteModal();
            })
            .catch(e => {
                alert('Error: ' + e);
                closeDeleteModal();
            });
        }

        function confirmDeleteAll(date, count) {
            deleteAllDate = date;
            document.getElementById('delete-all-info').textContent = 'Delete ' + count + ' videos from ' + date + '?';
            document.getElementById('delete-all-modal').style.display = 'block';
        }

        function closeDeleteAllModal() {
            document.getElementById('delete-all-modal').style.display = 'none';
            deleteAllDate = null;
        }

        function doDeleteAll() {
            if (!deleteAllDate) return;

            fetch('/api/video/delete-date', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: deleteAllDate })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    location.href = '/video';
                } else {
                    alert('Error: ' + (data.error || 'Delete failed'));
                }
                closeDeleteAllModal();
            })
            .catch(e => {
                alert('Error: ' + e);
                closeDeleteAllModal();
            });
        }
    </script>
</body>
</html>
"""


# Store config globally for video routes
_config = None


@app.route('/video')
def video_page():
    """Video review page."""
    global _config
    if _config is None:
        _config = load_config()

    data_dir = _config['storage']['data_dir']
    selected_date = request.args.get('date')
    videos = get_video_list(data_dir, date_filter=selected_date)
    dates = get_video_dates(data_dir)

    # Calculate totals
    total_size_bytes = sum(v['size_bytes'] for v in videos)
    total_duration_sec = sum(v['duration_sec'] for v in videos)

    return render_template_string(
        VIDEO_PAGE_HTML,
        videos=videos,
        dates=dates,
        selected_date=selected_date,
        total_videos=len(videos),
        total_size_gb=round(total_size_bytes / (1024**3), 2),
        total_duration=f"{total_duration_sec // 3600}h {(total_duration_sec % 3600) // 60}m"
    )


@app.route('/video/stream/<path:filepath>')
def video_stream(filepath):
    """Serve video file for playback with range support."""
    global _config
    if _config is None:
        _config = load_config()

    data_dir = _config['storage']['data_dir']
    video_path = validate_video_path(data_dir, filepath)

    if video_path is None:
        return "Not found", 404

    return send_file(
        video_path,
        mimetype='video/mp4',
        conditional=True  # Enables HTTP range requests for seeking
    )


@app.route('/api/videos')
def api_videos():
    """List all recorded videos."""
    global _config
    if _config is None:
        _config = load_config()

    data_dir = _config['storage']['data_dir']
    date_filter = request.args.get('date')
    return jsonify(get_video_list(data_dir, date_filter=date_filter))


@app.route('/api/video/delete', methods=['POST'])
def api_video_delete():
    """Delete a video file."""
    global _config
    if _config is None:
        _config = load_config()

    data = request.get_json()
    filepath = data.get('filepath') if data else None

    if not filepath:
        return jsonify({'success': False, 'error': 'No filepath provided'}), 400

    data_dir = _config['storage']['data_dir']
    video_path = validate_video_path(data_dir, filepath)

    if video_path is None:
        return jsonify({'success': False, 'error': 'Invalid path or file not found'}), 404

    try:
        video_path.unlink()
        logger.info(f"Deleted video: {filepath}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Failed to delete video {filepath}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/video/delete-date', methods=['POST'])
def api_video_delete_date():
    """Delete all videos for a specific date."""
    global _config
    if _config is None:
        _config = load_config()

    data = request.get_json()
    date = data.get('date') if data else None

    if not date:
        return jsonify({'success': False, 'error': 'No date provided'}), 400

    # Validate date format (YYYY-MM-DD)
    import re
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        return jsonify({'success': False, 'error': 'Invalid date format'}), 400

    data_dir = Path(_config['storage']['data_dir'])
    video_dir = data_dir / date / 'video'

    if not video_dir.exists():
        return jsonify({'success': False, 'error': 'No videos for this date'}), 404

    # Delete all mp4 files in the directory
    deleted = 0
    errors = []
    for video_file in video_dir.glob('*.mp4'):
        try:
            video_file.unlink()
            deleted += 1
        except Exception as e:
            errors.append(f"{video_file.name}: {e}")

    logger.info(f"Deleted {deleted} videos for {date}")

    if errors:
        return jsonify({
            'success': True,
            'deleted': deleted,
            'errors': errors
        })

    return jsonify({'success': True, 'deleted': deleted})


@app.route('/api/camera/<camera_id>/start', methods=['POST'])
def api_camera_start(camera_id):
    """Start camera recording service."""
    if camera_id not in ('cockpit', 'sails'):
        return jsonify({'success': False, 'error': 'Invalid camera ID'}), 400

    service_name = f'sailframes-camera-{camera_id}'
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'start', service_name],
            capture_output=True, text=True, timeout=10
        )
        success = result.returncode == 0
        if success:
            logger.info(f"Camera {camera_id} started via API")
        else:
            logger.warning(f"Failed to start camera {camera_id}: {result.stderr}")
        return jsonify({'success': success, 'error': result.stderr if not success else None})
    except Exception as e:
        logger.error(f"Camera {camera_id} start error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/camera/<camera_id>/stop', methods=['POST'])
def api_camera_stop(camera_id):
    """Stop camera recording service."""
    if camera_id not in ('cockpit', 'sails'):
        return jsonify({'success': False, 'error': 'Invalid camera ID'}), 400

    service_name = f'sailframes-camera-{camera_id}'
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'stop', service_name],
            capture_output=True, text=True, timeout=10
        )
        success = result.returncode == 0
        if success:
            logger.info(f"Camera {camera_id} stopped via API")
        else:
            logger.warning(f"Failed to stop camera {camera_id}: {result.stderr}")
        return jsonify({'success': success, 'error': result.stderr if not success else None})
    except Exception as e:
        logger.error(f"Camera {camera_id} stop error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system/shutdown', methods=['POST'])
def api_system_shutdown():
    """Safely shutdown the system - stops all services first to ensure data is saved."""
    try:
        logger.warning("Shutdown requested via API - initiating safe shutdown")

        # Stop all SailFrames services in order to ensure clean file closure
        # Order: cameras first (video files), then sensors, then battery logger
        services_to_stop = [
            'sailframes-camera-cockpit',
            'sailframes-camera-sails',
            'sailframes-gps',
            'sailframes-imu',
            'sailframes-pressure',
            'sailframes-wind',
            'sailframes-battery-logger',
        ]

        for service in services_to_stop:
            try:
                result = subprocess.run(
                    ['sudo', 'systemctl', 'stop', service],
                    capture_output=True, timeout=15
                )
                if result.returncode == 0:
                    logger.info(f"Stopped {service}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout stopping {service}")
            except Exception as e:
                logger.warning(f"Error stopping {service}: {e}")

        logger.info("All services stopped - initiating system shutdown")

        # Initiate shutdown
        subprocess.Popen(
            ['sudo', 'shutdown', '-h', '+0'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return jsonify({'success': True, 'message': 'Shutdown initiated - all data saved'})
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bluetooth/scan', methods=['POST'])
def api_bluetooth_scan():
    """Scan for Bluetooth LE devices."""
    import asyncio
    try:
        from bleak import BleakScanner
    except ImportError:
        return jsonify({'success': False, 'error': 'bleak not installed'}), 500

    async def do_scan():
        devices = await BleakScanner.discover(timeout=15)
        results = []
        for d in devices:
            name = d.name or ''
            is_wind = 'calypso' in name.lower() or 'ultrasonic' in name.lower() or 'wind' in name.lower()
            results.append({
                'name': d.name,
                'address': d.address,
                'rssi': d.rssi if hasattr(d, 'rssi') else None,
                'is_wind_sensor': is_wind,
            })
        # Sort: wind sensors first, then by signal strength
        results.sort(key=lambda x: (not x['is_wind_sensor'], -(x['rssi'] or -100)))
        return results

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        devices = loop.run_until_complete(do_scan())
        loop.close()
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        logger.error(f"Bluetooth scan error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bluetooth/set-wind', methods=['POST'])
def api_bluetooth_set_wind():
    """Save wind sensor MAC address to config."""
    data = request.get_json() or {}
    address = data.get('address')
    if not address:
        return jsonify({'success': False, 'error': 'address required'}), 400

    # Update config file
    config_path = '/etc/sailframes/sailframes.yaml'
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'sailframes.yaml')

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        config['wind']['ble_mac_address'] = address

        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.info(f"Set wind sensor MAC to {address}")

        # Restart wind service to pick up new MAC
        subprocess.run(['sudo', 'systemctl', 'restart', 'sailframes-wind'],
                      capture_output=True, timeout=10)

        return jsonify({'success': True, 'address': address})
    except Exception as e:
        logger.error(f"Failed to save wind MAC: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/wind/status')
def api_wind_status():
    """Get current wind sensor status."""
    return jsonify(get_wind_status() or {'connected': False})


@app.route('/api/imu/calibrate', methods=['POST'])
def api_imu_calibrate():
    """
    Zero heel and pitch offsets based on current IMU readings.
    Call this when boat is level at the dock.
    """
    try:
        imu_status = get_imu_status()
        if not imu_status or not imu_status.get('connected'):
            return jsonify({'success': False, 'error': 'IMU not connected'}), 400

        # Get raw values (before any existing calibration)
        raw_heel = imu_status.get('raw_heel_deg')
        raw_pitch = imu_status.get('raw_pitch_deg')

        if raw_heel is None or raw_pitch is None:
            return jsonify({'success': False, 'error': 'No IMU readings available'}), 400

        # Save new calibration offsets
        calibration = {
            'heel_offset': raw_heel,
            'pitch_offset': raw_pitch,
            'calibrated_at': datetime.now(timezone.utc).isoformat(),
        }

        calibration_file = Path('/etc/sailframes/imu-calibration.json')
        calibration_file.parent.mkdir(parents=True, exist_ok=True)

        with open(calibration_file, 'w') as f:
            json.dump(calibration, f, indent=2)

        logger.info(f"IMU calibrated: heel_offset={raw_heel:.2f}°, pitch_offset={raw_pitch:.2f}°")

        return jsonify({
            'success': True,
            'heel_offset': raw_heel,
            'pitch_offset': raw_pitch,
        })

    except Exception as e:
        logger.error(f"IMU calibration failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/imu/calibration', methods=['GET'])
def api_imu_calibration():
    """Get current IMU calibration offsets."""
    try:
        calibration_file = Path('/etc/sailframes/imu-calibration.json')
        if calibration_file.exists():
            with open(calibration_file, 'r') as f:
                return jsonify(json.load(f))
        return jsonify({'heel_offset': 0, 'pitch_offset': 0, 'calibrated_at': None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/imu/calibration/reset', methods=['POST'])
def api_imu_calibration_reset():
    """Reset IMU calibration to zero offsets."""
    try:
        calibration_file = Path('/etc/sailframes/imu-calibration.json')
        if calibration_file.exists():
            calibration_file.unlink()
        logger.info("IMU calibration reset to zero")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── WiFi Mode API ──

def get_wifi_status():
    """Get current WiFi mode and connection status."""
    try:
        # Get current mode from script
        result = subprocess.run(
            ['/home/paul/sailframes/scripts/wifi-mode.sh', 'current'],
            capture_output=True, text=True, timeout=5
        )
        current_mode = result.stdout.strip() if result.returncode == 0 else 'unknown'

        # Get saved mode
        mode_file = Path('/etc/sailframes/wifi-mode')
        saved_mode = mode_file.read_text().strip() if mode_file.exists() else 'ap'

        # Get connection details
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'GENERAL.CONNECTION,IP4.ADDRESS', 'device', 'show', 'wlan0'],
            capture_output=True, text=True, timeout=5
        )

        connection = None
        ip_address = None
        for line in result.stdout.split('\n'):
            if line.startswith('GENERAL.CONNECTION:'):
                connection = line.split(':', 1)[1]
            elif line.startswith('IP4.ADDRESS'):
                ip_address = line.split(':', 1)[1].split('/')[0] if ':' in line else None

        return {
            'current_mode': current_mode,
            'saved_mode': saved_mode,
            'connection': connection,
            'ip_address': ip_address,
            'ap_ssid': 's1',
            'ap_password': 'hello',
            'client_ssid': 'Home-IOT',
        }
    except Exception as e:
        logger.error(f"WiFi status error: {e}")
        return {'current_mode': 'unknown', 'error': str(e)}


@app.route('/api/wifi/status')
def api_wifi_status():
    """Get current WiFi mode and status."""
    return jsonify(get_wifi_status())


@app.route('/api/wifi/mode', methods=['POST'])
def api_wifi_mode():
    """Switch WiFi mode (ap/client/toggle)."""
    try:
        data = request.get_json() or {}
        mode = data.get('mode', 'toggle')

        if mode not in ['ap', 'client', 'toggle']:
            return jsonify({'success': False, 'error': 'Invalid mode. Use: ap, client, or toggle'}), 400

        logger.info(f"Switching WiFi mode: {mode}")

        result = subprocess.run(
            ['sudo', '/home/paul/sailframes/scripts/wifi-mode.sh', mode],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            return jsonify({
                'success': False,
                'error': result.stderr or 'WiFi mode switch failed'
            }), 500

        # Get new status
        status = get_wifi_status()

        return jsonify({
            'success': True,
            'mode': status['current_mode'],
            'output': result.stdout,
        })

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'WiFi switch timed out'}), 500
    except Exception as e:
        logger.error(f"WiFi mode switch failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def run(config):
    global _config
    _config = config  # Store config for video routes

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
