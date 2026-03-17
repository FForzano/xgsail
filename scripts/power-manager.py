#!/usr/bin/env python3
"""
SailFrames Power Manager
Monitors USB-C power and enables/disables display + browsers to save battery.
- USB-C connected: Enable HDMI, start browsers
- On battery: Disable HDMI, kill browsers
"""

import os
import sys
import time
import glob
import signal
import subprocess
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [POWER] %(levelname)s %(message)s'
)
logger = logging.getLogger('sailframes.power')

# Configuration
CHECK_INTERVAL = 10  # seconds between checks
CURRENT_THRESHOLD = 0  # negative current = USB-C connected
INA219_ADDR = 0x43
REG_SHUNT_VOLTAGE = 0x01
SHUNT_OHMS = 0.1

running = True
display_enabled = None  # Track current state


def signal_handler(sig, frame):
    global running
    logger.info("Shutdown signal received")
    running = False


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def get_current_ma():
    """Read current from INA219. Negative = USB-C charging."""
    try:
        import smbus2
        bus = smbus2.SMBus(1)
        raw_shunt = bus.read_word_data(INA219_ADDR, REG_SHUNT_VOLTAGE)
        raw_shunt = ((raw_shunt & 0xFF) << 8) | ((raw_shunt >> 8) & 0xFF)
        if raw_shunt > 32767:
            raw_shunt -= 65536
        shunt_mv = raw_shunt * 0.01
        current_ma = shunt_mv / SHUNT_OHMS
        bus.close()
        return current_ma
    except Exception as e:
        logger.error(f"Failed to read current: {e}")
        return None


def is_usb_connected():
    """Check if USB-C is providing power (negative current = charging)."""
    current = get_current_ma()
    if current is None:
        return None
    return current < CURRENT_THRESHOLD


def enable_display():
    """Enable HDMI and start browsers."""
    global display_enabled
    if display_enabled:
        return  # Already enabled

    logger.info("USB-C connected - enabling display")

    # Set DISPLAY for subprocess commands
    env = os.environ.copy()
    env['DISPLAY'] = ':0'

    # Signal display helper to turn on display
    try:
        with open('/tmp/sailframes-display-control', 'w') as f:
            f.write('on')
        logger.info("Signaled display helper to turn on")
    except Exception as e:
        logger.warning(f"Could not signal display helper: {e}")

    # Start dashboard script (which opens browsers)
    dashboard_script = os.path.expanduser('~/sailframes-dashboard.sh')
    if os.path.exists(dashboard_script):
        try:
            subprocess.Popen([dashboard_script], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Started dashboard browsers")
        except Exception as e:
            logger.warning(f"Could not start dashboard: {e}")

    display_enabled = True


def disable_display():
    """Disable HDMI and kill browsers to save power."""
    global display_enabled
    if display_enabled is False:
        return  # Already disabled

    logger.info("On battery - disabling display to save power")

    env = os.environ.copy()
    env['DISPLAY'] = ':0'

    # Kill browsers (main power savings)
    try:
        subprocess.run(['pkill', '-9', 'chromium'], capture_output=True, timeout=5)
        logger.info("Killed browsers")
    except Exception:
        pass

    # Signal display helper to turn off display (Wayland requires in-session control)
    try:
        with open('/tmp/sailframes-display-control', 'w') as f:
            f.write('off')
        logger.info("Signaled display helper to turn off")
    except Exception as e:
        logger.warning(f"Could not signal display helper: {e}")

    display_enabled = False


def run():
    global display_enabled
    logger.info("Power manager started")

    # Check initial state
    usb_connected = is_usb_connected()
    if usb_connected is True:
        enable_display()
    elif usb_connected is False:
        disable_display()

    while running:
        time.sleep(CHECK_INTERVAL)

        usb_connected = is_usb_connected()
        if usb_connected is None:
            continue  # Read error, skip this cycle

        if usb_connected and not display_enabled:
            enable_display()
        elif not usb_connected and display_enabled:
            disable_display()


if __name__ == '__main__':
    run()
