import requests
import logging
import time
import random
import os
import json
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class HomeAssistantError(Exception):
    """Exception raised for Home Assistant errors."""
    pass

class HomeAssistant:
    """Client for interacting with Home Assistant API."""
    
    def __init__(self, host: str, token: str, entity_id: str, current_entity_id: Optional[str] = None, mock: bool = False):
        """Initialize the Home Assistant client.
        
        Args:
            host: Home Assistant host (e.g., http://10.0.0.43)
            token: Long-lived access token
            entity_id: Entity ID of the power sensor
            current_entity_id: Entity ID of the current sensor (optional)
            mock: Whether to use mock data instead of real requests
        """
        self.host = host.rstrip('/')
        self.token = token
        self.entity_id = entity_id
        self.current_entity_id = current_entity_id
        self.mock = mock
        
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        self.power_history = []
        self.current_history = []
        self.max_history_size = 100
        
        self.last_mock_power = 200.0
        self.last_mock_current = 2.0
        
        self._load_history_from_daemon()

    def _load_history_from_daemon(self):
        """Load historical data from daemon if available."""
        history_file = os.path.expanduser("~/.local/share/wattwise/history.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    history_data = json.load(f)
                    power_history = history_data.get('power', [])
                    current_history = history_data.get('current', [])
                    
                    if power_history and not self.power_history:
                        self.power_history = power_history
                        
                    if current_history and not self.current_history:
                        self.current_history = current_history
                        
                    logger.info(f"Loaded {len(self.power_history)} power readings and {len(self.current_history)} current readings from daemon history")
            except Exception as e:
                logger.warning(f"Could not load history from daemon: {e}")

    def validate_connection(self) -> Tuple[bool, Optional[str]]:
        """Validate connection to Home Assistant."""
        if self.mock:
            return True, None
            
        if not self.host or not self.token:
            return False, "Missing Home Assistant host or token"
            
        try:
            response = self._make_request(f"/api/states/{self.entity_id}")
            if response is None:
                return False, "Could not connect to Home Assistant"
                
            if self.current_entity_id:
                current_response = self._make_request(f"/api/states/{self.current_entity_id}")
                if current_response is None:
                    logger.warning(f"Current sensor {self.current_entity_id} not found")
            
            return True, None
        except Exception as e:
            logger.error(f"Failed to connect to Home Assistant: {e}")
            return False, str(e)

    def _make_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Make a request to the Home Assistant API."""
        if self.mock:
            if self.entity_id in endpoint:
                self.last_mock_power = self.last_mock_power + random.uniform(-20, 20)
                self.last_mock_power = max(50, min(400, self.last_mock_power))
                return {
                    "entity_id": self.entity_id,
                    "state": str(self.last_mock_power),
                    "attributes": {
                        "unit_of_measurement": "W",
                        "friendly_name": "Mock Power Consumption"
                    }
                }
            elif self.current_entity_id and self.current_entity_id in endpoint:
                self.last_mock_current = self.last_mock_current + random.uniform(-0.2, 0.2)
                self.last_mock_current = max(0.5, min(4.0, self.last_mock_current))
                return {
                    "entity_id": self.current_entity_id,
                    "state": str(self.last_mock_current),
                    "attributes": {
                        "unit_of_measurement": "A",
                        "friendly_name": "Mock Current"
                    }
                }
            return {}
        
        try:
            url = f"{self.host}{endpoint}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None

    def get_power_usage(self) -> Optional[float]:
        """Get current power usage from Home Assistant.
        
        Returns:
            Current power usage in watts or None if unavailable
            
        Raises:
            HomeAssistantError: If there's an error retrieving data
        """
        try:
            response = self._make_request(f"/api/states/{self.entity_id}")
            if response is None:
                raise HomeAssistantError("Failed to get power data")
                
            try:
                watts = float(response["state"])
                
                timestamp = time.time()
                self.power_history.append((timestamp, watts))
                
                if len(self.power_history) > self.max_history_size:
                    self.power_history = self.power_history[-self.max_history_size:]
                    
                return watts
            except (KeyError, ValueError) as e:
                logger.error(f"Invalid power data format: {e}")
                raise HomeAssistantError(f"Invalid power data format: {e}")
                
        except Exception as e:
            logger.error(f"Failed to get power data from Home Assistant: {e}")
            raise HomeAssistantError(f"Failed to get power data: {e}")

    def get_current_amperage(self) -> Optional[float]:
        """Get current amperage from Home Assistant.
        
        Returns:
            Current in amperes or None if unavailable
            
        Raises:
            HomeAssistantError: If there's an error retrieving data
        """
        if not self.current_entity_id:
            return None
            
        try:
            response = self._make_request(f"/api/states/{self.current_entity_id}")
            if response is None:
                raise HomeAssistantError("Failed to get current data")
                
            try:
                amperes = float(response["state"])
                
                timestamp = time.time()
                self.current_history.append((timestamp, amperes))
                
                if len(self.current_history) > self.max_history_size:
                    self.current_history = self.current_history[-self.max_history_size:]
                    
                return amperes
            except (KeyError, ValueError) as e:
                logger.error(f"Invalid current data format: {e}")
                raise HomeAssistantError(f"Invalid current data format: {e}")
                
        except Exception as e:
            logger.error(f"Failed to get current data from Home Assistant: {e}")
            raise HomeAssistantError(f"Failed to get current data: {e}")

    def get_power_trend(self, minutes: int = 5) -> Optional[Dict[str, Any]]:
        """Get power usage trend data for the past X minutes.
        
        Args:
            minutes: Number of minutes to analyze
            
        Returns:
            Dictionary with trend data or None if insufficient data
        """
        return self._get_trend_data(self.power_history, minutes)

    def get_current_trend(self, minutes: int = 5) -> Optional[Dict[str, Any]]:
        """Get current amperage trend data for the past X minutes.
        
        Args:
            minutes: Number of minutes to analyze
            
        Returns:
            Dictionary with trend data or None if insufficient data
        """
        return self._get_trend_data(self.current_history, minutes)
        
    def _get_trend_data(self, history, minutes: int = 5) -> Optional[Dict[str, Any]]:
        """Get trend data from history.
        
        Args:
            history: List of (timestamp, value) tuples
            minutes: Number of minutes to analyze
            
        Returns:
            Dictionary with trend data or None if insufficient data
        """
        if not history:
            return None
            
        now = time.time()
        cutoff = now - (minutes * 60)
        
        relevant_history = [(t, v) for t, v in history if t >= cutoff]
        
        if len(relevant_history) < 2:
            return None
            
        values = [v for _, v in relevant_history]
        
        return {
            "current": values[-1],
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "samples": len(values),
            "period_minutes": minutes
        }
