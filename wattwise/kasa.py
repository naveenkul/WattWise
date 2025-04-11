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

from . import config
from rich.console import Console
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)

# Store a global event loop to prevent "event loop is closed" errors
_event_loop = None

def get_event_loop():
    """Get a persistent event loop to avoid 'event loop is closed' errors."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop

class KasaError(Exception):
    """Exception raised for Kasa device errors."""
    pass

try:
    from kasa import Discover
    from kasa.device import Device
    from kasa.iot import IotPlug
    KASA_AVAILABLE = True
except ImportError:
    KASA_AVAILABLE = False
    logger.warning("python-kasa library not found. Install with 'pip install python-kasa' to use Kasa devices.")

class KasaDevice:
    """Client for TP-Link Kasa smart plugs."""
    
    def __init__(self, device_ip: str, alias: str = "", username: Optional[str] = None, password: Optional[str] = None):
        if not KASA_AVAILABLE:
            raise ImportError("python-kasa library not installed. Run 'pip install python-kasa' to use Kasa devices.")
            
        self.device_ip = device_ip
        self.alias = alias
        
        try:
            self.plug = IotPlug(device_ip)
        except Exception as e:
            logger.error(f"Failed to initialize Device with error: {e}")
            raise
            
        self.history = []
        self.max_history_size = 100
        
        self._load_history_from_daemon()
    
    def _load_history_from_daemon(self):
        history_file = os.path.join(config.get_data_dir(), "history.json")
        
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
    
    def _device_has_emeter(self) -> bool:
        try:
            return self.plug.has_emeter
        except Exception as e:
            logger.error(f"Error checking if device has emeter: {e}")
            return False
    
    def _get_emeter_data(self) -> Dict[str, Any]:
        try:
            loop = get_event_loop()
            
            try:
                emeter_task = loop.create_task(self.plug.get_emeter_realtime())
                return loop.run_until_complete(asyncio.wait_for(emeter_task, timeout=5.0))
            except Exception as e:
                logger.error(f"Error getting data from emeter: {e}")
            
            return {}
        except Exception as e:
            logger.error(f"Error getting emeter data: {e}")
            return {}
    
    def get_device_info_sync(self) -> Dict[str, Any]:
        try:
            loop = get_event_loop()
            
            # Update the device
            update_task = loop.create_task(self.plug.update())
            loop.run_until_complete(asyncio.wait_for(update_task, timeout=10.0))
            
            # Get device capabilities
            has_emeter = self._device_has_emeter()
            
            # Create base device info
            info = {
                "model": getattr(self.plug, "model", "Unknown"),
                "alias": getattr(self.plug, "alias", self.alias or "Unknown"),
                "device_id": getattr(self.plug, "device_id", "Unknown"),
                "has_emeter": has_emeter,
                "is_on": getattr(self.plug, "is_on", False)
            }
            
            if has_emeter:
                try:
                    emeter = self._get_emeter_data()
                    
                    if isinstance(emeter, dict):
                        # Handle different units based on the device variant
                        watts = emeter.get("power_mw", 0) / 1000 if "power_mw" in emeter else emeter.get("power", 0)
                        current = emeter.get("current_ma", 0) / 1000 if "current_ma" in emeter else emeter.get("current", 0)
                        voltage = emeter.get("voltage_mv", 0) / 1000 if "voltage_mv" in emeter else emeter.get("voltage", 0)
                    else:
                        logger.warning(f"Unexpected emeter data format from {self.device_ip}: {type(emeter)}")
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
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return {
                "model": "Unknown",
                "alias": self.alias or "Unknown",
                "device_id": "Unknown",
                "has_emeter": False,
                "is_on": False,
                "current_consumption": 0,
                "voltage": 0,
                "current": 0
            }
    
    def get_power_usage_sync(self) -> Optional[float]:
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

async def discover_devices(timeout: int = 5) -> Dict[str, Any]:
    if not KASA_AVAILABLE:
        raise ImportError("python-kasa library not installed. Run 'pip install python-kasa' to use Kasa devices.")
    
    try:
        console.print(f"Discovering Kasa devices on your network for {timeout} seconds...")
        devices = await Discover.discover(timeout=timeout)
        return devices
    except Exception as e:
        logger.error(f"Error discovering devices: {e}")
        return {}

def display_discovered_devices(devices: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not devices:
        console.print("[yellow]No Kasa devices found on your network.[/yellow]")
        console.print("Make sure your devices are powered on and connected to the same network.")
        return []
    
    table = Table(title="Discovered Kasa Devices")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("IP Address", style="blue")
    table.add_column("Model", style="magenta")
    table.add_column("Power", style="yellow")
    table.add_column("State", style="red")
    
    device_list = []
    index = 1
    
    loop = get_event_loop()
    
    for ip, device in devices.items():
        name = getattr(device, "alias", "Unknown")
        model = getattr(device, "model", "Unknown")
        state = getattr(device, "is_on", False)
        state_display = "[green]ON[/green]" if state else "[red]OFF[/red]"
        power = "N/A"
        
        has_emeter = False
        if hasattr(device, 'has_emeter'):
            has_emeter = device.has_emeter
        
        if has_emeter:
            try:
                if hasattr(device, 'get_emeter_realtime'):
                    emeter_task = loop.create_task(device.get_emeter_realtime())
                    emeter = loop.run_until_complete(asyncio.wait_for(emeter_task, timeout=5.0))
                    if isinstance(emeter, dict):
                        watts = emeter.get("power_mw", 0) / 1000 if "power_mw" in emeter else emeter.get("power", 0)
                        power = f"{watts:.1f} W"
            except Exception as e:
                logger.debug(f"Error getting power consumption for {name}: {e}")
                power = "Error"
        
        table.add_row(
            str(index),
            name,
            ip,
            model,
            power,
            state_display
        )
        
        device_list.append({
            "index": index,
            "name": name,
            "ip": ip,
            "model": model,
            "has_emeter": has_emeter,
            "state": state
        })
        
        index += 1
    
    console.print(table)
    console.print(f"Found {len(device_list)} Kasa devices on your network.\n")
    
    return device_list

def discover_devices_sync(timeout: int = 5, display: bool = True) -> List[Dict[str, Any]]:
    if not KASA_AVAILABLE:
        logger.warning("python-kasa library not installed. Run 'pip install python-kasa' to use Kasa devices.")
        return []
    
    try:
        loop = get_event_loop()
        
        devices = loop.run_until_complete(discover_devices(timeout))
        
        if display:
            return display_discovered_devices(devices)
        
        device_list = []
        index = 1
        
        for ip, device in devices.items():
            name = getattr(device, "alias", "Unknown")
            model = getattr(device, "model", "Unknown")
            state = getattr(device, "is_on", False)
            
            has_emeter = False
            if hasattr(device, 'has_emeter'):
                has_emeter = device.has_emeter
            
            device_list.append({
                "index": index,
                "name": name,
                "ip": ip,
                "model": model,
                "has_emeter": has_emeter,
                "state": state
            })
            
            index += 1
        
        return device_list
    except Exception as e:
        logger.error(f"Discovery error: {e}")
        return []

async def get_device_power_history(device: Device) -> Tuple[List[float], List[float], List[datetime]]:
    if not hasattr(device, 'has_emeter') or not device.has_emeter:
        return [], [], []
    
    daily_stats = await device.get_emeter_daily()
    
    sorted_stats = sorted(daily_stats, key=lambda x: x["day"])
    
    energy_kwh = []
    costs = []
    timestamps = []
    
    for entry in sorted_stats:
        day = entry["day"]
        month = entry["month"]
        year = entry["year"]
        
        date = datetime(year, month, day)
        
        energy = entry.get("energy_wh", 0) / 1000.0 if "energy_wh" in entry else entry.get("energy", 0)
        
        cost = entry.get("cost", 0)
        
        energy_kwh.append(energy)
        costs.append(cost)
        timestamps.append(date)
    
    return energy_kwh, costs, timestamps
