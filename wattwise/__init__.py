"""
WattWise - A CLI tool for monitoring power usage of devices connected to smart plugs.

This package allows users to monitor power consumption in real-time
from the command line, either directly from a TP-Link Kasa smart plug or
through an existing Home Assistant setup.
"""

__version__ = "0.1.3"
__author__ = "Naveen"
__email__ = "hey@naveen.ing"

import logging


logging.getLogger(__name__).addHandler(logging.NullHandler())

from . import config
from . import homeassistant
from . import kasa
from . import display
from . import cli


def main():
    """Entry point for the application."""
    cli.main()
