"""Notes management system for organizing subjects and chapters."""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
import logging

from .stroke import NoteType

logger = logging.getLogger(__name__)


class NotesLibrary:
    """Manages the library of subjects and notes."""
    
    def __init__(self, library_path: Optional[str] = None):
        """Initialize the notes library.
        
        Args:
            library_path: Path to the library directory. If None, uses default.
        """
        if library_path is None:
            library_path = str(Path.home() / ".canvasnote" / "library")
        
        self.library_path = Path(library_path)
        self.library_path.mkdir(parents=True, exist_ok=True)
        
        self.index_file = self.library_path / "index.json"
        self.subjects: Dict[str, Dict] = {}
        self.load_index()
    
    def load_index(self):
        """Load the library index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r') as f:
                    data = json.load(f)
                    self.subjects = data.get('subjects', {})
                logger.info(f"Loaded library index with {len(self.subjects)} subjects")
            except Exception as e:
                logger.error(f"Error loading library index: {e}")
                self.subjects = {}
        else:
            self.subjects = {}
            self.save_index()
    
    def save_index(self):
        """Save the library index to disk."""
        try:
            data = {
                'version': '1.0',
                'subjects': self.subjects
            }
            with open(self.index_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Library index saved")
        except Exception as e:
            logger.error(f"Error saving library index: {e}")
    
    def create_subject(self, subject_name: str) -> bool:
        """Create a new subject.
        
        Args:
            subject_name: Name of the subject to create.
            
        Returns:
            True if created successfully, False if already exists.
        """
        if subject_name in self.subjects:
            return False
        
        subject_dir = self.library_path / subject_name
        subject_dir.mkdir(parents=True, exist_ok=True)
        
        self.subjects[subject_name] = {
            'name': subject_name,
            'path': str(subject_dir),
            'notes': {}
        }
        self.save_index()
        logger.info(f"Created subject: {subject_name}")
        return True
    
    def delete_subject(self, subject_name: str) -> bool:
        """Delete a subject and all its notes.
        
        Args:
            subject_name: Name of the subject to delete.
            
        Returns:
            True if deleted successfully.
        """
        if subject_name not in self.subjects:
            return False
        
        # Delete the directory
        subject_dir = Path(self.subjects[subject_name]['path'])
        if subject_dir.exists():
            import shutil
            shutil.rmtree(subject_dir)
        
        del self.subjects[subject_name]
        self.save_index()
        logger.info(f"Deleted subject: {subject_name}")
        return True
    
    def create_note(self, subject_name: str, note_name: str, note_type: NoteType = NoteType.A4_NOTES, page_template = None) -> Optional[str]:
        """Create a new note in a subject.
        
        Args:
            subject_name: Name of the subject.
            note_name: Name of the note to create.
            note_type: Type of note (CANVAS or A4_NOTES).
            page_template: Template for A4 pages (optional, defaults to BLANK).
            
        Returns:
            Path to the note file, or None if subject doesn't exist.
        """
        if subject_name not in self.subjects:
            return None
        
        # Generate unique filename
        subject_notes = self.subjects[subject_name]['notes']
        note_id = len(subject_notes)
        note_filename = f"{note_id:03d}_{note_name.replace(' ', '_')}.n2i"
        note_path = Path(self.subjects[subject_name]['path']) / note_filename
        
        # Create empty note file with template
        from .stroke import DrawingDocument, PageTemplate
        if page_template is None:
            page_template = PageTemplate.BLANK
        doc = DrawingDocument(note_type=note_type, page_template=page_template)
        doc.save_to_file(str(note_path))
        
        subject_notes[note_name] = {
            'name': note_name,
            'path': str(note_path),
            'type': note_type.value,
            'created': self._get_timestamp()
        }
        self.save_index()
        logger.info(f"Created {note_type.value} note with {page_template.value} template: {subject_name}/{note_name}")
        return str(note_path)
    
    def delete_note(self, subject_name: str, note_name: str) -> bool:
        """Delete a note from a subject.
        
        Args:
            subject_name: Name of the subject.
            note_name: Name of the note to delete.
            
        Returns:
            True if deleted successfully.
        """
        if subject_name not in self.subjects:
            return False
        
        subject_notes = self.subjects[subject_name]['notes']
        if note_name not in subject_notes:
            return False
        
        # Delete the file
        note_path = Path(subject_notes[note_name]['path'])
        if note_path.exists():
            os.unlink(note_path)
        
        del subject_notes[note_name]
        self.save_index()
        logger.info(f"Deleted note: {subject_name}/{note_name}")
        return True
    
    def get_note_path(self, subject_name: str, note_name: str) -> Optional[str]:
        """Get the file path for a note.
        
        Args:
            subject_name: Name of the subject.
            note_name: Name of the note.
            
        Returns:
            Path to the note file, or None if not found.
        """
        if subject_name not in self.subjects:
            return None
        
        subject_notes = self.subjects[subject_name]['notes']
        if note_name not in subject_notes:
            return None
        
        return subject_notes[note_name]['path']
    
    def get_note_type(self, subject_name: str, note_name: str) -> Optional[NoteType]:
        """Get the type of a note.
        
        Args:
            subject_name: Name of the subject.
            note_name: Name of the note.
            
        Returns:
            Note type, or None if not found.
        """
        if subject_name not in self.subjects:
            return None
        
        subject_notes = self.subjects[subject_name]['notes']
        if note_name not in subject_notes:
            return None
        
        note_type_str = subject_notes[note_name].get('type', 'a4_notes')
        return NoteType(note_type_str)
    
    def get_subjects(self) -> List[str]:
        """Get list of all subjects.
        
        Returns:
            List of subject names.
        """
        return sorted(self.subjects.keys())
    
    def get_notes(self, subject_name: str) -> List[str]:
        """Get list of all notes in a subject.
        
        Args:
            subject_name: Name of the subject.
            
        Returns:
            List of note names.
        """
        if subject_name not in self.subjects:
            return []
        
        return sorted(self.subjects[subject_name]['notes'].keys())
    
    def rename_subject(self, old_name: str, new_name: str) -> bool:
        """Rename a subject.
        
        Args:
            old_name: Current name of the subject.
            new_name: New name for the subject.
            
        Returns:
            True if renamed successfully.
        """
        if old_name not in self.subjects or new_name in self.subjects:
            return False
        
        # Rename directory
        old_path = Path(self.subjects[old_name]['path'])
        new_path = self.library_path / new_name
        old_path.rename(new_path)
        
        # Update index
        self.subjects[new_name] = self.subjects[old_name]
        self.subjects[new_name]['name'] = new_name
        self.subjects[new_name]['path'] = str(new_path)
        del self.subjects[old_name]
        
        self.save_index()
        logger.info(f"Renamed subject: {old_name} -> {new_name}")
        return True
    
    def rename_note(self, subject_name: str, old_name: str, new_name: str) -> bool:
        """Rename a note.
        
        Args:
            subject_name: Name of the subject.
            old_name: Current name of the note.
            new_name: New name for the note.
            
        Returns:
            True if renamed successfully.
        """
        if subject_name not in self.subjects:
            return False
        
        subject_notes = self.subjects[subject_name]['notes']
        if old_name not in subject_notes or new_name in subject_notes:
            return False
        
        # Keep the same file, just update the index
        subject_notes[new_name] = subject_notes[old_name]
        subject_notes[new_name]['name'] = new_name
        del subject_notes[old_name]
        
        self.save_index()
        logger.info(f"Renamed note: {subject_name}/{old_name} -> {new_name}")
        return True
    
    def duplicate_note(self, subject_name: str, note_name: str, new_name: str = None) -> Optional[str]:
        """Duplicate a note in a subject.
        
        Args:
            subject_name: Name of the subject.
            note_name: Name of the note to duplicate.
            new_name: Name for the duplicate. If None, generates name like "Note Copy".
            
        Returns:
            Path to the duplicated note file, or None if failed.
        """
        if subject_name not in self.subjects:
            return None
        
        subject_notes = self.subjects[subject_name]['notes']
        if note_name not in subject_notes:
            return None
        
        # Generate new name if not provided
        if new_name is None:
            new_name = f"{note_name} Copy"
            counter = 2
            while new_name in subject_notes:
                new_name = f"{note_name} Copy {counter}"
                counter += 1
        elif new_name in subject_notes:
            return None  # Name already exists
        
        # Get original note info
        original_note = subject_notes[note_name]
        original_path = Path(original_note['path'])
        
        if not original_path.exists():
            logger.error(f"Original note file not found: {original_path}")
            return None
        
        # Generate new filename
        note_id = len(subject_notes)
        new_filename = f"{note_id:03d}_{new_name.replace(' ', '_')}.n2i"
        new_path = Path(self.subjects[subject_name]['path']) / new_filename
        
        # Copy the file
        import shutil
        shutil.copy2(str(original_path), str(new_path))
        
        # Add to index
        subject_notes[new_name] = {
            'name': new_name,
            'path': str(new_path),
            'type': original_note['type'],
            'created': self._get_timestamp()
        }
        self.save_index()
        logger.info(f"Duplicated note: {subject_name}/{note_name} -> {new_name}")
        return str(new_path)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime
        return datetime.now().isoformat()
