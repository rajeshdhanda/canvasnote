"""Main application window with Microsoft Whiteboard-style design."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio, Pango
import cairo
import logging
import os
from pathlib import Path

from ..core.canvas import DrawingCanvas
from ..core.stroke import PenType, DrawingDocument, ShapeType
from ..core.input_handler import InputHandler
from ..core.notes_manager import NotesLibrary

logger = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Main application window with Microsoft Whiteboard-style design."""
    
    def __init__(self, app):
        super().__init__(application=app)
        
        self.app = app
        self.current_file = None
        self.current_subject = None
        self.current_note = None
        self.autosave_timeout = None
        
        # Notes library
        self.notes_library = NotesLibrary()
        
        # Set up window
        self.set_title("CanvasNote")
        self.set_default_size(1400, 900)
        
        # Show window controls (minimize, maximize, close buttons)
        self.set_show_menubar(False)
        
        # Tool buttons for visual feedback
        self.tool_buttons = {}
        self.active_tool_button = None
        
        # Sidebar state
        self.sidebar_visible = False
        self.sidebar_width = 320  # Wider for better readability
        
        # Toolbar position: 'top', 'bottom', 'left', 'right'
        self.toolbar_position = 'top'
        
        # Input handler for palm rejection
        self.input_handler = InputHandler()
        
        # Create canvas
        self.canvas = DrawingCanvas()
        
        # Build UI
        self.setup_ui()
        
        # Set up keyboard shortcuts
        self.setup_keyboard_shortcuts()
        
        # Start input monitoring
        self.input_handler.on_stylus_state_change = self.on_stylus_state_changed
        GLib.timeout_add(500, self.start_input_monitoring)
        
        # Set up canvas callback for page changes
        self.canvas.on_page_changed_callback = self.update_page_label
        
        # Set up autosave
        self.setup_autosave()
        
        # Give canvas input focus after window is shown
        GLib.idle_add(self.canvas.grab_focus)
        
        logger.info("MainWindow initialized")
    
    def get_asset_path(self, filename):
        """Get the full path to an asset file."""
        assets_dir = Path(__file__).parent.parent / "assets"
        return str(assets_dir / filename)
    
    def create_image_button(self, icon_filename, size=24):
        """Create a button with a PNG image icon."""
        image = Gtk.Image.new_from_file(self.get_asset_path(icon_filename))
        image.set_pixel_size(size)
        return image
    
    def start_input_monitoring(self):
        """Start input monitoring after a short delay."""
        try:
            success = self.input_handler.start_monitoring()
            if success:
                logger.info("Input monitoring started successfully")
            else:
                logger.warning("Failed to start input monitoring")
        except Exception as e:
            logger.error(f"Error starting input monitoring: {e}")
        return False  # Don't repeat
    
    def on_stylus_state_changed(self, stylus_active: bool):
        """Handle stylus state changes."""
        # Update visual indicator when stylus is detected
        if stylus_active:
            self.status_label.set_text("✏️ Stylus Active")
        else:
            self.status_label.set_text("Ready")
        logger.info(f"Stylus: {'active' if stylus_active else 'inactive'}")
    
    def setup_ui(self):
        """Build the user interface with Microsoft Whiteboard-style design."""
        # Main overlay container for sidebar
        overlay = Gtk.Overlay()
        
        # Main container with header bar at top
        main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Create a minimal header bar with window controls
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)  # Show minimize, maximize, close
        header.set_show_start_title_buttons(False)
        header.set_title_widget(Gtk.Label(label="CanvasNote"))
        
        # Make header bar minimal/compact
        header.add_css_class("flat")
        
        main_container.append(header)
        
        # Main content area - will be reconfigured based on toolbar position
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Compact toolbar with minimal design
        self.toolbar = self.create_compact_toolbar()
        
        # Wrap toolbar in scrolled window for vertical positioning
        self.toolbar_scroll = Gtk.ScrolledWindow()
        self.toolbar_scroll.set_child(self.toolbar)
        self.toolbar_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.toolbar_scroll.set_propagate_natural_width(True)
        self.toolbar_scroll.set_propagate_natural_height(True)
        
        self.toolbar_revealer = Gtk.Revealer()
        self.toolbar_revealer.set_child(self.toolbar_scroll)
        self.toolbar_revealer.set_reveal_child(True)
        
        # Store menu for access via keyboard shortcut or toolbar button
        self.menu = Gio.Menu()
        
        # File operations
        file_section = Gio.Menu()
        file_section.append("Export PNG...", "app.export_png")
        file_section.append("Export PDF...", "app.export_pdf")
        self.menu.append_section(None, file_section)
        
        # View options
        view_section = Gio.Menu()
        view_section.append("Toggle Dark Mode", "app.toggle_dark")
        view_section.append("Fullscreen", "app.fullscreen")
        view_section.append("Device Info", "app.device_info")
        self.menu.append_section(None, view_section)
        
        # Toolbar position options
        toolbar_section = Gio.Menu()
        toolbar_section.append("Toolbar: Top", "app.toolbar_top")
        toolbar_section.append("Toolbar: Bottom", "app.toolbar_bottom")
        toolbar_section.append("Toolbar: Left", "app.toolbar_left")
        toolbar_section.append("Toolbar: Right", "app.toolbar_right")
        self.menu.append_section("Toolbar Position", toolbar_section)
        
        # Canvas container that shifts when sidebar opens
        self.canvas_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        
        # Canvas in scrolled window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_child(self.canvas)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_hexpand(True)
        
        # Monitor scroll position to update page indicator
        vadjustment = self.scrolled.get_vadjustment()
        vadjustment.connect('value-changed', self.on_scroll_changed)
        
        self.canvas_box.append(self.scrolled)
        
        # Minimal status bar
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.status_box.set_margin_start(12)
        self.status_box.set_margin_end(12)
        self.status_box.set_margin_top(4)
        self.status_box.set_margin_bottom(4)
        self.status_box.add_css_class("statusbar")
        
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("caption")
        self.status_box.append(self.status_label)
        
        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.status_box.append(spacer)
        
        # Palm rejection status indicator
        self.palm_status_label = Gtk.Label(label="🖐️ Palm Rejection: ON")
        self.palm_status_label.set_halign(Gtk.Align.END)
        self.palm_status_label.add_css_class("caption")
        self.status_box.append(self.palm_status_label)
        
        # Configure toolbar position
        self.update_toolbar_position()
        
        # Add main content to overlay
        overlay.set_child(self.main_box)
        
        # Create collapsible sidebar
        self.sidebar = self.create_sidebar()
        self.sidebar_revealer = Gtk.Revealer()
        self.sidebar_revealer.set_child(self.sidebar)
        self.sidebar_revealer.set_reveal_child(False)
        self.sidebar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        self.sidebar_revealer.set_transition_duration(250)
        self.sidebar_revealer.set_halign(Gtk.Align.START)
        self.sidebar_revealer.set_valign(Gtk.Align.FILL)
        
        overlay.add_overlay(self.sidebar_revealer)
        
        # Add overlay to main container
        main_container.append(overlay)
        
        self.set_content(main_container)
        
        # Connect menu to menu button now that menu is created
        if hasattr(self, 'menu_button'):
            self.menu_button.set_menu_model(self.menu)
        
        # Apply custom CSS for clean design
        self.apply_custom_css()
        
        # Set up actions
        self.setup_actions()
        
        # Set default tool to Pen
        GLib.idle_add(self.set_pen_type, PenType.PEN)
    
    def create_compact_toolbar(self):
        """Create compact Microsoft Whiteboard-style toolbar."""
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_start(16)
        toolbar.set_margin_end(16)
        toolbar.set_margin_top(2)
        toolbar.set_margin_bottom(2)
        toolbar.set_halign(Gtk.Align.CENTER)
        toolbar.add_css_class("toolbar")
        
        # Notes toggle button (first in toolbar)
        self.notes_button = Gtk.Button()
        self.notes_button.set_child(self.create_image_button("show-notes.png", 20))
        self.notes_button.set_size_request(36, 36)
        self.notes_button.set_tooltip_text("Notes Library")
        self.notes_button.connect('clicked', self.toggle_sidebar)
        self.notes_button.add_css_class("compact-tool")
        toolbar.append(self.notes_button)
        
        # Separator after notes button
        sep_notes = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep_notes.set_margin_start(6)
        sep_notes.set_margin_end(6)
        toolbar.append(sep_notes)
        
        # Tool buttons - compact icon-only, each independent
        pen_btn = Gtk.Button()
        pen_btn.set_child(self.create_image_button("pen.png", 20))
        pen_btn.set_size_request(36, 36)
        pen_btn.set_tooltip_text("Pen")
        pen_btn.connect('clicked', lambda _: self.set_pen_type(PenType.PEN))
        pen_btn.add_css_class("circular")
        pen_btn.add_css_class("compact-tool")
        self.tool_buttons[PenType.PEN] = pen_btn
        toolbar.append(pen_btn)
        
        pencil_btn = Gtk.Button()
        pencil_btn.set_child(self.create_image_button("pencil.png", 20))
        pencil_btn.set_size_request(36, 36)
        pencil_btn.set_tooltip_text("Pencil")
        pencil_btn.connect('clicked', lambda _: self.set_pen_type(PenType.PENCIL))
        pencil_btn.add_css_class("circular")
        pencil_btn.add_css_class("compact-tool")
        self.tool_buttons[PenType.PENCIL] = pencil_btn
        toolbar.append(pencil_btn)
        
        highlight_btn = Gtk.Button()
        highlight_btn.set_child(self.create_image_button("highlighter.png", 20))
        highlight_btn.set_size_request(36, 36)
        highlight_btn.set_tooltip_text("Highlighter")
        highlight_btn.connect('clicked', lambda _: self.set_pen_type(PenType.HIGHLIGHTER))
        highlight_btn.add_css_class("circular")
        highlight_btn.add_css_class("compact-tool")
        self.tool_buttons[PenType.HIGHLIGHTER] = highlight_btn
        toolbar.append(highlight_btn)
        
        eraser_btn = Gtk.Button()
        eraser_btn.set_child(self.create_image_button("eraser.png", 20))
        eraser_btn.set_size_request(36, 36)
        eraser_btn.set_tooltip_text("Eraser")
        eraser_btn.connect('clicked', lambda _: self.set_pen_type(PenType.ERASER))
        eraser_btn.add_css_class("circular")
        eraser_btn.add_css_class("compact-tool")
        self.tool_buttons[PenType.ERASER] = eraser_btn
        toolbar.append(eraser_btn)
        
        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep1.set_margin_start(6)
        sep1.set_margin_end(6)
        toolbar.append(sep1)
        
        # Selection tool button
        self.selection_btn = Gtk.Button()
        selection_label = Gtk.Label(label="⬚")  # Selection icon
        selection_label.add_css_class("title-2")
        self.selection_btn.set_child(selection_label)
        self.selection_btn.set_size_request(36, 36)
        self.selection_btn.set_tooltip_text("Select Objects (Ctrl+A to select all)")
        self.selection_btn.connect('clicked', self.on_selection_clicked)
        self.selection_btn.add_css_class("circular")
        self.selection_btn.add_css_class("compact-tool")
        self.tool_buttons['selection'] = self.selection_btn
        toolbar.append(self.selection_btn)
        
        # Separator
        sep1a = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep1a.set_margin_start(6)
        sep1a.set_margin_end(6)
        toolbar.append(sep1a)
        
        # Shapes button with popover
        self.shapes_button = Gtk.MenuButton()
        self.shapes_button.set_child(self.create_image_button("shapes.png", 20))
        self.shapes_button.set_size_request(36, 36)
        self.shapes_button.set_tooltip_text("Insert Shape")
        self.shapes_button.add_css_class("circular")
        self.shapes_button.add_css_class("compact-tool")
        
        # Create shapes popover with enhanced options
        shapes_popover = Gtk.Popover()
        shapes_main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        shapes_main_box.set_margin_start(16)
        shapes_main_box.set_margin_end(16)
        shapes_main_box.set_margin_top(16)
        shapes_main_box.set_margin_bottom(16)
        
        # Title
        shapes_title = Gtk.Label(label="Shape Tools")
        shapes_title.add_css_class("heading")
        shapes_main_box.append(shapes_title)
        
        # Divider
        divider1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        shapes_main_box.append(divider1)
        
        # Shape selection section
        shapes_section_label = Gtk.Label(label="Shape Type")
        shapes_section_label.add_css_class("caption")
        shapes_section_label.set_halign(Gtk.Align.START)
        shapes_main_box.append(shapes_section_label)
        
        # Shape options in a grid (2 columns)
        shapes_grid = Gtk.Grid()
        shapes_grid.set_row_spacing(4)
        shapes_grid.set_column_spacing(4)
        
        shapes_list = [
            (ShapeType.STRAIGHT_LINE, "Line", "─"),
            (ShapeType.ARROW, "Arrow", "→"),
            (ShapeType.RECTANGLE, "Rectangle", "▭"),
            (ShapeType.CIRCLE, "Circle", "○"),
            (ShapeType.TRIANGLE, "Triangle", "△"),
            (ShapeType.PENTAGON, "Pentagon", "⬠"),
        ]
        
        for idx, (shape_type, label, icon) in enumerate(shapes_list):
            shape_btn = Gtk.Button()
            shape_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            shape_box.set_margin_start(8)
            shape_box.set_margin_end(8)
            shape_box.set_margin_top(6)
            shape_box.set_margin_bottom(6)
            
            # Icon
            icon_label = Gtk.Label(label=icon)
            icon_label.add_css_class("title-3")
            shape_box.append(icon_label)
            
            # Label
            text_label = Gtk.Label(label=label)
            text_label.set_halign(Gtk.Align.START)
            shape_box.append(text_label)
            
            shape_btn.set_child(shape_box)
            shape_btn.add_css_class("flat")
            shape_btn.connect('clicked', lambda b, st=shape_type: self.set_shape_type(st))
            
            row = idx // 2
            col = idx % 2
            shapes_grid.attach(shape_btn, col, row, 1, 1)
        
        shapes_main_box.append(shapes_grid)
        
        # Divider
        divider2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        shapes_main_box.append(divider2)
        
        # Fill/Outline toggle
        fill_label = Gtk.Label(label="Style")
        fill_label.add_css_class("caption")
        fill_label.set_halign(Gtk.Align.START)
        shapes_main_box.append(fill_label)
        
        fill_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        self.shape_outline_btn = Gtk.ToggleButton(label="Outline")
        self.shape_outline_btn.set_active(True)
        self.shape_outline_btn.add_css_class("pill")
        self.shape_outline_btn.set_hexpand(True)
        self.shape_outline_btn.connect('toggled', self.on_shape_style_toggled)
        fill_box.append(self.shape_outline_btn)
        
        self.shape_fill_btn = Gtk.ToggleButton(label="Filled")
        self.shape_fill_btn.add_css_class("pill")
        self.shape_fill_btn.set_hexpand(True)
        self.shape_fill_btn.connect('toggled', self.on_shape_style_toggled)
        fill_box.append(self.shape_fill_btn)
        
        shapes_main_box.append(fill_box)
        
        # Divider
        divider3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        shapes_main_box.append(divider3)
        
        # Line style options
        line_style_label = Gtk.Label(label="Line Style")
        line_style_label.add_css_class("caption")
        line_style_label.set_halign(Gtk.Align.START)
        shapes_main_box.append(line_style_label)
        
        line_style_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        self.shape_solid_btn = Gtk.ToggleButton(label="─── Solid")
        self.shape_solid_btn.set_active(True)
        self.shape_solid_btn.add_css_class("pill")
        self.shape_solid_btn.set_hexpand(True)
        self.shape_solid_btn.connect('toggled', lambda b: self.on_line_style_changed('solid') if b.get_active() else None)
        line_style_box.append(self.shape_solid_btn)
        
        self.shape_dashed_btn = Gtk.ToggleButton(label="- - - Dashed")
        self.shape_dashed_btn.add_css_class("pill")
        self.shape_dashed_btn.set_hexpand(True)
        self.shape_dashed_btn.connect('toggled', lambda b: self.on_line_style_changed('dashed') if b.get_active() else None)
        line_style_box.append(self.shape_dashed_btn)
        
        self.shape_dotted_btn = Gtk.ToggleButton(label="··· Dotted")
        self.shape_dotted_btn.add_css_class("pill")
        self.shape_dotted_btn.set_hexpand(True)
        self.shape_dotted_btn.connect('toggled', lambda b: self.on_line_style_changed('dotted') if b.get_active() else None)
        line_style_box.append(self.shape_dotted_btn)
        
        shapes_main_box.append(line_style_box)
        
        shapes_popover.set_child(shapes_main_box)
        self.shapes_button.set_popover(shapes_popover)
        toolbar.append(self.shapes_button)
        
        # Text tool button
        self.text_btn = Gtk.Button()
        text_label = Gtk.Label(label="T")
        text_label.add_css_class("title-2")
        self.text_btn.set_child(text_label)
        self.text_btn.set_size_request(36, 36)
        self.text_btn.set_tooltip_text("Text Tool (Type with keyboard)")
        self.text_btn.connect('clicked', self.on_text_clicked)
        self.text_btn.add_css_class("circular")
        self.text_btn.add_css_class("compact-tool")
        self.tool_buttons['text'] = self.text_btn
        toolbar.append(self.text_btn)
        
        # Separator
        sep1a = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep1a.set_margin_start(6)
        sep1a.set_margin_end(6)
        toolbar.append(sep1a)
        
        # Color picker button with enhanced icon
        self.color_indicator = Gtk.Button()
        self.color_indicator_image = self.create_image_button("color-palette.png", 20)
        self.color_indicator.set_child(self.color_indicator_image)
        self.color_indicator.set_size_request(36, 36)
        self.color_indicator.add_css_class("color-indicator")
        self.color_indicator.add_css_class("circular")
        self.color_indicator.add_css_class("compact-tool")
        self.color_indicator.set_tooltip_text("Color Palette")
        
        # Create color popover
        self.color_popover = Gtk.Popover()
        self.color_popover.set_parent(self.color_indicator)
        
        color_grid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        color_grid_box.set_margin_start(12)
        color_grid_box.set_margin_end(12)
        color_grid_box.set_margin_top(12)
        color_grid_box.set_margin_bottom(12)
        
        # 5x5 Color grid
        color_grid = Gtk.Grid()
        color_grid.set_row_spacing(4)
        color_grid.set_column_spacing(4)
        
        # Define 25 colors (5x5)
        colors = [
            # Row 1 - Blacks and grays
            (0.0, 0.0, 0.0, 1.0), (0.25, 0.25, 0.25, 1.0), (0.5, 0.5, 0.5, 1.0), 
            (0.75, 0.75, 0.75, 1.0), (1.0, 1.0, 1.0, 1.0),
            # Row 2 - Reds and oranges
            (0.6, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 1.0), (1.0, 0.3, 0.0, 1.0), 
            (1.0, 0.5, 0.0, 1.0), (1.0, 0.65, 0.0, 1.0),
            # Row 3 - Yellows and greens
            (1.0, 0.8, 0.0, 1.0), (1.0, 1.0, 0.0, 1.0), (0.5, 0.8, 0.0, 1.0), 
            (0.0, 0.8, 0.0, 1.0), (0.0, 0.5, 0.0, 1.0),
            # Row 4 - Cyans and blues
            (0.0, 0.8, 0.6, 1.0), (0.0, 1.0, 1.0, 1.0), (0.0, 0.7, 1.0, 1.0), 
            (0.0, 0.4, 1.0, 1.0), (0.0, 0.0, 0.8, 1.0),
            # Row 5 - Purples and pinks
            (0.3, 0.0, 0.8, 1.0), (0.5, 0.0, 0.5, 1.0), (0.8, 0.0, 0.8, 1.0), 
            (1.0, 0.0, 0.5, 1.0), (1.0, 0.4, 0.7, 1.0),
        ]
        
        for i, color in enumerate(colors):
            row = i // 5
            col = i % 5
            btn = self.create_color_grid_button(color)
            color_grid.attach(btn, col, row, 1, 1)
        
        color_grid_box.append(color_grid)
        self.color_popover.set_child(color_grid_box)
        
        self.color_indicator.connect('clicked', lambda b: self.color_popover.popup())
        toolbar.append(self.color_indicator)
        
        # Separator
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep2.set_margin_start(6)
        sep2.set_margin_end(6)
        toolbar.append(sep2)
        
        # Thickness indicator button with enhanced icon
        self.thickness_indicator = Gtk.Button()
        self.thickness_indicator.set_child(self.create_image_button("strok-thickness.png", 20))
        self.thickness_indicator.set_size_request(36, 36)
        self.thickness_indicator.add_css_class("thickness-indicator")
        self.thickness_indicator.add_css_class("circular")
        self.thickness_indicator.add_css_class("compact-tool")
        self.thickness_indicator.set_tooltip_text("Pen Size")
        
        # Create thickness popover - modern design
        self.thickness_popover = Gtk.Popover()
        self.thickness_popover.set_parent(self.thickness_indicator)
        
        thickness_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        thickness_box.set_margin_start(20)
        thickness_box.set_margin_end(20)
        thickness_box.set_margin_top(16)
        thickness_box.set_margin_bottom(16)
        
        # Title with minimal design - will be updated based on active tool
        self.thickness_label = Gtk.Label(label="Pen Size")
        self.thickness_label.add_css_class("heading")
        self.thickness_label.set_margin_bottom(8)
        thickness_box.append(self.thickness_label)
        
        # Store current thickness value (1-6 for presets)
        self.current_thickness_preset = 2  # Default to Fine
        
        # Circular size buttons (like GoodNotes/Notability)
        self.thickness_buttons = []
        thickness_sizes = [
            ("Ultra Fine", 1, 1.5),   # 1.5px
            ("Fine", 2, 3.0),         # 3px
            ("Medium", 3, 5.0),       # 5px
            ("Bold", 4, 8.0),         # 8px
            ("Heavy", 5, 12.0),       # 12px
            ("Marker", 6, 18.0)       # 18px
        ]
        
        buttons_grid = Gtk.Grid()
        buttons_grid.set_row_spacing(12)
        buttons_grid.set_column_spacing(16)
        buttons_grid.set_halign(Gtk.Align.CENTER)
        
        for idx, (label, preset, px_size) in enumerate(thickness_sizes):
            # Container for each size option
            size_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            size_box.set_halign(Gtk.Align.CENTER)
            
            # Circular button with visual thickness indicator
            btn = Gtk.Button()
            btn.set_size_request(50, 50)
            btn.add_css_class("thickness-preset-btn")
            btn.set_tooltip_text(f"{label} ({px_size}px)")
            
            # Draw area inside button
            draw_area = Gtk.DrawingArea()
            draw_area.set_size_request(50, 50)
            draw_area.set_draw_func(lambda a, cr, w, h, size=px_size: self.draw_thickness_button(cr, w, h, size))
            btn.set_child(draw_area)
            
            # Connect click handler
            btn.connect('clicked', lambda b, p=preset, s=px_size: self.set_thickness_size(p, s))
            self.thickness_buttons.append((btn, preset))
            
            size_box.append(btn)
            
            # Label below button
            name_label = Gtk.Label(label=label)
            name_label.add_css_class("caption")
            name_label.set_opacity(0.7)
            size_box.append(name_label)
            
            # Grid layout: 3 columns x 2 rows
            row = idx // 3
            col = idx % 3
            buttons_grid.attach(size_box, col, row, 1, 1)
        
        thickness_box.append(buttons_grid)
        
        # Fine-tune slider (optional, for precise adjustment)
        slider_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        slider_section.set_margin_top(12)
        
        fine_tune_label = Gtk.Label(label="Fine Adjust")
        fine_tune_label.add_css_class("caption")
        fine_tune_label.set_opacity(0.6)
        slider_section.append(fine_tune_label)
        
        # Horizontal slider for fine-tuning
        self.thickness_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.5, 20.0, 0.5
        )
        self.thickness_scale.set_value(3.0)  # Default
        self.thickness_scale.set_size_request(240, -1)
        self.thickness_scale.set_draw_value(True)
        self.thickness_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.thickness_scale.connect('value-changed', self.on_thickness_slider_changed)
        self.thickness_scale.add_css_class("thickness-slider")
        slider_section.append(self.thickness_scale)
        
        thickness_box.append(slider_section)
        
        self.thickness_popover.set_child(thickness_box)
        self.thickness_indicator.connect('clicked', lambda b: self.on_thickness_button_clicked())
        
        # Set initial thickness (Fine = 3px)
        self.canvas.set_width(3.0)
        
        # Mark Fine preset as selected
        if hasattr(self, 'thickness_buttons') and len(self.thickness_buttons) > 1:
            self.thickness_buttons[1][0].add_css_class("selected")  # Fine is index 1
        
        toolbar.append(self.thickness_indicator)
        
        # Separator
        sep3 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep3.set_margin_start(6)
        sep3.set_margin_end(6)
        toolbar.append(sep3)
        
        # Compact action buttons - each independent
        undo_btn = Gtk.Button(label="↶")
        undo_btn.set_size_request(36, 36)
        undo_btn.set_tooltip_text("Undo")
        undo_btn.connect('clicked', lambda _: self.canvas.undo())
        undo_btn.add_css_class("circular")
        undo_btn.add_css_class("compact-tool")
        toolbar.append(undo_btn)
        
        redo_btn = Gtk.Button(label="↷")
        redo_btn.set_size_request(36, 36)
        redo_btn.set_tooltip_text("Redo")
        redo_btn.connect('clicked', lambda _: self.canvas.redo())
        redo_btn.add_css_class("circular")
        redo_btn.add_css_class("compact-tool")
        toolbar.append(redo_btn)
        
        # Save button
        save_btn = Gtk.Button()
        save_btn.set_child(self.create_image_button("auto-save.png", 20))
        save_btn.set_size_request(36, 36)
        save_btn.set_tooltip_text("Save Note (Auto-saves every 30s)")
        save_btn.connect('clicked', lambda _: self.on_save_clicked())
        save_btn.add_css_class("circular")
        save_btn.add_css_class("compact-tool")
        save_btn.add_css_class("suggested-action")
        toolbar.append(save_btn)
        
        clear_btn = Gtk.Button()
        clear_btn.set_child(self.create_image_button("clear-canvas.png", 20))
        clear_btn.set_size_request(36, 36)
        clear_btn.set_tooltip_text("Clear Entire Canvas")
        clear_btn.connect('clicked', lambda _: self.on_clear_clicked())
        clear_btn.add_css_class("circular")
        clear_btn.add_css_class("compact-tool")
        clear_btn.add_css_class("destructive-action")
        toolbar.append(clear_btn)
        
        # Separator
        sep4 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep4.set_margin_start(6)
        sep4.set_margin_end(6)
        toolbar.append(sep4)
        
        # Palm rejection toggle (compact)
        self.palm_reject_toggle = Gtk.ToggleButton()
        self.palm_reject_toggle.set_child(self.create_image_button("palm-rejection.png", 20))
        self.palm_reject_toggle.set_size_request(36, 36)
        self.palm_reject_toggle.set_tooltip_text("Palm Rejection (Pen Only)")
        self.palm_reject_toggle.set_active(True)
        self.palm_reject_toggle.connect('toggled', self.on_palm_reject_toggled)
        self.palm_reject_toggle.add_css_class("circular")
        self.palm_reject_toggle.add_css_class("compact-tool")
        toolbar.append(self.palm_reject_toggle)
        
        # Separator for page navigation
        self.sep_pages = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.sep_pages.set_margin_start(6)
        self.sep_pages.set_margin_end(6)
        self.sep_pages.set_visible(False)
        toolbar.append(self.sep_pages)
        
        # Page navigation (only visible for A4 notes)
        self.prev_page_btn = Gtk.Button()
        self.prev_page_btn.set_label("◀")
        self.prev_page_btn.set_size_request(36, 36)
        self.prev_page_btn.set_tooltip_text("Previous Page")
        self.prev_page_btn.connect('clicked', lambda _: self.on_prev_page())
        self.prev_page_btn.add_css_class("circular")
        self.prev_page_btn.add_css_class("compact-tool")
        self.prev_page_btn.set_visible(False)
        toolbar.append(self.prev_page_btn)
        
        self.page_label = Gtk.Label()
        self.page_label.set_text("1/1")
        self.page_label.add_css_class("toolbar-button-label")
        self.page_label.set_visible(False)
        toolbar.append(self.page_label)
        
        self.next_page_btn = Gtk.Button()
        self.next_page_btn.set_label("▶")
        self.next_page_btn.set_size_request(36, 36)
        self.next_page_btn.set_tooltip_text("Next Page")
        self.next_page_btn.connect('clicked', lambda _: self.on_next_page())
        self.next_page_btn.add_css_class("circular")
        self.next_page_btn.add_css_class("compact-tool")
        self.next_page_btn.set_visible(False)
        toolbar.append(self.next_page_btn)
        
        # Template selector (only visible for A4 notes)
        self.template_dropdown = Gtk.DropDown()
        template_strings = Gtk.StringList()
        template_strings.append("📄 Blank")
        template_strings.append("📝 Ruled")
        template_strings.append("⊞ Grid")
        template_strings.append("⋮ Dot Grid")
        self.template_dropdown.set_model(template_strings)
        self.template_dropdown.set_selected(0)
        self.template_dropdown.set_tooltip_text("Page Template")
        self.template_dropdown.connect('notify::selected', self.on_template_changed)
        self.template_dropdown.set_visible(False)
        toolbar.append(self.template_dropdown)
        
        # Separator before menu
        sep_menu = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep_menu.set_margin_start(6)
        sep_menu.set_margin_end(6)
        toolbar.append(sep_menu)
        
        # Menu button (replaces header bar menu)
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_size_request(36, 36)
        menu_button.set_tooltip_text("Menu")
        menu_button.add_css_class("circular")
        menu_button.add_css_class("compact-tool")
        # Menu model will be set after main_box setup
        toolbar.append(menu_button)
        self.menu_button = menu_button
        
        return toolbar
    
    def create_color_grid_button(self, color):
        """Create a color button for the grid."""
        btn = Gtk.Button()
        btn.set_size_request(32, 32)
        btn.add_css_class("color-swatch")
        
        # Create colored box
        box = Gtk.Box()
        box.set_size_request(32, 32)
        
        # Set inline style ONLY for dynamic background color
        # All other styling (borders, hover effects, etc.) is in styles.css
        css_provider = Gtk.CssProvider()
        css = f"""button.color-swatch {{ background-color: rgba({int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)}, {color[3]}); }}"""
        css_provider.load_from_data(css.encode())
        btn.get_style_context().add_provider(
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        btn.set_child(box)
        btn.connect('clicked', lambda b: self.on_color_selected(color))
        return btn
    
    def update_color_indicator(self, color):
        """Update the current color (keep PNG icon as is)."""
        self.current_color = color
    
    def draw_paint_bucket_icon(self, cr, width, height, color):
        """Draw a paint bucket icon."""
        # Determine if we need white or black icon based on color brightness
        brightness = color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114
        icon_color = (1, 1, 1) if brightness < 0.5 else (0, 0, 0)
        
        cr.set_source_rgba(icon_color[0], icon_color[1], icon_color[2], 0.9)
        cr.set_line_width(2)
        
        # Draw bucket body (trapezoid)
        cr.move_to(width * 0.3, height * 0.4)
        cr.line_to(width * 0.25, height * 0.75)
        cr.line_to(width * 0.75, height * 0.75)
        cr.line_to(width * 0.7, height * 0.4)
        cr.close_path()
        cr.stroke()
        
        # Draw handle (arc)
        cr.arc(width * 0.5, height * 0.25, width * 0.25, 0, 3.14159)
        cr.stroke()
        
        # Draw paint drop
        cr.arc(width * 0.5, height * 0.55, width * 0.08, 0, 2 * 3.14159)
        cr.fill()
    
    def on_color_selected(self, color):
        """Handle color selection from grid."""
        self.set_color(color)
        self.update_color_indicator(color)
        self.color_popover.popdown()
    
    def update_thickness_indicator(self, value=None):
        """Update the thickness value (keep PNG icon as is)."""
        # Just store the thickness, don't override the icon
        pass
    
    def draw_thickness_indicator(self, cr, width, height, thickness):
        """Draw the thickness indicator with pen nib icon."""
        color = self.canvas.current_color
        
        # Background gradient
        gradient = cairo.LinearGradient(0, 0, 0, height)
        gradient.add_color_stop_rgba(0, 0.95, 0.95, 0.95, 1)
        gradient.add_color_stop_rgba(1, 0.85, 0.85, 0.85, 1)
        cr.set_source(gradient)
        cr.paint()
        
        # Draw pen nib icon
        cx = width / 2
        cy = height / 2
        
        # Nib body (triangle)
        cr.set_source_rgba(0.2, 0.2, 0.2, 0.8)
        cr.move_to(cx, cy - 12)
        cr.line_to(cx - 6, cy + 8)
        cr.line_to(cx + 6, cy + 8)
        cr.close_path()
        cr.fill()
        
        # Nib tip hole
        cr.set_source_rgba(0.9, 0.9, 0.9, 1)
        cr.arc(cx, cy + 2, 2, 0, 2 * 3.14159)
        cr.fill()
        
        # Draw thickness indicator line with current color
        line_width = max(2, min(thickness, 12))
        cr.set_source_rgba(color[0], color[1], color[2], color[3])
        cr.set_line_width(line_width)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.move_to(cx - 8, cy + 12)
        cr.line_to(cx + 8, cy + 12)
        cr.stroke()
        
        # Draw border
        cr.set_source_rgba(0, 0, 0, 0.2)
        cr.set_line_width(1.5)
        cr.rectangle(0.5, 0.5, width - 1, height - 1)
        cr.stroke()
    
    def draw_thickness_button(self, cr, width, height, size):
        """Draw circular thickness indicator on preset buttons."""
        color = self.canvas.current_color
        cx, cy = width / 2, height / 2
        
        # Background circle
        cr.set_source_rgba(0.95, 0.95, 0.95, 1.0)
        cr.arc(cx, cy, width / 2 - 2, 0, 2 * 3.14159)
        cr.fill()
        
        # Draw the actual thickness circle
        radius = min(size / 2, (width / 2) - 8)
        cr.set_source_rgba(color[0], color[1], color[2], 1.0)
        cr.arc(cx, cy, radius, 0, 2 * 3.14159)
        cr.fill()
        
        # Subtle shadow/border for depth
        cr.set_source_rgba(0, 0, 0, 0.15)
        cr.set_line_width(1)
        cr.arc(cx, cy, radius, 0, 2 * 3.14159)
        cr.stroke()
    
    def on_thickness_button_clicked(self):
        """Handle thickness button click - update label based on active tool."""
        if hasattr(self, 'thickness_label'):
            if self.canvas.current_pen_type == PenType.ERASER:
                self.thickness_label.set_label("Eraser Size")
            else:
                self.thickness_label.set_label("Pen Size")
        self.thickness_popover.popup()
    
    def set_thickness_size(self, preset, px_size):
        """Set thickness from preset button."""
        self.current_thickness_preset = preset
        
        # Update slider to match
        self.thickness_scale.set_value(px_size)
        
        # Update canvas
        self.canvas.set_width(px_size)
        
        # Update button states
        for btn, btn_preset in self.thickness_buttons:
            if btn_preset == preset:
                btn.add_css_class("selected")
            else:
                btn.remove_css_class("selected")
        
        # Update indicator
        self.update_thickness_indicator_from_px(px_size)
        
        # Redraw all buttons to show current color
        for btn, _ in self.thickness_buttons:
            child = btn.get_child()
            if child:
                child.queue_draw()
    
    def on_thickness_slider_changed(self, scale):
        """Handle fine-tune thickness slider changes."""
        px_size = scale.get_value()
        
        # Update canvas
        self.canvas.set_width(px_size)
        
        # Update indicator
        self.update_thickness_indicator_from_px(px_size)
        
        # Clear preset selection since we're doing custom
        for btn, _ in self.thickness_buttons:
            btn.remove_css_class("selected")
        
        # Redraw all preset buttons to show current color
        for btn, _ in self.thickness_buttons:
            child = btn.get_child()
            if child:
                child.queue_draw()
    
    def update_thickness_indicator_from_px(self, px_size):
        """Update the thickness indicator button with actual pixel size."""
        if hasattr(self, 'thickness_indicator_area'):
            self.thickness_indicator_area.queue_draw()
    
    def create_sidebar(self):
        """Create modern, human-centric sidebar with better UX."""
        # Main container with gradient background
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar_box.set_size_request(320, -1)  # Wider for better readability
        sidebar_box.add_css_class("modern-sidebar")
        
        # === HEADER SECTION ===
        header_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        header_section.set_margin_start(20)
        header_section.set_margin_end(20)
        header_section.set_margin_top(20)
        header_section.set_margin_bottom(16)
        
        # Branding header with close button
        branding = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        # App icon
        app_icon = Gtk.Label(label="✏️")
        app_icon.add_css_class("sidebar-app-icon")
        branding.append(app_icon)
        
        # Title area
        title_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        app_title = Gtk.Label(label="Notes")
        app_title.add_css_class("sidebar-title")
        app_title.set_halign(Gtk.Align.START)
        
        subtitle = Gtk.Label(label="Organize your ideas")
        subtitle.add_css_class("sidebar-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        
        title_area.append(app_title)
        title_area.append(subtitle)
        title_area.set_hexpand(True)
        branding.append(title_area)
        
        # Hide Notes button
        hide_notes_btn = Gtk.Button()
        hide_notes_btn.set_icon_name("window-close-symbolic")
        hide_notes_btn.set_tooltip_text("Hide Notes")
        hide_notes_btn.connect('clicked', self.toggle_sidebar)
        hide_notes_btn.add_css_class("flat")
        hide_notes_btn.add_css_class("circular")
        branding.append(hide_notes_btn)
        
        header_section.append(branding)
        
        # Quick actions bar
        quick_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # New subject button (primary action)
        new_subject_btn = Gtk.Button()
        new_subject_btn.set_label("New Subject")
        new_subject_btn.set_icon_name("folder-new-symbolic")
        new_subject_btn.connect('clicked', self.on_new_subject)
        new_subject_btn.add_css_class("pill-button")
        new_subject_btn.add_css_class("suggested-action")
        new_subject_btn.set_hexpand(True)
        quick_actions.append(new_subject_btn)
        
        header_section.append(quick_actions)
        
        sidebar_box.append(header_section)
        
        # Divider
        divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        divider.add_css_class("modern-divider")
        sidebar_box.append(divider)
        
        # === CONTENT SECTION ===
        # Stats bar (shows count)
        stats_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stats_bar.set_margin_start(20)
        stats_bar.set_margin_end(20)
        stats_bar.set_margin_top(12)
        stats_bar.set_margin_bottom(8)
        
        self.stats_label = Gtk.Label(label="All Notes")
        self.stats_label.add_css_class("caption")
        self.stats_label.add_css_class("dim-label")
        self.stats_label.set_halign(Gtk.Align.START)
        self.stats_label.set_hexpand(True)
        stats_bar.append(self.stats_label)
        
        sidebar_box.append(stats_bar)
        
        # Notes list (scrollable)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add_css_class("modern-scrolled")
        
        self.subjects_listbox = Gtk.ListBox()
        self.subjects_listbox.add_css_class("modern-listbox")
        self.subjects_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.set_child(self.subjects_listbox)
        
        sidebar_box.append(scrolled)
        
        # === FOOTER SECTION ===
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_start(20)
        footer.set_margin_end(20)
        footer.set_margin_top(12)
        footer.set_margin_bottom(16)
        footer.add_css_class("sidebar-footer")
        
        # Storage info
        storage_label = Gtk.Label(label="📊")
        footer.append(storage_label)
        
        self.storage_info = Gtk.Label(label="0 notes")
        self.storage_info.add_css_class("caption")
        self.storage_info.add_css_class("dim-label")
        self.storage_info.set_halign(Gtk.Align.START)
        self.storage_info.set_hexpand(True)
        footer.append(self.storage_info)
        
        sidebar_box.append(footer)
        
        # Load subjects and update stats
        self.refresh_subjects_list()
        self.update_sidebar_stats()
        
        return sidebar_box
    
    def refresh_subjects_list(self, search_filter=None, expand_all=None):
        """Refresh the subjects list in sidebar.
        
        Args:
            search_filter: Optional search text to filter subjects/notes
            expand_all: Optional boolean to expand (True) or collapse (False) all subjects
        """
        # Clear existing items
        child = self.subjects_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.subjects_listbox.remove(child)
            child = next_child
        
        # Track results for search feedback
        matched_subjects = 0
        matched_notes = 0
        
        # Add subjects
        for subject_name in self.notes_library.get_subjects():
            notes = self.notes_library.get_notes(subject_name)
            
            # Filter by search text
            if search_filter:
                # Check if subject name or any note name matches search
                subject_matches = search_filter in subject_name.lower()
                matching_notes = [note for note in notes if search_filter in note.lower()]
                
                if not subject_matches and not matching_notes:
                    continue
                
                # Track matches for feedback
                matched_subjects += 1
                matched_notes += len(matching_notes)
            
            subject_row = self.create_subject_row(subject_name, expand_all=expand_all, search_filter=search_filter)
            self.subjects_listbox.append(subject_row)
        
        # Update stats after refresh
        self.update_sidebar_stats(search_filter=search_filter, 
                                 matched_subjects=matched_subjects if search_filter else None,
                                 matched_notes=matched_notes if search_filter else None)
    
    def create_subject_row(self, subject_name: str, expand_all=None, search_filter=None):
        """Create modern subject card with better visual hierarchy.
        
        Args:
            subject_name: Name of the subject
            expand_all: Optional boolean to expand (True) or collapse (False) the subject
            search_filter: Optional search text to filter notes
        """
        # Main card container
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("subject-card")
        card.set_margin_start(12)
        card.set_margin_end(12)
        card.set_margin_top(6)
        card.set_margin_bottom(6)
        
        # === SUBJECT HEADER (CLICKABLE) ===
        # Container for header and actions
        header_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        
        # Make header a button so entire area is clickable
        header_btn = Gtk.Button()
        header_btn.add_css_class("subject-header-button")
        header_btn.add_css_class("flat")
        header_btn.set_tooltip_text(f"Click to expand/collapse {subject_name}")
        header_btn.set_hexpand(True)
        
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_start(16)
        header.set_margin_end(16)
        header.set_margin_top(14)
        header.set_margin_bottom(14)
        
        # Determine initial expand state
        if expand_all is not None:
            is_expanded = expand_all
        elif search_filter:
            is_expanded = True
        else:
            is_expanded = False
        
        # Subject info section
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)
        
        # Subject name with folder icon
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # Folder icon
        folder_icon = Gtk.Label(label="📂")
        folder_icon.add_css_class("subject-icon")
        name_box.append(folder_icon)
        
        subject_label = Gtk.Label(label=subject_name)
        subject_label.set_halign(Gtk.Align.START)
        subject_label.add_css_class("subject-name")
        subject_label.set_ellipsize(Pango.EllipsizeMode.END)
        subject_label.set_max_width_chars(20)
        name_box.append(subject_label)
        
        info_box.append(name_box)
        
        # Note count badge
        notes_count = len(self.notes_library.get_notes(subject_name))
        if notes_count > 0:
            count_label = Gtk.Label(label=f"{notes_count} note{'s' if notes_count != 1 else ''}")
            count_label.set_halign(Gtk.Align.START)
            count_label.add_css_class("note-count-badge")
            info_box.append(count_label)
        
        header.append(info_box)
        
        # Set header as child of button
        header_btn.set_child(header)
        header_container.append(header_btn)
        
        # Action buttons (OUTSIDE header button to be clickable)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions_box.set_margin_end(16)
        actions_box.set_margin_top(14)
        actions_box.set_margin_bottom(14)
        
        # Add note button - always visible
        add_note_btn = Gtk.Button()
        add_note_btn.set_icon_name("list-add-symbolic")
        add_note_btn.set_tooltip_text(f"Add note to {subject_name}")
        add_note_btn.connect('clicked', lambda b: self.on_new_note(subject_name))
        add_note_btn.add_css_class("flat")
        actions_box.append(add_note_btn)
        
        # Delete subject button
        delete_subject_btn = Gtk.Button()
        delete_subject_btn.set_icon_name("user-trash-symbolic")
        delete_subject_btn.set_tooltip_text(f"Delete {subject_name}")
        delete_subject_btn.connect('clicked', lambda b: self.on_delete_subject(subject_name))
        delete_subject_btn.add_css_class("flat")
        delete_subject_btn.add_css_class("destructive-action")
        actions_box.append(delete_subject_btn)
        
        header_container.append(actions_box)
        card.append(header_container)
        
        # === NOTES LIST (EXPANDABLE) ===
        notes_revealer = Gtk.Revealer()
        notes_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        notes_revealer.set_transition_duration(250)
        
        notes_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        notes_container.set_margin_start(16)
        notes_container.set_margin_end(16)
        notes_container.set_margin_bottom(12)
        notes_container.add_css_class("notes-list")
        
        # Get and filter notes
        filtered_notes = []
        for note_name in self.notes_library.get_notes(subject_name):
            if search_filter and search_filter not in note_name.lower():
                continue
            filtered_notes.append(note_name)
        
        # Add note items
        for i, note_name in enumerate(filtered_notes):
            note_item = self.create_note_item(subject_name, note_name)
            notes_container.append(note_item)
        
        # Empty state if no notes
        if not filtered_notes:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            empty_box.set_margin_top(8)
            empty_box.set_margin_bottom(8)
            empty_box.set_margin_start(20)
            
            empty_icon = Gtk.Label(label="📝")
            empty_icon.add_css_class("dim-label")
            empty_box.append(empty_icon)
            
            empty_label = Gtk.Label(label="No notes yet")
            empty_label.add_css_class("caption")
            empty_label.add_css_class("dim-label")
            empty_box.append(empty_label)
            
            notes_container.append(empty_box)
        
        notes_revealer.set_child(notes_container)
        card.append(notes_revealer)
        
        # Connect header button click to toggle expansion
        def on_header_clicked(btn):
            nonlocal is_expanded
            is_expanded = not is_expanded
            notes_revealer.set_reveal_child(is_expanded)
        
        header_btn.connect('clicked', on_header_clicked)
        
        # Set initial reveal state
        notes_revealer.set_reveal_child(is_expanded)
        
        return card
        
        return note_btn
    
    def update_sidebar_stats(self, search_filter=None, matched_subjects=None, matched_notes=None):
        """Update sidebar statistics display.
        
        Args:
            search_filter: Optional search text if filtering
            matched_subjects: Number of subjects matching search
            matched_notes: Number of notes matching search
        """
        subjects = self.notes_library.get_subjects()
        total_notes = sum(len(self.notes_library.get_notes(s)) for s in subjects)
        
        # Update stats label
        if hasattr(self, 'stats_label'):
            if search_filter:
                # Show search results
                if matched_subjects == 0:
                    self.stats_label.set_text(f"🔍 No results for '{search_filter}'")
                else:
                    self.stats_label.set_text(f"🔍 Found {matched_notes} note{'s' if matched_notes != 1 else ''} in {matched_subjects} subject{'s' if matched_subjects != 1 else ''}")
            elif len(subjects) == 0:
                self.stats_label.set_text("No subjects yet")
            else:
                self.stats_label.set_text(f"{len(subjects)} subject{'s' if len(subjects) != 1 else ''}")
        
        # Update footer storage info
        if hasattr(self, 'storage_info'):
            self.storage_info.set_text(f"{total_notes} note{'s' if total_notes != 1 else ''}")
    
    def create_note_item(self, subject_name: str, note_name: str):
        """Create a modern note item with hover effects."""
        # Note button as main container
        note_btn = Gtk.Button()
        note_btn.add_css_class("note-item")
        note_btn.connect('clicked', lambda b: self.open_note(subject_name, note_name))
        
        # Note content
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        content_box.set_margin_top(10)
        content_box.set_margin_bottom(10)
        
        # Bullet point
        bullet = Gtk.Label(label="•")
        bullet.add_css_class("note-bullet")
        content_box.append(bullet)
        
        # Note name
        note_label = Gtk.Label(label=note_name)
        note_label.set_halign(Gtk.Align.START)
        note_label.set_hexpand(True)
        note_label.add_css_class("note-name")
        note_label.set_ellipsize(Pango.EllipsizeMode.END)
        content_box.append(note_label)
        
        # Delete note button (visible on hover)
        delete_note_btn = Gtk.Button()
        delete_note_btn.set_icon_name("user-trash-symbolic")
        delete_note_btn.set_tooltip_text(f"Delete {note_name}")
        
        # Connect with click controller to stop event propagation
        def on_delete_clicked(button, subject, note):
            self.on_delete_note(subject, note)
            return True  # Stop propagation
        
        click = Gtk.GestureClick.new()
        click.connect('pressed', lambda gesture, n, x, y: on_delete_clicked(delete_note_btn, subject_name, note_name))
        delete_note_btn.add_controller(click)
        
        delete_note_btn.add_css_class("flat")
        delete_note_btn.add_css_class("destructive-action")
        delete_note_btn.add_css_class("note-delete-btn")
        content_box.append(delete_note_btn)
        
        # Chevron indicator (hover-visible)
        chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
        chevron.add_css_class("note-chevron")
        content_box.append(chevron)
        
        note_btn.set_child(content_box)
        return note_btn
    
    def on_search_changed(self, entry):
        """Handle search text changes."""
        search_text = entry.get_text().strip().lower()
        logger.info(f"Search changed: '{search_text}'")
        # Only filter if there's actual search text
        if search_text:
            self.refresh_subjects_list(search_filter=search_text)
        else:
            self.refresh_subjects_list(search_filter=None)
    
    def expand_all_subjects(self, button):
        """Expand all subjects in the sidebar."""
        self.refresh_subjects_list(expand_all=True)
    
    def collapse_all_subjects(self, button):
        """Collapse all subjects in the sidebar."""
        self.refresh_subjects_list(expand_all=False)
    
    def toggle_sidebar(self, button=None):
        """Toggle sidebar visibility."""
        self.sidebar_visible = not self.sidebar_visible
        self.sidebar_revealer.set_reveal_child(self.sidebar_visible)
        
        if self.sidebar_visible:
            # Create a box with icon and label
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            button_box.append(self.create_image_button("show-notes.png", 18))
            label = Gtk.Label(label="Hide Notes")
            label.add_css_class("toolbar-button-label")
            button_box.append(label)
            self.notes_button.set_child(button_box)
            self.notes_button.set_tooltip_text("Hide Notes Library")
        else:
            self.notes_button.set_child(self.create_image_button("show-notes.png", 18))
            self.notes_button.set_tooltip_text("Show Notes Library")
    
    def on_delete_subject(self, subject_name: str):
        """Delete a subject with confirmation."""
        notes_count = len(self.notes_library.get_notes(subject_name))
        
        # Confirmation dialog
        dialog = Gtk.AlertDialog()
        dialog.set_modal(True)
        dialog.set_message(f"Delete '{subject_name}'?")
        if notes_count > 0:
            dialog.set_detail(f"This will permanently delete {notes_count} note{'s' if notes_count != 1 else ''} in this subject. This action cannot be undone.")
        else:
            dialog.set_detail("This action cannot be undone.")
        dialog.set_buttons(["Cancel", "Delete"])
        dialog.set_cancel_button(0)
        dialog.set_default_button(0)
        
        def on_response(dialog, result):
            try:
                button_index = dialog.choose_finish(result)
                if button_index == 1:  # Delete button clicked
                    # Check if we're deleting the currently open subject
                    closing_current = self.current_subject == subject_name
                    
                    # Delete the subject
                    if self.notes_library.delete_subject(subject_name):
                        # Clear canvas if this was the current subject
                        if closing_current:
                            self.canvas.clear_canvas()
                            self.current_subject = None
                            self.current_note = None
                            self.current_file = None
                            self.status_label.set_text("Subject deleted")
                        
                        # Force refresh of the sidebar
                        self.refresh_subjects_list()
                        logger.info(f"Deleted subject: {subject_name}")
                        
                        # Show feedback
                        if not closing_current:
                            self.status_label.set_text(f"Deleted: {subject_name}")
                            GLib.timeout_add_seconds(3, lambda: self.status_label.set_text(
                                f"{self.current_subject} / {self.current_note}" if self.current_subject else "Ready"
                            ) if hasattr(self, 'status_label') else False)
                    else:
                        logger.error(f"Failed to delete subject: {subject_name}")
                        self.status_label.set_text(f"Error deleting {subject_name}")
            except Exception as e:
                logger.error(f"Error in delete subject dialog: {e}")
                self.status_label.set_text(f"Error: {str(e)}")
        
        dialog.choose(self, None, on_response)
    
    def on_delete_note(self, subject_name: str, note_name: str):
        """Delete a note with confirmation."""
        # Confirmation dialog
        dialog = Gtk.AlertDialog()
        dialog.set_modal(True)
        dialog.set_message(f"Delete '{note_name}'?")
        dialog.set_detail(f"This will permanently delete this note from '{subject_name}'. This action cannot be undone.")
        dialog.set_buttons(["Cancel", "Delete"])
        dialog.set_cancel_button(0)
        dialog.set_default_button(0)
        
        def on_response(dialog, result):
            try:
                button_index = dialog.choose_finish(result)
                if button_index == 1:  # Delete button clicked
                    # Check if we're deleting the currently open note
                    closing_current = (self.current_subject == subject_name and 
                                     self.current_note == note_name)
                    
                    # Delete the note
                    if self.notes_library.delete_note(subject_name, note_name):
                        # Clear canvas if this was the current note
                        if closing_current:
                            self.canvas.clear_canvas()
                            self.current_subject = None
                            self.current_note = None
                            self.current_file = None
                            self.status_label.set_text("Note deleted")
                        
                        # Force refresh of the sidebar
                        self.refresh_subjects_list()
                        logger.info(f"Deleted note: {subject_name}/{note_name}")
                        
                        # Show feedback
                        if not closing_current:
                            self.status_label.set_text(f"Deleted: {note_name}")
                            GLib.timeout_add_seconds(3, lambda: self.status_label.set_text(
                                f"{self.current_subject} / {self.current_note}" if self.current_subject else "Ready"
                            ) if hasattr(self, 'status_label') else False)
                    else:
                        logger.error(f"Failed to delete note: {subject_name}/{note_name}")
                        self.status_label.set_text(f"Error deleting {note_name}")
            except Exception as e:
                logger.error(f"Error in delete note dialog: {e}")
                self.status_label.set_text(f"Error: {str(e)}")
        
        dialog.choose(self, None, on_response)
    
    def on_new_subject(self, button):
        """Create a new subject."""
        dialog = Gtk.Dialog(title="Create New Subject", transient_for=self, modal=True)
        dialog.set_default_size(450, 250)
        
        # Add standard dialog buttons
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        create_button = dialog.add_button("Create Subject", Gtk.ResponseType.OK)
        create_button.add_css_class("suggested-action")
        
        content = dialog.get_content_area()
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.set_margin_top(20)
        content.set_margin_bottom(24)
        content.set_spacing(16)
        
        # Icon and description
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box.set_halign(Gtk.Align.CENTER)
        
        icon_label = Gtk.Label(label="📁")
        icon_label.set_css_classes(["title-1"])
        title_box.append(icon_label)
        
        title = Gtk.Label(label="Create a new subject")
        title.set_css_classes(["title-2"])
        title_box.append(title)
        
        content.append(title_box)
        
        # Description
        desc = Gtk.Label(label="Organize your notes by subject or topic")
        desc.add_css_class("dim-label")
        desc.set_halign(Gtk.Align.CENTER)
        content.append(desc)
        
        # Entry field with label
        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        entry_label = Gtk.Label(label="Subject Name")
        entry_label.set_halign(Gtk.Align.START)
        entry_label.add_css_class("caption")
        entry_label.add_css_class("dim-label")
        entry_box.append(entry_label)
        
        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g., Mathematics, Physics, Chemistry")
        entry.set_activates_default(True)
        entry_box.append(entry)
        
        content.append(entry_box)
        
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.connect('response', lambda d, r: self.on_new_subject_response(d, r, entry))
        dialog.present()
    
    def on_new_subject_response(self, dialog, response, entry):
        """Handle new subject dialog response."""
        if response == Gtk.ResponseType.OK:
            subject_name = entry.get_text().strip()
            if subject_name:
                if self.notes_library.create_subject(subject_name):
                    self.refresh_subjects_list()
                    self.status_label.set_text(f"Created subject: {subject_name}")
                else:
                    self.show_error(f"Subject '{subject_name}' already exists")
        dialog.destroy()
    
    def on_new_note(self, subject_name: str):
        """Create a new note in a subject."""
        dialog = Gtk.Dialog(title=f"Create New Note - {subject_name}", transient_for=self, modal=True)
        dialog.set_default_size(500, 350)
        
        # Add standard dialog buttons
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        create_button = dialog.add_button("Create Note", Gtk.ResponseType.OK)
        create_button.add_css_class("suggested-action")
        
        content = dialog.get_content_area()
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.set_margin_top(20)
        content.set_margin_bottom(24)
        content.set_spacing(16)
        
        # Icon and description
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box.set_halign(Gtk.Align.CENTER)
        
        icon_label = Gtk.Label(label="📝")
        icon_label.set_css_classes(["title-1"])
        title_box.append(icon_label)
        
        title = Gtk.Label(label=f"Add note to {subject_name}")
        title.set_css_classes(["title-2"])
        title_box.append(title)
        
        content.append(title_box)
        
        # Description
        desc = Gtk.Label(label="Give your note a descriptive name and choose type")
        desc.add_css_class("dim-label")
        desc.set_halign(Gtk.Align.CENTER)
        content.append(desc)
        
        # Entry field with label
        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        entry_label = Gtk.Label(label="Note Name")
        entry_label.set_halign(Gtk.Align.START)
        entry_label.add_css_class("caption")
        entry_label.add_css_class("dim-label")
        entry_box.append(entry_label)
        
        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g., Chapter 1, Lecture Notes")
        entry.set_activates_default(True)
        entry_box.append(entry)
        
        content.append(entry_box)
        
        # Note type selection
        type_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        type_label = Gtk.Label(label="Note Type")
        type_label.set_halign(Gtk.Align.START)
        type_label.add_css_class("caption")
        type_label.add_css_class("dim-label")
        type_box.append(type_label)
        
        # Radio buttons for note type
        radio_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        a4_radio = Gtk.CheckButton()
        a4_radio.set_label("📄 A4 Notes (Paginated notebook for students)")
        a4_radio.set_active(True)
        radio_box.append(a4_radio)
        
        canvas_radio = Gtk.CheckButton()
        canvas_radio.set_label("🎨 Canvas (Infinite playground)")
        canvas_radio.set_group(a4_radio)
        radio_box.append(canvas_radio)
        
        type_box.append(radio_box)
        content.append(type_box)
        
        # Template selection (only for A4 notes)
        template_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        template_label = Gtk.Label(label="Page Template (A4 Notes only)")
        template_label.set_halign(Gtk.Align.START)
        template_label.add_css_class("caption")
        template_label.add_css_class("dim-label")
        template_box.append(template_label)
        
        # Dropdown for template selection
        template_dropdown = Gtk.DropDown()
        template_strings = Gtk.StringList()
        template_strings.append("📄 Blank - Plain page")
        template_strings.append("📝 Ruled - Horizontal lines (notebook)")
        template_strings.append("⊞ Grid - Square grid pattern")
        template_strings.append("⋮ Dot Grid - Dotted grid")
        template_dropdown.set_model(template_strings)
        template_dropdown.set_selected(0)  # Default to Blank
        template_box.append(template_dropdown)
        
        content.append(template_box)
        
        # Show/hide template selection based on note type
        def on_note_type_changed(radio):
            is_a4 = a4_radio.get_active()
            template_box.set_visible(is_a4)
            template_box.set_sensitive(is_a4)
        
        a4_radio.connect('toggled', on_note_type_changed)
        canvas_radio.connect('toggled', on_note_type_changed)
        
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.connect('response', lambda d, r: self.on_new_note_response(d, r, subject_name, entry, a4_radio, template_dropdown))
        dialog.present()
    
    def on_new_note_response(self, dialog, response, subject_name, entry, a4_radio, template_dropdown):
        """Handle new note dialog response."""
        if response == Gtk.ResponseType.OK:
            note_name = entry.get_text().strip()
            if note_name:
                from ..core.stroke import NoteType, PageTemplate
                # Determine note type based on radio selection
                note_type = NoteType.A4_NOTES if a4_radio.get_active() else NoteType.CANVAS
                
                # Determine page template for A4 notes
                page_template = PageTemplate.BLANK
                if note_type == NoteType.A4_NOTES:
                    template_idx = template_dropdown.get_selected()
                    if template_idx == 0:
                        page_template = PageTemplate.BLANK
                    elif template_idx == 1:
                        page_template = PageTemplate.RULED
                    elif template_idx == 2:
                        page_template = PageTemplate.GRID
                    elif template_idx == 3:
                        page_template = PageTemplate.DOT_GRID
                
                note_path = self.notes_library.create_note(subject_name, note_name, note_type, page_template)
                if note_path:
                    self.refresh_subjects_list()
                    self.open_note(subject_name, note_name)
                    type_str = "A4 Notes" if note_type == NoteType.A4_NOTES else "Canvas"
                    self.status_label.set_text(f"Created {type_str}: {subject_name}/{note_name}")
                else:
                    self.show_error("Failed to create note")
        dialog.destroy()
    
    def open_note(self, subject_name: str, note_name: str):
        """Open a note for editing."""
        note_path = self.notes_library.get_note_path(subject_name, note_name)
        if note_path:
            try:
                self.canvas.document = DrawingDocument.load_from_file(note_path)
                
                # Reset view (zoom and pan) when opening a note
                self.canvas.reset_view()
                
                self.canvas.queue_draw()
                self.current_file = note_path
                self.current_subject = subject_name
                self.current_note = note_name
                
                # Update UI based on note type
                from ..core.stroke import NoteType, PageTemplate
                is_a4_notes = self.canvas.document.note_type == NoteType.A4_NOTES
                
                # Show/hide page navigation
                self.sep_pages.set_visible(is_a4_notes)
                self.prev_page_btn.set_visible(is_a4_notes)
                self.page_label.set_visible(is_a4_notes)
                self.next_page_btn.set_visible(is_a4_notes)
                self.template_dropdown.set_visible(is_a4_notes)
                
                if is_a4_notes:
                    self.update_page_label()
                    
                    # Set template dropdown to match current template
                    template = self.canvas.document.page_template
                    if template == PageTemplate.BLANK:
                        self.template_dropdown.set_selected(0)
                    elif template == PageTemplate.RULED:
                        self.template_dropdown.set_selected(1)
                    elif template == PageTemplate.GRID:
                        self.template_dropdown.set_selected(2)
                    elif template == PageTemplate.DOT_GRID:
                        self.template_dropdown.set_selected(3)
                    
                    note_type_icon = "📄"
                else:
                    note_type_icon = "🎨"
                
                self.status_label.set_text(f"{note_type_icon} {subject_name} / {note_name}")
                logger.info(f"Opened note: {subject_name}/{note_name}")
                
                # Keep sidebar visible so user can navigate between notes
            except Exception as e:
                logger.error(f"Error opening note: {e}")
                self.show_error(f"Failed to open note: {e}")
    
    def apply_custom_css(self):
        """Load CSS from external stylesheet file."""
        css_provider = Gtk.CssProvider()
        css_file = self.get_asset_path("styles.css")
        
        try:
            css_provider.load_from_path(css_file)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            logger.info(f"Loaded CSS from {css_file}")
        except Exception as e:
            logger.error(f"Failed to load CSS file: {e}")
            # Fall back to minimal inline CSS if file loading fails
            css_provider.load_from_data(b".toolbar { padding: 4px; }")
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    
    def setup_actions(self):
        """Set up application actions."""
        actions = [
            ('export_png', self.on_export_png),
            ('export_pdf', self.on_export_pdf),
            ('toggle_dark', self.on_toggle_dark),
            ('fullscreen', self.on_fullscreen),
            ('device_info', self.on_device_info),
            ('expand_all', lambda a, p: self.expand_all_subjects(None)),
            ('collapse_all', lambda a, p: self.collapse_all_subjects(None)),
            ('sort_name_asc', lambda a, p: None),  # Future implementation
            ('sort_name_desc', lambda a, p: None),  # Future implementation
            ('sort_recent', lambda a, p: None),  # Future implementation
            ('toolbar_top', lambda a, p: self.set_toolbar_position('top')),
            ('toolbar_bottom', lambda a, p: self.set_toolbar_position('bottom')),
            ('toolbar_left', lambda a, p: self.set_toolbar_position('left')),
            ('toolbar_right', lambda a, p: self.set_toolbar_position('right')),
        ]
        
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.app.add_action(action)
    
    def setup_keyboard_shortcuts(self):
        """Set up keyboard shortcuts for selection and editing."""
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(key_controller)
        logger.info("Keyboard shortcuts configured")
    
    def on_key_pressed(self, controller, keyval, keycode, state):
        """Handle keyboard shortcuts."""
        # Check for Ctrl modifier
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        
        # Ctrl+A: Select all
        if ctrl and keyval == Gdk.KEY_a:
            self.canvas.select_all()
            logger.info("Select All (Ctrl+A)")
            return True
        
        # Ctrl+C: Copy
        elif ctrl and keyval == Gdk.KEY_c:
            self.canvas.copy_selection()
            logger.info("Copy (Ctrl+C)")
            return True
        
        # Ctrl+V: Paste
        elif ctrl and keyval == Gdk.KEY_v:
            self.canvas.paste_selection()
            logger.info("Paste (Ctrl+V)")
            return True
        
        # Ctrl+X: Cut
        elif ctrl and keyval == Gdk.KEY_x:
            self.canvas.copy_selection()
            self.canvas.delete_selection()
            logger.info("Cut (Ctrl+X)")
            return True
        
        # Ctrl+D: Duplicate
        elif ctrl and keyval == Gdk.KEY_d:
            self.canvas.duplicate_selection()
            logger.info("Duplicate (Ctrl+D)")
            return True
        
        # Delete or Backspace: Delete selection
        elif keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            if self.canvas.selection_mode and not self.canvas.selection.is_empty():
                self.canvas.delete_selection()
                logger.info("Delete selection (Delete)")
                return True
        
        # Escape: Clear selection
        elif keyval == Gdk.KEY_Escape:
            if self.canvas.selection_mode and not self.canvas.selection.is_empty():
                self.canvas.selection.clear()
                self.canvas.queue_draw()
                logger.info("Clear selection (Escape)")
                return True
        
        # Ctrl+Plus/Equal: Zoom in
        elif ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.canvas.zoom_in()
            logger.info("Zoom in (Ctrl++)")
            return True
        
        # Ctrl+Minus: Zoom out
        elif ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.canvas.zoom_out()
            logger.info("Zoom out (Ctrl+-)")
            return True
        
        # Ctrl+0: Reset zoom to fit
        elif ctrl and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.canvas.reset_view()
            logger.info("Reset zoom (Ctrl+0)")
            return True
        
        return False
    
    def on_text_clicked(self, button):
        """Handle text tool button click."""
        # Toggle text mode
        if self.canvas.text_mode:
            self.canvas.set_text_mode(False)
            button.remove_css_class("suggested-action")
            # Restore previous tool
            if self.active_tool_button and self.active_tool_button != button:
                self.active_tool_button.add_css_class("suggested-action")
        else:
            # Disable selection mode when enabling text mode
            if self.canvas.selection_mode:
                self.canvas.disable_selection_mode()
            
            # Disable shape mode when enabling text mode
            if self.canvas.shape_mode:
                self.canvas.shape_mode = False
            
            self.canvas.set_text_mode(True)
            # Remove highlight from previous tool
            if self.active_tool_button:
                self.active_tool_button.remove_css_class("suggested-action")
            button.add_css_class("suggested-action")
            self.active_tool_button = button
            self.status_label.set_text("Text mode: Click to add text, type to edit, Escape to exit")
        
        logger.info(f"Text mode: {self.canvas.text_mode}")
    
    def on_selection_clicked(self, button):
        """Handle selection tool button click."""
        # Toggle selection mode
        if self.canvas.selection_mode:
            self.canvas.disable_selection_mode()
            button.remove_css_class("suggested-action")
            # Restore previous tool
            if self.active_tool_button and self.active_tool_button != button:
                self.active_tool_button.add_css_class("suggested-action")
        else:
            # Disable text mode when enabling selection
            if self.canvas.text_mode:
                self.canvas.set_text_mode(False)
            
            self.canvas.enable_selection_mode()
            # Remove highlight from previous tool
            if self.active_tool_button:
                self.active_tool_button.remove_css_class("suggested-action")
            button.add_css_class("suggested-action")
            self.active_tool_button = button
        
        logger.info(f"Selection mode: {self.canvas.selection_mode}")
    
    def update_toolbar_position(self):
        """Update toolbar layout based on current position setting."""
        # Clear main_box
        child = self.main_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.main_box.remove(child)
            child = next_child
        
        if self.toolbar_position in ['top', 'bottom']:
            # Horizontal layout
            self.main_box.set_orientation(Gtk.Orientation.VERTICAL)
            self.toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
            
            # Disable scrolling and expansion for horizontal toolbar
            self.toolbar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            self.toolbar_scroll.set_vexpand(False)
            self.toolbar_scroll.set_hexpand(False)
            
            # Reset margins
            self.toolbar.set_margin_start(0)
            self.toolbar.set_margin_end(0)
            self.toolbar.set_margin_top(8 if self.toolbar_position == 'top' else 0)
            self.toolbar.set_margin_bottom(8 if self.toolbar_position == 'bottom' else 0)
            
            # Set transition
            if self.toolbar_position == 'top':
                self.toolbar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
                self.main_box.append(self.toolbar_revealer)
                self.main_box.append(self.canvas_box)
                self.main_box.append(self.status_box)
            else:  # bottom
                self.toolbar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
                self.main_box.append(self.canvas_box)
                self.main_box.append(self.status_box)
                self.main_box.append(self.toolbar_revealer)
        else:
            # Vertical layout (left or right)
            self.main_box.set_orientation(Gtk.Orientation.HORIZONTAL)
            self.toolbar.set_orientation(Gtk.Orientation.VERTICAL)
            
            # Enable vertical scrolling for vertical toolbar
            self.toolbar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.toolbar_scroll.set_vexpand(True)
            self.toolbar_scroll.set_hexpand(False)
            
            # Reset margins
            self.toolbar.set_margin_top(8)
            self.toolbar.set_margin_bottom(8)
            self.toolbar.set_margin_start(8 if self.toolbar_position == 'left' else 0)
            self.toolbar.set_margin_end(8 if self.toolbar_position == 'right' else 0)
            
            # Create vertical container for canvas and status
            content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            content_box.append(self.canvas_box)
            content_box.append(self.status_box)
            
            # Set transition
            if self.toolbar_position == 'left':
                self.toolbar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
                self.main_box.append(self.toolbar_revealer)
                self.main_box.append(content_box)
            else:  # right
                self.toolbar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)
                self.main_box.append(content_box)
                self.main_box.append(self.toolbar_revealer)
        
        logger.info(f"Toolbar position updated to: {self.toolbar_position}")
    
    def set_toolbar_position(self, position: str):
        """Change the toolbar position."""
        if position not in ['top', 'bottom', 'left', 'right']:
            return
        
        self.toolbar_position = position
        self.update_toolbar_position()
        logger.info(f"Toolbar position changed to: {position}")
    
    def set_pen_type(self, pen_type: PenType):
        """Set the pen type and update visual feedback."""
        self.canvas.set_pen_type(pen_type)
        
        # Disable text mode when switching to a drawing tool
        if self.canvas.text_mode:
            self.canvas.set_text_mode(False)
        
        # Disable selection mode when switching to a drawing tool
        if self.canvas.selection_mode:
            self.canvas.disable_selection_mode()
        
        # Remove highlight from text button if it was active
        if hasattr(self, 'text_btn'):
            self.text_btn.remove_css_class("suggested-action")
        
        # Remove highlight from shapes button if it was active
        if hasattr(self, 'shapes_button'):
            self.shapes_button.remove_css_class("suggested-action")
        
        # Remove highlight from selection button if it was active
        if hasattr(self, 'selection_btn'):
            self.selection_btn.remove_css_class("suggested-action")
        
        # Update button styling - remove active state from previous button
        if self.active_tool_button:
            self.active_tool_button.remove_css_class("suggested-action")
        
        # Add active state to current button
        if pen_type in self.tool_buttons:
            self.tool_buttons[pen_type].add_css_class("suggested-action")
            self.active_tool_button = self.tool_buttons[pen_type]
        
        # Update thickness indicator tooltip based on tool
        if hasattr(self, 'thickness_indicator'):
            if pen_type == PenType.ERASER:
                self.thickness_indicator.set_tooltip_text("Eraser Size")
            else:
                self.thickness_indicator.set_tooltip_text("Pen Size")
        
        # Update thickness slider to show current tool's width
        if hasattr(self, 'thickness_scale'):
            self.thickness_scale.set_value(self.canvas.current_width)
        
        # Update status
        if self.current_note:
            self.status_label.set_text(f"{self.current_subject} / {self.current_note}")
        else:
            self.status_label.set_text(f"{pen_type.value.title()} selected")
        logger.info(f"Tool changed to {pen_type.value}")
    
    def set_shape_type(self, shape_type: ShapeType):
        """Set the shape type on the canvas."""
        self.canvas.set_shape_type(shape_type)
        
        # Disable text mode when switching to shape tool
        if self.canvas.text_mode:
            self.canvas.set_text_mode(False)
        
        # Disable selection mode when switching to shape tool
        if self.canvas.selection_mode:
            self.canvas.disable_selection_mode()
        
        # Close the popover
        if hasattr(self, 'shapes_button'):
            popover = self.shapes_button.get_popover()
            if popover:
                popover.popdown()
        
        # Clear active tool button since we're in shape mode
        if self.active_tool_button:
            self.active_tool_button.remove_css_class("suggested-action")
            self.active_tool_button = None
        
        # Remove highlight from text button if it was active
        if hasattr(self, 'text_btn'):
            self.text_btn.remove_css_class("suggested-action")
        
        # Remove highlight from selection button if it was active
        if hasattr(self, 'selection_btn'):
            self.selection_btn.remove_css_class("suggested-action")
        
        # Highlight shapes button
        self.shapes_button.add_css_class("suggested-action")
        
        # Update status
        shape_name = shape_type.value.replace('_', ' ').title()
        if self.current_note:
            self.status_label.set_text(f"{self.current_subject} / {self.current_note}")
        else:
            self.status_label.set_text(f"Shape: {shape_name}")
        logger.info(f"Shape tool changed to {shape_name}")
    
    def on_shape_style_toggled(self, button):
        """Handle fill/outline toggle"""
        if not button.get_active():
            return
        
        # Ensure only one is active
        if button == self.shape_fill_btn:
            self.shape_outline_btn.set_active(False)
            if self.canvas:
                self.canvas.set_shape_filled(True)
        else:
            self.shape_fill_btn.set_active(False)
            if self.canvas:
                self.canvas.set_shape_filled(False)
    
    def on_line_style_changed(self, style: str):
        """Handle line style change"""
        # Deactivate other line style buttons
        if style == 'solid':
            self.shape_dashed_btn.set_active(False)
            self.shape_dotted_btn.set_active(False)
        elif style == 'dashed':
            self.shape_solid_btn.set_active(False)
            self.shape_dotted_btn.set_active(False)
        elif style == 'dotted':
            self.shape_solid_btn.set_active(False)
            self.shape_dashed_btn.set_active(False)
        
        if self.canvas:
            self.canvas.set_shape_line_style(style)
    
    def set_color(self, color):
        """Set the pen color."""
        self.canvas.set_color(color)
        # Update thickness indicator and preview
        if hasattr(self, 'thickness_indicator'):
            current_value = self.thickness_vertical_scale.get_value() if hasattr(self, 'thickness_vertical_scale') else 10
            self.update_thickness_indicator(current_value)
        if hasattr(self, 'thickness_popover_preview'):
            self.thickness_popover_preview.queue_draw()
    
    def on_width_changed(self, scale):
        """Handle width scale change."""
        width = scale.get_value()
        self.canvas.set_width(width)
    
    def on_palm_reject_toggled(self, toggle):
        """Handle palm rejection toggle."""
        is_active = toggle.get_active()
        self.canvas.set_palm_rejection_mode(is_active)
        
        # Update status indicator
        if is_active:
            self.palm_status_label.set_text("🖐️ Palm Rejection: ON")
        else:
            self.palm_status_label.set_text("🖐️ Palm Rejection: OFF")
        
        logger.info(f"Palm rejection: {'enabled' if is_active else 'disabled'}")
    
    def on_clear_clicked(self):
        """Handle clear button click."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Clear entire canvas?"
        )
        dialog.set_property('secondary-text', 'This will erase all your drawings. This action cannot be undone.')
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        clear_button = dialog.add_button("Clear Canvas", Gtk.ResponseType.YES)
        clear_button.add_css_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.connect('response', self.on_clear_response)
        dialog.present()
    
    def on_clear_response(self, dialog, response):
        """Handle clear dialog response."""
        if response == Gtk.ResponseType.YES:
            self.canvas.clear_canvas()
        dialog.destroy()
    
    def on_save_clicked(self):
        """Handle save button click with feedback."""
        if self.current_file:
            self.save_current_note()
            self.status_label.set_text(f"💾 Saved: {self.current_subject}/{self.current_note}")
            # Reset status after 3 seconds
            GLib.timeout_add_seconds(3, lambda: self.status_label.set_text(f"{self.current_subject} / {self.current_note}") if hasattr(self, 'status_label') else False)
        else:
            self.status_label.set_text("⚠️ No note is currently open")
    
    def save_current_note(self):
        """Save the current note."""
        if self.current_file:
            try:
                self.canvas.document.save_to_file(self.current_file)
                logger.info(f"Saved: {self.current_subject}/{self.current_note}")
            except Exception as e:
                logger.error(f"Error saving note: {e}")
    
    def on_export_png(self, action, param):
        """Export to PNG."""
        dialog = Gtk.FileChooserDialog(
            title="Export to PNG",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Export", Gtk.ResponseType.ACCEPT)
        
        filter_png = Gtk.FileFilter()
        filter_png.set_name("PNG Images")
        filter_png.add_pattern("*.png")
        dialog.add_filter(filter_png)
        
        dialog.set_current_name("note.png")
        dialog.connect('response', self.on_export_png_response)
        dialog.present()
    
    def on_export_png_response(self, dialog, response):
        """Handle PNG export dialog response."""
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            filepath = file.get_path()
            
            if not filepath.endswith('.png'):
                filepath += '.png'
            
            try:
                self.canvas.export_to_png(filepath)
                self.status_label.set_text(f"Exported: {Path(filepath).name}")
            except Exception as e:
                logger.error(f"Error exporting PNG: {e}")
                self.show_error(f"Failed to export PNG: {e}")
        
        dialog.destroy()
    
    def on_export_pdf(self, action, param):
        """Export to PDF."""
        dialog = Gtk.FileChooserDialog(
            title="Export to PDF",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Export", Gtk.ResponseType.ACCEPT)
        
        filter_pdf = Gtk.FileFilter()
        filter_pdf.set_name("PDF Documents")
        filter_pdf.add_pattern("*.pdf")
        dialog.add_filter(filter_pdf)
        
        dialog.set_current_name("note.pdf")
        dialog.connect('response', self.on_export_pdf_response)
        dialog.present()
    
    def on_export_pdf_response(self, dialog, response):
        """Handle PDF export dialog response."""
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            filepath = file.get_path()
            
            if not filepath.endswith('.pdf'):
                filepath += '.pdf'
            
            try:
                self.export_to_pdf(filepath)
                self.status_label.set_text(f"Exported: {Path(filepath).name}")
            except Exception as e:
                logger.error(f"Error exporting PDF: {e}")
                self.show_error(f"Failed to export PDF: {e}")
        
        dialog.destroy()
    
    def export_to_pdf(self, filepath: str):
        """Export canvas to PDF."""
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        
        # Export to PNG first
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        
        self.canvas.export_to_png(tmp_path)
        
        # Create PDF with the PNG
        pdf = canvas.Canvas(filepath, pagesize=A4)
        pdf.drawImage(tmp_path, 0, 0, width=A4[0], height=A4[1])
        pdf.save()
        
        # Clean up
        os.unlink(tmp_path)
        logger.info(f"Exported to PDF: {filepath}")
    
    def on_toggle_dark(self, action, param):
        """Toggle dark mode."""
        current = self.canvas.dark_mode
        self.canvas.set_dark_mode(not current)
        
        # Also update app style
        style_manager = Adw.StyleManager.get_default()
        if current:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    
    def on_fullscreen(self, action, param):
        """Toggle fullscreen mode."""
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()
    
    def on_device_info(self, action, param):
        """Show device information dialog."""
        info = self.input_handler.get_device_info()
        
        message = f"""Device Information:

