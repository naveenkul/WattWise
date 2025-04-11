import os
import sys
import yaml
import stat
import logging
import base64
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigError(Exception):
    """Exception for configuration errors."""
    pass

def get_config_dir() -> str:
    """Get the configuration directory path."""
    home_dir = str(Path.home())
    config_dir = os.path.join(home_dir, ".config", "wattwise")
    
    # Ensure directory exists with correct permissions
    os.makedirs(config_dir, exist_ok=True)
    
    if not os.access(config_dir, os.W_OK):
        try:
            os.chmod(config_dir, 0o755)  # rwx r-x r-x
        except Exception as e:
            logger.warning(f"Could not set permissions on config directory: {e}")
    
    return config_dir

def get_config_path() -> str:
    """Get the configuration file path."""
    return os.path.join(get_config_dir(), "config.yaml")

def get_token_path() -> str:
    """Get the token file path."""
    return os.path.join(get_config_dir(), "token.secret")

def get_data_dir() -> str:
    """Get the data directory path."""
    home_dir = str(Path.home())
    data_dir = os.path.join(home_dir, ".local", "share", "wattwise")
    
    os.makedirs(data_dir, exist_ok=True)
    
    if not os.access(data_dir, os.W_OK):
        try:
            os.chmod(data_dir, 0o755)  # rwx r-x r-x
        except Exception as e:
            logger.warning(f"Could not set permissions on data directory: {e}")
    
    return data_dir

def ensure_config_dir() -> None:
    """Ensure that the config directory exists."""
    try:
        os.makedirs(get_config_dir(), exist_ok=True)
    except OSError as e:
        print(f"Error creating config directory {get_config_dir()}: {e}", file=sys.stderr)
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
        

        with open(get_token_path(), 'w') as f:
            f.write(token)
            

        os.chmod(get_token_path(), stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        print(f"Error saving token: {e}", file=sys.stderr)
        raise ConfigError(f"Could not save token: {e}")

def load_token() -> str:
    """Load the token from the secure file.
    
    Returns:
        The token or an empty string if not found
    """
    if not os.path.exists(get_token_path()):
        return ""
        
    try:
        with open(get_token_path(), 'r') as f:
            return f.read().strip()
    except OSError as e:
        print(f"Error loading token: {e}", file=sys.stderr)
        return ""

def load_config() -> Dict[str, Any]:
    """Load configuration from file."""
    config_path = get_config_path()
    
    # Default configuration
    default_config = {
        "homeassistant": {
            "host": "",
            "token": "",
            "entity_id": "",
            "current_entity_id": ""
        },
        "kasa": {
            "device_ip": "",
            "alias": "PC"
        }
    }
    
    # If config file doesn't exist, create it with defaults
    if not os.path.exists(config_path):
        try:
            with open(config_path, "w") as f:
                yaml.dump(default_config, f)
            # Set file permissions (rw- r-- r--)
            os.chmod(config_path, 0o644)
        except Exception as e:
            logger.error(f"Failed to create default config file: {e}")
            raise ConfigError(f"Could not create configuration file: {e}")
    
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        # If config is None (empty file), use default
        if config is None:
            config = default_config
        
        # Ensure all required sections exist
        if "homeassistant" not in config:
            config["homeassistant"] = default_config["homeassistant"]
        if "kasa" not in config:
            config["kasa"] = default_config["kasa"]
        
        # Load token if exists
        token_path = get_token_path()
        if os.path.exists(token_path):
            try:
                with open(token_path, "r") as f:
                    encoded_token = f.read().strip()
                    try:
                        config["homeassistant"]["token"] = base64.b64decode(encoded_token).decode("utf-8")
                    except Exception as e:
                        logger.warning(f"Failed to decode token: {e}")
                        # If token is corrupted, remove the token file and set an empty token
                        try:
                            os.remove(token_path)
                            logger.info(f"Removed corrupted token file: {token_path}")
                        except Exception as remove_error:
                            logger.warning(f"Could not remove corrupted token file: {remove_error}")
                        config["homeassistant"]["token"] = ""
            except Exception as e:
                logger.warning(f"Error loading token: {e}")
                config["homeassistant"]["token"] = ""
        
        return config
    
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        raise ConfigError(f"Could not load configuration: {e}")

def update_nested_dict(d: Dict, u: Dict) -> Dict:
    """Update a nested dictionary with values from another dictionary."""
    for k, v in u.items():
        if isinstance(v, dict) and k in d and isinstance(d[k], dict):
            update_nested_dict(d[k], v)
        else:
            d[k] = v
    return d

def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    config_dir = get_config_dir()
    config_path = get_config_path()
    token_path = get_token_path()
    
    try:
        token = config["homeassistant"].get("token", "")
        config_copy = config.copy()
        
        config_copy["homeassistant"] = config_copy["homeassistant"].copy()
        config_copy["homeassistant"]["token"] = ""
        
        os.makedirs(config_dir, exist_ok=True)
        
        with open(config_path, "w") as f:
            yaml.dump(config_copy, f)
        
        # Set file permissions (rw- r-- r--)
        os.chmod(config_path, 0o644)
        
        if token:
            try:
                encoded_token = base64.b64encode(token.encode("utf-8")).decode("utf-8")
                with open(token_path, "w") as f:
                    f.write(encoded_token)
                # Set restrictive permissions (rw- --- ---)
                os.chmod(token_path, 0o600)
            except Exception as e:
                logger.error(f"Failed to save token: {e}")
                raise ConfigError(f"Could not save authentication token: {e}")
        
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        raise ConfigError(f"Could not save configuration: {e}")
