"""Dark trading-app stylesheet for PyQt6."""

DARK_STYLE = """
QMainWindow, QDialog {
    background-color: #1a1a2e;
    color: #e0e0e0;
}

QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QTabWidget::pane {
    border: 1px solid #16213e;
    background-color: #16213e;
}

QTabBar::tab {
    background-color: #0f3460;
    color: #b0b0c0;
    padding: 8px 18px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background-color: #e94560;
    color: white;
}

QTabBar::tab:hover:!selected {
    background-color: #1a4a7a;
}

QTableWidget {
    background-color: #16213e;
    alternate-background-color: #1e2d4e;
    gridline-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
}

QTableWidget::item:selected {
    background-color: #e94560;
    color: white;
}

QHeaderView::section {
    background-color: #0f3460;
    color: #90c8f0;
    padding: 6px;
    border: none;
    font-weight: bold;
    font-size: 12px;
}

QPushButton {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #1a4a7a;
    border-radius: 5px;
    padding: 6px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #1a4a7a;
    border-color: #e94560;
}

QPushButton:pressed {
    background-color: #e94560;
    color: white;
}

QPushButton:disabled {
    background-color: #2a2a3e;
    color: #666680;
    border-color: #3a3a5e;
}

QPushButton#danger {
    background-color: #6b1a1a;
    border-color: #e94560;
}

QPushButton#danger:hover {
    background-color: #e94560;
    color: white;
}

QPushButton#success {
    background-color: #1a5c2e;
    border-color: #27ae60;
    color: #27ae60;
}

QPushButton#success:hover {
    background-color: #27ae60;
    color: white;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #1a4a7a;
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: #e94560;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #e94560;
}

QComboBox::drop-down {
    border: none;
    background-color: #1a4a7a;
    width: 20px;
    border-radius: 0 4px 4px 0;
}

QComboBox QAbstractItemView {
    background-color: #0f3460;
    color: #e0e0e0;
    selection-background-color: #e94560;
    border: 1px solid #1a4a7a;
}

QLabel {
    color: #e0e0e0;
}

QLabel#header {
    font-size: 16px;
    font-weight: bold;
    color: #90c8f0;
}

QLabel#subheader {
    font-size: 13px;
    font-weight: bold;
    color: #b0b0c0;
}

QLabel#value_positive {
    color: #27ae60;
    font-weight: bold;
}

QLabel#value_negative {
    color: #e94560;
    font-weight: bold;
}

QLabel#value_neutral {
    color: #e0e0e0;
    font-weight: bold;
}

QGroupBox {
    border: 1px solid #0f3460;
    border-radius: 6px;
    margin-top: 12px;
    padding: 10px;
    color: #90c8f0;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}

QTextEdit {
    background-color: #0d0d1a;
    color: #a0e0a0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}

QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #0f3460;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #1a4a7a;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QStatusBar {
    background-color: #0f3460;
    color: #90c8f0;
    border-top: 1px solid #1a4a7a;
}

QMenuBar {
    background-color: #0f3460;
    color: #e0e0e0;
}

QMenuBar::item:selected {
    background-color: #e94560;
}

QMenu {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
}

QMenu::item:selected {
    background-color: #e94560;
}

QCheckBox {
    color: #e0e0e0;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #1a4a7a;
    border-radius: 3px;
    background-color: #0f3460;
}

QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}

QSplitter::handle {
    background-color: #0f3460;
}

QFrame#separator {
    color: #0f3460;
}
"""

# Colour constants used directly in Python code
CLR_POSITIVE = "#27ae60"
CLR_NEGATIVE = "#e94560"
CLR_NEUTRAL  = "#e0e0e0"
CLR_ACCENT   = "#90c8f0"
CLR_BG       = "#16213e"
CLR_BG_DARK  = "#0f3460"
