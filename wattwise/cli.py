import typer
import logging
import time
import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.prompt import Prompt, Confirm

from . import config
from . import homeassistant
from . import display
from . import get_version


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)

logger = logging.getLogger("wattwise")

DATA_DIR = config.get_data_dir()
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

os.makedirs(DATA_DIR, exist_ok=True)

app = typer.Typer(
    name="wattwise",
    help="Monitor power usage from smart plugs using Home Assistant or python-kasa",
    add_completion=False,
)


config_app = typer.Typer(
    help="Configuration commands for data sources",
    add_completion=False,
)
app.add_typer(config_app, name="config")

console = Console()

@config_app.command("show")
def show_config():
    """Show current configuration."""
    try:
        cfg = config.load_config()
        display_mgr = display.DisplayManager(cfg)
        
        ha_config = cfg["homeassistant"]
        token_display = "Not configured"
        if ha_config["token"]:
            token = ha_config["token"]
            if len(token) > 8:
                token_display = f"{token[:4]}...{token[-4:]}"
            else:
                token_display = "****"
                
        ha_stats = {
            "host": ha_config["host"],
            "entity_id": f"Power: {ha_config.get('entity_id', 'Not configured')}",
            "current_entity_id": f"Current: {ha_config.get('current_entity_id', 'Not configured')}",
            "token": token_display
        }
        display_mgr.display_stats("Home Assistant Configuration", ha_stats)
        
        kasa_config = cfg["kasa"]
        kasa_stats = {
            "device_ip": kasa_config.get("device_ip", "Not configured"),
            "alias": kasa_config.get("alias", "Not configured")
        }
        display_mgr.display_stats("Kasa Device Configuration", kasa_stats)
        
        display_mgr.display_stats("Configuration Info", {
            "config_file": config.get_config_path(),
            "data_dir": DATA_DIR,
            "version": get_version()
        })
    except config.ConfigError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

@config_app.command("ha")
def configure_ha():
    """Configure Home Assistant integration."""
    try:
        cfg = config.load_config()
        display_mgr = display.DisplayManager(cfg)
        
        console.print("[bold blue]WattWise - Home Assistant Configuration[/bold blue]")
        
        cfg["homeassistant"]["host"] = Prompt.ask(
            "Home Assistant host",
            default=cfg["homeassistant"]["host"]
        )
        
        current_token = cfg["homeassistant"]["token"]
        token_prompt = "Home Assistant Long-Lived Access Token"
        if current_token:
            token_prompt += " (current token set, leave empty to keep)"
            
        new_token = Prompt.ask(
            token_prompt,
            default="",
            password=True
        )
        
        if new_token:
            cfg["homeassistant"]["token"] = new_token
        
        device_name = Prompt.ask(
            "Device name (e.g. epyc_workstation)",
            default=cfg["homeassistant"].get("device_name", "epyc_workstation")
        )
        cfg["homeassistant"]["device_name"] = device_name
        
        power_entity_id = f"sensor.{device_name}_current_consumption"
        current_entity_id = f"sensor.{device_name}_current"
        
        console.print(f"[dim]Using power sensor: [cyan]{power_entity_id}[/cyan][/dim]")
        console.print(f"[dim]Using current sensor: [cyan]{current_entity_id}[/cyan][/dim]")
        
        if Confirm.ask("Customize sensor entity IDs?", default=False):
            power_entity_id = Prompt.ask(
                "Power consumption entity ID",
                default=power_entity_id
            )
            current_entity_id = Prompt.ask(
                "Current amperage entity ID",
                default=current_entity_id
            )
        
        cfg["homeassistant"]["entity_id"] = power_entity_id
        cfg["homeassistant"]["current_entity_id"] = current_entity_id
        
        if cfg["homeassistant"]["host"] and cfg["homeassistant"]["token"]:
            console.print("Testing Home Assistant connection...")
            ha_client = homeassistant.HomeAssistant(
                cfg["homeassistant"]["host"],
                cfg["homeassistant"]["token"],
                cfg["homeassistant"]["entity_id"],
                current_entity_id=cfg["homeassistant"]["current_entity_id"]
            )
            
            success, error = ha_client.validate_connection()
            if success:
                display_mgr.show_success("Home Assistant", "Connection successful!")
            else:
                display_mgr.show_error("Home Assistant", f"Connection failed: {error}")
        else:
            console.print("[yellow]Note: Both Home Assistant host and token are required.[/yellow]")
        
        config.save_config(cfg)
        display_mgr.show_success("Configuration", "Home Assistant settings saved successfully!")
        
        console.print("\n[bold]Next steps:[/bold]")
        console.print("- Run [bold cyan]wattwise[/bold cyan] to see your current power usage")
        console.print("- Run [bold cyan]wattwise --current[/bold cyan] to see both power and current")
        console.print("- Run [bold cyan]wattwise --watch[/bold cyan] to continuously monitor power usage")
        
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

