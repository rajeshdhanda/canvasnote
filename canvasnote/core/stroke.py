"""Stroke and drawing data structures."""
from dataclasses import dataclass, field
from typing import List, Tuple, Dict
from enum import Enum
import json


class NoteType(Enum):
    """Types of notes that can be created."""
    CANVAS = "canvas"  # Infinite playground, no pages
    A4_NOTES = "a4_notes"  # Paginated A4-sized notes for students


class PageTemplate(Enum):
    """Templates available for A4 pages."""
    BLANK = "blank"  # Plain white page
    RULED = "ruled"  # Horizontal lines (like notebook paper)
    GRID = "grid"  # Square grid pattern
    DOT_GRID = "dot_grid"  # Dotted grid pattern


class PenType(Enum):
    """Pen types available for drawing."""
    PEN = "pen"
    PENCIL = "pencil"
    HIGHLIGHTER = "highlighter"
    ERASER = "eraser"


class ShapeType(Enum):
    """Shape types available for drawing."""
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    TRIANGLE = "triangle"
    PENTAGON = "pentagon"
    STRAIGHT_LINE = "straight_line"
    ARROW = "arrow"


class SelectionMode(Enum):
    """Selection modes available."""
    NONE = "none"
    RECTANGLE = "rectangle"  # Rectangle selection box
    LASSO = "lasso"  # Free-form lasso selection


@dataclass
class TextBox:
    """A text box for typing text notes."""
    x: float
    y: float
    text: str = ""
    font_size: float = 16.0
    font_family: str = "Sans"
    color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # RGBA
    bold: bool = False
    italic: bool = False
    underline: bool = False
    width: float = 200.0  # Default text box width
    
    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Get bounding box (min_x, min_y, max_x, max_y)."""
        # Estimate height based on text and font size
        num_lines = max(1, self.text.count('\n') + 1)
        height = num_lines * self.font_size * 1.5
        return (self.x, self.y, self.x + self.width, self.y + height)
    
    def translate(self, dx: float, dy: float):
        """Move the text box."""
        self.x += dx
        self.y += dy
    
    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'text': self.text,
            'font_size': self.font_size,
            'font_family': self.font_family,
            'color': list(self.color),
            'bold': self.bold,
            'italic': self.italic,
            'underline': self.underline,
            'width': self.width
        }
    
    @staticmethod
    def from_dict(data):
        return TextBox(
            x=data['x'],
            y=data['y'],
            text=data.get('text', ''),
            font_size=data.get('font_size', 16.0),
            font_family=data.get('font_family', 'Sans'),
            color=tuple(data.get('color', [0.0, 0.0, 0.0, 1.0])),
            bold=data.get('bold', False),
            italic=data.get('italic', False),
            underline=data.get('underline', False),
            width=data.get('width', 200.0)
        )


@dataclass
class Point:
    """A point in the drawing with pressure and tilt information."""
    x: float
    y: float
    pressure: float = 1.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    
    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'pressure': self.pressure,
            'tilt_x': self.tilt_x,
            'tilt_y': self.tilt_y
        }
    
    @staticmethod
    def from_dict(data):
        return Point(
            x=data['x'],
            y=data['y'],
            pressure=data.get('pressure', 1.0),
            tilt_x=data.get('tilt_x', 0.0),
            tilt_y=data.get('tilt_y', 0.0)
        )


@dataclass
class Stroke:
    """A stroke consisting of multiple points."""
    points: List[Point] = field(default_factory=list)
    pen_type: PenType = PenType.PEN
    color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # RGBA
    width: float = 2.0
    
    def add_point(self, point: Point):
        """Add a point to the stroke."""
        self.points.append(point)
    
    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Get bounding box (min_x, min_y, max_x, max_y)."""
        if not self.points:
            return (0, 0, 0, 0)
        
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        # Add padding for stroke width
        padding = self.width
        return (min_x - padding, min_y - padding, max_x + padding, max_y + padding)
    
    def contains_point(self, x: float, y: float, tolerance: float = 10.0) -> bool:
        """Check if point is near any part of the stroke."""
        for point in self.points:
            dx = x - point.x
            dy = y - point.y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= tolerance:
                return True
        return False
    
    def translate(self, dx: float, dy: float):
        """Move stroke by offset."""
        for point in self.points:
            point.x += dx
            point.y += dy
    
    def to_dict(self):
        return {
            'points': [p.to_dict() for p in self.points],
            'pen_type': self.pen_type.value,
            'color': list(self.color),
            'width': self.width
        }
    
    @staticmethod
    def from_dict(data):
        return Stroke(
            points=[Point.from_dict(p) for p in data['points']],
            pen_type=PenType(data['pen_type']),
            color=tuple(data['color']),
            width=data['width']
        )


