#!/bin/bash
# Notes2in1 Snap Test Script
# This script rebuilds and installs the snap for local testing
# Run this whenever you want to test changes to the app

set -e  # Exit on error

echo "========================================="
echo "  Notes2in1 Snap Build & Test Script"
echo "========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if snapcraft is installed
if ! command -v snapcraft &> /dev/null; then
    echo -e "${RED}Error: snapcraft is not installed${NC}"
    echo "Install it with: sudo snap install snapcraft --classic"
    exit 1
fi

# Kill any running instances
echo -e "${BLUE}Stopping any running instances...${NC}"
pkill -f "notes2in1" 2>/dev/null || true
sleep 1

echo -e "${BLUE}Step 1: Cleaning previous builds...${NC}"
snapcraft clean 2>/dev/null || true
rm -f notes2in1_*.snap

echo -e "${BLUE}Step 2: Building snap package...${NC}"
echo "This may take a few minutes on first build..."
snapcraft --verbose

# Find the generated snap file
SNAP_FILE=$(ls -t notes2in1_*.snap 2>/dev/null | head -1)

if [ -z "$SNAP_FILE" ]; then
    echo -e "${RED}Error: Snap file not found!${NC}"
    exit 1
fi

echo -e "${GREEN}Built: $SNAP_FILE${NC}"

echo -e "${BLUE}Step 3: Removing old installation (if exists)...${NC}"
sudo snap remove notes2in1 2>/dev/null || true

echo -e "${BLUE}Step 4: Installing snap package...${NC}"
sudo snap install --dangerous "$SNAP_FILE"

echo -e "${BLUE}Step 5: Connecting interfaces...${NC}"
sudo snap connect notes2in1:home
sudo snap connect notes2in1:removable-media 2>/dev/null || echo "removable-media interface not connected (optional)"
sudo snap connect notes2in1:gsettings 2>/dev/null || true

echo ""
echo -e "${GREEN}========================================="
echo "  ✅ Snap installed successfully!"
echo "=========================================${NC}"
echo ""
echo -e "Snap package: ${GREEN}$SNAP_FILE${NC}"
echo ""
echo "📋 Quick Commands:"
echo -e "  Run app:        ${YELLOW}snap run notes2in1${NC}"
echo -e "  View logs:      ${YELLOW}snap logs notes2in1 -f${NC}"
echo -e "  App info:       ${YELLOW}snap info notes2in1${NC}"
echo -e "  Connected plugs:${YELLOW}snap connections notes2in1${NC}"
echo -e "  Uninstall:      ${YELLOW}sudo snap remove notes2in1${NC}"
echo ""
echo "📁 App data location: ~/snap/notes2in1/current/"
echo ""
echo -e "${BLUE}Starting Notes2in1...${NC}"
echo ""
snap run notes2in1