@config_app.command("kasa")
def configure_kasa():
    """Configure Kasa smart plug integration."""
    try:
        from . import kasa
        
        cfg = config.load_config()
        display_mgr = display.DisplayManager(cfg)
        
        console.print("[bold blue]WattWise - Kasa Smart Plug Configuration[/bold blue]")
        
        # Discover devices automatically
        console.print("\n[bold]Discovering Kasa devices on your network...[/bold]")
        discovered_devices = kasa.discover_devices_sync(timeout=8)
        
        device_ip = ""
        device_alias = ""
        
        if discovered_devices:
            console.print("\n[bold]Select a device to configure:[/bold]")
            selection = Prompt.ask(
                "Enter device number, or enter IP address manually",
                default="" if not cfg["kasa"].get("device_ip") else cfg["kasa"].get("device_ip")
            )
            
            try:
                device_index = int(selection)
                # Find the device with this index
                selected_device = next((d for d in discovered_devices if d["index"] == device_index), None)
                
                if selected_device:
                    device_ip = selected_device["ip"]
                    device_alias = selected_device["name"]
                    console.print(f"[green]Selected:[/green] {device_alias} at {device_ip}")
                else:
                    console.print(f"[yellow]No device with index {device_index} found.[/yellow]")
                    # Fall back to manual entry
                    device_ip = Prompt.ask(
                        "Kasa device IP address",
                        default=cfg["kasa"].get("device_ip", "")
                    )
            except ValueError:
                # Not a number, treat as IP address
                device_ip = selection
        else:
            # No devices found, manual entry
            device_ip = Prompt.ask(
                "Kasa device IP address",
                default=cfg["kasa"].get("device_ip", "")
            )
        
        if device_ip and not device_alias:
            device_alias = Prompt.ask(
                "Kasa device alias",
                default=cfg["kasa"].get("alias", "PC")
            )
        
        cfg["kasa"]["device_ip"] = device_ip
        cfg["kasa"]["alias"] = device_alias

        require_auth = Confirm.ask(
            "Does this device require authentication?",
            default=False
        )
        
        if require_auth:
            username = Prompt.ask(
                "Username",
                default=cfg["kasa"].get("username", "")
            )
            cfg["kasa"]["username"] = username
            
            password = Prompt.ask(
                "Password",
                default=cfg["kasa"].get("password", ""),
                password=True
            )
            cfg["kasa"]["password"] = password
        else:
            cfg["kasa"].pop("username", None)
            cfg["kasa"].pop("password", None)
        
        if device_ip:
            console.print("Testing connection to Kasa device...")
            try:
                device = kasa.KasaDevice(
                    device_ip,
                    device_alias,
                    username=cfg["kasa"].get("username"),
                    password=cfg["kasa"].get("password")
                )
                
                # Use the persistent event loop instead of creating a new one
                loop = kasa.get_event_loop()
                success, error = loop.run_until_complete(device.connect())
                
                if success:
                    display_mgr.show_success("Kasa Device", "Connection successful!")
                else:
                    display_mgr.show_error("Kasa Device", f"Connection failed: {error}")
            except Exception as e:
                display_mgr.show_error("Kasa Device", f"Connection test failed: {e}")
        else:
            console.print("[yellow]Note: Device IP is required to test connection.[/yellow]")
        
        config.save_config(cfg)
        display_mgr.show_success("Configuration", "Kasa settings saved successfully!")
        
        console.print("\n[bold]Next steps:[/bold]")
        console.print("- Run [bold cyan]wattwise[/bold cyan] to see your current power usage")
        console.print("- Run [bold cyan]wattwise --watch[/bold cyan] to continuously monitor power usage")
        
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