@dataclass
class Shape:
    """A geometric shape with start and end points."""
    shape_type: ShapeType
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # RGBA
    width: float = 2.0
    filled: bool = False
    line_style: str = 'solid'  # 'solid', 'dashed', 'dotted'
    
    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Get bounding box (min_x, min_y, max_x, max_y)."""
        min_x = min(self.start_x, self.end_x)
        max_x = max(self.start_x, self.end_x)
        min_y = min(self.start_y, self.end_y)
        max_y = max(self.start_y, self.end_y)
        # Add padding for stroke width
        padding = self.width
        return (min_x - padding, min_y - padding, max_x + padding, max_y + padding)
    
    def contains_point(self, x: float, y: float, tolerance: float = 10.0) -> bool:
        """Check if point is within the shape or near its boundary."""
        min_x, min_y, max_x, max_y = self.get_bounds()
        return min_x <= x <= max_x and min_y <= y <= max_y
    
    def translate(self, dx: float, dy: float):
        """Move shape by offset."""
        self.start_x += dx
        self.start_y += dy
        self.end_x += dx
        self.end_y += dy
    
    def to_dict(self):
        return {
            'shape_type': self.shape_type.value,
            'start_x': self.start_x,
            'start_y': self.start_y,
            'end_x': self.end_x,
            'end_y': self.end_y,
            'color': list(self.color),
            'width': self.width,
            'filled': self.filled,
            'line_style': self.line_style
        }
    
    @staticmethod
    def from_dict(data):
        return Shape(
            shape_type=ShapeType(data['shape_type']),
            start_x=data['start_x'],
            start_y=data['start_y'],
            end_x=data['end_x'],
            end_y=data['end_y'],
            color=tuple(data['color']),
            width=data['width'],
            filled=data.get('filled', False),
            line_style=data.get('line_style', 'solid')
        )


class Selection:
    """Represents a selection of strokes and shapes."""
    
    def __init__(self):
        self.strokes: List[Stroke] = []
        self.shapes: List[Shape] = []
        self.text_boxes: List[TextBox] = []
        self.bounds: Tuple[float, float, float, float] = (0, 0, 0, 0)  # min_x, min_y, max_x, max_y
    
    def add_stroke(self, stroke: Stroke):
        """Add a stroke to the selection."""
        if stroke not in self.strokes:
            self.strokes.append(stroke)
            self._update_bounds()
    
    def add_shape(self, shape: Shape):
        """Add a shape to the selection."""
        if shape not in self.shapes:
            self.shapes.append(shape)
            self._update_bounds()
    
    def add_text_box(self, text_box: TextBox):
        """Add a text box to the selection."""
        if text_box not in self.text_boxes:
            self.text_boxes.append(text_box)
            self._update_bounds()
    
    def remove_stroke(self, stroke: Stroke):
        """Remove a stroke from the selection."""
        if stroke in self.strokes:
            self.strokes.remove(stroke)
            self._update_bounds()
    
    def remove_shape(self, shape: Shape):
        """Remove a shape from the selection."""
        if shape in self.shapes:
            self.shapes.remove(shape)
            self._update_bounds()
    
    def clear(self):
        """Clear the selection."""
        self.strokes.clear()
        self.shapes.clear()
        self.text_boxes.clear()
        self.bounds = (0, 0, 0, 0)
    
    def is_empty(self) -> bool:
        """Check if selection is empty."""
        return len(self.strokes) == 0 and len(self.shapes) == 0 and len(self.text_boxes) == 0
    
    def _update_bounds(self):
        """Update the bounding box of the selection."""
        if self.is_empty():
            self.bounds = (0, 0, 0, 0)
            return
        
        all_bounds = []
        for stroke in self.strokes:
            all_bounds.append(stroke.get_bounds())
        for shape in self.shapes:
            all_bounds.append(shape.get_bounds())
        for text_box in self.text_boxes:
            all_bounds.append(text_box.get_bounds())
        
        if all_bounds:
            min_x = min(b[0] for b in all_bounds)
            min_y = min(b[1] for b in all_bounds)
            max_x = max(b[2] for b in all_bounds)
            max_y = max(b[3] for b in all_bounds)
            self.bounds = (min_x, min_y, max_x, max_y)
    
    def translate(self, dx: float, dy: float):
        """Move all selected objects."""
        for stroke in self.strokes:
            stroke.translate(dx, dy)
        for shape in self.shapes:
            shape.translate(dx, dy)
        for text_box in self.text_boxes:
            text_box.translate(dx, dy)
        self._update_bounds()
    
    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Get the bounding box of the selection."""
        return self.bounds
    
    def copy(self) -> 'Selection':
        """Create a deep copy of the selection."""
        import copy
        new_selection = Selection()
        new_selection.strokes = [copy.deepcopy(stroke) for stroke in self.strokes]
        new_selection.shapes = [copy.deepcopy(shape) for shape in self.shapes]
        new_selection.text_boxes = [copy.deepcopy(text_box) for text_box in self.text_boxes]
        new_selection._update_bounds()
        return new_selection


