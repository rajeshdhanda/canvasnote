#!/bin/bash

###############################################################################
# Notes2in1 Development Script
# Automated testing and development launcher
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="notes2in1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/notes2in1_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="${SCRIPT_DIR}/.notes2in1.pid"
USE_SYSTEM_PYTHON=true  # Use system Python with GTK packages

###############################################################################
# Helper Functions
###############################################################################

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "${LOG_FILE}"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "${LOG_FILE}"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "${LOG_FILE}"
}

log_info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "${LOG_FILE}"
}

###############################################################################
# Cleanup Functions
###############################################################################

cleanup_previous_run() {
    log "🧹 Cleaning up previous run..."
    
    # Stop running instances
    if [ -f "${PID_FILE}" ]; then
        OLD_PID=$(cat "${PID_FILE}")
        if ps -p "${OLD_PID}" > /dev/null 2>&1; then
            log_info "Stopping previous instance (PID: ${OLD_PID})..."
            kill "${OLD_PID}" 2>/dev/null || true
            sleep 1
            
            # Force kill if still running
            if ps -p "${OLD_PID}" > /dev/null 2>&1; then
                log_warning "Force killing previous instance..."
                kill -9 "${OLD_PID}" 2>/dev/null || true
            fi
        fi
        rm -f "${PID_FILE}"
    fi
    
    # Also check for any running Python process with our app name
    pkill -f "python.*notes2in1" || true
    sleep 0.5
    
    # Clear old logs (keep last 10)
    if [ -d "${LOG_DIR}" ]; then
        log_info "Cleaning old log files..."
        ls -t "${LOG_DIR}"/notes2in1_*.log 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
    fi
    
    log "✅ Cleanup complete"
}

###############################################################################
# Environment Setup
###############################################################################

setup_environment() {
    log "🔧 Setting up environment..."
    
    # Create log directory
    mkdir -p "${LOG_DIR}"
    
    # Use system Python (no venv needed for GTK apps)
    log_info "Using system Python with GTK packages"
    
    # Verify Python version
    PYTHON_VERSION=$(python3 --version)
    log_info "Python version: ${PYTHON_VERSION}"
    
    # Export environment variables for debugging
    export G_MESSAGES_DEBUG=all
    # export GTK_DEBUG=interactive  # Uncomment for GTK inspector
    export PYTHONUNBUFFERED=1
    
    # Enable evdev debug logging
    export EVDEV_DEBUG=1
    
    log "✅ Environment ready"
}

###############################################################################
# Dependency Check
###############################################################################

check_dependencies() {
    log "📦 Checking dependencies..."
    
    # Check if requirements are installed
    python3 << 'EOF' >> "${LOG_FILE}" 2>&1
import sys

required_modules = [
    'gi',
    'cairo',
    'evdev',
    'PIL',
    'reportlab'
]

missing = []
for module in required_modules:
    try:
        __import__(module)
        print(f"✓ {module}")
    except ImportError:
        print(f"✗ {module} (missing)")
        missing.append(module)

if missing:
    print(f"\nMissing modules: {', '.join(missing)}")
    print("Install with: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-evdev python3-pil python3-reportlab")
    sys.exit(1)
else:
    print("\n✓ All dependencies installed")
    sys.exit(0)
EOF
    
    if [ $? -ne 0 ]; then
        log_error "Missing dependencies!"
        log_error "Please run: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-evdev python3-pil python3-reportlab"
        exit 1
    fi
    
    log "✅ Dependencies satisfied"
}

###############################################################################
# Input Device Detection
###############################################################################

detect_input_devices() {
    log "🖊️  Detecting input devices..."
    
    # List input devices with evdev access
    python3 << 'EOF' >> "${LOG_FILE}" 2>&1
import sys
try:
    from evdev import InputDevice, list_devices, ecodes
    
    print("\nInput Devices:")
    print("-" * 80)
    
    devices = [InputDevice(path) for path in list_devices()]
    
    if not devices:
        print("⚠️  No input devices found!")
        print("This might be a permissions issue.")
        print("Try running with sudo or adding user to 'input' group:")
        print("  sudo usermod -a -G input $USER")
        print("  (logout and login required)")
    
    stylus_found = False
    touch_found = False
    
    for device in devices:
        print(f"\n📱 {device.name}")
        print(f"   Path: {device.path}")
        print(f"   Phys: {device.phys}")
        
        caps = device.capabilities(verbose=False)
        
        # Check for stylus
        if ecodes.EV_KEY in caps:
            keys = caps[ecodes.EV_KEY]
            stylus_buttons = [
                ecodes.BTN_TOOL_PEN,
                ecodes.BTN_TOOL_RUBBER,
                ecodes.BTN_STYLUS,
            ]
            
            if any(btn in keys for btn in stylus_buttons):
                print(f"   Type: ✏️  STYLUS")
                stylus_found = True
        
        # Check for touch
        if ecodes.EV_ABS in caps:
            abs_caps = caps[ecodes.EV_ABS]
            if ecodes.ABS_MT_POSITION_X in abs_caps or ecodes.ABS_MT_SLOT in abs_caps:
                if not stylus_found or device.name not in ['pen', 'stylus']:
                    print(f"   Type: 👆 TOUCH")
                    touch_found = True
    
    print("\n" + "-" * 80)
    print(f"Summary: Stylus={'✓' if stylus_found else '✗'}, Touch={'✓' if touch_found else '✗'}")
    
except ImportError:
    print("⚠️  evdev module not available - palm rejection will not work")
except PermissionError as e:
    print(f"⚠️  Permission denied accessing input devices: {e}")
    print("Run with sudo or add user to 'input' group")
EOF
    
    log "✅ Device detection complete"
}