@config_app.command("fix-permissions")
def fix_permissions():
    """Fix permissions on configuration and data directories."""
    try:
        console.print("[bold blue]WattWise - Fixing Directory Permissions[/bold blue]")
        
        config_dir = config.get_config_dir()
        data_dir = config.get_data_dir()
        
        config_dir_exists = os.path.exists(config_dir)
        data_dir_exists = os.path.exists(data_dir)
        
        config_dir_writable = os.access(config_dir, os.W_OK) if config_dir_exists else False
        data_dir_writable = os.access(data_dir, os.W_OK) if data_dir_exists else False
        
        need_sudo = (config_dir_exists and not config_dir_writable) or (data_dir_exists and not data_dir_writable)
        
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)
        
        try:
            os.chmod(config_dir, 0o755)  # rwx r-x r-x
            console.print(f"[green]✓[/green] Set permissions on config directory: {config_dir}")
        except Exception as e:
            console.print(f"[red]✗[/red] Could not set permissions on config directory: {e}")
            need_sudo = True
        
        try:
            os.chmod(data_dir, 0o755)  # rwx r-x r-x
            console.print(f"[green]✓[/green] Set permissions on data directory: {data_dir}")
        except Exception as e:
            console.print(f"[red]✗[/red] Could not set permissions on data directory: {e}")
            need_sudo = True
        
        config_path = config.get_config_path()
        if os.path.exists(config_path):
            try:
                os.chmod(config_path, 0o644)  # rw- r-- r--
                console.print(f"[green]✓[/green] Set permissions on config file: {config_path}")
            except Exception as e:
                console.print(f"[red]✗[/red] Could not set permissions on config file: {e}")
                need_sudo = True
        
        token_path = config.get_token_path()
        if os.path.exists(token_path):
            try:
                os.chmod(token_path, 0o600)  # rw- --- ---
                console.print(f"[green]✓[/green] Set permissions on token file: {token_path}")
            except Exception as e:
                console.print(f"[red]✗[/red] Could not set permissions on token file: {e}")
                need_sudo = True
                # If token file is corrupted or has permission issues, try to remove it
                try:
                    os.remove(token_path)
                    console.print(f"[yellow]![/yellow] Removed problematic token file: {token_path}")
                except Exception as remove_error:
                    console.print(f"[red]✗[/red] Could not remove problematic token file: {remove_error}")
        
        # Check for history.json
        history_path = os.path.join(data_dir, "history.json")
        if os.path.exists(history_path):
            try:
                os.chmod(history_path, 0o644)  # rw- r-- r--
                console.print(f"[green]✓[/green] Set permissions on history file: {history_path}")
            except Exception as e:
                console.print(f"[red]✗[/red] Could not set permissions on history file: {e}")
                need_sudo = True
        
        console.print("\n[bold green]Permission check complete![/bold green]")
        
        if need_sudo:
            console.print("\n[bold yellow]Permissions could not be fully fixed.[/bold yellow]")
            console.print("You need to run the following command to take ownership of the configuration files:")
            console.print("[bold cyan]sudo chown -R $USER:$USER ~/.config/wattwise ~/.local/share/wattwise[/bold cyan]")
        else:
            console.print("\n[bold green]All permissions have been set correctly![/bold green]")
            console.print("You can now run [bold cyan]wattwise config kasa[/bold cyan] to set up your device.")
            
        console.print("\n[dim]If you continue to have issues, you can always try:[/dim]")
        console.print("[dim cyan]sudo chown -R $USER:$USER ~/.config/wattwise ~/.local/share/wattwise[/dim cyan]")
        
    except Exception as e:
        logger.error(f"Fix permissions error: {e}")
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print("[bold yellow]Try running the following command instead:[/bold yellow]")
        console.print("[bold cyan]sudo chown -R $USER:$USER ~/.config/wattwise ~/.local/share/wattwise[/bold cyan]")
        raise typer.Exit(code=1)

