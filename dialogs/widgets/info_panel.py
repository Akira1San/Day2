from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QPixmap
from pathlib import Path
from typing import Optional, Dict, Any, List


class CollectionInfoPanel(QWidget):
    """Widget displaying collection information and cover image."""
    
    def __init__(self, parent=None, covers_root: Optional[Path] = None,
                 fallback_dirs: Optional[List[Path]] = None):
        super().__init__(parent)
        self.covers_root = covers_root or Path('.')
        self.fallback_dirs = fallback_dirs or []
        self.setup_ui()
    
    def setup_ui(self):
        self.setFixedWidth(250)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("<b>Collection Info</b>"))
        
        # Cover image in a framed box
        cover_frame = QFrame()
        cover_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        cover_layout = QVBoxLayout(cover_frame)
        self.info_cover = QLabel("Cover:")
        self.info_cover.setFixedSize(200, 280)
        self.info_cover.setAlignment(Qt.AlignCenter)
        cover_layout.addWidget(self.info_cover)
        layout.addWidget(cover_frame)
        
        # Info fields in a framed box
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        info_layout = QVBoxLayout(info_frame)
        self.info_name = QLabel("Name: -")
        self.info_name.setWordWrap(True)
        info_layout.addWidget(self.info_name)
        
        self.info_desc = QLabel("Description:")
        self.info_desc.setWordWrap(True)
        info_layout.addWidget(self.info_desc)
        
        self.info_genre = QLabel("Genre: -")
        info_layout.addWidget(self.info_genre)
        
        self.info_year = QLabel("Year: -")
        info_layout.addWidget(self.info_year)
        layout.addWidget(info_frame)

        layout.addStretch()
    
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
        
        if not cover_full.exists():
            for alt_dir in self.fallback_dirs:
                candidate = alt_dir / Path(cover_path).name
                if candidate.exists():
                    cover_full = candidate
                    break
        
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


class VideoInfoDisplay(QWidget):
    """Widget to display selected video details."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        self.setFixedWidth(250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        frame_layout = QVBoxLayout(frame)

        self.info_label = QLabel("Select a video to see details")
        self.info_label.setWordWrap(True)
        frame_layout.addWidget(self.info_label)

        layout.addWidget(frame)
    
    def set_video_info(self, video: Dict[str, Any]):
        """Display video information."""
        name = video.get('name', '-')
        path = video.get('path', '-')
        duration = int(video.get('duration', 0))
        self.info_label.setText(f"Name: {name}\nPath: {path}\nDuration: {duration}s")
    
    def setText(self, text: str):
        """Maintain compatibility with setText() calls (used in series_dialogs)."""
        self.info_label.setText(text)
