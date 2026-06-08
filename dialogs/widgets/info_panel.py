from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QPixmap
from pathlib import Path
from typing import Optional, Dict, Any


class CollectionInfoPanel(QWidget):
    """Widget displaying collection information and cover image."""
    
    def __init__(self, parent=None, covers_root: Optional[Path] = None):
        super().__init__(parent)
        self.covers_root = covers_root or Path('.')
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Collection Info</b>"))
        
        # Cover image first, fixed size
        self.info_cover = QLabel("Cover:")
        self.info_cover.setFixedSize(200, 280)
        self.info_cover.setAlignment(Qt.AlignCenter)
        self.info_cover.setStyleSheet("border: 1px solid gray;")
        layout.addWidget(self.info_cover)
        
        self.info_name = QLabel("Name: -")
        layout.addWidget(self.info_name)
        
        self.info_desc = QLabel("Description:")
        self.info_desc.setWordWrap(True)
        layout.addWidget(self.info_desc)
        
        self.info_genre = QLabel("Genre: -")
        layout.addWidget(self.info_genre)
        
        self.info_year = QLabel("Year: -")
        layout.addWidget(self.info_year)
    
    def set_collection_info(self, info: Dict[str, Any]):
        """Update displayed collection information."""
        self.info_name.setText(f"Name: {info.get('name', '-')}")
        self.info_desc.setText(f"Description: {info.get('description', '-')}")
        self.info_genre.setText(f"Genre: {', '.join(info.get('genre', [])) if info.get('genre') else '-'}")
        self.info_year.setText(f"Year: {info.get('year', '-')}")
    
    def set_cover_image(self, cover_path: Optional[str]):
        """Display cover image, resolved relative to covers_root."""
        if not cover_path:
            self.info_cover.setText("Cover:\n(No cover)")
            self.info_cover.setPixmap(QPixmap())
            return
        
        cover_full = Path(cover_path)
        if not cover_full.is_absolute():
            cover_full = self.covers_root / cover_path
        
        if cover_full.exists():
            pixmap = QPixmap(str(cover_full))
            if not pixmap.isNull():
                scaled = pixmap.scaled(200, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.info_cover.setPixmap(scaled)
            else:
                self.info_cover.setText("Cover:\n(invalid image)")
                self.info_cover.setPixmap(QPixmap())
        else:
            self.info_cover.setText(f"Cover:\n{cover_path}\n(not found)")
            self.info_cover.setPixmap(QPixmap())
    
    def clear(self):
        """Clear all information."""
        self.info_name.setText("Name: -")
        self.info_desc.setText("Description: -")
        self.info_genre.setText("Genre: -")
        self.info_year.setText("Year: -")
        self.info_cover.setText("Cover:\n(No cover)")
        self.info_cover.setPixmap(QPixmap())


class VideoInfoDisplay(QLabel):
    """Simple widget to display selected video details."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setText("Select a video to see details")
    
    def set_video_info(self, video: Dict[str, Any]):
        """Display video information."""
        name = video.get('name', '-')
        path = video.get('path', '-')
        duration = int(video.get('duration', 0))
        self.setText(f"Name: {name}\nPath: {path}\nDuration: {duration}s")
