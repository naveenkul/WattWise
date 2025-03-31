"""
Module for interacting with TP-Link Kasa smart plugs.
"""
import time
import logging
import asyncio
import os
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

class KasaError(Exception):
    """Exception raised for Kasa device errors."""
    pass

try:
    from kasa import SmartPlug, SmartDevice
    KASA_AVAILABLE = True
except ImportError:
    KASA_AVAILABLE = False
    logger.warning("python-kasa library not found. Install with 'pip install python-kasa' to use Kasa devices.")

class KasaDevice:
    """Client for TP-Link Kasa smart plugs."""
    
    def __init__(self, device_ip: str, alias: str = "", username: Optional[str] = None, password: Optional[str] = None):
        """Initialize the Kasa device client.
        
        Args:
            device_ip: IP address of the Kasa smart plug
            alias: Friendly name for the device
            username: Optional username for devices that require authentication
            password: Optional password for devices that require authentication
        """
        if not KASA_AVAILABLE:
            raise ImportError("python-kasa library not installed. Run 'pip install python-kasa' to use Kasa devices.")
            
        self.device_ip = device_ip
        self.alias = alias
        
        if username and password:
            self.plug = SmartPlug(device_ip, username=username, password=password)
        else:
            self.plug = SmartPlug(device_ip)
            
        self.history = []
        self.max_history_size = 100
        
        self._load_history_from_daemon()
    
    def _load_history_from_daemon(self):
        """Load historical data from daemon if available."""
        history_file = os.path.expanduser("~/.local/share/wattwise/history.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    history_data = json.load(f)
                    power_history = history_data.get('power', [])
                    
                    if power_history and not self.history:
                        self.history = power_history
                        
                    logger.info(f"Loaded {len(self.history)} power readings from daemon history")
            except Exception as e:
                logger.warning(f"Could not load history from daemon: {e}")

    async def connect(self) -> Tuple[bool, Optional[str]]:
        """Connect to the Kasa device."""
        try:
            await asyncio.wait_for(self.plug.update(), timeout=10.0)
            return True, None
        except asyncio.TimeoutError:
            error_msg = f"Connection to {self.device_ip} timed out after 10 seconds"
            logger.error(error_msg)
            return False, error_msg
        except ConnectionRefusedError:
            error_msg = f"Connection refused by device at {self.device_ip}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            logger.error(f"Failed to connect to Kasa device at {self.device_ip}: {e}")
            return False, str(e)
    
    def get_device_info_sync(self) -> Dict[str, Any]:
        """Get device information synchronously."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            update_task = loop.create_task(self.plug.update())
            loop.run_until_complete(asyncio.wait_for(update_task, timeout=10.0))
            
            has_emeter = self.plug.has_emeter
            
            info = {
                "model": self.plug.model,
                "alias": self.plug.alias,
                "device_id": self.plug.device_id,
                "has_emeter": has_emeter,
                "is_on": self.plug.is_on
            }
            
            if has_emeter:
                try:
                    if hasattr(self.plug, "features"):
                        watts = None
                        current = None
                        voltage = None
                        
                        if hasattr(self.plug.features, "get"):
                            try:
                                if self.plug.features.get("power") is not None:
                                    watts = self.plug.features.get("power")
                                elif self.plug.features.get("current_power_w") is not None:
                                    watts = self.plug.features.get("current_power_w")
                                
                                if self.plug.features.get("current") is not None:
                                    current = self.plug.features.get("current")
                                elif self.plug.features.get("current_ma") is not None:
                                    current = self.plug.features.get("current_ma") / 1000
                                
                                if self.plug.features.get("voltage") is not None:
                                    voltage = self.plug.features.get("voltage")
                                elif self.plug.features.get("voltage_mv") is not None:
                                    voltage = self.plug.features.get("voltage_mv") / 1000
                            except Exception as e:
                                logger.debug(f"Error accessing feature API: {e}")
                    
                    if watts is None:
                        try:
                            emeter_task = loop.create_task(self.plug.get_emeter_realtime())
                            emeter = loop.run_until_complete(asyncio.wait_for(emeter_task, timeout=5.0))
                            
                            if isinstance(emeter, dict):
                                watts = emeter.get("power_mw", 0) / 1000 if "power_mw" in emeter else emeter.get("power", 0)
                                current = emeter.get("current_ma", 0) / 1000 if "current_ma" in emeter else emeter.get("current", 0)
                                voltage = emeter.get("voltage_mv", 0) / 1000 if "voltage_mv" in emeter else emeter.get("voltage", 0)
                            else:
                                logger.warning(f"Unexpected emeter data format from {self.device_ip}: {type(emeter)}")
                                watts = 0
                                current = 0
                                voltage = 0
                        except asyncio.TimeoutError:
                            logger.error(f"Timeout getting emeter data from {self.device_ip}")
                            watts = 0
                            current = 0
                            voltage = 0
                        except Exception as e:
                            logger.error(f"Error getting emeter data from {self.device_ip}: {e}")
                            watts = 0
                            current = 0
                            voltage = 0
                    
                    info.update({
                        "current_consumption": watts,
                        "voltage": voltage,
                        "current": current
                    })
                except Exception as e:
                    logger.error(f"Error getting emeter data: {e}")
                    info.update({
                        "current_consumption": 0,
                        "voltage": 0,
                        "current": 0
                    })
                
            return info
        finally:
            loop.close()
    
    def get_power_usage_sync(self) -> Optional[float]:
        """Get current power usage synchronously."""
        try:
            info = self.get_device_info_sync()
            
            if not info.get("has_emeter", False):
                logger.warning(f"Device {self.device_ip} does not support energy monitoring")
                return None
                
            watts = info.get("current_consumption")
            
            if watts is not None:
                timestamp = time.time()
                self.history.append((timestamp, watts))
                
                if len(self.history) > self.max_history_size:
                    self.history = self.history[-self.max_history_size:]
                    
                return watts
            return None
        except Exception as e:
            logger.error(f"Failed to get power usage from Kasa device: {e}")
            return None
    
    def get_power_trend(self, minutes: int = 5) -> Optional[Dict[str, Any]]:
        """Get power usage trend data for the past X minutes.
        
        Args:
            minutes: Number of minutes to analyze
            
        Returns:
            Dictionary with trend data or None if insufficient data
        """
        if not self.history:
            return None
            
        now = time.time()
        cutoff = now - (minutes * 60)
        
        relevant_history = [(t, p) for t, p in self.history if t >= cutoff]
        
        if len(relevant_history) < 2:
            return None
            
        values = [p for _, p in relevant_history]
        
        return {
            "current": values[-1],
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "samples": len(values),
            "period_minutes": minutes
        }

def discover_devices_sync(timeout: int = 5, username: Optional[str] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """Discover Kasa devices on the network.
    
    Args:
        timeout: Discovery timeout in seconds
        username: Optional username for devices that require authentication
        password: Optional password for devices that require authentication
        
    Returns:
        List of dictionaries with device information
    """
    if not KASA_AVAILABLE:
        logger.warning("python-kasa library not installed. Run 'pip install python-kasa' to use Kasa devices.")
        return []
        
    from kasa import Discover
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        try:
            discover_kwargs = {"timeout": timeout}
            
            if username and password:
                discover_kwargs["username"] = username
                discover_kwargs["password"] = password
                
            discover_task = Discover.discover(**discover_kwargs)
            devices = loop.run_until_complete(asyncio.wait_for(discover_task, timeout=timeout+5.0))
            
            if not devices:
                logger.warning("No devices found during discovery")
                return []
                
        except asyncio.TimeoutError:
            logger.error(f"Discovery timed out after {timeout+5} seconds")
            return []
        except TypeError as e:
            logger.debug(f"Falling back to legacy discovery: {e}")
            try:
                discover_task = Discover.discover(timeout=timeout)
                devices = loop.run_until_complete(asyncio.wait_for(discover_task, timeout=timeout+5.0))
                
                if not devices:
                    logger.warning("No devices found during legacy discovery")
                    return []
            except asyncio.TimeoutError:
                logger.error(f"Legacy discovery timed out after {timeout+5} seconds")
                return []
            except Exception as e:
                logger.error(f"Legacy discovery failed: {e}")
                return []
        
        result = []
        for addr, dev in devices.items():
            device_data = {
                "ip_address": addr,
                "model": getattr(dev, "model", "Unknown"),
                "alias": getattr(dev, "alias", "Unknown"),
                "device_type": str(getattr(dev, "device_type", "Unknown")),
                "has_emeter": False
            }
            
            if hasattr(dev, "has_emeter"):
                device_data["has_emeter"] = dev.has_emeter
            elif hasattr(dev, "features") and "power" in getattr(dev.features, "keys", lambda: [])():
                device_data["has_emeter"] = True
                
            result.append(device_data)
            
        return result
    except Exception as e:
        logger.error(f"Device discovery failed: {e}")
        return []
    finally:
        loop.close()

async def get_device_power_history(device: SmartDevice) -> Tuple[List[float], List[float], List[datetime]]:
    """Get the power usage history from the device.
    
    Args:
        device: The Kasa smart device.
        
    Returns:
        A tuple containing three lists:
        - List of power readings in watts
        - List of current readings in amps (if available, otherwise empty)
        - List of timestamps for the readings
        
    Raises:
        KasaError: If there's an issue getting the device's power history.
    """
    try:
        await device.update()
        
        emeter = device.emeter_realtime
        current_power = float(emeter["power"])
        
        current_amps = None
        if "current" in emeter:
            current_amps = float(emeter["current"])
        
        history = []
        history_current = []
        history_time = []
        
        try:
            current_month = datetime.now().month
            daystat = await device.get_emeter_daily(year=datetime.now().year, month=current_month)
            
            today = datetime.now().day
            day_data = daystat.get(today, [])
            
            if day_data:
                if isinstance(day_data, list):
                    for i, energy_wh in enumerate(day_data):
                        if energy_wh > 0:
                            power = energy_wh * 60
                            ts = datetime.now().replace(hour=i, minute=0, second=0, microsecond=0)
                            history.append(power)
                            if current_amps is not None:
                                estimated_current = power / 120
                                history_current.append(estimated_current)
                            history_time.append(ts)
                else:
                    energy_wh = day_data
                    if energy_wh > 0:
                        power = energy_wh / 24
                        ts = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
                        history.append(power)
                        if current_amps is not None:
                            estimated_current = power / 120
                            history_current.append(estimated_current)
                        history_time.append(ts)
        except Exception as e:
            print(f"Warning: Failed to get device history stats: {e}", file=sys.stderr)
            pass
        
        history.append(current_power)
        if current_amps is not None:
            history_current.append(current_amps)
        history_time.append(datetime.now())
        
        return history, history_current, history_time
    except Exception as e:
        print(f"Error getting device power history: {e}", file=sys.stderr)
        raise KasaError(f"Failed to get device power history: {e}")
