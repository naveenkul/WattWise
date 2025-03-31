#!/bin/bash

# WattWise Clean Uninstall Script
# This script removes all WattWise Docker resources and configuration

echo "WattWise Clean Uninstall"
echo "======================="
echo "This script will completely remove WattWise from your system, including:"
echo "- All WattWise Docker containers"
echo "- The WattWise Docker image"
echo "- All WattWise configuration files and data"
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read

# Stop and remove any running WattWise containers
echo "Stopping and removing any running WattWise containers..."
WATTWISE_CONTAINERS=$(docker ps -a --format "{{.Names}}" | grep wattwise)
if [ -n "$WATTWISE_CONTAINERS" ]; then
  echo "Removing WattWise-related containers..."
  for CONTAINER in $WATTWISE_CONTAINERS; do
    docker stop "$CONTAINER" 2>/dev/null
    docker rm "$CONTAINER"
    echo "✓ Removed $CONTAINER"
  done
else
  echo "✓ No WattWise-related containers found"
fi

# Remove the wattwise Docker image
echo "Removing WattWise Docker image..."
if docker images --format "{{.Repository}}" | grep -q "wattwise"; then
  docker rmi wattwise
  echo "✓ Removed wattwise Docker image"
else
  echo "✓ No wattwise Docker image found"
fi

# Remove configuration and data files
echo "Removing WattWise configuration and data files..."
if [ -d ~/.config/wattwise ]; then
  rm -rf ~/.config/wattwise
  echo "✓ Removed configuration directory (~/.config/wattwise)"
else
  echo "✓ No configuration directory found"
fi

if [ -d ~/.local/share/wattwise ]; then
  rm -rf ~/.local/share/wattwise
  echo "✓ Removed data directory (~/.local/share/wattwise)"
else
  echo "✓ No data directory found"
fi

# Check for pip installation and offer to uninstall
if command -v pip &> /dev/null && pip list | grep -q "wattwise"; then
  echo ""
  echo "WattWise is also installed via pip. Do you want to uninstall it? (y/n)"
  read UNINSTALL_PIP
  if [[ "$UNINSTALL_PIP" == "y" || "$UNINSTALL_PIP" == "Y" ]]; then
    pip uninstall -y wattwise
    echo "✓ Uninstalled WattWise pip package"
  fi
fi

echo ""
echo "WattWise has been completely removed from your system."
echo "Uninstallation complete!" 