@app.command(hidden=True)
def view(
    watch: bool = typer.Option(
        False, 
        "--watch", "-w", 
        help="Continuously watch power usage"
    ),
    interval: int = typer.Option(
        1, 
        "--interval", "-i", 
        help="Refresh interval in seconds when watching",
        min=1,
        max=60
    ),
    minutes: int = typer.Option(
        5,
        "--minutes", "-m",
        help="Minutes of history to analyze for trends",
        min=1,
        max=60
    ),
    show_current: bool = typer.Option(
        False,
        "--current", "-c",
        help="Show current amperage data when available"
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Use mock data instead of connecting to Home Assistant"
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        "-s",
        help="Force using a specific data source: 'homeassistant' or 'kasa'"
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Output only the raw watts value as a number, suitable for use in scripts"
    ),
    discover: bool = typer.Option(
        False,
        "--discover", "-d",
        help="Discover and show available Kasa devices on your network"
    )
):
    """View current power usage from smart plugs."""
    try:
        # Handle discovery mode
        if discover:
            from . import kasa
            console.print("[bold blue]WattWise - Discovering Kasa Devices[/bold blue]\n")
            kasa.discover_devices_sync(timeout=10)
            console.print("\nTo configure a device, run: [bold cyan]wattwise config kasa[/bold cyan]")
            return
            
        # Check for permission issues first
        config_dir = config.get_config_dir()
        if not os.access(config_dir, os.W_OK):
            display_mgr = display.DisplayManager({})
            display_mgr.show_error(
                "Permission Error", 
                "No write permission on configuration directory. Please run the following command to fix:"
            )
            console.print("\n[bold cyan]wattwise config fix-permissions[/bold cyan]")
            console.print("\nIf that doesn't work, you may need to run:")
            console.print("[bold cyan]sudo chown -R $USER:$USER ~/.config/wattwise ~/.local/share/wattwise[/bold cyan]")
            raise typer.Exit(code=1)
            
        cfg = config.load_config()
        display_mgr = display.DisplayManager(cfg)
        
        ha_config = cfg["homeassistant"]
        kasa_config = cfg["kasa"]
        

        use_ha = source == "homeassistant" or (source is None and ha_config["host"] and ha_config["token"])
        use_kasa = source == "kasa" or (source is None and kasa_config.get("device_ip") and not use_ha)
        
        if not use_ha and not use_kasa and not mock:
            # No data sources configured - first time setup
            from . import kasa
            
            display_mgr.show_error(
                "Configuration Error", 
                "No data sources configured. You need to set up a data source first."
            )
            
            # Try to discover available Kasa devices
            console.print("\n[bold]Looking for Kasa devices on your network...[/bold]")
            
            try:
                discovered_devices = kasa.discover_devices_sync(timeout=5)
                
                if discovered_devices:
                    console.print("\n[bold]To configure one of these devices, run:[/bold]")
                    console.print("[bold cyan]wattwise config kasa[/bold cyan]")
                else:
                    console.print("\n[yellow]No Kasa devices found on your network.[/yellow]")
                    console.print("If you have Kasa devices, make sure they are powered on and connected to your network.")
            except Exception as e:
                logger.warning(f"Error discovering devices: {e}")
            
            console.print("\n[bold]Please run one of the following commands to configure WattWise:[/bold]")
            console.print("- [bold cyan]wattwise config kasa[/bold cyan] - Configure Kasa smart plug")
            console.print("- [bold cyan]wattwise config ha[/bold cyan] - Configure Home Assistant")
            console.print("\nTo discover all available Kasa devices, run:")
            console.print("[bold cyan]wattwise --discover[/bold cyan]")
            
            raise typer.Exit(code=1)

        if use_ha or mock:
            current_entity_id = ha_config.get("current_entity_id") if show_current else None
            ha_client = homeassistant.HomeAssistant(
                ha_config["host"], 
                ha_config["token"], 
                ha_config["entity_id"],
                current_entity_id=current_entity_id,
                mock=mock
            )
            
            success, error = ha_client.validate_connection()
            if not success and not mock:
                display_mgr.show_error(
                    "Home Assistant Error", 
                    f"Failed to connect to Home Assistant: {error}"
                )
                raise typer.Exit(code=1)
            
            if mock:
                console.print("[bold yellow]Using mock data mode - no real connection to Home Assistant[/bold yellow]")
            
            data_source = ha_client
            source_name = "Home Assistant"
        else:
            from . import kasa
            try:
                kasa_client = kasa.KasaDevice(
                    kasa_config["device_ip"],
                    kasa_config.get("alias", ""),
                    username=kasa_config.get("username"),
                    password=kasa_config.get("password")
                )
                
                data_source = kasa_client
                source_name = "Kasa Smart Plug"
            except Exception as e:
                display_mgr.show_error(
                    "Kasa Connection Error", 
                    f"Failed to initialize Kasa device: {e}"
                )
                console.print("\nYou may need to run this command to fix permission issues:")
                console.print("[bold cyan]wattwise config fix-permissions[/bold cyan]")
                raise typer.Exit(code=1)
        
        # Load history
        if watch and os.path.exists(HISTORY_FILE) and not mock:
            try:
                with open(HISTORY_FILE, 'r') as f:
                    history_data = json.load(f)
                    
                    if hasattr(data_source, 'power_history') and not data_source.power_history:
                        data_source.power_history = history_data.get('power', [])
                    elif hasattr(data_source, 'history') and not data_source.history:
                        data_source.history = history_data.get('power', [])
                        
                    if show_current and hasattr(data_source, 'current_history') and not data_source.current_history:
                        data_source.current_history = history_data.get('current', [])
                        
                    logger.info(f"Loaded {len(data_source.power_history) if hasattr(data_source, 'power_history') else len(data_source.history)} power readings and " + 
                              (f"{len(data_source.current_history)} current readings" if hasattr(data_source, 'current_history') else "0 current readings") + 
                              " from history")
            except Exception as e:
                logger.warning(f"Could not load history from file: {e}")
        
        try:
            if watch:
                _watch_power_usage(data_source, display_mgr, interval, minutes, show_current, source_name, raw)
            else:
                _fetch_and_display_usage(data_source, display_mgr, show_current, source_name, raw)
        except KeyboardInterrupt:
            if not raw:
                console.print("\n[bold]Monitoring stopped.[/bold]")
            
            if watch:
                try:
                    power_history = []
                    if hasattr(data_source, 'power_history'):
                        power_history = data_source.power_history
                    elif hasattr(data_source, 'history'):
                        power_history = data_source.history
                    
                    if power_history:
                        with open(HISTORY_FILE, 'w') as f:
                            json.dump({
                                'power': power_history,
                                'current': getattr(data_source, 'current_history', [])
                            }, f)
                        logger.info(f"Saved history to {HISTORY_FILE}")
                except Exception as e:
                    logger.warning(f"Could not save history to file: {e}")
            
    except config.ConfigError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        console.print("\nYou may need to run this command to fix permission issues:")
        console.print("[bold cyan]wattwise config fix-permissions[/bold cyan]")
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error(f"View error: {e}")
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

