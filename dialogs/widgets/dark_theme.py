"""Shared dark-theme stylesheets (SPEC.md section 2.2 color palette).

Applied app-wide via ``app.setStyleSheet(DARK_APP_STYLESHEET)`` in
``daypart_scheduler.main()`` so every window and dialog - including future
widgets - gets the dark theme. Without these, widgets fall back to the
native style, which on Windows paints white backgrounds that clash with
the app's light text.

Widget-specific stylesheets set directly on widgets still take precedence
over these app-level rules where they overlap.
"""

from pathlib import Path

# Absolute file URL for the combo-box arrow. Relative url() values in
# stylesheets resolve against the working directory, which varies between
# start_scheduler.bat, tests, and ad-hoc runs - so resolve once from here.
_DOWN_ARROW_URL = Path(__file__).with_name("down_arrow.png").as_posix()

DARK_TABLE_STYLESHEET = """
    QTableWidget {
        background-color: #2a2a3e;
        alternate-background-color: #252535;
        color: #f8f8f2;
        gridline-color: #3a3a4e;
        border: 1px solid #3a3a4e;
        border-radius: 6px;
        selection-background-color: #7c3aed;
        selection-color: white;
    }
    QTableWidget::item {
        padding: 4px;
        border: none;
    }
    QTableWidget::item:selected {
        background-color: #7c3aed;
        color: white;
    }
    QHeaderView::section {
        background-color: #2a2a3e;
        color: #f8f8f2;
        border: 1px solid #3a3a4e;
        padding: 4px;
    }
"""

DARK_LIST_STYLESHEET = """
    QListWidget {
        background-color: #2a2a3e;
        alternate-background-color: #252535;
        color: #f8f8f2;
        border: 1px solid #3a3a4e;
        border-radius: 6px;
        padding: 4px;
        selection-background-color: #7c3aed;
        selection-color: white;
    }
    QListWidget::item {
        padding: 4px;
        margin: 1px;
        border: 1px solid transparent;
    }
    QListWidget::item:selected {
        background-color: #7c3aed;
        border: 2px solid #a78bfa;
        color: white;
    }
    QListWidget::item:hover {
        background-color: #3a3a4e;
    }
"""

DARK_FORM_STYLESHEET = """
    QComboBox {
        background-color: #2a2a3e;
        color: #f8f8f2;
        border: 1px solid #3a3a4e;
        border-radius: 4px;
        padding: 6px 12px;
    }
    QComboBox:hover {
        background-color: #3a3a4e;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox::down-arrow {
        image: url("__DOWN_ARROW__");
        width: 12px;
        height: 12px;
    }
    QComboBox QAbstractItemView {
        background-color: #2a2a3e;
        color: #f8f8f2;
        border: 1px solid #3a3a4e;
        selection-background-color: #7c3aed;
        selection-color: white;
        outline: none;
    }
    QSpinBox, QDoubleSpinBox {
        background-color: #2a2a3e;
        color: #f8f8f2;
        border: 1px solid #3a3a4e;
        border-radius: 4px;
        padding: 6px;
    }
    QLineEdit, QTimeEdit {
        background-color: #2a2a3e;
        color: #f8f8f2;
        border: 1px solid #3a3a4e;
        border-radius: 4px;
        padding: 8px;
    }
    QCheckBox, QRadioButton {
        color: #f8f8f2;
        spacing: 8px;
    }
    QMenu {
        background-color: #2a2a3e;
        color: #f8f8f2;
        border: 1px solid #3a3a4e;
    }
    QMenu::item:selected {
        background-color: #7c3aed;
        color: white;
    }
    QToolTip {
        background-color: #2a2a3e;
        color: #f8f8f2;
        padding: 4px 8px;
        border: 1px solid #3a3a4e;
        border-radius: 4px;
    }
"""

# Dialog shells + labels must go dark in the same change: the form rules
# above paint control text light, which would be unreadable on native
# (white) dialog backgrounds.
DARK_FORM_STYLESHEET = DARK_FORM_STYLESHEET.replace("__DOWN_ARROW__", _DOWN_ARROW_URL)

DARK_APP_STYLESHEET = (
    """
    QDialog {
        background-color: #1e1e2e;
    }
    QLabel {
        color: #f8f8f2;
    }
    """
    + DARK_FORM_STYLESHEET
)