###############################################################################
# Launch Application
###############################################################################

launch_app() {
    log "🚀 Launching Notes2in1..."
    log_info "Log file: ${LOG_FILE}"
    log_info "Working directory: ${SCRIPT_DIR}"
    
    # Change to script directory
    cd "${SCRIPT_DIR}"
    
    # Launch the application with logging (use system Python)
    /usr/bin/python3 -u main.py 2>&1 | tee -a "${LOG_FILE}" &
    APP_PID=$!
    
    # Save PID
    echo "${APP_PID}" > "${PID_FILE}"
    
    log "✅ Application started (PID: ${APP_PID})"
    log_info "Monitoring logs... Press Ctrl+C to stop"
    
    # Wait for the application
    wait "${APP_PID}"
    EXIT_CODE=$?
    
    log "Application exited with code: ${EXIT_CODE}"
    rm -f "${PID_FILE}"
    
    return ${EXIT_CODE}
}

###############################################################################
# Log Analysis
###############################################################################

analyze_logs() {
    log "📊 Analyzing logs..."
    
    if [ ! -f "${LOG_FILE}" ]; then
        log_warning "No log file found"
        return
    fi
    
    echo ""
    echo "════════════════════════════════════════════════════════════════════════════════"
    echo "                              LOG ANALYSIS"
    echo "════════════════════════════════════════════════════════════════════════════════"
    echo ""
    
    # Count errors
    ERROR_COUNT=$(grep -c "ERROR" "${LOG_FILE}" || echo "0")
    WARNING_COUNT=$(grep -c "WARNING" "${LOG_FILE}" || echo "0")
    
    echo "📈 Statistics:"
    echo "   Errors:   ${ERROR_COUNT}"
    echo "   Warnings: ${WARNING_COUNT}"
    echo ""
    
    # Show stylus events
    echo "✏️  Stylus Events:"
    grep -i "stylus" "${LOG_FILE}" | tail -n 20 || echo "   No stylus events found"
    echo ""
    
    # Show touch events
    echo "👆 Touch Events:"
    grep -i "touch" "${LOG_FILE}" | tail -n 20 || echo "   No touch events found"
    echo ""
    
    # Show palm rejection events
    echo "🖐️  Palm Rejection:"
    grep -i "palm\|disabled\|enabled" "${LOG_FILE}" | tail -n 20 || echo "   No palm rejection events found"
    echo ""
    
    # Show errors if any
    if [ "${ERROR_COUNT}" -gt 0 ]; then
        echo "❌ Errors:"
        grep "ERROR" "${LOG_FILE}" | tail -n 10
        echo ""
    fi
    
    # Show warnings if any
    if [ "${WARNING_COUNT}" -gt 0 ]; then
        echo "⚠️  Warnings:"
        grep "WARNING" "${LOG_FILE}" | tail -n 10
        echo ""
    fi
    
    echo "════════════════════════════════════════════════════════════════════════════════"
    echo ""
    echo "Full log available at: ${LOG_FILE}"
    echo ""
}

###############################################################################
# Main Execution
###############################################################################

main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║                        Notes2in1 Development Launcher                      ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Trap Ctrl+C for clean shutdown
    trap cleanup_on_exit INT TERM
    
    # Execute steps
    cleanup_previous_run
    setup_environment
    check_dependencies
    detect_input_devices
    
    echo ""
    echo "────────────────────────────────────────────────────────────────────────────────"
    echo ""
    
    # Launch app
    launch_app
    EXIT_CODE=$?
    
    echo ""
    echo "────────────────────────────────────────────────────────────────────────────────"
    echo ""
    
    # Analyze logs
    analyze_logs
    
    if [ ${EXIT_CODE} -eq 0 ]; then
        log "✅ Session completed successfully"
    else
        log_error "Session completed with errors (exit code: ${EXIT_CODE})"
    fi
    
    exit ${EXIT_CODE}
}

cleanup_on_exit() {
    echo ""
    log_warning "Interrupted by user"
    
    if [ -f "${PID_FILE}" ]; then
        PID=$(cat "${PID_FILE}")
        if ps -p "${PID}" > /dev/null 2>&1; then
            log_info "Stopping application..."
            kill "${PID}" 2>/dev/null || true
            sleep 1
            kill -9 "${PID}" 2>/dev/null || true
        fi
        rm -f "${PID_FILE}"
    fi
    
    analyze_logs
    exit 130
}

# Run main
main "$@"