def _watch_power_usage(
    data_source,
    display_mgr: display.DisplayManager,
    interval: int,
    minutes: int,
    show_current: bool,
    source_name: str,
    raw: bool
):
    """Continuously watch and display power usage from smart plugs."""

    if hasattr(data_source, 'get_power_usage'):

        def get_power():
            try:
                return data_source.get_power_usage()
            except Exception as e:
                logger.error(f"Error getting power data: {e}")
                return None
                
        def get_power_trend(minutes):
            return data_source.get_power_trend(minutes)
            
        def get_current():
            if show_current and hasattr(data_source, 'get_current_amperage'):
                try:
                    return data_source.get_current_amperage()
                except Exception as e:
                    logger.error(f"Error getting current data: {e}")
                    return None
            return None
            
        def get_current_trend(minutes):
            if show_current and hasattr(data_source, 'get_current_trend'):
                return data_source.get_current_trend(minutes)
            return None
    else:

        def get_power():
            try:
                return data_source.get_power_usage_sync()
            except Exception as e:
                logger.error(f"Error getting power from Kasa: {e}")
                return None
                
        def get_power_trend(minutes):
            return data_source.get_power_trend(minutes)
            
        def get_current():
            return None
            
        def get_current_trend(minutes):
            return None
    

    display_mgr.display_continuous_usage(
        get_power, 
        get_power_trend, 
        source_name, 
        interval,
        get_current_callback=get_current,
        get_current_trend_callback=get_current_trend,
        show_current=show_current,
        raw=raw
    )

