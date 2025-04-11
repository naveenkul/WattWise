from .utils import convert_to_bytes, get_default_config_path
from .config import load_config, ConfigError
from . import kasa
from . import display
import asyncio
import signal
import time
import sys
import logging

logger = logging.getLogger(__name__)

class WattWatcher:
    """Main class for watching power consumption."""
    
    def __init__(self, config=None, config_path=None):
        """Initialize the WattWatcher."""
        if config is None:
            config_path = config_path or get_default_config_path()
            try:
                self.config = load_config(config_path)
            except ConfigError as e:
                raise ConfigError(f"Failed to load config: {e}")
        else:
            self.config = config
            
        self.display_mgr = display.DisplayManager(self.config)
        self.running = False
        self.device = None
        
    def _create_kasa_device(self):
        """Create a Kasa device from config."""
        kasa_config = self.config.get("kasa", {})
        device_ip = kasa_config.get("device_ip")
        
        if not device_ip:
            raise ConfigError("Kasa device IP not configured. Run 'wattwise config kasa' first.")
            
        return kasa.KasaDevice(
            ip=device_ip,
            alias=kasa_config.get("alias", "PC"),
            username=kasa_config.get("username"),
            password=kasa_config.get("password")
        )
    
    def get_usage(self):
        """Get current power usage."""
        self.device = self._create_kasa_device()
        
        # Use the persistent event loop
        loop = kasa.get_event_loop()
        try:
            success, error = loop.run_until_complete(self.device.connect())
            if not success:
                self.display_mgr.show_error("Connection Error", error)
                return None
                
            usage = self.device.get_emeter_realtime_sync()
            if not usage:
                self.display_mgr.show_error("Read Error", "Failed to get power usage data")
                return None
                
            return usage
        except Exception as e:
            logger.error(f"Failed to get usage: {e}")
            self.display_mgr.show_error("Error", f"Failed to get usage: {e}")
            return None
    
    def display_usage(self, usage):
        """Display the current power usage."""
        if not usage:
            return
            
        # Format for display
        current_power = usage.get("power_mw", 0) / 1000  # Convert to watts
        voltage = usage.get("voltage_mv", 0) / 1000  # Convert to volts
        current = usage.get("current_ma", 0) / 1000  # Convert to amps
        
        # Display in the configured format
        self.display_mgr.show_power_usage(current_power, voltage, current)
    
    def watch(self, interval=2):
        """Watch power usage continuously."""
        self.device = self._create_kasa_device()
        self.running = True
        
        # Set up signal handling for graceful exit
        def handle_exit_signal(sig, frame):
            logger.info("Exiting wattwise watch mode...")
            self.running = False
            self.display_mgr.show_info("Exiting", "WattWise watch mode stopped")
            sys.exit(0)
            
        signal.signal(signal.SIGINT, handle_exit_signal)
        signal.signal(signal.SIGTERM, handle_exit_signal)
        
        # Use the persistent event loop
        loop = kasa.get_event_loop()
        
        # First connect to the device
        success, error = loop.run_until_complete(self.device.connect())
        if not success:
            self.display_mgr.show_error("Connection Error", error)
            return
            
        self.display_mgr.show_info("Watch Mode", f"Monitoring power usage every {interval} seconds. Press Ctrl+C to exit.")
        
        while self.running:
            try:
                # Update device info
                success, error = loop.run_until_complete(self.device.update())
                if not success:
                    self.display_mgr.show_error("Update Error", error)
                    time.sleep(interval)
                    continue
                
                # Get usage data
                usage = self.device.get_emeter_realtime_sync()
                if not usage:
                    self.display_mgr.show_error("Read Error", "Failed to get power usage data")
                else:
                    self.display_usage(usage)
                    
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Watch error: {e}")
                self.display_mgr.show_error("Error", f"Watch error: {e}")
                time.sleep(interval) 