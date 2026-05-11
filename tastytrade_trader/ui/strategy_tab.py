from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
)
from PyQt6.QtGui import QColor

from .strategy_dialog import StrategyDialog
from ..trading.strategy import StrategyConfig, StrategyStatus
from .styles import CLR_POSITIVE, CLR_NEGATIVE, CLR_ACCENT


class StrategyTab(QWidget):
    def __init__(self, engine, settings, parent=None):
        super().__init__(parent)
        self.engine   = engine
        self.settings = settings
        self._build_ui()
        self._load_strategies()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Toolbar
        bar = QHBoxLayout()
        self.add_btn    = QPushButton("+ New Strategy")
        self.edit_btn   = QPushButton("Edit")
        self.remove_btn = QPushButton("Delete")
        self.remove_btn.setObjectName("danger")
        self.toggle_btn = QPushButton("Enable / Disable")

        for btn in (self.add_btn, self.edit_btn, self.remove_btn, self.toggle_btn):
            bar.addWidget(btn)
        bar.addStretch()
        layout.addLayout(bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Name", "Type", "Symbols", "DTE",
            "Delta", "Stop Loss", "Profit Tgt", "Max Risk/Trade",
            "Interval", "Status",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # Connect
        self.add_btn.clicked.connect(self._add_strategy)
        self.edit_btn.clicked.connect(self._edit_strategy)
        self.remove_btn.clicked.connect(self._remove_strategy)
        self.toggle_btn.clicked.connect(self._toggle_strategy)
        self.table.doubleClicked.connect(self._edit_strategy)

    # ------------------------------------------------------------------ #

    def _load_strategies(self):
        saved = self.settings.get_strategies()
        for d in saved:
            try:
                s = StrategyConfig.from_dict(d)
                self.engine.add_strategy(s)
            except Exception:
                pass
        self._refresh_table()

    def _refresh_table(self):
        strategies = self.engine.strategies
        self.table.setRowCount(len(strategies))
        for row, s in enumerate(strategies):
            active = s.enabled and s.status == StrategyStatus.ACTIVE
            cells = [
                s.name,
                s.strategy_type.value,
                ", ".join(s.underlyings),
                f"{s.dte_min}–{s.dte_max}d (exit {s.dte_exit}d)",
                f"P:{s.put_delta_target:.2f} / C:{s.call_delta_target:.2f} ±{s.delta_tolerance:.2f}",
                f"{s.stop_loss_pct:.1f}×",
                f"{s.profit_target_pct:.0%}",
                f"${s.max_risk_per_trade:,.0f}",
                f"{s.scan_interval_minutes}m",
                "● Active" if active else "○ Paused",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 9:
                    item.setForeground(QColor(CLR_POSITIVE if active else CLR_NEGATIVE))
                self.table.setItem(row, col, item)

    def _save_strategies(self):
        self.settings.save_strategies([s.to_dict() for s in self.engine.strategies])

    # ------------------------------------------------------------------ #

    def _add_strategy(self):
        dlg = StrategyDialog(parent=self)
        if dlg.exec():
            s = dlg.get_strategy()
            self.engine.add_strategy(s)
            self._refresh_table()
            self._save_strategies()

    def _edit_strategy(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.engine.strategies):
            return
        existing = self.engine.strategies[row]
        dlg = StrategyDialog(existing, parent=self)
        if dlg.exec():
            updated = dlg.get_strategy()
            self.engine.update_strategy(updated)
            self._refresh_table()
            self._save_strategies()

    def _remove_strategy(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.engine.strategies):
            return
        s = self.engine.strategies[row]
        reply = QMessageBox.question(
            self, "Delete Strategy",
            f"Delete strategy '{s.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.engine.remove_strategy(s.id)
            self._refresh_table()
            self._save_strategies()

    def _toggle_strategy(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.engine.strategies):
            return
        s = self.engine.strategies[row]
        s.enabled = not s.enabled
        self.engine.update_strategy(s)
        self._refresh_table()
        self._save_strategies()
