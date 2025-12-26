#!/bin/bash
set -e  # Exit on error

# ============================================
# CanvasNote Snap Publishing Script
# ============================================

# === CONFIGURATION (Environment Variables) ===
export SNAP_NAME="canvasnote"
export SNAP_VERSION="1.0"
export SNAP_CHANNEL="stable"  # Options: stable, candidate, beta, edge
export SNAP_ARCHITECTURES="amd64"
export PUBLISH_TIMEOUT=600  # 10 minutes

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================
# Helper Functions
# ============================================

print_step() {
    echo -e "${BLUE}==>${NC} ${1}"
}

print_success() {
    echo -e "${GREEN}✓${NC} ${1}"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} ${1}"
}

print_error() {
    echo -e "${RED}✗${NC} ${1}"
}

# ============================================
# Main Publishing Flow
# ============================================

main() {
    print_step "Starting CanvasNote Snap Publishing Process"
    echo ""
    
    # Check if snapcraft is installed
    if ! command -v snapcraft &> /dev/null; then
        print_error "snapcraft is not installed. Install with: sudo snap install snapcraft --classic"
        exit 1
    fi
    
    # Check login status
    print_step "Checking Snapcraft login status..."
    if snapcraft whoami &> /dev/null; then
        SNAPCRAFT_USER=$(snapcraft whoami | grep "email:" | awk '{print $2}')
        print_success "Already logged in as: $SNAPCRAFT_USER"
    else
        print_warning "Not logged in. Please run: snapcraft login"
        exit 1
    fi
    echo ""
    
    # Check if snap name is registered
    print_step "Checking snap name registration..."
    if snapcraft list-registered 2>&1 | grep -q "$SNAP_NAME"; then
        print_success "Snap name '$SNAP_NAME' is already registered"
    else
        print_warning "Snap name '$SNAP_NAME' is not registered"
        echo ""
        read -p "Do you want to register '$SNAP_NAME' now? (y/n) " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_step "Registering snap name..."
            if snapcraft register "$SNAP_NAME"; then
                print_success "Successfully registered '$SNAP_NAME'"
            else
                print_error "Failed to register snap name. It may already be taken."
                exit 1
            fi
        else
            print_error "Cannot publish without registering the snap name first"
            exit 1
        fi
    fi
    echo ""
    
    # Clean previous builds
    print_step "Cleaning previous builds..."
    snapcraft clean || true
    rm -f "${SNAP_NAME}_${SNAP_VERSION}_${SNAP_ARCHITECTURES}.snap"
    print_success "Cleaned previous builds"
    echo ""
    
    # Build the snap
    print_step "Building snap package..."
    if snapcraft pack; then
        print_success "Snap built successfully"
    else
        print_error "Failed to build snap"
        exit 1
    fi
    echo ""
    
    # Verify snap file exists
    SNAP_FILE="${SNAP_NAME}_${SNAP_VERSION}_${SNAP_ARCHITECTURES}.snap"
    if [ ! -f "$SNAP_FILE" ]; then
        print_error "Snap file not found: $SNAP_FILE"
        exit 1
    fi
    
    SNAP_SIZE=$(du -h "$SNAP_FILE" | awk '{print $1}')
    print_success "Snap file ready: $SNAP_FILE ($SNAP_SIZE)"
    echo ""
    
    # Upload to Snap Store
    print_step "Uploading to Snap Store..."
    print_warning "This may take several minutes..."
    
    if UPLOAD_OUTPUT=$(snapcraft upload "$SNAP_FILE" 2>&1); then
        print_success "Upload successful!"
        
        # Extract revision number from upload output
        REVISION=$(echo "$UPLOAD_OUTPUT" | grep -oP "Revision \K[0-9]+" | head -1)
        
        if [ -n "$REVISION" ]; then
            print_success "Assigned revision: $REVISION"
        else
            print_warning "Could not extract revision number from output"
            echo "$UPLOAD_OUTPUT"
            echo ""
            read -p "Enter the revision number manually: " REVISION
        fi
    else
        print_error "Upload failed!"
        echo "$UPLOAD_OUTPUT"
        exit 1
    fi
    echo ""
    
    # Release to channel
    print_step "Releasing to '$SNAP_CHANNEL' channel..."
    
    if [ -z "$REVISION" ]; then
        print_error "Revision number is required for release"
        exit 1
    fi
    
    if snapcraft release "$SNAP_NAME" "$REVISION" "$SNAP_CHANNEL"; then
        print_success "Successfully released to '$SNAP_CHANNEL' channel!"
    else
        print_error "Failed to release snap"
        exit 1
    fi
    echo ""
    
    # Show final status
    print_step "Publication Summary:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Snap Name:     $SNAP_NAME"
    echo "  Version:       $SNAP_VERSION"
    echo "  Revision:      $REVISION"
    echo "  Channel:       $SNAP_CHANNEL"
    echo "  Architecture:  $SNAP_ARCHITECTURES"
    echo "  File Size:     $SNAP_SIZE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    print_success "✨ CanvasNote published successfully!"
    echo ""
    echo "Users can now install with:"
    echo "  ${GREEN}sudo snap install $SNAP_NAME${NC}"
    echo ""
    echo "View your snap at:"
    echo "  ${BLUE}https://snapcraft.io/$SNAP_NAME${NC}"
    echo ""
}

# ============================================
# Script Entry Point
# ============================================

# Check if running from correct directory
if [ ! -f "snapcraft.yaml" ]; then
    print_error "snapcraft.yaml not found. Please run this script from the project root."
    exit 1
fi

# Run main function
main "$@"