def _fetch_and_display_usage(
    data_source,
    display_mgr: display.DisplayManager,
    show_current: bool,
    source_name: str,
    raw: bool
):
    """Fetch and display power usage for a single reading from a smart plug."""
    try:
        watts = None
        amperes = None
        

        if hasattr(data_source, 'get_power_usage'):

            watts = data_source.get_power_usage()
            if show_current and hasattr(data_source, 'get_current_amperage'):
                amperes = data_source.get_current_amperage()
        else:

            watts = data_source.get_power_usage_sync()
        
        if watts is not None:
            if raw:
                sys.stdout.write(f"{watts:.0f}\n")
                sys.stdout.flush()
            else:
                display_mgr.display_current_usage(watts, source_name, current_amperes=amperes)
        else:
            if raw:
                sys.exit(1)
            else:
                display_mgr.show_error("Data Error", f"Could not get power usage data from {source_name}")
    except Exception as e:
        if raw:
            sys.exit(1) 
        else:
            display_mgr.show_error("Error", str(e))

@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    watch: bool = typer.Option(
        False, 
        "--watch", "-w", 
        help="Continuously watch power usage"
    ),
    interval: int = typer.Option(
        1, 
        "--interval", "-i", 
        help="Refresh interval in seconds when watching",
        min=1,
        max=60
    ),
    minutes: int = typer.Option(
        5,
        "--minutes", "-m",
        help="Minutes of history to analyze for trends",
        min=1,
        max=60
    ),
    show_current: bool = typer.Option(
        False,
        "--current", "-c",
        help="Show current amperage data when available"
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Use mock data instead of connecting to Home Assistant"
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        "-s",
        help="Force using a specific data source: 'homeassistant' or 'kasa'"
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Output only the raw watts value as a number, suitable for use in scripts"
    ),
    discover: bool = typer.Option(
        False,
        "--discover", "-d",
        help="Discover and show available Kasa devices on your network"
    )
):
    """
    WattWise - Monitor power usage from smart plugs with Home Assistant or Kasa.
    
    Examples:
      wattwise                   Show current power usage (single reading)
      wattwise --watch           Monitor power continuously with charts
      wattwise --current         Show power and current (single reading)
      wattwise --current --watch Monitor power and current continuously
      wattwise --raw             Output only the raw watts value for scripting use
      wattwise --mock            Use mock data for testing (no real connection)
      wattwise --discover        Find all Kasa devices on your network
      wattwise config kasa       Configure Kasa smart plug
      wattwise config ha         Configure Home Assistant
    """

    if ctx.invoked_subcommand is None:
        ctx.invoke(
            view,
            watch=watch,
            interval=interval,
            minutes=minutes,
            show_current=show_current,
            mock=mock,
            source=source,
            raw=raw,
            discover=discover
        )

def main():
    """Main entry point for the application."""
    try:
        app()
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        console.print(f"[bold red]Unhandled error:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
