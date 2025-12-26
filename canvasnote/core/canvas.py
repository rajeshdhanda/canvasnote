"""Canvas widget for drawing with Cairo."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf
import cairo
from typing import Optional
import logging
from pathlib import Path

from .stroke import DrawingDocument, Stroke, Point, PenType, Shape, ShapeType, Selection, SelectionMode, TextBox
import copy

logger = logging.getLogger(__name__)


class DrawingCanvas(Gtk.DrawingArea):
    """Custom drawing area with Cairo rendering."""
    
    def __init__(self):
        super().__init__()
        
        self.document = DrawingDocument()
        self.current_stroke: Optional[Stroke] = None
        self.undo_stack = []
        self.redo_stack = []
        
        # Drawing state
        self.is_drawing = False
        self.last_x = 0
        self.last_y = 0
        
        # Current tool settings
        self.current_pen_type = PenType.PEN
        self.current_color = (0.0, 0.0, 0.0, 1.0)  # Black
        self.current_width = 2.0
        
        # Separate width storage for pen and eraser
        self.pen_width = 3.0  # Default pen width
        self.eraser_width = 20.0  # Default eraser width (thicker)
        
        # Shape drawing mode
        self.shape_mode = False
        self.current_shape_type = None
        self.shape_start_x = 0.0
        self.shape_start_y = 0.0
        self.shape_preview = None
        self.shape_filled = False
        self.shape_line_style = 'solid'
        
        # Selection mode
        self.selection_mode = False
        self.selection = Selection()
        self.selection_box_start_x = 0.0
        self.selection_box_start_y = 0.0
        self.selection_box_end_x = 0.0
        self.selection_box_end_y = 0.0
        self.is_selecting = False
        self.is_dragging_selection = False
        self.drag_start_x = 0.0
        self.drag_start_y = 0.0
        self.clipboard = None  # Stores copied selection
        
        # Text mode
        self.text_mode = False
        self.current_text_box: Optional[TextBox] = None
        self.text_cursor_pos = 0  # Cursor position in current text
        self.text_font_size = 16.0
        self.text_bold = False
        self.text_italic = False
        self.text_underline = False
        
        # Canvas transform
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.zoom = 1.0
        
        # Dark mode
        self.dark_mode = False
        
        # Palm rejection mode - when active, only stylus input is accepted
        self.palm_rejection_mode = True  # Always on by default when drawing tools active
        
        # Pen-mode lock - when drawing, disable zoom/pan gestures
        self.pen_mode_lock_during_draw = True
        
        # Eraser mode: 'stroke' (entire stroke) or 'pixel' (partial erase)
        self.eraser_mode = 'pixel'  # Default to pixel eraser for more precise control
        
        # Custom cursors for tools
        self.cursors = {}
        self.load_custom_cursors()
        
        # Set up drawing function
        self.set_draw_func(self.on_draw)
        
        # Set up size
        self.set_size_request(800, 600)
        self.set_hexpand(True)
        self.set_vexpand(True)
        
        # Content size for scrolling (will be updated dynamically)
        # Start with viewport size to prevent horizontal scroll
        self.set_content_width(800)
        self.set_content_height(3000)
        
        # Make canvas focusable and able to receive events
        self.set_can_focus(True)
        self.set_focusable(True)
        self.set_can_target(True)
        
        # Enable events
        self.setup_gestures()
        
        # Add keyboard controller for text input
        self.key_controller = Gtk.EventControllerKey.new()
        self.key_controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(self.key_controller)
        
        # Callback for page updates (will be set by main window)
        self.on_page_changed_callback = None
        
        logger.info("DrawingCanvas initialized")
    
    def get_asset_path(self, filename):
        """Get the full path to an asset file."""
        assets_dir = Path(__file__).parent.parent / "assets"
        return str(assets_dir / filename)
    
    def load_custom_cursors(self):
        """Load custom cursors for each tool from PNG assets."""
        # Define cursor mappings with appropriate hotspot positions
        # Hotspot is where the actual writing/erasing point is located
        cursor_mappings = {
            # Pen: tip is at bottom-left (x=4, y=28 for 32x32 icon)
            PenType.PEN: ("pen.png", 4, 28),
            # Pencil: tip is at bottom-left (x=4, y=28 for 32x32 icon)
            PenType.PENCIL: ("pencil.png", 4, 28),
            # Highlighter: tip is at bottom-left (x=6, y=26 for 32x32 icon)
            PenType.HIGHLIGHTER: ("highlighter.png", 6, 26),
            # Eraser: center-bottom of eraser (x=16, y=24 for 32x32 icon)
            PenType.ERASER: ("eraser.png", 16, 24)
        }
        
        try:
            for pen_type, (icon_file, hotspot_x, hotspot_y) in cursor_mappings.items():
                icon_path = self.get_asset_path(icon_file)
                if Path(icon_path).exists():
                    # Load the PNG as a pixbuf
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        icon_path, 32, 32, True
                    )
                    # Create texture from pixbuf
                    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                    # Create cursor from texture with hotspot at the tool's tip/working point
                    cursor = Gdk.Cursor.new_from_texture(texture, hotspot_x, hotspot_y, None)
                    self.cursors[pen_type] = cursor
                    logger.info(f"Loaded cursor for {pen_type.value} with hotspot at ({hotspot_x}, {hotspot_y})")
                else:
                    logger.warning(f"Cursor icon not found: {icon_path}")
        except Exception as e:
            logger.error(f"Error loading custom cursors: {e}")
    
    def update_cursor(self):
        """Update the canvas cursor based on current tool."""
        if self.selection_mode:
            # Use default cursor for selection mode
            self.set_cursor(Gdk.Cursor.new_from_name("default", None))
        elif self.text_mode:
            # Use text cursor for text mode
            self.set_cursor(Gdk.Cursor.new_from_name("text", None))
        elif self.shape_mode:
            # Use crosshair for shape drawing
            self.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))
        elif self.current_pen_type in self.cursors:
            # Use custom cursor for drawing tools
            self.set_cursor(self.cursors[self.current_pen_type])
        else:
            # Fallback to crosshair
            self.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))
    
    def setup_gestures(self):
        """Set up gesture controllers for input."""
        # Stylus/Touch drawing gesture
        self.gesture_stylus = Gtk.GestureStylus.new()
        self.gesture_stylus.connect('down', self.on_stylus_down)
        self.gesture_stylus.connect('motion', self.on_stylus_motion)
        self.gesture_stylus.connect('up', self.on_stylus_up)
        self.add_controller(self.gesture_stylus)
        
        # Mouse/Universal drawing gesture - handles all pointer devices
        self.gesture_drag = Gtk.GestureDrag.new()
        self.gesture_drag.set_button(1)  # Left click
        # Set to accept all device types (mouse, pen, touchscreen)
        self.gesture_drag.set_exclusive(False)
        self.gesture_drag.connect('drag-begin', self.on_drag_begin)
        self.gesture_drag.connect('drag-update', self.on_drag_update)
        self.gesture_drag.connect('drag-end', self.on_drag_end)
        self.add_controller(self.gesture_drag)
        
        # Motion controller for drawing continuation
        self.motion_controller = Gtk.EventControllerMotion.new()
        self.motion_controller.connect('motion', self.on_motion)
        self.add_controller(self.motion_controller)
        
        # Legacy event controller to catch all pointer events
        self.legacy_controller = Gtk.EventControllerLegacy.new()
        self.legacy_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.legacy_controller.connect('event', self.on_legacy_event)
        self.add_controller(self.legacy_controller)
        
        # Simple gesture click to detect any clicks
        self.gesture_click = Gtk.GestureClick.new()
        self.gesture_click.set_button(0)  # Listen to all buttons
        self.gesture_click.set_exclusive(True)  # Claim events exclusively
        self.gesture_click.connect('pressed', self.on_click_pressed)
        self.gesture_click.connect('released', self.on_click_released)
        self.add_controller(self.gesture_click)
        
        # Right-click gesture for context menu
        self.gesture_right_click = Gtk.GestureClick.new()
        self.gesture_right_click.set_button(3)  # Right mouse button
        self.gesture_right_click.connect('pressed', self.on_right_click)
        self.add_controller(self.gesture_right_click)
        
        # Zoom gesture for pinch-to-zoom (2-finger)
        self.gesture_zoom = Gtk.GestureZoom.new()
        self.gesture_zoom.connect('scale-changed', self.on_zoom_changed)
        self.gesture_zoom.connect('begin', self.on_zoom_begin)
        self.add_controller(self.gesture_zoom)
        
        # Store initial zoom level for relative scaling
        self.zoom_start = 1.0
        
        # Scroll controller for Ctrl+Wheel zoom
        self.scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        self.scroll_controller.connect('scroll', self.on_scroll)
        self.add_controller(self.scroll_controller)
        
        # Increase priority for legacy controller to catch events first
        self.legacy_controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        
        # Create context menu for selection
        self.create_context_menu()
        
        logger.info("Gestures configured")
    
    def create_context_menu(self):
        """Create context menu for selection operations."""
        self.context_menu = Gtk.PopoverMenu()
        
        # Create menu model
        menu = Gio.Menu()
        
        # Selection operations section
        selection_section = Gio.Menu()
        selection_section.append("Select All", "canvas.select_all")
        selection_section.append("Clear Selection", "canvas.clear_selection")
        menu.append_section(None, selection_section)
        
        # Edit operations section
        edit_section = Gio.Menu()
        edit_section.append("Copy", "canvas.copy")
        edit_section.append("Cut", "canvas.cut")
        edit_section.append("Paste", "canvas.paste")
        edit_section.append("Duplicate", "canvas.duplicate")
        menu.append_section(None, edit_section)
        
        # Delete section
        delete_section = Gio.Menu()
        delete_section.append("Delete", "canvas.delete")
        menu.append_section(None, delete_section)
        
        self.context_menu.set_menu_model(menu)
        self.context_menu.set_parent(self)
        self.context_menu.set_has_arrow(False)
        
        # Create action group for context menu actions
        self.action_group = Gio.SimpleActionGroup()
        
        # Define actions
        actions = [
            ('select_all', self.on_context_select_all),
            ('clear_selection', self.on_context_clear_selection),
            ('copy', self.on_context_copy),
            ('cut', self.on_context_cut),
            ('paste', self.on_context_paste),
            ('duplicate', self.on_context_duplicate),
            ('delete', self.on_context_delete),
        ]
        
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.action_group.add_action(action)
        
        self.insert_action_group('canvas', self.action_group)
        
        logger.info("Context menu created")
    
    def on_key_pressed(self, controller, keyval, keycode, state):
        """Handle keyboard input."""
        # Handle text input in text mode
        if self.text_mode:
            return self.handle_text_key_press(keyval, keycode, state)
        
        return False
    
    def on_right_click(self, gesture, n_press, x, y):
        """Handle right-click to show context menu."""
        logger.info(f"Right-click at ({x:.1f}, {y:.1f})")
        
        # Only show menu in selection mode or if there's something to paste
        if self.selection_mode or self.clipboard is not None:
            # Set menu position
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            self.context_menu.set_pointing_to(rect)
            
            # Show menu
            self.context_menu.popup()
            logger.info("Context menu shown")
            return True
        
        return False
    
    def on_context_select_all(self, action, parameter):
        """Handle Select All from context menu."""
        self.select_all()
    
    def on_context_clear_selection(self, action, parameter):
        """Handle Clear Selection from context menu."""
        self.selection.clear()
        self.queue_draw()
        logger.info("Selection cleared from context menu")
    
    def on_context_copy(self, action, parameter):
        """Handle Copy from context menu."""
        self.copy_selection()
    
    def on_context_cut(self, action, parameter):
        """Handle Cut from context menu."""
        self.copy_selection()
        self.delete_selection()
    
    def on_context_paste(self, action, parameter):
        """Handle Paste from context menu."""
        self.paste_selection()
    
    def on_context_duplicate(self, action, parameter):
        """Handle Duplicate from context menu."""
        self.duplicate_selection()
    
    def on_context_delete(self, action, parameter):
        """Handle Delete from context menu."""
        self.delete_selection()
    
    def on_draw(self, area, cr, width, height):
        """Draw the canvas content."""
        # Background
        if self.dark_mode:
            cr.set_source_rgb(0.15, 0.15, 0.15)
        else:
            cr.set_source_rgb(0.95, 0.95, 0.95)  # Very light gray background
        cr.paint()
        
        # Apply transformations
        cr.translate(self.pan_x, self.pan_y)
        cr.scale(self.zoom, self.zoom)
        
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            # Draw all pages vertically with gaps
            self.draw_all_pages(cr, width, height)
        else:
            # Canvas mode - draw with proper layering
            current_strokes = self.document.get_current_strokes()
            
            # Draw strokes with z-order: highlighters first, then others
            self.draw_strokes_by_layer(cr, current_strokes)
            
            current_shapes = self.document.get_current_shapes()
            for shape in current_shapes:
                self.draw_shape(cr, shape)
            
            # Draw text boxes
            current_text_boxes = self.document.get_current_text_boxes()
            for text_box in current_text_boxes:
                self.draw_text_box(cr, text_box)
            
            # Draw current text box being edited
            if self.current_text_box:
                self.draw_text_box(cr, self.current_text_box, show_cursor=True)
            
            # Draw current stroke being drawn
            if self.current_stroke and len(self.current_stroke.points) > 0:
                self.draw_stroke(cr, self.current_stroke)
            
            # Draw shape preview
            if self.shape_preview:
                self.draw_shape(cr, self.shape_preview, preview=True)
            
            # Draw selection box and selected items
            if self.selection_mode:
                if self.is_selecting:
                    self.draw_selection_box(cr)
                if not self.selection.is_empty():
                    self.draw_selection_bounds(cr)
    
    def get_page_layout(self, canvas_width):
        """Calculate page layout with 10% padding on each side."""
        # Calculate page position (10% padding on each side = 80% width)
        canvas_width_unzoomed = canvas_width / self.zoom
        page_width = self.document.width
        
        # Center the page horizontally - exactly 10% padding on each side
        offset_x = canvas_width_unzoomed * 0.1
        
        return offset_x
    
    def draw_all_pages(self, cr, canvas_width, canvas_height):
        """Draw all pages vertically stacked for scrolling."""
        page_width = self.document.width
        page_height = self.document.height
        page_gap = 20  # Gap between pages for visual separation
        top_padding = 30  # Padding at the top
        
        offset_x = self.get_page_layout(canvas_width)
        
        # Update content size for scrolling
        page_numbers = sorted(self.document.pages.keys())
        total_height = top_padding + len(page_numbers) * (page_height + page_gap) + 100
        total_height_zoomed = int(total_height * self.zoom)
        
        # Force content width to exactly match canvas width (no horizontal scroll)
        # Content height allows vertical scrolling only
        canvas_width_int = int(canvas_width) if canvas_width > 0 else 800
        self.set_content_width(canvas_width_int)
        self.set_content_height(max(total_height_zoomed, canvas_height + 100))
        
        # Get all page numbers
        page_numbers = sorted(self.document.pages.keys())
        
        for page_num in page_numbers:
            # Calculate Y position for this page
            page_y = top_padding + (page_num - 1) * (page_height + page_gap)
            
            cr.save()
            cr.translate(offset_x, page_y)
            
            # Draw subtle shadow for depth
            shadow_offset = 4 / self.zoom
            cr.set_source_rgba(0, 0, 0, 0.1)
            cr.rectangle(shadow_offset, shadow_offset, page_width, page_height)
            cr.fill()
            
            # Draw page background (white)
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.rectangle(0, 0, page_width, page_height)
            cr.fill()
            
            # Draw page boundary with highlight for current page
            if self.document.current_page == page_num:
                # Active page - blue highlight
                cr.set_source_rgba(0.3, 0.5, 0.9, 0.3)
                cr.set_line_width(3 / self.zoom)
            else:
                # Inactive page - gray border
                cr.set_source_rgba(0.8, 0.8, 0.8, 0.6)
                cr.set_line_width(1 / self.zoom)
            cr.rectangle(0, 0, page_width, page_height)
            cr.stroke()
            
            # Draw template for this page
            self.draw_page_template_at(cr, 0, 0, page_width, page_height)
            
            # Draw strokes for this page with proper layering
            page_strokes = self.document.pages.get(page_num, [])
            self.draw_strokes_by_layer(cr, page_strokes)
            
            # Draw shapes for this page
            page_shapes = self.document.page_shapes.get(page_num, [])
            for shape in page_shapes:
                self.draw_shape(cr, shape)
            
            # Draw text boxes for this page
            page_text_boxes = self.document.page_text_boxes.get(page_num, [])
            for text_box in page_text_boxes:
                self.draw_text_box(cr, text_box)
            
            # Draw current stroke if on this page
            if self.document.current_page == page_num:
                if self.current_stroke and len(self.current_stroke.points) > 0:
                    self.draw_stroke(cr, self.current_stroke)
                
                if self.shape_preview:
                    self.draw_shape(cr, self.shape_preview, preview=True)
                
                # Draw current text box being edited
                if self.current_text_box:
                    self.draw_text_box(cr, self.current_text_box, show_cursor=True)
                
                if self.selection_mode:
                    if self.is_selecting:
                        self.draw_selection_box(cr)
                    if not self.selection.is_empty():
                        self.draw_selection_bounds(cr)
            
            # Draw page number at bottom right corner
            cr.set_source_rgba(0.6, 0.6, 0.6, 0.5)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(10 / self.zoom)
            page_text = f"{page_num}"
            extents = cr.text_extents(page_text)
            cr.move_to(page_width - extents.width - 15, page_height - 10)
            cr.show_text(page_text)
            
            cr.restore()
    
    def draw_page_boundary(self, cr, canvas_width, canvas_height):
        """Draw page boundary for A4 notes (legacy method - now using draw_all_pages)."""
        # This is kept for backward compatibility but not used in multi-page layout
        page_width = self.document.width
        page_height = self.document.height
        
        cr.save()
        cr.set_source_rgba(0.7, 0.7, 0.7, 0.3)
        cr.set_line_width(2 / self.zoom)
        cr.rectangle(0, 0, page_width, page_height)
        cr.stroke()
        cr.restore()
    
    def draw_page_template(self, cr, canvas_width, canvas_height):
        """Draw the template pattern for A4 pages (legacy - now using draw_page_template_at)."""
        page_width = self.document.width
        page_height = self.document.height
        self.draw_page_template_at(cr, 0, 0, page_width, page_height)
    
    def draw_page_template_at(self, cr, x, y, page_width, page_height):
        """Draw the template pattern at a specific position."""
        from .stroke import PageTemplate
        
        cr.save()
        
        # Set template line color (light gray/blue)
        if self.dark_mode:
            cr.set_source_rgba(0.3, 0.3, 0.35, 0.4)
        else:
            cr.set_source_rgba(0.7, 0.75, 0.85, 0.5)
        
        template = self.document.page_template
        
        if template == PageTemplate.RULED:
            # Draw horizontal lines like ruled notebook paper
            line_spacing = 30  # pixels between lines
            margin_top = 50  # top margin before lines start
            
            cr.set_line_width(0.5 / self.zoom)  # Adjust for zoom
            line_y = margin_top
            while line_y < page_height - 20:
                cr.move_to(x + 40, line_y)
                cr.line_to(x + page_width - 40, line_y)
                cr.stroke()
                line_y += line_spacing
        
        elif template == PageTemplate.GRID:
            # Draw square grid
            grid_size = 25  # pixels per grid square
            cr.set_line_width(0.3 / self.zoom)  # Adjust for zoom
            
            # Vertical lines
            grid_x = 0
            while grid_x <= page_width:
                cr.move_to(x + grid_x, y)
                cr.line_to(x + grid_x, y + page_height)
                cr.stroke()
                grid_x += grid_size
            
            # Horizontal lines
            grid_y = 0
            while grid_y <= page_height:
                cr.move_to(x, y + grid_y)
                cr.line_to(x + page_width, y + grid_y)
                cr.stroke()
                grid_y += grid_size
        
        elif template == PageTemplate.DOT_GRID:
            # Draw dot grid pattern
            dot_spacing = 20  # pixels between dots
            dot_radius = 1.0 / self.zoom  # dot size adjusted for zoom
            
            dot_x = dot_spacing
            while dot_x < page_width:
                dot_y = dot_spacing
                while dot_y < page_height:
                    cr.arc(x + dot_x, y + dot_y, dot_radius, 0, 2 * 3.14159)
                    cr.fill()
                    dot_y += dot_spacing
                dot_x += dot_spacing
        
        # PageTemplate.BLANK draws nothing (just white background)
        
        cr.restore()
    
    def draw_strokes_by_layer(self, cr, strokes):
        """Draw strokes in proper z-order: highlighters first, then others."""
        # Layer 1: Highlighters (background layer)
        for stroke in strokes:
            if stroke.pen_type == PenType.HIGHLIGHTER:
                self.draw_stroke(cr, stroke)
        
        # Layer 2: Regular strokes (pens, pencils) on top
        # Skip eraser strokes - they should never be drawn
        for stroke in strokes:
            if stroke.pen_type != PenType.HIGHLIGHTER and stroke.pen_type != PenType.ERASER:
                self.draw_stroke(cr, stroke)
    
    def draw_stroke(self, cr, stroke: Stroke):
        """Draw a single stroke."""
        # Never draw eraser strokes - they're only for tracking the eraser path
        if stroke.pen_type == PenType.ERASER:
            return
        
        if len(stroke.points) < 2:
            if len(stroke.points) == 1:
                # Draw a dot
                p = stroke.points[0]
                if stroke.pen_type == PenType.HIGHLIGHTER:
                    # Highlighter is semi-transparent
                    cr.set_source_rgba(stroke.color[0], stroke.color[1], stroke.color[2], 0.4)
                else:
                    cr.set_source_rgba(*stroke.color)
                cr.arc(p.x, p.y, stroke.width / 2, 0, 2 * 3.14159)
                cr.fill()
            return
        
        # Set line properties based on pen type
        if stroke.pen_type == PenType.HIGHLIGHTER:
            # Highlighter: semi-transparent, square caps, wider
            cr.set_source_rgba(stroke.color[0], stroke.color[1], stroke.color[2], 0.4)
            cr.set_line_cap(cairo.LINE_CAP_SQUARE)
            cr.set_line_join(cairo.LINE_JOIN_BEVEL)
        elif stroke.pen_type == PenType.PENCIL:
            # Pencil: full opacity but textured appearance
            cr.set_source_rgba(*stroke.color)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
        else:
            # Pen: smooth and opaque
            cr.set_source_rgba(*stroke.color)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
        
        # Draw the stroke with variable width based on pressure
        for i in range(len(stroke.points) - 1):
            p1 = stroke.points[i]
            p2 = stroke.points[i + 1]
            
            # Calculate width based on pressure and pen type
            if stroke.pen_type == PenType.HIGHLIGHTER:
                # Highlighter is wider and more uniform
                width = stroke.width * 2.5  # Make highlighter thicker
            elif stroke.pen_type == PenType.PENCIL:
                # Pencil has more pressure variation and is slightly thinner
                width = stroke.width * p1.pressure * 0.8
                
                # Apply tilt-based width variation (simulates pencil angle)
                # Higher tilt values (pen tilted) = wider stroke (shading)
                tilt_magnitude = (p1.tilt_x ** 2 + p1.tilt_y ** 2) ** 0.5
                if tilt_magnitude > 0.1:  # If tilt is significant
                    # Increase width up to 1.5x when tilted
                    tilt_factor = 1.0 + (tilt_magnitude * 0.5)
                    width *= tilt_factor
                    # Reduce opacity slightly when tilted (lighter shading)
                    tilt_opacity = max(0.6, 1.0 - (tilt_magnitude * 0.2))
                    cr.set_source_rgba(stroke.color[0], stroke.color[1], stroke.color[2], 
                                     stroke.color[3] * tilt_opacity)
                
                # Add slight variation for texture
                import random
                random.seed(int(p1.x * p1.y))  # Deterministic randomness
                width *= (0.9 + random.random() * 0.2)
            else:
                # Pen has normal pressure response
                width = stroke.width * p1.pressure
            
            cr.set_line_width(max(0.5, width))
            cr.move_to(p1.x, p1.y)
            cr.line_to(p2.x, p2.y)
            cr.stroke()
            
            # For pencil, add texture with additional faint lines
            if stroke.pen_type == PenType.PENCIL and i % 2 == 0:
                cr.save()
                cr.set_source_rgba(stroke.color[0], stroke.color[1], stroke.color[2], 0.1)
                cr.set_line_width(max(0.3, width * 0.5))
                # Slight offset for texture
                offset = 0.5
                cr.move_to(p1.x + offset, p1.y + offset)
                cr.line_to(p2.x + offset, p2.y + offset)
                cr.stroke()
                cr.restore()
    
    def draw_shape(self, cr, shape: Shape, preview=False):
        """Draw a geometric shape."""
        import math
        
        cr.save()
        
        # Set color and line properties
        if preview:
            # Preview with dashed line
            cr.set_source_rgba(*shape.color[:3], 0.6)
            cr.set_dash([5, 5])
        else:
            cr.set_source_rgba(*shape.color)
            # Apply line style
            if shape.line_style == 'dashed':
                cr.set_dash([10, 5])  # 10px line, 5px gap
            elif shape.line_style == 'dotted':
                cr.set_dash([2, 4])  # 2px dot, 4px gap
            # else: solid (no dash)
        
        cr.set_line_width(shape.width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        
        x1, y1 = shape.start_x, shape.start_y
        x2, y2 = shape.end_x, shape.end_y
        
        if shape.shape_type == ShapeType.STRAIGHT_LINE:
            # Draw straight line
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()
            
        elif shape.shape_type == ShapeType.RECTANGLE:
            # Draw rectangle
            width = x2 - x1
            height = y2 - y1
            cr.rectangle(x1, y1, width, height)
            if shape.filled:
                cr.fill()
            else:
                cr.stroke()
                
        elif shape.shape_type == ShapeType.CIRCLE:
            # Draw circle/ellipse
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            rx = abs(x2 - x1) / 2
            ry = abs(y2 - y1) / 2
            
            # Prevent invalid matrix error when radius is zero
            if rx < 0.1 or ry < 0.1:
                return
            
            # Draw ellipse using arc transformations
            cr.save()
            cr.translate(cx, cy)
            cr.scale(rx, ry)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            
            if shape.filled:
                cr.fill()
            else:
                cr.stroke()
                
        elif shape.shape_type == ShapeType.TRIANGLE:
            # Draw equilateral triangle
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            height = abs(y2 - y1)
            width = abs(x2 - x1)
            
            # Three points of triangle
            cr.move_to(cx, y1)  # Top point
            cr.line_to(x1, y2)  # Bottom left
            cr.line_to(x2, y2)  # Bottom right
            cr.close_path()
            
            if shape.filled:
                cr.fill()
            else:
                cr.stroke()
                
        elif shape.shape_type == ShapeType.PENTAGON:
            # Draw regular pentagon
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            radius = min(abs(x2 - x1), abs(y2 - y1)) / 2
            
            # Pentagon has 5 sides, starting from top
            for i in range(5):
                angle = (i * 2 * math.pi / 5) - math.pi / 2  # Start from top
                px = cx + radius * math.cos(angle)
                py = cy + radius * math.sin(angle)
                
                if i == 0:
                    cr.move_to(px, py)
                else:
                    cr.line_to(px, py)
            
            cr.close_path()
            
            if shape.filled:
                cr.fill()
            else:
                cr.stroke()
                
        elif shape.shape_type == ShapeType.ARROW:
            # Draw arrow from start to end point
            # Calculate arrow direction
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy)
            
            if length > 0:
                # Normalize direction
                dx /= length
                dy /= length
                
                # Arrow dimensions
                arrow_head_length = min(20, length * 0.3)  # 30% of line or 20px
                arrow_head_width = arrow_head_length * 0.6
                
                # Draw main line
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
                cr.stroke()
                
                # Calculate arrow head points
                # Perpendicular vector
                perp_x = -dy
                perp_y = dx
                
                # Arrow head tip is at end point
                # Calculate base of arrow head
                base_x = x2 - dx * arrow_head_length
                base_y = y2 - dy * arrow_head_length
                
                # Two points at the base
                p1_x = base_x + perp_x * arrow_head_width / 2
                p1_y = base_y + perp_y * arrow_head_width / 2
                p2_x = base_x - perp_x * arrow_head_width / 2
                p2_y = base_y - perp_y * arrow_head_width / 2
                
                # Draw arrow head (filled triangle)
                cr.move_to(x2, y2)
                cr.line_to(p1_x, p1_y)
                cr.line_to(p2_x, p2_y)
                cr.close_path()
                cr.fill()
        
        cr.restore()
    
    def draw_selection_box(self, cr):
        """Draw the selection box while selecting."""
        cr.save()
        
        # Draw semi-transparent blue selection box
        cr.set_source_rgba(0.2, 0.5, 0.9, 0.2)
        x1 = min(self.selection_box_start_x, self.selection_box_end_x)
        y1 = min(self.selection_box_start_y, self.selection_box_end_y)
        x2 = max(self.selection_box_start_x, self.selection_box_end_x)
        y2 = max(self.selection_box_start_y, self.selection_box_end_y)
        cr.rectangle(x1, y1, x2 - x1, y2 - y1)
        cr.fill()
        
        # Draw border
        cr.set_source_rgba(0.2, 0.5, 0.9, 0.8)
        cr.set_line_width(2.0)
        cr.rectangle(x1, y1, x2 - x1, y2 - y1)
        cr.stroke()
        
        cr.restore()
    
    def draw_selection_bounds(self, cr):
        """Draw bounds and handles for selected items."""
        if self.selection.is_empty():
            return
        
        min_x, min_y, max_x, max_y = self.selection.get_bounds()
        
        cr.save()
        
        # Draw blue bounding box
        cr.set_source_rgba(0.2, 0.5, 0.9, 0.8)
        cr.set_line_width(2.0)
        cr.set_dash([8, 4])
        cr.rectangle(min_x, min_y, max_x - min_x, max_y - min_y)
        cr.stroke()
        
        # Draw resize handles at corners and midpoints
        handle_size = 8
        handles = [
            (min_x, min_y),  # Top-left
            ((min_x + max_x) / 2, min_y),  # Top-middle
            (max_x, min_y),  # Top-right
            (max_x, (min_y + max_y) / 2),  # Right-middle
            (max_x, max_y),  # Bottom-right
            ((min_x + max_x) / 2, max_y),  # Bottom-middle
            (min_x, max_y),  # Bottom-left
            (min_x, (min_y + max_y) / 2),  # Left-middle
        ]
        
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)  # White fill
        for hx, hy in handles:
            cr.rectangle(hx - handle_size/2, hy - handle_size/2, handle_size, handle_size)
            cr.fill()
        
        cr.set_source_rgba(0.2, 0.5, 0.9, 1.0)  # Blue border
        for hx, hy in handles:
            cr.rectangle(hx - handle_size/2, hy - handle_size/2, handle_size, handle_size)
            cr.stroke()
        
        cr.restore()
    
    def on_stylus_down(self, gesture, x, y):
        """Handle stylus down event."""
        # Don't draw if in text mode
        if self.text_mode:
            return False
        
        device = gesture.get_device()
        source = device.get_source()
        source_value = int(source)
        source_name = {1: "MOUSE", 2: "PEN", 3: "TOUCHSCREEN", 4: "TOUCHPAD", 
                      5: "TRACKPOINT", 6: "TABLET_PAD"}.get(source_value, f"UNKNOWN({source_value})")
        
        logger.info(f"Stylus gesture: DOWN at ({x:.2f}, {y:.2f}), device: {device.get_name()}, source: {source_name}")
        
        # Check for stylus eraser button or eraser tool
        tool = device.get_device_tool() if device and hasattr(device, 'get_device_tool') else None
        if tool and hasattr(tool, 'get_tool_type'):
            tool_type = tool.get_tool_type()
            logger.info(f"Stylus tool type: {tool_type}")
            
            # Auto-switch to eraser if stylus eraser is being used
            if tool_type == Gdk.DeviceToolType.ERASER:
                logger.info("Stylus eraser detected - switching to eraser mode")
                self.current_pen_type = PenType.ERASER
        
        # Check for stylus button 2 (common eraser button)
        try:
            event = gesture.get_last_event(None)
            if event:
                # Check if secondary stylus button is pressed (button 2)
                # This is often the eraser button on stylus
                state = event.get_modifier_state()
                # GDK doesn't expose stylus button states directly, but we can check axes
                axes = gesture.get_axes()
                if axes and Gdk.AxisUse.PRESSURE in axes:
                    # Some stylus drivers report eraser via tool type change
                    pass  # Already handled above
        except Exception as e:
            logger.debug(f"Could not check stylus button: {e}")
        
        # Claim this event sequence to prevent other gestures from handling it
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        
        # IMPORTANT: If GestureStylus fires, it means GTK detected stylus-like input
        # Trust the gesture handler - don't block it even if source says TOUCHSCREEN
        # This handles cases where Wayland reports stylus as "Wayland Touch Logical Pointer"
        logger.info(f"✓ Allowing stylus gesture (GestureStylus handler = stylus input)")
        
        # Note: We removed the palm rejection check here because if GestureStylus
        # fires, it's stylus input by definition, regardless of what the source says
        
        # Don't draw if in text mode
        if self.text_mode:
            return False
        
        self.start_stroke(x, y, 1.0)
        return True
    
    def on_stylus_motion(self, gesture, x, y):
        """Handle stylus motion event."""
        if not self.is_drawing:
            return False
        
        # Claim this event sequence
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        
        # Get pressure and tilt
        axes = gesture.get_axis(Gdk.AxisUse.PRESSURE)
        pressure = axes if axes is not None else 1.0
        
        tilt_x = gesture.get_axis(Gdk.AxisUse.XTILT)
        tilt_y = gesture.get_axis(Gdk.AxisUse.YTILT)
        
        self.continue_stroke(x, y, pressure, tilt_x or 0.0, tilt_y or 0.0)
        return True
    
    def on_stylus_up(self, gesture, x, y):
        """Handle stylus up event."""
        logger.info(f"Stylus gesture: UP at ({x:.2f}, {y:.2f})")
        
        # Claim this event sequence
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        
        self.end_stroke()
        return True
    
    def on_legacy_event(self, controller, event):
        """Catch all pointer events for debugging and handling stylus."""
        if not event:
            return False
            
        event_type = event.get_event_type()
        
        # Only log button press/release and motion for stylus
        if event_type in [Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE, Gdk.EventType.MOTION_NOTIFY]:
            device = event.get_device()
            source = device.get_source() if device else None
            
            if source:
                source_value = int(source)
                source_name = {1: "MOUSE", 2: "PEN", 3: "TOUCHSCREEN", 4: "TOUCHPAD", 
                              5: "TRACKPOINT", 6: "TABLET_PAD"}.get(source_value, f"UNKNOWN({source_value})")
                
                device_name = device.get_name() if device else "Unknown"
                
                if event_type == Gdk.EventType.BUTTON_PRESS:
                    x, y = event.get_position()
                    logger.info(f"LEGACY EVENT: PRESS from '{device_name}' | Source: {source_name} | Position: ({x:.1f}, {y:.2f})")
                    
                    # Don't draw if in text mode
                    if self.text_mode:
                        return False
                    
                    # Handle stylus input here
                    if self.palm_rejection_mode and source != Gdk.InputSource.PEN:
                        logger.warning(f"❌ BLOCKED {source_name} in legacy handler")
                        return True  # Block the event
                    
                    # Start drawing
                    logger.info(f"✓ Starting stroke from legacy handler")
                    self.start_stroke(x, y, 1.0)
                    return True  # Consume the event
                    
                elif event_type == Gdk.EventType.MOTION_NOTIFY and self.is_drawing:
                    x, y = event.get_position()
                    self.continue_stroke(x, y, 1.0, 0.0, 0.0)
                    return True
                    
                elif event_type == Gdk.EventType.BUTTON_RELEASE and self.is_drawing:
                    logger.info(f"LEGACY EVENT: RELEASE - ending stroke")
                    self.end_stroke()
                    return True
        
        return False
    
    def on_click_pressed(self, gesture, n_press, x, y):
        """Simple click detector to log and handle all button presses."""
        # Handle text mode clicks
        if self.text_mode:
            # Convert screen coordinates to canvas coordinates
            canvas_x = (x - self.pan_x) / self.zoom
            canvas_y = (y - self.pan_y) / self.zoom
            
            # Save current text box if exists
            if self.current_text_box and self.current_text_box.text.strip():
                self.document.add_text_box(self.current_text_box)
                self.undo_stack.append(('text_box', self.current_text_box))
                self.redo_stack.clear()
            
            # Create new text box at click position
            self.current_text_box = TextBox(
                x=canvas_x,
                y=canvas_y,
                font_size=self.text_font_size,
                color=self.current_color,
                bold=self.text_bold,
                italic=self.text_italic,
                underline=self.text_underline
            )
            self.queue_draw()
            return True
        
        # Skip if already drawing (another handler already started)
        if self.is_drawing:
            logger.debug("Already drawing, skipping click handler")
            return False
        
        device = gesture.get_device()
        source = device.get_source() if device else None
        device_name = device.get_name() if device else "Unknown"
        source_value = int(source) if source else -1
        source_name = {1: "MOUSE", 2: "PEN", 3: "TOUCHSCREEN", 4: "TOUCHPAD", 
                      5: "TRACKPOINT", 6: "TABLET_PAD"}.get(source_value, f"UNKNOWN({source_value})")
        
        logger.info(f"🔵 CLICK PRESSED: device='{device_name}', source={source_name}, pos=({x:.1f}, {y:.1f})")
        
        # Check palm rejection
        if self.palm_rejection_mode:
            # Check if device is a stylus by name (for UNKNOWN sources)
            device_name_lower = device_name.lower() if device_name else ""
            is_stylus_by_name = "stylus" in device_name_lower
            
            # Block touchscreen, but allow stylus even with UNKNOWN source
            if (source == Gdk.InputSource.TOUCHSCREEN or source_value == 3) and not is_stylus_by_name:
                logger.warning(f"❌ BLOCKED TOUCHSCREEN in click handler")
                gesture.set_state(Gtk.EventSequenceState.DENIED)
                return True
        
        # Claim the gesture and start drawing
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        logger.info(f"✓ Starting drawing from click handler")
        self.start_stroke(x, y, 1.0)
        return True
    
    def on_click_released(self, gesture, n_press, x, y):
        """Simple click detector to log all button releases."""
        logger.info(f"🔴 CLICK RELEASED at ({x:.1f}, {y:.1f})")
        if self.is_drawing:
            self.end_stroke()
        return True
    
    def on_motion(self, controller, x, y):
        """Handle motion events for drawing continuation."""
        if self.is_drawing:
            self.continue_stroke(x, y, 1.0, 0.0, 0.0)
            return True
        return False
    
    def on_scroll(self, controller, dx, dy):
        """Handle scroll events for Ctrl+Wheel zoom."""
        # Get modifier state
        state = controller.get_current_event_state()
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        
        if ctrl:
            # Ctrl is held - zoom instead of scroll
            # Get mouse position for zoom center
            event = controller.get_current_event()
            if event:
                x, y = event.get_position()
                
                if dy < 0:  # Scroll up = zoom in
                    self.zoom_in(x, y)
                else:  # Scroll down = zoom out
                    self.zoom_out(x, y)
                
                return True  # Consume the event
        
        return False  # Let normal scrolling happen
    
    def on_zoom_begin(self, gesture, sequence):
        """Handle zoom gesture begin."""
        self.zoom_start = self.zoom
        logger.info(f"Zoom gesture begin at zoom level {self.zoom:.2f}")
        return True
    
    def on_zoom_changed(self, gesture, scale):
        """Handle pinch-to-zoom gesture with smooth scaling."""
        # Calculate new zoom level with improved sensitivity
        # Apply logarithmic scaling for smoother feel
        new_zoom = self.zoom_start * scale
        
        # Clamp zoom between 0.5x and 5x for A4 pages (reasonable range)
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            fit_zoom = self.calculate_fit_zoom()
            min_zoom = max(0.3, fit_zoom * 0.5)  # Don't zoom out too much
            max_zoom = fit_zoom * 3.0  # Allow 3x the fit zoom
            new_zoom = max(min_zoom, min(max_zoom, new_zoom))
        else:
            new_zoom = max(0.1, min(10.0, new_zoom))
        
        # Get the center point of the gesture in widget coordinates
        success, center_x, center_y = gesture.get_bounding_box_center()
        if success:
            # Convert to document coordinates before zoom
            doc_x = (center_x - self.pan_x) / self.zoom
            doc_y = (center_y - self.pan_y) / self.zoom
            
            # Update zoom
            self.zoom = new_zoom
            
            # Adjust pan to keep the center point stationary
            self.pan_x = center_x - doc_x * self.zoom
            self.pan_y = center_y - doc_y * self.zoom
        else:
            self.zoom = new_zoom
        
        self.queue_draw()
        return True
    
    def on_drag_begin(self, gesture, x, y):
        """Handle mouse drag begin."""
        # Don't draw if in text mode
        if self.text_mode:
            return
        
        # Skip if already drawing (click handler already started)
        if self.is_drawing:
            logger.debug("Already drawing from click handler, skipping drag begin")
            return
        
        # Claim the gesture sequence to prevent default cursor behavior
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        
        # Get device info
        device = gesture.get_device()
        source = device.get_source()
        device_name = device.get_name() if device else "Unknown"
        
        # Map source values to readable names
        source_value = int(source)
        source_name = {1: "MOUSE", 2: "PEN", 3: "TOUCHSCREEN", 4: "TOUCHPAD", 
                      5: "TRACKPOINT", 6: "TABLET_PAD"}.get(source_value, f"UNKNOWN({source_value})")
        
        # Check if device has stylus capability by checking if we can get axes
        has_pressure = False
        try:
            if device:
                # Try to get the axes from the device
                axes = device.get_axes()
                has_pressure = Gdk.AxisUse.PRESSURE in axes if axes else False
        except:
            has_pressure = False
        
        # Check if this is a stylus based on device name or tool type
        device_name_lower = device_name.lower() if device_name else ""
        is_stylus_by_name = any(keyword in device_name_lower for keyword in 
                               ['pen', 'stylus', 'wacom', 'huion', 'xp-pen', 'tablet'])
        
        # For X11 "Core Pointer" with unknown source, check if it has tool info
        is_core_pointer = device_name == "Core Pointer" and source_value == 0
        tool = device.get_device_tool() if device and hasattr(device, 'get_device_tool') else None
        tool_type = tool.get_tool_type() if tool and hasattr(tool, 'get_tool_type') else None
        
        # Always log input source for debugging
        logger.info(f"Input from device '{device_name}' | Source: {source_name} | Pressure: {has_pressure} | Tool: {tool_type}")
        
        # Determine if this is a stylus input
        is_stylus = (source == Gdk.InputSource.PEN or is_stylus_by_name or 
                    (is_core_pointer and tool_type in [Gdk.DeviceToolType.PEN, Gdk.DeviceToolType.BRUSH, 
                                                        Gdk.DeviceToolType.PENCIL, Gdk.DeviceToolType.AIRBRUSH]))
        
        # If palm rejection mode is active, check input type
        if self.palm_rejection_mode:
            # Check if device is a stylus by name (for UNKNOWN sources)
            device_name_lower = device_name.lower() if device_name else ""
            is_stylus_by_name_check = "stylus" in device_name_lower
            
            # Block ONLY touchscreen (source 3), but allow stylus even with UNKNOWN source
            if (source == Gdk.InputSource.TOUCHSCREEN or source_value == 3) and not is_stylus_by_name_check:
                logger.warning(f"❌ BLOCKED TOUCHSCREEN input (palm rejection active)")
                gesture.set_state(Gtk.EventSequenceState.DENIED)
                return
            else:
                # Allow all other inputs (including stylus, mouse, touchpad)
                logger.info(f"✓ Allowing input: device='{device_name}', source={source_name}, tool={tool_type}")
        
        logger.info(f"Drawing stroke begin at ({x:.2f}, {y:.2f})")
        
        # Try to get pressure for stylus devices
        pressure = 1.0
        if has_pressure:
            # Try to get pressure from the last event
            event = gesture.get_last_event(None)
            if event:
                pressure_value = event.get_axis(Gdk.AxisUse.PRESSURE)
                if pressure_value is not None:
                    pressure = pressure_value
                    logger.info(f"Stylus pressure detected: {pressure:.3f}")
        
        self.start_stroke(x, y, pressure)
    
    def on_drag_update(self, gesture, offset_x, offset_y):
        """Handle mouse drag update."""
        if not self.is_drawing:
            return
        
        # get_start_point returns (success, x, y) in GTK4
        success, start_x, start_y = gesture.get_start_point()
        if not success:
            return
            
        x = start_x + offset_x
        y = start_y + offset_y
        
        # Try to get pressure for stylus
        pressure = 1.0
        try:
            event = gesture.get_last_event(None)
            if event:
                pressure_value = event.get_axis(Gdk.AxisUse.PRESSURE)
                if pressure_value is not None and pressure_value > 0:
                    pressure = pressure_value
        except:
            pass
        
        self.continue_stroke(x, y, pressure, 0.0, 0.0)
    
    def on_drag_end(self, gesture, offset_x, offset_y):
        """Handle mouse drag end."""
        logger.info("Mouse drag end")
        self.end_stroke()
    
    def start_stroke(self, x, y, pressure):
        """Start a new stroke, shape, or selection."""
        # Don't draw if in text mode
        if self.text_mode:
            return
        
        self.is_drawing = True
        self.last_x = x
        self.last_y = y
        
        # Transform coordinates
        tx = (x - self.pan_x) / self.zoom
        ty = (y - self.pan_y) / self.zoom
        
        # Handle A4 notes - convert to page-relative coordinates
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            # Get page layout
            offset_x = self.get_page_layout(self.get_width())
            page_height = self.document.height
            page_gap = 20  # Gap between pages
            top_padding = 30
            
            # Adjust for page offset
            tx = tx - offset_x
            ty_relative = ty - top_padding
            
            # Calculate which page we're on
            page_num = int(ty_relative / (page_height + page_gap)) + 1
            if page_num < 1:
                page_num = 1
            
            # Update current page
            self.document.current_page = page_num
            
            # Ensure page exists
            if page_num not in self.document.pages:
                self.document.pages[page_num] = []
                self.document.page_shapes[page_num] = []
            
            # Convert to page-relative coordinates
            ty = ty_relative - (page_num - 1) * (page_height + page_gap)
            
            # Clip to page boundaries
            tx = max(0, min(self.document.width, tx))
            ty = max(0, min(page_height, ty))
        
        if self.selection_mode:
            # Check if clicking on existing selection to drag it
            if not self.selection.is_empty():
                min_x, min_y, max_x, max_y = self.selection.get_bounds()
                if min_x <= tx <= max_x and min_y <= ty <= max_y:
                    # Start dragging selection
                    self.is_dragging_selection = True
                    self.drag_start_x = tx
                    self.drag_start_y = ty
                    logger.debug(f"Started dragging selection from ({tx:.2f}, {ty:.2f})")
                    return
            
            # Start new selection box (don't clear selection yet - wait until drag completes)
            self.is_selecting = True
            self.selection_box_start_x = tx
            self.selection_box_start_y = ty
            self.selection_box_end_x = tx
            self.selection_box_end_y = ty
            logger.debug(f"Started selection at ({tx:.2f}, {ty:.2f})")
        elif self.shape_mode and self.current_shape_type:
            # Start shape drawing
            self.shape_start_x = tx
            self.shape_start_y = ty
            self.shape_preview = Shape(
                shape_type=self.current_shape_type,
                start_x=tx,
                start_y=ty,
                end_x=tx,
                end_y=ty,
                color=self.current_color,
                width=self.current_width,
                filled=self.shape_filled,
                line_style=self.shape_line_style
            )
            logger.debug(f"Started shape at ({tx:.2f}, {ty:.2f})")
        else:
            # Check if using eraser
            if self.current_pen_type == PenType.ERASER:
                # Start eraser mode - erase at this point
                self.erase_at_point(tx, ty, self.current_width)
                # Create a temporary "stroke" to track eraser path for continuous erasing
                self.current_stroke = Stroke(
                    pen_type=self.current_pen_type,
                    color=self.current_color,
                    width=self.current_width
                )
                point = Point(tx, ty, pressure)
                self.current_stroke.add_point(point)
                logger.debug(f"Started erasing at ({tx:.2f}, {ty:.2f})")
            else:
                # Start normal stroke
                self.current_stroke = Stroke(
                    pen_type=self.current_pen_type,
                    color=self.current_color,
                    width=self.current_width
                )
                
                point = Point(tx, ty, pressure)
                self.current_stroke.add_point(point)
                
                logger.debug(f"Started stroke at ({tx:.2f}, {ty:.2f})")
    
    def continue_stroke(self, x, y, pressure, tilt_x, tilt_y):
        """Continue drawing the current stroke, shape, or selection."""
        if not self.is_drawing:
            return
        
        # Transform coordinates
        tx = (x - self.pan_x) / self.zoom
        ty = (y - self.pan_y) / self.zoom
        
        # Handle A4 notes - convert to page-relative coordinates
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            offset_x = self.get_page_layout(self.get_width())
            page_height = self.document.height
            page_gap = 20  # Gap between pages
            top_padding = 30
            
            # Adjust for page offset
            tx = tx - offset_x
            ty_relative = ty - top_padding
            
            # Calculate which page (stay on current page during stroke)
            page_num = self.document.current_page
            
            # Convert to page-relative coordinates
            ty = ty_relative - (page_num - 1) * (page_height + page_gap)
            
            # Clip to page boundaries
            tx = max(0, min(self.document.width, tx))
            ty = max(0, min(page_height, ty))
        
        if self.selection_mode:
            if self.is_dragging_selection:
                # Drag selected items
                dx = tx - self.drag_start_x
                dy = ty - self.drag_start_y
                self.selection.translate(dx, dy)
                self.drag_start_x = tx
                self.drag_start_y = ty
                self.queue_draw()
            elif self.is_selecting:
                # Update selection box
                self.selection_box_end_x = tx
                self.selection_box_end_y = ty
                self.queue_draw()
        elif self.shape_mode and self.shape_preview:
            # Update shape preview
            self.shape_preview.end_x = tx
            self.shape_preview.end_y = ty
            self.queue_draw()
        elif self.current_stroke:
            # Add point if moved enough (smoothing)
            dx = tx - self.last_x
            dy = ty - self.last_y
            distance = (dx * dx + dy * dy) ** 0.5
            
            if distance > 1.0:  # Minimum distance threshold
                point = Point(tx, ty, pressure, tilt_x, tilt_y)
                self.current_stroke.add_point(point)
                
                # If erasing, erase at this point too
                if self.current_pen_type == PenType.ERASER:
                    self.erase_at_point(tx, ty, self.current_width)
                
                self.last_x = tx
                self.last_y = ty
            
            # Always queue redraw to show stroke in real-time
            self.queue_draw()
    
    def end_stroke(self):
        """End the current stroke, shape, or selection."""
        if not self.is_drawing:
            return
        
        if self.selection_mode:
            if self.is_selecting:
                # Complete selection - find all objects in selection box
                self.complete_selection()
                self.is_selecting = False
                # Reset selection box coordinates
                self.selection_box_start_x = 0.0
                self.selection_box_start_y = 0.0
                self.selection_box_end_x = 0.0
                self.selection_box_end_y = 0.0
            elif self.is_dragging_selection:
                # End dragging
                self.is_dragging_selection = False
                self.drag_start_x = 0.0
                self.drag_start_y = 0.0
                logger.info("Completed dragging selection")
        elif self.shape_mode and self.shape_preview:
            # Complete shape
            self.document.add_shape(self.shape_preview)
            self.undo_stack.append(('shape', self.shape_preview))
            self.redo_stack.clear()
            logger.info(f"Completed {self.shape_preview.shape_type.value} shape")
            self.shape_preview = None
        elif self.current_stroke and len(self.current_stroke.points) > 0:
            # Don't save eraser strokes - they're just for tracking the eraser path
            if self.current_pen_type != PenType.ERASER:
                # Add stroke to document
                self.document.add_stroke(self.current_stroke)
                self.undo_stack.append(('stroke', self.current_stroke))
                self.redo_stack.clear()
                logger.info(f"Completed stroke with {len(self.current_stroke.points)} points")
            else:
                logger.info(f"Completed erasing")
            
            self.current_stroke = None
        
        self.is_drawing = False
        self.queue_draw()
    
    def erase_at_point(self, x, y, eraser_size):
        """Erase strokes, shapes, and text boxes at the given point.
        Supports both stroke eraser (entire stroke) and pixel eraser (partial).
        
        Args:
            x: X coordinate to erase at
            y: Y coordinate to erase at
            eraser_size: Radius of the eraser
        """
        eraser_radius = eraser_size * 2  # Make eraser effective area larger
        
        current_strokes = self.document.get_current_strokes()
        current_shapes = self.document.get_current_shapes()
        current_text_boxes = self.document.get_current_text_boxes()
        
        # Check strokes for intersection with eraser
        strokes_to_remove = []
        strokes_to_add = []
        
        if self.eraser_mode == 'pixel':
            # Pixel eraser mode: split strokes at erase point
            for stroke in current_strokes:
                # Find all points within eraser radius
                erase_indices = []
                for i, point in enumerate(stroke.points):
                    dx = point.x - x
                    dy = point.y - y
                    distance = (dx * dx + dy * dy) ** 0.5
                    if distance <= eraser_radius:
                        erase_indices.append(i)
                
                if erase_indices:
                    # Split stroke at erase points
                    strokes_to_remove.append(stroke)
                    
                    # Create segments between erased points
                    segments = []
                    last_end = 0
                    
                    for erase_idx in erase_indices:
                        # Add segment before this erase point
                        if erase_idx > last_end:
                            segment_points = stroke.points[last_end:erase_idx]
                            if len(segment_points) >= 2:  # Only keep segments with 2+ points
                                segments.append(segment_points)
                        last_end = erase_idx + 1
                    
                    # Add final segment after last erase point
                    if last_end < len(stroke.points):
                        segment_points = stroke.points[last_end:]
                        if len(segment_points) >= 2:
                            segments.append(segment_points)
                    
                    # Create new strokes from segments
                    for segment_points in segments:
                        new_stroke = Stroke(
                            points=segment_points,
                            pen_type=stroke.pen_type,
                            color=stroke.color,
                            width=stroke.width
                        )
                        strokes_to_add.append(new_stroke)
        else:
            # Stroke eraser mode: remove entire stroke
            for stroke in current_strokes:
                # Check if any point in the stroke is within eraser radius
                for point in stroke.points:
                    dx = point.x - x
                    dy = point.y - y
                    distance = (dx * dx + dy * dy) ** 0.5
                    if distance <= eraser_radius:
                        strokes_to_remove.append(stroke)
                        break  # No need to check other points
        
        # Remove erased strokes and add split segments
        for stroke in strokes_to_remove:
            if stroke in current_strokes:
                current_strokes.remove(stroke)
        
        for new_stroke in strokes_to_add:
            current_strokes.append(new_stroke)
                
        # Note: We don't add to undo stack during continuous erasing
        # to avoid creating too many undo steps
        
        # Check shapes for intersection
        shapes_to_remove = []
        for shape in current_shapes:
            min_x, min_y, max_x, max_y = shape.get_bounds()
            # Check if eraser point is within or near shape bounds
            if (min_x - eraser_radius <= x <= max_x + eraser_radius and
                min_y - eraser_radius <= y <= max_y + eraser_radius):
                shapes_to_remove.append(shape)
        
        # Remove shapes
        for shape in shapes_to_remove:
            if shape in current_shapes:
                current_shapes.remove(shape)
        
        # Check text boxes for intersection
        text_boxes_to_remove = []
        for text_box in current_text_boxes:
            min_x, min_y, max_x, max_y = text_box.get_bounds()
            # Check if eraser point is within or near text box bounds
            if (min_x - eraser_radius <= x <= max_x + eraser_radius and
                min_y - eraser_radius <= y <= max_y + eraser_radius):
                text_boxes_to_remove.append(text_box)
        
        # Remove text boxes
        for text_box in text_boxes_to_remove:
            if text_box in current_text_boxes:
                current_text_boxes.remove(text_box)
        
        # Redraw if anything was erased
        if strokes_to_remove or shapes_to_remove or text_boxes_to_remove:
            self.queue_draw()
    
    def complete_selection(self):
        """Find and select all objects within the selection box."""
        min_x = min(self.selection_box_start_x, self.selection_box_end_x)
        max_x = max(self.selection_box_start_x, self.selection_box_end_x)
        min_y = min(self.selection_box_start_y, self.selection_box_end_y)
        max_y = max(self.selection_box_start_y, self.selection_box_end_y)
        
        # Calculate selection box size
        width = max_x - min_x
        height = max_y - min_y
        
        # Only select if box is large enough (minimum 5 pixels) to avoid accidental tiny selections
        if width < 5 and height < 5:
            logger.debug(f"Selection box too small ({width:.1f}x{height:.1f}), ignoring")
            return
        
        # Clear previous selection before selecting new items
        self.selection.clear()
        
        # Check strokes
        current_strokes = self.document.get_current_strokes()
        for stroke in current_strokes:
            stroke_min_x, stroke_min_y, stroke_max_x, stroke_max_y = stroke.get_bounds()
            # Check if stroke is within or overlaps selection box
            if (stroke_min_x <= max_x and stroke_max_x >= min_x and
                stroke_min_y <= max_y and stroke_max_y >= min_y):
                self.selection.add_stroke(stroke)
        
        # Check shapes
        current_shapes = self.document.get_current_shapes()
        for shape in current_shapes:
            shape_min_x, shape_min_y, shape_max_x, shape_max_y = shape.get_bounds()
            # Check if shape is within or overlaps selection box
            if (shape_min_x <= max_x and shape_max_x >= min_x and
                shape_min_y <= max_y and shape_max_y >= min_y):
                self.selection.add_shape(shape)
        
        # Check text boxes
        current_text_boxes = self.document.get_current_text_boxes()
        for text_box in current_text_boxes:
            text_min_x, text_min_y, text_max_x, text_max_y = text_box.get_bounds()
            # Check if text box is within or overlaps selection box
            if (text_min_x <= max_x and text_max_x >= min_x and
                text_min_y <= max_y and text_max_y >= min_y):
                self.selection.add_text_box(text_box)
        
        logger.info(f"Selected {len(self.selection.strokes)} strokes, {len(self.selection.shapes)} shapes, and {len(self.selection.text_boxes)} text boxes")
    
    def undo(self):
        """Undo the last stroke, shape, or text box."""
        if len(self.undo_stack) > 0:
            item = self.undo_stack.pop()
            item_type, obj = item
            
            if item_type == 'stroke':
                current_strokes = self.document.get_current_strokes()
                if obj in current_strokes:
                    current_strokes.remove(obj)
            elif item_type == 'shape':
                current_shapes = self.document.get_current_shapes()
                if obj in current_shapes:
                    current_shapes.remove(obj)
            elif item_type == 'text_box':
                current_text_boxes = self.document.get_current_text_boxes()
                if obj in current_text_boxes:
                    current_text_boxes.remove(obj)
            
            self.redo_stack.append(item)
            self.queue_draw()
            logger.info(f"Undo last {item_type}")
    
    def redo(self):
        """Redo the last undone stroke, shape, or text box."""
        if len(self.redo_stack) > 0:
            item = self.redo_stack.pop()
            item_type, obj = item
            
            if item_type == 'stroke':
                self.document.add_stroke(obj)
            elif item_type == 'shape':
                self.document.add_shape(obj)
            elif item_type == 'text_box':
                self.document.add_text_box(obj)
            
            self.undo_stack.append(item)
            self.queue_draw()
            logger.info(f"Redo {item_type}")
    
    def clear_canvas(self):
        """Clear all strokes."""
        self.document.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.queue_draw()
        logger.info("Canvas cleared")
    
    def enable_selection_mode(self):
        """Enable selection mode."""
        self.selection_mode = True
        self.shape_mode = False
        self.current_shape_type = None
        self.update_cursor()
        logger.info("Selection mode enabled")
    
    def disable_selection_mode(self):
        """Disable selection mode."""
        self.selection_mode = False
        self.selection.clear()
        self.update_cursor()
        self.queue_draw()
        logger.info("Selection mode disabled")
    
    def select_all(self):
        """Select all objects on the canvas."""
        if not self.selection_mode:
            self.enable_selection_mode()
        
        self.selection.clear()
        
        # Select all strokes
        current_strokes = self.document.get_current_strokes()
        for stroke in current_strokes:
            self.selection.add_stroke(stroke)
        
        # Select all shapes
        current_shapes = self.document.get_current_shapes()
        for shape in current_shapes:
            self.selection.add_shape(shape)
        
        # Select all text boxes
        current_text_boxes = self.document.get_current_text_boxes()
        for text_box in current_text_boxes:
            self.selection.add_text_box(text_box)
        
        self.queue_draw()
        logger.info(f"Selected all: {len(self.selection.strokes)} strokes, {len(self.selection.shapes)} shapes, and {len(self.selection.text_boxes)} text boxes")
    
    def copy_selection(self):
        """Copy selected items to clipboard."""
        if self.selection.is_empty():
            logger.warning("Nothing selected to copy")
            return
        
        self.clipboard = self.selection.copy()
        logger.info(f"Copied {len(self.clipboard.strokes)} strokes, {len(self.clipboard.shapes)} shapes, and {len(self.clipboard.text_boxes)} text boxes to clipboard")
    
    def paste_selection(self):
        """Paste items from clipboard."""
        if self.clipboard is None or self.clipboard.is_empty():
            logger.warning("Clipboard is empty")
            return
        
        # Create a copy and offset it slightly
        pasted = self.clipboard.copy()
        pasted.translate(20, 20)  # Offset by 20 pixels
        
        # Add to document
        for stroke in pasted.strokes:
            self.document.add_stroke(stroke)
            self.undo_stack.append(('stroke', stroke))
        
        for shape in pasted.shapes:
            self.document.add_shape(shape)
            self.undo_stack.append(('shape', shape))
        
        for text_box in pasted.text_boxes:
            self.document.add_text_box(text_box)
            self.undo_stack.append(('text_box', text_box))
        
        self.redo_stack.clear()
        
        # Select the pasted items
        self.selection = pasted
        
        self.queue_draw()
        logger.info(f"Pasted {len(pasted.strokes)} strokes, {len(pasted.shapes)} shapes, and {len(pasted.text_boxes)} text boxes")
    
    def delete_selection(self):
        """Delete selected items."""
        if self.selection.is_empty():
            logger.warning("Nothing selected to delete")
            return
        
        current_strokes = self.document.get_current_strokes()
        current_shapes = self.document.get_current_shapes()
        current_text_boxes = self.document.get_current_text_boxes()
        
        # Remove selected strokes
        for stroke in self.selection.strokes:
            if stroke in current_strokes:
                current_strokes.remove(stroke)
                self.undo_stack.append(('delete_stroke', stroke))
        
        # Remove selected shapes
        for shape in self.selection.shapes:
            if shape in current_shapes:
                current_shapes.remove(shape)
                self.undo_stack.append(('delete_shape', shape))
        
        # Remove selected text boxes
        for text_box in self.selection.text_boxes:
            if text_box in current_text_boxes:
                current_text_boxes.remove(text_box)
                self.undo_stack.append(('delete_text_box', text_box))
        
        self.redo_stack.clear()
        
        count_strokes = len(self.selection.strokes)
        count_shapes = len(self.selection.shapes)
        count_text_boxes = len(self.selection.text_boxes)
        self.selection.clear()
        
        self.queue_draw()
        logger.info(f"Deleted {count_strokes} strokes, {count_shapes} shapes, and {count_text_boxes} text boxes")
    
    def duplicate_selection(self):
        """Duplicate selected items."""
        if self.selection.is_empty():
            logger.warning("Nothing selected to duplicate")
            return
        
        # Copy and paste
        self.copy_selection()
        self.paste_selection()
    
    def set_pen_type(self, pen_type: PenType):
        """Set the current pen type."""
        # Save current width before switching
        if self.current_pen_type == PenType.ERASER:
            self.eraser_width = self.current_width
        else:
            self.pen_width = self.current_width
        
        self.current_pen_type = pen_type
        self.shape_mode = False
        self.current_shape_type = None
        
        # Load width for the new tool
        if pen_type == PenType.ERASER:
            self.current_width = self.eraser_width
        else:
            self.current_width = self.pen_width
        
        # Update cursor to match the tool
        self.update_cursor()
        
        logger.info(f"Pen type changed to {pen_type.value}, width: {self.current_width}")
    
    def set_shape_type(self, shape_type: ShapeType):
        """Set the current shape type and enable shape mode."""
        self.current_shape_type = shape_type
        self.shape_mode = True
        self.update_cursor()
        logger.info(f"Shape type changed to {shape_type.value}")
    
    def set_shape_filled(self, filled: bool):
        """Set whether shapes should be filled."""
        self.shape_filled = filled
        logger.info(f"Shape filled: {filled}")
    
    def set_shape_line_style(self, style: str):
        """Set the line style for shapes."""
        self.shape_line_style = style
        logger.info(f"Shape line style: {style}")
    
    def set_color(self, color):
        """Set the current drawing color."""
        self.current_color = color
        logger.info(f"Color changed to {color}")
    
    def set_width(self, width):
        """Set the current pen width."""
        self.current_width = width
        # Save to appropriate storage
        if self.current_pen_type == PenType.ERASER:
            self.eraser_width = width
        else:
            self.pen_width = width
        logger.info(f"Width changed to {width} for {self.current_pen_type.value}")
    
    def set_dark_mode(self, enabled):
        """Toggle dark mode."""
        self.dark_mode = enabled
        if enabled:
            self.document.background_color = (0.15, 0.15, 0.15, 1.0)
        else:
            self.document.background_color = (1.0, 1.0, 1.0, 1.0)
        self.queue_draw()
        logger.info(f"Dark mode: {enabled}")
    
    def set_palm_rejection_mode(self, enabled):
        """Enable or disable palm rejection mode."""
        self.palm_rejection_mode = enabled
        logger.info(f"Palm rejection {'enabled' if enabled else 'disabled'}")
    
    def set_eraser_mode(self, mode):
        """Set eraser mode: 'stroke' or 'pixel'."""
        if mode in ['stroke', 'pixel']:
            self.eraser_mode = mode
            logger.info(f"Eraser mode set to: {mode}")
        else:
            logger.warning(f"Invalid eraser mode: {mode}")
    
    def calculate_fit_zoom(self):
        """Calculate zoom level to fit page width to screen (80% of screen width)."""
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            canvas_width = self.get_width()
            if canvas_width > 0:
                page_width = self.document.width
                # Target: page takes 80% of screen width (10% padding each side)
                target_width = canvas_width * 0.8
                fit_zoom = target_width / page_width
                return max(0.1, min(10.0, fit_zoom))  # Clamp between 0.1 and 10
        return 1.0
    
    def zoom_in(self, center_x=None, center_y=None):
        """Zoom in by 20% (1.2x multiplier)."""
        from .stroke import NoteType
        
        # For A4 notes, maintain page centering
        if self.document.note_type == NoteType.A4_NOTES:
            # Get canvas dimensions
            canvas_width = self.get_width()
            canvas_height = self.get_height()
            
            if canvas_width <= 0:
                canvas_width = 800
            if canvas_height <= 0:
                canvas_height = 600
            
            # Calculate current page center in canvas coordinates
            page_width = self.document.width
            offset_x = self.get_page_layout(canvas_width)
            page_center_x = offset_x + page_width / 2
            
            # Use document center as zoom focus
            doc_x = page_center_x
            doc_y = self.document.height / 2
            
            # Map to canvas coordinates
            center_x = doc_x * self.zoom + self.pan_x
            center_y = doc_y * self.zoom + self.pan_y
        else:
            if center_x is None:
                center_x = self.get_width() / 2
            if center_y is None:
                center_y = self.get_height() / 2
            
            # Convert to document coordinates before zoom
            doc_x = (center_x - self.pan_x) / self.zoom
            doc_y = (center_y - self.pan_y) / self.zoom
        
        # Calculate new zoom (increase by 20%)
        new_zoom = self.zoom * 1.2
        new_zoom = max(0.1, min(10.0, new_zoom))
        
        # Update zoom
        old_zoom = self.zoom
        self.zoom = new_zoom
        
        # Adjust pan to keep center point stationary
        if self.document.note_type == NoteType.A4_NOTES:
            # Recalculate page position with new zoom
            canvas_width = self.get_width() if self.get_width() > 0 else 800
            offset_x = self.get_page_layout(canvas_width)
            page_center_x = offset_x + self.document.width / 2
            
            # Keep page horizontally centered
            self.pan_x = center_x - page_center_x * self.zoom
            self.pan_y = center_y - doc_y * self.zoom
        else:
            self.pan_x = center_x - doc_x * self.zoom
            self.pan_y = center_y - doc_y * self.zoom
        
        self.queue_draw()
        logger.info(f"Zoom in: {old_zoom:.2f}x → {self.zoom:.2f}x")
    
    def zoom_out(self, center_x=None, center_y=None):
        """Zoom out by 20% (0.833x multiplier)."""
        from .stroke import NoteType
        
        # For A4 notes, maintain page centering
        if self.document.note_type == NoteType.A4_NOTES:
            # Get canvas dimensions
            canvas_width = self.get_width()
            canvas_height = self.get_height()
            
            if canvas_width <= 0:
                canvas_width = 800
            if canvas_height <= 0:
                canvas_height = 600
            
            # Calculate current page center in canvas coordinates
            page_width = self.document.width
            offset_x = self.get_page_layout(canvas_width)
            page_center_x = offset_x + page_width / 2
            
            # Use document center as zoom focus
            doc_x = page_center_x
            doc_y = self.document.height / 2
            
            # Map to canvas coordinates
            center_x = doc_x * self.zoom + self.pan_x
            center_y = doc_y * self.zoom + self.pan_y
        else:
            if center_x is None:
                center_x = self.get_width() / 2
            if center_y is None:
                center_y = self.get_height() / 2
            
            # Convert to document coordinates before zoom
            doc_x = (center_x - self.pan_x) / self.zoom
            doc_y = (center_y - self.pan_y) / self.zoom
        
        # Calculate new zoom (decrease by 20%)
        new_zoom = self.zoom / 1.2
        new_zoom = max(0.1, min(10.0, new_zoom))
        
        # Update zoom
        old_zoom = self.zoom
        self.zoom = new_zoom
        
        # Adjust pan to keep center point stationary
        if self.document.note_type == NoteType.A4_NOTES:
            # Recalculate page position with new zoom
            canvas_width = self.get_width() if self.get_width() > 0 else 800
            offset_x = self.get_page_layout(canvas_width)
            page_center_x = offset_x + self.document.width / 2
            
            # Keep page horizontally centered
            self.pan_x = center_x - page_center_x * self.zoom
            self.pan_y = center_y - doc_y * self.zoom
        else:
            self.pan_x = center_x - doc_x * self.zoom
            self.pan_y = center_y - doc_y * self.zoom
        
        self.queue_draw()
        logger.info(f"Zoom out: {old_zoom:.2f}x → {self.zoom:.2f}x")
    
    def reset_view(self):
        """Reset zoom and pan to fit page to screen."""
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            # Auto-fit zoom for A4 pages
            self.zoom = self.calculate_fit_zoom()
        else:
            self.zoom = 1.0
        
        self.pan_x = 0.0
        self.pan_y = 0.0
        
        # Ensure content width matches canvas width (no horizontal scroll)
        canvas_width = self.get_width()
        if canvas_width > 0:
            self.set_content_width(int(canvas_width))
        
        self.queue_draw()
        logger.info(f"View reset (zoom={self.zoom:.2f}, pan=0,0)")
    
    def get_visible_page_from_scroll(self, scroll_y):
        """Determine which page is currently visible based on scroll position.
        
        Args:
            scroll_y: Current vertical scroll position
            
        Returns:
            Page number (1-indexed) of the page that's most visible
        """
        from .stroke import NoteType
        if self.document.note_type != NoteType.A4_NOTES:
            return None
        
        page_height = self.document.height
        page_gap = 20
        top_padding = 30
        
        # Adjust for zoom and pan
        adjusted_scroll = (scroll_y - self.pan_y) / self.zoom
        
        # Calculate which page this position corresponds to
        if adjusted_scroll < top_padding:
            return 1
        
        # Find the page based on scroll position
        position_in_pages = adjusted_scroll - top_padding
        page_index = int(position_in_pages / (page_height + page_gap))
        page_num = page_index + 1
        
        # Clamp to valid page range
        total_pages = self.document.get_total_pages()
        return max(1, min(page_num, total_pages))
    
    def next_page(self):
        """Go to next page (for A4 notes)."""
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            self.document.next_page()
            self.queue_draw()
            logger.info(f"Next page: {self.document.current_page}/{self.document.get_total_pages()}")
            # Notify parent if callback is set
            if self.on_page_changed_callback:
                self.on_page_changed_callback()
    
    def prev_page(self):
        """Go to previous page (for A4 notes)."""
        from .stroke import NoteType
        if self.document.note_type == NoteType.A4_NOTES:
            self.document.prev_page()
            self.queue_draw()
            logger.info(f"Previous page: {self.document.current_page}/{self.document.get_total_pages()}")
            # Notify parent if callback is set
            if self.on_page_changed_callback:
                self.on_page_changed_callback()
    
    def update_current_page_from_scroll(self, scroll_y):
        """Update current page based on scroll position.
        
        Args:
            scroll_y: Current vertical scroll position
        """
        from .stroke import NoteType
        if self.document.note_type != NoteType.A4_NOTES:
            return
        
        new_page = self.get_visible_page_from_scroll(scroll_y)
        if new_page and new_page != self.document.current_page:
            self.document.current_page = new_page
            self.queue_draw()
            logger.debug(f"Current page updated to: {new_page}")
            # Notify parent if callback is set
            if self.on_page_changed_callback:
                self.on_page_changed_callback()
    
    def set_text_mode(self, enabled: bool):
        """Enable or disable text input mode."""
        self.text_mode = enabled
        self.shape_mode = False
        self.selection_mode = False
        
        if not enabled and self.current_text_box:
            # Save the text box if exiting text mode
            if self.current_text_box.text.strip():
                self.document.add_text_box(self.current_text_box)
                self.undo_stack.append(('text_box', self.current_text_box))
                self.redo_stack.clear()
            self.current_text_box = None
        
        self.update_cursor()
        self.queue_draw()
        logger.info(f"Text mode: {'enabled' if enabled else 'disabled'}")
    
    def set_text_formatting(self, bold=None, italic=None, underline=None, font_size=None):
        """Set text formatting options."""
        if bold is not None:
            self.text_bold = bold
        if italic is not None:
            self.text_italic = italic
        if underline is not None:
            self.text_underline = underline
        if font_size is not None:
            self.text_font_size = font_size
        
        # Update current text box if editing
        if self.current_text_box:
            if bold is not None:
                self.current_text_box.bold = bold
            if italic is not None:
                self.current_text_box.italic = italic
            if underline is not None:
                self.current_text_box.underline = underline
            if font_size is not None:
                self.current_text_box.font_size = font_size
            self.queue_draw()
    
    def draw_text_box(self, cr, text_box: TextBox, show_cursor=False):
        """Draw a text box on the canvas."""
        from gi.repository import Pango, PangoCairo
        
        # Create Pango layout
        layout = PangoCairo.create_layout(cr)
        layout.set_text(text_box.text if text_box.text else " ", -1)
        layout.set_width(int(text_box.width * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        
        # Set font description
        font_desc = Pango.FontDescription()
        font_desc.set_family(text_box.font_family)
        font_desc.set_size(int(text_box.font_size * Pango.SCALE))
        
        if text_box.bold:
            font_desc.set_weight(Pango.Weight.BOLD)
        if text_box.italic:
            font_desc.set_style(Pango.Style.ITALIC)
        
        layout.set_font_description(font_desc)
        
        # Draw text
        cr.save()
        cr.move_to(text_box.x, text_box.y)
        cr.set_source_rgba(*text_box.color)
        PangoCairo.show_layout(cr, layout)
        
        # Draw underline if needed
        if text_box.underline and text_box.text:
            ink_rect, logical_rect = layout.get_pixel_extents()
            cr.set_line_width(1)
            y_underline = text_box.y + logical_rect.height
            cr.move_to(text_box.x, y_underline)
            cr.line_to(text_box.x + logical_rect.width, y_underline)
            cr.stroke()
        
        # Draw cursor if this is the active text box
        if show_cursor:
            # Get cursor position at the end of text
            text_length = len(text_box.text) if text_box.text else 0
            cursor_rect = layout.get_cursor_pos(text_length)[1]  # Get strong cursor position
            
            # Convert from Pango units to pixels
            cursor_x = text_box.x + cursor_rect.x / Pango.SCALE
            cursor_y = text_box.y + cursor_rect.y / Pango.SCALE
            cursor_height = cursor_rect.height / Pango.SCALE
            
            # Draw cursor line
            cr.set_source_rgba(0, 0, 0, 0.8)
            cr.set_line_width(2)
            cr.move_to(cursor_x, cursor_y)
            cr.line_to(cursor_x, cursor_y + cursor_height)
            cr.stroke()
            
            # Draw text box border when editing
            ink_rect, logical_rect = layout.get_pixel_extents()
            # Add padding around the text
            padding = 5
            cr.set_source_rgba(0.5, 0.5, 1.0, 0.3)
            cr.set_line_width(1)
            cr.set_dash([5, 5])
            cr.rectangle(
                text_box.x - padding, 
                text_box.y - padding,
                logical_rect.width + 2 * padding, 
                logical_rect.height + 2 * padding
            )
            cr.stroke()
            cr.set_dash([])
        
        cr.restore()
    
    def handle_text_key_press(self, keyval, keycode, state):
        """Handle keyboard input for text editing."""
        if not self.text_mode or not self.current_text_box:
            return False
        
        # Get the Unicode character
        char = Gdk.keyval_to_unicode(keyval)
        
        if keyval == Gdk.KEY_BackSpace:
            # Delete last character
            if self.current_text_box.text:
                self.current_text_box.text = self.current_text_box.text[:-1]
                self.queue_draw()
            return True
        elif keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            # Add newline
            self.current_text_box.text += '\n'
            self.queue_draw()
            return True
        elif keyval == Gdk.KEY_Escape:
            # Exit text mode
            self.set_text_mode(False)
            return True
        elif char and char != 0:
            # Add character
            self.current_text_box.text += chr(char)
            self.queue_draw()
            return True
        
        return False
    
    def export_to_png(self, filepath: str, width: int = None, height: int = None):
        """Export canvas to PNG."""
        if width is None:
            width = int(self.document.width)
        if height is None:
            height = int(self.document.height)
        
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(surface)
        
        # Background
        cr.set_source_rgba(*self.document.background_color)
        cr.paint()
        
        # Draw all strokes
        for stroke in self.document.strokes:
            self.draw_stroke(cr, stroke)
        
        surface.write_to_png(filepath)
        logger.info(f"Exported to PNG: {filepath}")
