#!/usr/bin/env python3
"""
WattWise - A CLI tool for monitoring power usage of devices plugged into smart plugs.
"""

import os
import sys

# Add the current directory to the Python path to find the wattwise package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wattwise.cli import main

if __name__ == "__main__":
    main() 
