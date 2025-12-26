"""Input handling with palm rejection using evdev."""
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib

try:
    from evdev import InputDevice, categorize, ecodes, list_devices
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    logging.warning("evdev not available, palm rejection will be disabled")

logger = logging.getLogger(__name__)


class InputHandler:
    """Handles input device monitoring for palm rejection."""
    
    def __init__(self):
        self.stylus_active = False
        self.touch_enabled = True
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        self.stylus_devices = []
        self.touch_devices = []
        
        self.on_stylus_state_change: Optional[Callable[[bool], None]] = None
        
        logger.info(f"InputHandler initialized (evdev available: {EVDEV_AVAILABLE})")
    
    def start_monitoring(self):
        """Start monitoring input devices."""
        if not EVDEV_AVAILABLE:
            logger.warning("Cannot start monitoring: evdev not available")
            return False
        
        if self.monitoring:
            logger.warning("Already monitoring")
            return False
        
        # Detect devices
        self.detect_devices()
        
        if not self.stylus_devices and not self.touch_devices:
            logger.warning("No stylus or touch devices found")
            return False
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Input monitoring started")
        return True
    
    def stop_monitoring(self):
        """Stop monitoring input devices."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
            self.monitor_thread = None
        logger.info("Input monitoring stopped")
    
    def detect_devices(self):
        """Detect stylus and touch input devices."""
        if not EVDEV_AVAILABLE:
            return
        
        self.stylus_devices.clear()
        self.touch_devices.clear()
        
        try:
            devices = [InputDevice(path) for path in list_devices()]
            
            for device in devices:
                caps = device.capabilities(verbose=False)
                name = device.name.lower()
                
                logger.debug(f"Checking device: {device.name} ({device.path})")
                
                # Check if device supports pen/stylus input
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    
                    # Look for stylus-specific button codes
                    stylus_buttons = [
                        ecodes.BTN_TOOL_PEN,
                        ecodes.BTN_TOOL_RUBBER,
                        ecodes.BTN_STYLUS,
                        ecodes.BTN_STYLUS2,
                    ]
                    
                    if any(btn in keys for btn in stylus_buttons):
                        self.stylus_devices.append(device)
                        logger.info(f"Found stylus device: {device.name} ({device.path})")
                        continue
                
                # Check for touch screen
                if ecodes.EV_ABS in caps:
                    abs_caps = caps[ecodes.EV_ABS]
                    
                    # Touch devices typically have ABS_MT_* (multi-touch) events
                    if (ecodes.ABS_MT_POSITION_X in abs_caps or 
                        ecodes.ABS_MT_SLOT in abs_caps):
                        
                        # Avoid adding the same device as both stylus and touch
                        if device not in self.stylus_devices:
                            self.touch_devices.append(device)
                            logger.info(f"Found touch device: {device.name} ({device.path})")
        
        except Exception as e:
            logger.error(f"Error detecting devices: {e}")
    
    def _monitor_loop(self):
        """Main monitoring loop running in a separate thread."""
        logger.info("Monitor loop started")
        
        while self.monitoring:
            try:
                # Monitor stylus devices for proximity
                stylus_detected = False
                
                for device in self.stylus_devices:
                    try:
                        # Check if device has pending events
                        if device.active_keys():
                            stylus_detected = True
                            break
                        
                        # Non-blocking read with timeout
                        for event in device.read():
                            if event.type == ecodes.EV_KEY:
                                # Stylus proximity or button events
                                if event.code in [ecodes.BTN_TOOL_PEN, 
                                                 ecodes.BTN_TOOL_RUBBER,
                                                 ecodes.BTN_TOUCH]:
                                    if event.value == 1:  # Pressed/In proximity
                                        stylus_detected = True
                                        break
                    
                    except BlockingIOError:
                        # No events available, continue
                        pass
                    except Exception as e:
                        logger.debug(f"Error reading from {device.name}: {e}")
                
                # Update stylus state
                if stylus_detected != self.stylus_active:
                    self.stylus_active = stylus_detected
                    self.touch_enabled = not stylus_detected
                    
                    logger.info(f"Stylus state changed: active={stylus_detected}, touch_enabled={self.touch_enabled}")
                    
                    # Notify callback on main thread
                    if self.on_stylus_state_change:
                        GLib.idle_add(self.on_stylus_state_change, stylus_detected)
                    
                    # Disable/enable touch devices
                    self._set_touch_enabled(self.touch_enabled)
                
                # Small sleep to avoid busy-waiting
                time.sleep(0.05)
            
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                time.sleep(0.5)
        
        logger.info("Monitor loop stopped")
    
    def _set_touch_enabled(self, enabled: bool):
        """Enable or disable touch input devices."""
        # Note: Actually disabling touch devices requires root permissions
        # In practice, this is handled at the application level by ignoring touch events
        # when stylus is active. The evdev monitoring provides the detection mechanism.
        
        state_str = "enabled" if enabled else "disabled"
        logger.info(f"Touch input {state_str}")
        
        # In a production system, you might use:
        # - xinput disable/enable commands
        # - libinput device configuration
        # - Custom kernel module or udev rules
        
        # For now, we rely on the application layer to ignore touch when stylus is active
    
    def is_touch_allowed(self) -> bool:
        """Check if touch input should be processed."""
        return self.touch_enabled and not self.stylus_active
    
    def is_stylus_active(self) -> bool:
        """Check if stylus is currently in use."""
        return self.stylus_active
    
    def get_device_info(self) -> dict:
        """Get information about detected devices."""
        info = {
            'evdev_available': EVDEV_AVAILABLE,
            'monitoring': self.monitoring,
            'stylus_active': self.stylus_active,
            'touch_enabled': self.touch_enabled,
            'stylus_devices': [],
            'touch_devices': []
        }
        
        if EVDEV_AVAILABLE:
            info['stylus_devices'] = [
                {'name': d.name, 'path': d.path} for d in self.stylus_devices
            ]
            info['touch_devices'] = [
                {'name': d.name, 'path': d.path} for d in self.touch_devices
            ]
        
        return info
