import os
import sys
import yaml
import stat
from typing import Dict, Any, Optional
from pathlib import Path

class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass

CONFIG_DIR = os.path.expanduser("~/.config/wattwise")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
TOKEN_FILE = os.path.join(CONFIG_DIR, "token.secret")

DEFAULT_CONFIG = {
    "homeassistant": {
        "host": "http://10.0.0.43",
        "token": "",
        "device_name": "epyc_workstation",
        "entity_id": "sensor.epyc_workstation_current_consumption",
        "current_entity_id": "sensor.epyc_workstation_current"
    },
    "kasa": {
        "device_ip": "",
        "alias": "PC"
    },
    "display": {
        "thresholds": {
            "warning": 300,
            "critical": 1200
        },
        "colors": {
            "normal": "green",
            "warning": "yellow",
            "critical": "red"
        }
    }
}

def ensure_config_dir() -> None:
    """Ensure that the config directory exists."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except OSError as e:
        print(f"Error creating config directory {CONFIG_DIR}: {e}", file=sys.stderr)
        raise ConfigError(f"Could not create config directory: {e}")

def save_token(token: str) -> None:
    """Save the token to a secure file with restricted permissions.
    
    Args:
        token: The token to save
        
    Raises:
        ConfigError: If the token can't be saved
    """
    if not token:
        return
        
    try:
        ensure_config_dir()
        

        with open(TOKEN_FILE, 'w') as f:
            f.write(token)
            

        os.chmod(TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        print(f"Error saving token: {e}", file=sys.stderr)
        raise ConfigError(f"Could not save token: {e}")

def load_token() -> str:
    """Load the token from the secure file.
    
    Returns:
        The token or an empty string if not found
    """
    if not os.path.exists(TOKEN_FILE):
        return ""
        
    try:
        with open(TOKEN_FILE, 'r') as f:
            return f.read().strip()
    except OSError as e:
        print(f"Error loading token: {e}", file=sys.stderr)
        return ""

def load_config() -> Dict[str, Any]:
    """Load configuration from file.
    
    Returns:
        Dict containing configuration values.
        
    Raises:
        ConfigError: If the configuration can't be loaded.
    """
    if not os.path.exists(CONFIG_FILE):

        try:
            ensure_config_dir()
            with open(CONFIG_FILE, "w") as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
            return DEFAULT_CONFIG
        except (OSError, yaml.YAMLError) as e:
            print(f"Error creating default config: {e}", file=sys.stderr)
            raise ConfigError(f"Could not create default configuration: {e}")
    
    try:
        with open(CONFIG_FILE, "r") as f:
            config = yaml.safe_load(f)
        

        if config is None:
            print("Warning: Empty configuration file, using defaults", file=sys.stderr)
            config = {}
        
        if not isinstance(config, dict):
            raise ConfigError(f"Invalid configuration format: expected dict, got {type(config)}")
            

        merged_config = DEFAULT_CONFIG.copy()
        update_nested_dict(merged_config, config)
        

        for section in ["homeassistant", "kasa", "display"]:
            if section not in merged_config:
                raise ConfigError(f"Missing required configuration section: {section}")
        

        token = load_token()
        if token:
            merged_config["homeassistant"]["token"] = token
            
        return merged_config
    except (OSError, yaml.YAMLError) as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        raise ConfigError(f"Could not load configuration: {e}")
    except Exception as e:
        print(f"Unexpected error loading configuration: {e}", file=sys.stderr)
        raise ConfigError(f"Unexpected error loading configuration: {e}")

def update_nested_dict(d: Dict, u: Dict) -> Dict:
    """Update a nested dictionary with values from another dictionary."""
    for k, v in u.items():
        if isinstance(v, dict) and k in d and isinstance(d[k], dict):
            update_nested_dict(d[k], v)
        else:
            d[k] = v
    return d

def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file.
    
    Args:
        config: Configuration dictionary to save.
        
    Raises:
        ConfigError: If the configuration can't be saved.
    """
    try:
        ensure_config_dir()
        
        token = config["homeassistant"]["token"]
        save_token(token)
        
        config_to_save = config.copy()
        config_to_save["homeassistant"] = config["homeassistant"].copy()
        config_to_save["homeassistant"]["token"] = ""
        
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(config_to_save, f, default_flow_style=False)
    except (OSError, yaml.YAMLError) as e:
        print(f"Error saving config: {e}", file=sys.stderr)
        raise ConfigError(f"Could not save configuration: {e}")

def get_config_path() -> str:
    """Return the path to the config file."""
    return CONFIG_FILE
