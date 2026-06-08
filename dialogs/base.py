from PySide6.QtWidgets import QDialog, QLineEdit, QLabel, QHBoxLayout, QTimeEdit
from PySide6.QtCore import QTime


class BaseTagDialog(QDialog):
    """Base class for dialogs that require start/end time inputs."""

    def __init__(self, parent=None, tag=None):
        super().__init__(parent)
        self.tag = tag
        self.collection_videos = []
        self.blacklist = []

    def _setup_time_inputs(self, layout: QHBoxLayout, start_time: QTime = None, end_time: QTime = None):
        """Create start and end time editors and add them to the given layout."""
        start_time = start_time or QTime(0, 0)
        end_time = end_time or QTime(1, 0)

        layout.addWidget(QLabel("Start Time:"))
        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        self.start_time_edit.setTime(start_time)
        layout.addWidget(self.start_time_edit)

        layout.addWidget(QLabel("End Time:"))
        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm")
        self.end_time_edit.setTime(end_time)
        layout.addWidget(self.end_time_edit)
