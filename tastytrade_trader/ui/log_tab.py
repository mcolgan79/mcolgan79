import csv
from datetime import datetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QLabel,
)
from PyQt6.QtGui import QColor
from ui.styles import CLR_POSITIVE, CLR_NEGATIVE, CLR_ACCENT

_COLS = ["Time", "Order ID", "Strategy", "Symbol", "Type", "Description", "Price"]


class LogTab(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._build_ui()
        self._load_history()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        bar = QHBoxLayout()
        self.count_lbl = QLabel("0 trades")
        self.count_lbl.setStyleSheet(f"color: {CLR_ACCENT};")
        export_btn = QPushButton("Export CSV…")
        export_btn.clicked.connect(self._export_csv)
        bar.addWidget(self.count_lbl)
        bar.addStretch()
        bar.addWidget(export_btn)
        layout.addLayout(bar)

        self.table = QTableWidget()
        self.table.setColumnCount(len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def _load_history(self):
        trades = self.settings.load_trades()
        for t in reversed(trades):
            self._insert_row(t)

    def add_trade(self, event: dict):
        self.settings.append_trade(event)
        self._insert_row(event)

    def _insert_row(self, event: dict):
        row = 0
        self.table.insertRow(row)
        etype = event.get("type", "")
        color = CLR_POSITIVE if etype == "entry" else (
            CLR_NEGATIVE if etype == "exit" else CLR_ACCENT
        )
        ts  = event.get("timestamp", "")[:19].replace("T", " ")
        cells = [
            ts,
            event.get("order_id", "—"),
            event.get("strategy", ""),
            event.get("symbol", ""),
            etype.upper(),
            event.get("description", event.get("reason", "")),
            f"${float(event.get('price', 0)):.2f}",
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(color))
            self.table.setItem(row, col, item)
        self.count_lbl.setText(f"{self.table.rowCount()} trades")

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Trade Log", f"trades_{datetime.now():%Y%m%d}.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(_COLS)
            for row in range(self.table.rowCount()):
                writer.writerow([
                    self.table.item(row, col).text() if self.table.item(row, col) else ""
                    for col in range(len(_COLS))
                ])