class DrawingDocument:
    """A complete drawing document with multiple strokes."""
    
    def __init__(self, note_type: NoteType = NoteType.CANVAS, page_template: PageTemplate = PageTemplate.BLANK):
        self.note_type = note_type
        self.page_template = page_template  # Template for A4 pages
        self.width = 1920
        self.height = 1080
        self.background_color = (1.0, 1.0, 1.0, 1.0)  # White
        
        # For A4_NOTES: pages dictionary, for CANVAS: single page with all strokes
        if note_type == NoteType.A4_NOTES:
            # A4 dimensions at 96 DPI: 794 x 1123 pixels
            self.width = 794
            self.height = 1123
            self.pages: Dict[int, List[Stroke]] = {1: []}  # page_number -> strokes
            self.page_shapes: Dict[int, List[Shape]] = {1: []}  # page_number -> shapes
            self.page_text_boxes: Dict[int, List[TextBox]] = {1: []}  # page_number -> text boxes
            self.current_page = 1
        else:
            self.strokes: List[Stroke] = []  # For canvas mode
            self.shapes: List[Shape] = []  # For canvas mode shapes
            self.text_boxes: List[TextBox] = []  # For canvas mode text boxes
            self.pages = None
            self.page_shapes = None
            self.page_text_boxes = None
            self.current_page = None
    
    def add_stroke(self, stroke: Stroke):
        """Add a stroke to the document."""
        if self.note_type == NoteType.A4_NOTES:
            if self.current_page not in self.pages:
                self.pages[self.current_page] = []
            self.pages[self.current_page].append(stroke)
        else:
            self.strokes.append(stroke)
    
    def add_shape(self, shape):
        """Add a shape to the document."""
        if self.note_type == NoteType.A4_NOTES:
            if self.current_page not in self.page_shapes:
                self.page_shapes[self.current_page] = []
            self.page_shapes[self.current_page].append(shape)
        else:
            self.shapes.append(shape)
    
    def add_text_box(self, text_box):
        """Add a text box to the document."""
        if self.note_type == NoteType.A4_NOTES:
            if self.current_page not in self.page_text_boxes:
                self.page_text_boxes[self.current_page] = []
            self.page_text_boxes[self.current_page].append(text_box)
        else:
            self.text_boxes.append(text_box)
    
    def clear(self):
        """Clear all strokes, shapes, and text boxes (or current page for A4 notes)."""
        if self.note_type == NoteType.A4_NOTES:
            self.pages[self.current_page] = []
            self.page_shapes[self.current_page] = []
            self.page_text_boxes[self.current_page] = []
        else:
            self.strokes.clear()
            self.shapes.clear()
            self.text_boxes.clear()
    
    def get_current_strokes(self) -> List[Stroke]:
        """Get strokes for current view."""
        if self.note_type == NoteType.A4_NOTES:
            return self.pages.get(self.current_page, [])
        else:
            return self.strokes
    
    def get_current_shapes(self):
        """Get shapes for current view."""
        if self.note_type == NoteType.A4_NOTES:
            return self.page_shapes.get(self.current_page, [])
        else:
            return self.shapes
    
    def get_current_text_boxes(self):
        """Get text boxes for current view."""
        if self.note_type == NoteType.A4_NOTES:
            return self.page_text_boxes.get(self.current_page, [])
        else:
            return self.text_boxes
    
    def next_page(self):
        """Go to next page (A4 notes only)."""
        if self.note_type == NoteType.A4_NOTES:
            self.current_page += 1
            if self.current_page not in self.pages:
                self.pages[self.current_page] = []
                self.page_shapes[self.current_page] = []
                self.page_text_boxes[self.current_page] = []
    
    def prev_page(self):
        """Go to previous page (A4 notes only)."""
        if self.note_type == NoteType.A4_NOTES and self.current_page > 1:
            self.current_page -= 1
    
    def get_total_pages(self) -> int:
        """Get total number of pages."""
        if self.note_type == NoteType.A4_NOTES:
            return len(self.pages)
        return 1
    
    def to_dict(self):
        result = {
            'version': '1.0',
            'note_type': self.note_type.value,
            'width': self.width,
            'height': self.height,
            'background_color': list(self.background_color)
        }
        
        if self.note_type == NoteType.A4_NOTES:
            result['page_template'] = self.page_template.value
            result['current_page'] = self.current_page
            result['pages'] = {
                str(page_num): [s.to_dict() for s in strokes]
                for page_num, strokes in self.pages.items()
            }
            result['page_shapes'] = {
                str(page_num): [s.to_dict() for s in shapes]
                for page_num, shapes in self.page_shapes.items()
            }
            result['page_text_boxes'] = {
                str(page_num): [t.to_dict() for t in text_boxes]
                for page_num, text_boxes in self.page_text_boxes.items()
            }
        else:
            result['strokes'] = [s.to_dict() for s in self.strokes]
            result['shapes'] = [s.to_dict() for s in self.shapes]
            result['text_boxes'] = [t.to_dict() for t in self.text_boxes]
        
        return result
    
    @staticmethod
    def from_dict(data):
        # Determine note type from data
        note_type_str = data.get('note_type', 'canvas')
        note_type = NoteType(note_type_str) if note_type_str else NoteType.CANVAS
        
        # Determine page template (with backward compatibility)
        page_template_str = data.get('page_template', 'blank')
        page_template = PageTemplate(page_template_str) if page_template_str else PageTemplate.BLANK
        
        doc = DrawingDocument(note_type=note_type, page_template=page_template)
        doc.width = data.get('width', 1920 if note_type == NoteType.CANVAS else 794)
        doc.height = data.get('height', 1080 if note_type == NoteType.CANVAS else 1123)
        doc.background_color = tuple(data.get('background_color', [1.0, 1.0, 1.0, 1.0]))
        
        if note_type == NoteType.A4_NOTES:
            doc.current_page = data.get('current_page', 1)
            pages_data = data.get('pages', {'1': []})
            doc.pages = {
                int(page_num): [Stroke.from_dict(s) for s in strokes]
                for page_num, strokes in pages_data.items()
            }
            # Load shapes (with backward compatibility)
            page_shapes_data = data.get('page_shapes', {})
            doc.page_shapes = {
                int(page_num): [Shape.from_dict(s) for s in shapes]
                for page_num, shapes in page_shapes_data.items()
            }
            # Load text boxes (with backward compatibility)
            page_text_boxes_data = data.get('page_text_boxes', {})
            doc.page_text_boxes = {
                int(page_num): [TextBox.from_dict(t) for t in text_boxes]
                for page_num, text_boxes in page_text_boxes_data.items()
            }
            # Ensure all pages have shape and text box lists
            for page_num in doc.pages.keys():
                if page_num not in doc.page_shapes:
                    doc.page_shapes[page_num] = []
                if page_num not in doc.page_text_boxes:
                    doc.page_text_boxes[page_num] = []
        else:
            # Backward compatibility: load old format or canvas mode
            doc.strokes = [Stroke.from_dict(s) for s in data.get('strokes', [])]
            doc.shapes = [Shape.from_dict(s) for s in data.get('shapes', [])]
            doc.text_boxes = [TextBox.from_dict(t) for t in data.get('text_boxes', [])]
        
        return doc
    
    def save_to_file(self, filepath: str):
        """Save document to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @staticmethod
    def load_from_file(filepath: str):
        """Load document from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return DrawingDocument.from_dict(data)
