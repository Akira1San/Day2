from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton, QListWidget, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class SchedulePreviewDialog(QDialog):
    """Modal dialog to preview a saved schedule (30-day calendar) with horizontal scrolling."""

    def __init__(self, parent=None, profile_name: str = "", calendar_data: dict = None):
        super().__init__(parent)
        self.profile_name = profile_name
        self.calendar_data = calendar_data or {}
        self.setWindowTitle(f"Schedule Preview - {profile_name}")
        self.setModal(True)
        self.resize(1400, 700)
        self.setup_ui()
        self.apply_styles()
        self.populate_schedule()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Title label with profile name
        title_label = QLabel(f"Schedule Preview - {self.profile_name}")
        title_label.setFont(QFont("", 16, QFont.Bold))
        layout.addWidget(title_label)

        # Scroll area with horizontal scrolling
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Container widget inside scroll area - horizontal layout for days
        container = QWidget()
        self.container_layout = QHBoxLayout(container)
        self.container_layout.setSpacing(20)
        self.container_layout.setAlignment(Qt.AlignLeft)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Cancel button at bottom
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def apply_styles(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #f8f8f2; }
            QPushButton {
                background-color: #2a2a3e;
                color: #f8f8f2;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3a3a4e; }
            QPushButton:pressed { background-color: #4a4a5e; }
            QScrollArea {
                background-color: #2a2a3e;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
            }
            QWidget {
                background-color: #2a2a3e;
            }
        """)

    def populate_schedule(self):
        # Sort calendar keys by date (they are like "2026-05-02_saturday")
        sorted_keys = sorted(self.calendar_data.keys())

        for key in sorted_keys:
            day_info = self.calendar_data[key]
            date_str = day_info.get("date", key)
            day_name = day_info.get("day", "")
            entries = day_info.get("entries", [])

            # Create a vertical widget for this day
            day_widget = QWidget()
            day_layout = QVBoxLayout(day_widget)
            day_layout.setSpacing(4)

            # Day header (vertical orientation)
            header = QLabel(f"{date_str}\n{day_name}")
            header.setFont(QFont("", 11, QFont.Bold))
            is_weekend = day_name.lower() in ("saturday", "sunday")
            header_color = "#ef4444" if is_weekend else "#7c3aed"
            header.setStyleSheet(f"color: {header_color};")
            header.setAlignment(Qt.AlignCenter)
            day_layout.addWidget(header)

            # Separator line
            line = QLabel("─" * 40)
            line.setStyleSheet("color: #3a3a4e;")
            day_layout.addWidget(line)

            # Entries for this day (vertical list)
            entries_list = QListWidget()
            entries_list.setFixedHeight(500)
            entries_list.setStyleSheet("""
                QListWidget {
                    background-color: #1e1e2e;
                    border: 1px solid #3a3a4e;
                    border-radius: 4px;
                }
                QListWidget::item {
                    padding: 4px;
                    color: #a0a0b0;
                }
            """)

            for entry in entries:
                time_str = entry.get("time", "00:00:00")
                video_name = entry.get("file", "").split("/")[-1]  # extract filename
                if not video_name:
                    video_name = entry.get("video_name", "Unknown")
                entry_text = f"{time_str} {video_name}"
                entries_list.addItem(entry_text)

            day_layout.addWidget(entries_list)
            self.container_layout.addWidget(day_widget)
