"""Main application entry point."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
import logging
import sys
from pathlib import Path

from .ui.main_window import MainWindow

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


class CanvasNoteApp(Adw.Application):
    """Main application class."""
    
    def __init__(self):
        super().__init__(
            application_id='com.canvasnote.app',
            flags=Gio.ApplicationFlags.NON_UNIQUE
        )
        self.window = None
        logger.info("CanvasNote application initialized")
    
    def do_activate(self):
        """Activate the application."""
        if not self.window:
            self.window = MainWindow(self)
        
        self.window.present()
        logger.info("Application window presented")
    
    def do_shutdown(self):
        """Shutdown the application."""
        logger.info("Application shutting down")
        Adw.Application.do_shutdown(self)


def main():
    """Main entry point."""
    logger.info("Starting CanvasNote application")
    
    # Check for required dependencies
    try:
        import cairo
        import evdev
        logger.info("All dependencies available")
    except ImportError as e:
        logger.warning(f"Missing dependency: {e}")
    
    app = CanvasNoteApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
