import configparser
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QMessageBox
)

from utils import get_config_paths


class ConfigDialog(QDialog):
    """Modal dialog for configuring application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Config Settings")
        self.setModal(True)
        self.config_path = "config.ini"
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        collection_path, blacklist_path = get_config_paths()

        # Collection path
        layout.addWidget(QLabel("Collection Path:"))
        collection_layout = QHBoxLayout()
        self.collection_path_edit = QLineEdit()
        self.collection_path_edit.setPlaceholderText(collection_path)
        collection_layout.addWidget(self.collection_path_edit)
        browse_col_btn = QPushButton("Browse")
        browse_col_btn.clicked.connect(self.browse_collection_path)
        collection_layout.addWidget(browse_col_btn)
        layout.addLayout(collection_layout)

        # Blacklist path
        layout.addWidget(QLabel("Blacklist Path:"))
        blacklist_layout = QHBoxLayout()
        self.blacklist_path_edit = QLineEdit()
        self.blacklist_path_edit.setPlaceholderText(blacklist_path)
        blacklist_layout.addWidget(self.blacklist_path_edit)
        browse_bl_btn = QPushButton("Browse")
        browse_bl_btn.clicked.connect(self.browse_blacklist_path)
        blacklist_layout.addWidget(browse_bl_btn)
        layout.addLayout(blacklist_layout)

        # Covers path
        layout.addWidget(QLabel("Covers Path (optional):"))
        covers_layout = QHBoxLayout()
        self.covers_path_edit = QLineEdit()
        self.covers_path_edit.setPlaceholderText("Leave empty to use default")
        covers_layout.addWidget(self.covers_path_edit)
        browse_cov_btn = QPushButton("Browse")
        browse_cov_btn.clicked.connect(self.browse_covers_path)
        covers_layout.addWidget(browse_cov_btn)
        layout.addLayout(covers_layout)

        # Schedule profiles
        layout.addWidget(QLabel("Schedule Profiles (comma-separated names):"))
        self.schedule_profiles_edit = QLineEdit()
        self.schedule_profiles_edit.setPlaceholderText("akiratv, superman, horror")
        layout.addWidget(self.schedule_profiles_edit)

        # Auto-add videos option
        self.auto_add_check = QCheckBox("Auto-add videos for Random Fill")
        self.auto_add_check.setToolTip(
            "When enabled, all non-blacklisted videos are automatically added to the 'Added Videos' list when a collection is loaded in Random Fill dialog"
        )
        layout.addWidget(self.auto_add_check)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def browse_collection_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Collection Directory", "")
        if path:
            self.collection_path_edit.setText(path)

    def browse_blacklist_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Blacklist Directory", "")
        if path:
            self.blacklist_path_edit.setText(path)

    def browse_covers_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Covers Directory", "")
        if path:
            self.covers_path_edit.setText(path)

    def load_config(self):
        if Path(self.config_path).exists():
            config = configparser.ConfigParser()
            config.read(self.config_path)
            if 'Paths' in config:
                self.collection_path_edit.setText(config['Paths'].get('collection_path', ''))
                self.blacklist_path_edit.setText(config['Paths'].get('blacklist_path', ''))
                self.covers_path_edit.setText(config['Paths'].get('covers_path', ''))
            if 'ScheduleProfiles' in config:
                self.schedule_profiles_edit.setText(config['ScheduleProfiles'].get('profiles', ''))
            if 'RandomFill' in config:
                auto_add = config['RandomFill'].get('auto_add', 'false').lower()
                self.auto_add_check.setChecked(auto_add in ('true', '1', 'yes', 'on'))

    def save_config(self):
        config = configparser.ConfigParser()
        config['Paths'] = {
            'collection_path': self.collection_path_edit.text(),
            'blacklist_path': self.blacklist_path_edit.text(),
            'covers_path': self.covers_path_edit.text()
        }
        profiles = self.schedule_profiles_edit.text().strip()
        if profiles:
            config['ScheduleProfiles'] = {'profiles': profiles}
        config['RandomFill'] = {
            'auto_add': 'true' if self.auto_add_check.isChecked() else 'false'
        }
        with open(self.config_path, 'w') as f:
            config.write(f)
        self.accept()
