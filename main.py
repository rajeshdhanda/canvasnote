#!/usr/bin/env python3
"""Launch script for Notes2in1."""
import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging - skip file logging if running as snap
is_snap = os.getenv('SNAP') is not None
handlers = []

if not is_snap:
    # Only create log files for local development
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / f"notes2in1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    handlers.append(logging.FileHandler(log_file))
    print(f"Logging to: {log_file}")

# Always log to stdout
handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=handlers
)

from notes2in1.app import main

if __name__ == '__main__':
    sys.exit(main())
