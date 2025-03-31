import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Union
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich.align import Align
from rich import box

logger = logging.getLogger(__name__)

console = Console()

class DisplayManager:
    """Manager for displaying power usage information in the terminal."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the display manager with configuration settings."""
        self.config = config
        self.display_config = config.get("display", {})
        self.thresholds = self.display_config.get("thresholds", {"warning": 300, "critical": 1200})
        self.colors = self.display_config.get("colors", {"normal": "green", "warning": "yellow", "critical": "red"})
        self.console = Console()
        self.history: List[Tuple[float, float]] = []
        self.max_history_size = 100
        self.max_Watts = 1800
        self.current_history: List[Tuple[float, float]] = []

    def get_color_for_watts(self, watts: float) -> str:
        """Get the appropriate color based on power usage."""
        critical = self.thresholds.get("critical", 1200)
        warning = self.thresholds.get("warning", 300)
        
        if watts >= critical:
            return self.colors.get("critical", "red")
        elif watts >= warning:
            return self.colors.get("warning", "yellow")
        else:
            return self.colors.get("normal", "green")
    
    def add_to_history(self, watts: float) -> None:
        """Add a power reading to the history."""
        timestamp = time.time()
        self.history.append((timestamp, watts))
        
        if len(self.history) > self.max_history_size:
            self.history = self.history[-self.max_history_size:]
    
    def display_current_usage(self, watts: float, source: str, current_amperes: Optional[float] = None) -> None:
        """Display current power usage."""
        self.add_to_history(watts)
        
        color = self.get_color_for_watts(watts)
        
        text = Text()
        text.append(f"Power Usage: ", style="bold")
        text.append(f"{watts:.2f} Watts", style=f"bold {color}")
        
        if current_amperes is not None:
            timestamp = time.time()
            self.current_history.append((timestamp, current_amperes))
            
            if len(self.current_history) > self.max_history_size:
                self.current_history = self.current_history[-self.max_history_size:]
            
            text.append(f"\nCurrent: ", style="bold")
            text.append(f"{current_amperes:.2f} Amps", style="bold blue")
        
        panel = Panel(
            text,
            title=f"[bold]WattWise[/bold] ({source})",
            subtitle=f"Last updated: {datetime.now().strftime('%H:%M:%S')}",
            border_style=color,
        )
        
        self.console.print(panel)
    
    def _create_live_display(self) -> Layout:
        """Create a layout for live display mode."""
        layout = Layout()
        
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        
        layout["main"].split_row(
            Layout(name="stats", ratio=1),
            Layout(name="chart", ratio=2),
        )
        
        header_text = Text()
        header_text.append("WattWise", style="bold blue")
        header_text.append(" | ", style="dim")
        header_text.append("Real-time power and current monitoring for smart plugs", style="italic")
        
        centered_header = Align.center(header_text)
        
        header_panel = Panel(
            centered_header,
            box=box.ROUNDED,
            padding=(0, 2)
        )
        layout["header"].update(header_panel)
        
        layout["stats"].update(
            Panel(
                Text("Loading power data..."),
                title="Current Stats",
                subtitle="W = watts | A = amps",
                border_style="green"
            )
        )
        
        layout["chart"].update(
            Panel(
                Text("Collecting data for chart..."),
                title="Power Usage History",
                border_style="blue"
            )
        )
        
        layout["footer"].update(
            Panel(
                Text(f"Press Ctrl+C to stop monitoring", justify="center"),
                border_style="blue"
            )
        )
        
        return layout
        
    def _update_live_display(
        self, 
        layout: Layout, 
        watts: float, 
        trend_data: Optional[Dict[str, Any]], 
        source: str,
        timestamp: float,
        current_amperes: Optional[float] = None,
        current_trend_data: Optional[Dict[str, Any]] = None,
        show_current: bool = False
    ) -> None:
        """Update the live display with current data."""
        color = self.get_color_for_watts(watts)
        
        terminal_width = self.get_term_size()[0]
        stats_width = max(terminal_width // 3 - 4, 30)
        table_width = stats_width - 4 
        
        sections_grid = Table.grid(padding=0)
        sections_grid.add_column("sections", width=stats_width)
        
        sections_grid.add_row("")
        
        col1_width = 16
        col2_width = table_width - col1_width - 2
        
        power_table = Table(box=box.ROUNDED, show_header=False, title_justify="center", title="Power", padding=(0, 1), width=table_width)
        power_table.add_column("Metric", style="bright_blue", width=col1_width)
        power_table.add_column("Value", width=col2_width)
        power_table.add_row("Current", f"[bold {color}]{watts:.2f} W[/bold {color}]")
        
        if trend_data:
            power_table.add_row("Min", f"{trend_data['min']:.2f} W")
            power_table.add_row("Max", f"{trend_data['max']:.2f} W")
            power_table.add_row("Avg", f"{trend_data['avg']:.2f} W")
        
        current_table = None
        if show_current and current_amperes is not None:
            current_table = Table(box=box.ROUNDED, show_header=False, title_justify="center", title="Current", padding=(0, 1), width=table_width)
            current_table.add_column("Metric", style="bright_blue", width=col1_width)
            current_table.add_column("Value", width=col2_width)
            current_table.add_row("Current", f"[bold blue]{current_amperes:.2f} A[/bold blue]")
            
            if current_trend_data:
                current_table.add_row("Min", f"{current_trend_data['min']:.2f} A")
                current_table.add_row("Max", f"{current_trend_data['max']:.2f} A")
                current_table.add_row("Avg", f"{current_trend_data['avg']:.2f} A")
        
        energy_table = Table(box=box.ROUNDED, show_header=False, title_justify="center", title="Energy", padding=(0, 1), width=table_width)
        energy_table.add_column("Metric", style="bright_blue", width=col1_width)
        energy_table.add_column("Value", width=col2_width)
        
        if trend_data:
            avg_watts = trend_data['avg']
            
            if len(self.history) >= 2:
                start_time = self.history[0][0]
                end_time = self.history[-1][0]
                hours_elapsed = max(0.001, (end_time - start_time) / 3600)
                
                actual_kwh = (avg_watts * hours_elapsed) / 1000
                hourly_kwh = avg_watts / 1000
                
                if hours_elapsed < 1:
                    energy_table.add_row("Used (est.)", f"{hourly_kwh:.3f} kWh/hour")
                else:
                    energy_table.add_row("Used (actual)", f"{actual_kwh:.3f} kWh ({hours_elapsed:.1f}h)")
                    energy_table.add_row("Used (hourly)", f"{hourly_kwh:.3f} kWh/hour")
            else:
                kwh = avg_watts / 1000
                energy_table.add_row("Used (est.)", f"{kwh:.3f} kWh/hour")
        
        source_table = Table(box=box.ROUNDED, show_header=False, title_justify="center", title="Source", padding=(0, 1), width=table_width)
        source_table.add_column("Metric", style="bright_blue", width=col1_width)
        source_table.add_column("Value", width=col2_width)
        source_table.add_row("Data Provider", source)
        
        try:
            dt = datetime.fromtimestamp(timestamp)
            
            try:
                time_with_tz = dt.strftime("%H:%M:%S %Z")
            except ValueError:
                time_with_tz = dt.strftime("%H:%M:%S")
                
            try:
                local_dt = dt.astimezone()
                utc_offset = local_dt.strftime("%z")
                if utc_offset and len(utc_offset) >= 5:
                    formatted_offset = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"
                    if formatted_offset not in time_with_tz:
                        time_with_tz += f" ({formatted_offset})"
            except Exception:
                pass
                
        except Exception as e:
            time_with_tz = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
            logger.debug(f"Error formatting time with timezone: {e}")
            
        source_table.add_row("Last Update", time_with_tz)
        
        sections_grid.add_row(power_table)
        
        if current_table:
            sections_grid.add_row("")
            sections_grid.add_row(current_table)
            
        sections_grid.add_row("")
        sections_grid.add_row(energy_table)
        sections_grid.add_row("") 
        sections_grid.add_row(source_table)
        
        layout["stats"].update(
            Panel(
                sections_grid,
                title="Current Stats",
                subtitle="W = Watts | A = Amps",
                border_style=color
            )
        )
        
        layout["footer"].update(
            Panel(
                Text(f"Press Ctrl+C to stop monitoring", justify="center"),
                border_style="blue"
            )
        )
    
    def _update_chart(self, layout: Layout, show_current: bool = False) -> None:
        """Update the chart with historical data."""
        if not self.history:
            return
        

        try:
            terminal_width = os.get_terminal_size().columns
        except (OSError, AttributeError):
            terminal_width = 80
        

        chart_width = max(20, int(terminal_width * 0.7) - 15)
        
        main_chart = Table.grid(padding=0)
        main_chart.add_column("charts")
        
        bar_chart_section = Table.grid(padding=0)
        bar_chart_section.add_column("bar_chart")
        bar_chart_section.add_row("")
        
        bar_chart_title = Text("Last 10 updates | power usage", style="italic", justify="center")
        bar_chart_section.add_row(bar_chart_title)
        
        bar_chart = Table(box=None, padding=0, show_header=False)
        bar_chart.add_column("Time & Value", min_width=20)
        bar_chart.add_column("Chart", min_width=chart_width, no_wrap=True)
        
        if show_current and self.current_history:
            bar_chart.add_column("Current", min_width=chart_width, no_wrap=True)
        
        history_count = min(len(self.history), 30)
        recent_history = self.history[-history_count:]
        

        max_watts = self.max_Watts
        

        recent_current_history = []
        max_amperes = 0
        if show_current and self.current_history:
            recent_current_history = self.current_history[-history_count:]
            if recent_current_history:
                max_amperes = max(amps for _, amps in recent_current_history)
        

        display_count = 10
        if history_count >= display_count:

            indices = [history_count - 1 - i * (history_count // display_count) for i in range(display_count)]
            indices.sort()
            

            for i in indices:
                if i < len(recent_history):
                    timestamp, watts = recent_history[i]
                    

                    time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
                    value_display = f"{time_str} [{watts:.1f} W]"
                    

                    bar_width = max(1, int((watts / max_watts) * chart_width))
                    color = self.get_color_for_watts(watts)
                    power_bar = f"[{color}]{'█' * bar_width}[/{color}]"
                    

                    if show_current and i < len(recent_current_history):
                        _, amperes = recent_current_history[i]
                        current_bar_width = max(1, int((amperes / max_amperes) * chart_width)) if max_amperes > 0 else 0
                        current_bar = f"[blue]{'█' * current_bar_width}[/blue]"
                        bar_chart.add_row(value_display, power_bar, current_bar)
                    else:
                        bar_chart.add_row(value_display, power_bar)
        
        bar_chart_section.add_row(bar_chart)
        

        spacer = Text("", justify="center")
        

        line_chart_section = Table.grid(padding=0)
        line_chart_section.add_column("line_chart")
        

        line_chart_title = Text("Last 30 updates", style="italic", justify="center")
        line_chart_section.add_row(line_chart_title)
        

        line_chart = self._create_line_chart(chart_width)
        line_chart_section.add_row(line_chart)
        

        main_chart.add_row(bar_chart_section)
        main_chart.add_row(spacer)
        main_chart.add_row(spacer)
        main_chart.add_row(line_chart_section)
        

        layout["chart"].update(
            Panel(
                main_chart,
                title="Power Usage History",
                border_style="green"
            )
        )
    
    def _create_line_chart(self, width: int) -> Table:
        """Create a simple ASCII line chart of recent history."""
        if not self.history or len(self.history) < 2:
            return Text("Not enough data for line chart")
        
        points = min(len(self.history), 30)
        history = self.history[-points:]
        
        values = [watts for _, watts in history]
        actual_max = max(values)
        actual_min = min(values)
        
        padding_factor = 0.1
        value_padding = max(1, (actual_max - actual_min) * padding_factor)
        
        min_value = max(0, actual_min - value_padding)
        max_value = actual_max + value_padding
        
        value_range = max_value - min_value
        if value_range < 1:
            value_range = 1
        
        height = 7
        chart_height = height
        
        y_label_width = 14
        
        grid = [[' ' for _ in range(width)] for _ in range(chart_height + 1)]
        
        for i in range(points):
            _, value = history[i]
            
            y_pos = chart_height - 1 - int((value - min_value) / value_range * (chart_height - 1))
            y_pos = max(0, min(chart_height - 1, y_pos))
            
            x_pos = int(i / (points - 1) * (width - 1))
            
            grid[y_pos][x_pos] = '●'
        

        for x in range(width):
            grid[chart_height][x] = '─'
            

        for y in range(chart_height + 1):
            if y < chart_height:
                grid[y][0] = '│'
            else:
                grid[y][0] = '└'
        

        chart_lines = []
        for i, row in enumerate(grid):
            if i < chart_height:

                label_value = max_value - (i / (chart_height - 1)) * value_range

                watts_label = f"{label_value:4.0f} Watts"

                y_label = f"{watts_label:>{y_label_width-1}}"
                line = f"{y_label}{''.join(row)}"
                chart_lines.append(line)
            else:

                line = f"{' ' * (y_label_width-1)}{''.join(row)}"
                chart_lines.append(line)
        

        if len(history) > 0:
            start_time = datetime.fromtimestamp(history[0][0]).strftime("%H:%M")
            end_time = datetime.fromtimestamp(history[-1][0]).strftime("%H:%M")
            mid_index = len(history) // 2
            mid_time = datetime.fromtimestamp(history[mid_index][0]).strftime("%H:%M")
            
            mid_pos = width // 2
            time_markers = f"{' ' * y_label_width}{start_time}{' ' * (mid_pos - len(start_time) - 1)}{mid_time}{' ' * (width - mid_pos - len(mid_time) - len(end_time) - 1)}{end_time}"
            chart_lines.append(time_markers)
        

        line_chart_table = Table(box=None, padding=0, show_header=False)
        line_chart_table.add_column("chart", no_wrap=True)
        for line in chart_lines:
            line_chart_table.add_row(line)
        
        return line_chart_table
    
    def display_continuous_usage(
        self, 
        get_power_callback, 
        get_power_trend_callback, 
        source: str, 
        interval: int,
        get_current_callback=None,
        get_current_trend_callback=None,
        show_current: bool = False,
        raw: bool = False
    ) -> None:
        """Display continuous power usage with updates at specified intervals.
        
        Args:
            get_power_callback: Callback function to get current power usage
            get_power_trend_callback: Callback function to get power usage trend
            source: Source of the power data (e.g., "Home Assistant", "Kasa Direct")
            interval: Update interval in seconds
            get_current_callback: Optional callback function to get current amperage
            get_current_trend_callback: Optional callback function to get current amperage trend
            show_current: Whether to show current (amperage) data
            raw: Whether to output only raw values for scripting use
        """
        
        if raw:
            try:
                while True:
                    watts = get_power_callback()
                    if watts is not None:
                        sys.stdout.write(f"{watts:.0f}\n")
                        sys.stdout.flush()
                    time.sleep(interval)
            except KeyboardInterrupt:
                return
            return
            
        layout = self._create_live_display()
        

        last_stat_update = 0
        last_chart_update = 0
        


        if interval <= 1:
            refresh_per_second = 4
        elif interval <= 5:
            refresh_per_second = 2
        else:
            refresh_per_second = 1
        
        with Live(layout, refresh_per_second=refresh_per_second, screen=True) as live:
            try:
                while True:
                    current_time = time.time()
                    

                    if current_time - last_stat_update >= interval:

                        watts = get_power_callback()
                        amperes = get_current_callback() if show_current and get_current_callback else None
                        
                        if watts is not None:
                            self.add_to_history(watts)
                            

                            power_trend = get_power_trend_callback(5) if get_power_trend_callback else None
                            

                            current_trend = None
                            if amperes is not None and get_current_trend_callback:
                                current_trend = get_current_trend_callback(5)
                            

                            self._update_live_display(layout, watts, power_trend, source, current_time, amperes, current_trend, show_current)
                            last_stat_update = current_time
                    

                    if current_time - last_chart_update >= max(interval * 2, 5):
                        self._update_chart(layout, show_current)
                        last_chart_update = current_time
                    


                    sleep_time = 1.0 / refresh_per_second
                    time.sleep(sleep_time)
                    
            except KeyboardInterrupt:

                pass
    
    def display_stats(self, title: str, stats: Dict[str, Any]) -> None:
        """Display a stats panel with key-value pairs.
        
        Args:
            title: Title for the panel
            stats: Dictionary of statistics to display
        """
        stats_table = Table(show_header=False, padding=(0, 1))
        stats_table.add_column("Stat")
        stats_table.add_column("Value")
        
        for key, value in stats.items():
            formatted_key = key.replace("_", " ").title()
            stats_table.add_row(formatted_key, str(value))
        
        panel = Panel(
            stats_table,
            title=title,
            border_style="blue"
        )
        
        self.console.print(panel)
    
    def show_error(self, title: str, message: str) -> None:
        """Display an error message.
        
        Args:
            title: Error title
            message: Error message
        """
        panel = Panel(
            Text(message, style="bold red"),
            title=title,
            border_style="red"
        )
        
        self.console.print(panel)
        
    def show_success(self, title: str, message: str) -> None:
        """Display a success message.
        
        Args:
            title: Success title
            message: Success message
        """
        panel = Panel(
            Text(message, style="bold green"),
            title=title,
            border_style="green"
        )
        
        self.console.print(panel)
        
    def get_term_size(self) -> Tuple[int, int]:
        """Get the terminal size.
        
        Returns:
            Tuple of (columns, rows)
        """
        try:
            columns, rows = os.get_terminal_size(0)
            return columns, rows
        except (OSError, AttributeError):
            return 80, 24