Evdev Available: {info['evdev_available']}
Monitoring: {info['monitoring']}
Stylus Active: {info['stylus_active']}
Touch Enabled: {info['touch_enabled']}

Stylus Devices ({len(info['stylus_devices'])}):
"""
        for dev in info['stylus_devices']:
            message += f"  • {dev['name']}\n    {dev['path']}\n"
        
        message += f"\nTouch Devices ({len(info['touch_devices'])}):\n"
        for dev in info['touch_devices']:
            message += f"  • {dev['name']}\n    {dev['path']}\n"
        
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Device Information"
        )
        dialog.set_property('secondary-text', message)
        dialog.connect('response', lambda d, r: d.destroy())
        dialog.present()
    
    def show_error(self, message: str):
        """Show an error dialog."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Error"
        )
        dialog.set_property('secondary-text', message)
        dialog.connect('response', lambda d, r: d.destroy())
        dialog.present()
    
    def setup_autosave(self):
        """Set up autosave timer."""
        # Autosave every 30 seconds
        self.autosave_timeout = GLib.timeout_add_seconds(30, self.do_autosave)
    
    def do_autosave(self):
        """Perform autosave."""
        if self.current_file and self.current_subject and self.current_note:
            self.save_current_note()
        return True  # Continue autosave timer
    
    def do_close_request(self):
        """Handle window close request."""
        self.input_handler.stop_monitoring()
        if self.autosave_timeout:
            GLib.source_remove(self.autosave_timeout)
        return False  # Allow close
    
    def on_prev_page(self):
        """Go to previous page."""
        self.canvas.prev_page()
        self.update_page_label()
        # Autosave when changing pages
        if self.current_file:
            self.save_current_note()
    
    def on_next_page(self):
        """Go to next page."""
        self.canvas.next_page()
        self.update_page_label()
        # Autosave when changing pages
        if self.current_file:
            self.save_current_note()
    
    def on_scroll_changed(self, adjustment):
        """Handle scroll position changes to update current page."""
        from ..core.stroke import NoteType
        if self.canvas.document.note_type == NoteType.A4_NOTES:
            scroll_y = adjustment.get_value()
            self.canvas.update_current_page_from_scroll(scroll_y)
    
    def update_page_label(self):
        """Update the page indicator label."""
        from ..core.stroke import NoteType
        if self.canvas.document.note_type == NoteType.A4_NOTES:
            current = self.canvas.document.current_page
            total = self.canvas.document.get_total_pages()
            self.page_label.set_text(f"{current}/{total}")
    
    def on_template_changed(self, dropdown, _param):
        """Handle page template change."""
        from ..core.stroke import PageTemplate, NoteType
        
        # Only apply to A4 notes
        if self.canvas.document.note_type != NoteType.A4_NOTES:
            return
        
        template_idx = dropdown.get_selected()
        if template_idx == 0:
            new_template = PageTemplate.BLANK
        elif template_idx == 1:
            new_template = PageTemplate.RULED
        elif template_idx == 2:
            new_template = PageTemplate.GRID
        elif template_idx == 3:
            new_template = PageTemplate.DOT_GRID
        else:
            return
        
        # Update the document template
        self.canvas.document.page_template = new_template
        self.canvas.queue_draw()
        
        # Autosave with new template
        if self.current_file:
            self.save_current_note()
        
        self.status_label.set_text(f"Template changed to {new_template.value}")
