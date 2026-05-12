from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QGroupBox, QHeaderView,
)
from ui.styles import CLR_POSITIVE, CLR_NEGATIVE, CLR_NEUTRAL


def _money(v: float) -> str:
    return f"${v:,.2f}"

def _color(v: float) -> str:
    return CLR_POSITIVE if v > 0 else (CLR_NEGATIVE if v < 0 else CLR_NEUTRAL)


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # ---- Account summary row ---- #
        summary_box = QGroupBox("Account Summary")
        summary_layout = QHBoxLayout(summary_box)
        summary_layout.setSpacing(30)

        self._balance_labels: dict[str, QLabel] = {}
        fields = [
            ("net_liquidating_value", "Net Liq"),
            ("cash_balance",          "Cash"),
            ("option_buying_power",   "Option BP"),
            ("maintenance_excess",    "Maint Excess"),
        ]
        for key, label in fields:
            vbox = QVBoxLayout()
            name_lbl = QLabel(label)
            name_lbl.setObjectName("subheader")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl = QLabel("—")
            val_lbl.setObjectName("value_neutral")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(name_lbl)
            vbox.addWidget(val_lbl)
            summary_layout.addLayout(vbox)
            self._balance_labels[key] = val_lbl

        layout.addWidget(summary_box)

        # ---- Positions table ---- #
        pos_box = QGroupBox("Open Positions")
        pos_layout = QVBoxLayout(pos_box)

        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(9)
        self.pos_table.setHorizontalHeaderLabels([
            "Symbol", "Underlying", "Type", "Qty", "Open Price",
            "Mark", "Unrealized P&L", "Day P&L", "Expires",
        ])
        self.pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pos_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pos_table.verticalHeader().setVisible(False)

        pos_layout.addWidget(self.pos_table)
        layout.addWidget(pos_box, stretch=1)

    # ------------------------------------------------------------------

    def update_account(self, balance: dict):
        for key, lbl in self._balance_labels.items():
            val = balance.get(key, 0)
            lbl.setText(_money(val))
            lbl.setStyleSheet(f"color: {_color(val)}; font-weight: bold; font-size: 15px;")

    def update_positions(self, positions: list):
        self.pos_table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            unreal = float(pos.get("unrealized_gain", 0) or 0)
            day_pl = float(pos.get("realized_day_gain", 0) or 0)

            cells = [
                pos.get("symbol", ""),
                pos.get("underlying_symbol", ""),
                pos.get("instrument_type", ""),
                str(int(float(pos.get("quantity", 0) or 0))),
                _money(float(pos.get("average_open_price", 0) or 0)),
                _money(float(pos.get("mark_price", 0) or 0)),
                _money(unreal),
                _money(day_pl),
                pos.get("expires_at", "")[:10],
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 6:
                    item.setForeground(
                        __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                            CLR_POSITIVE if unreal >= 0 else CLR_NEGATIVE
                        )
                    )
                if col == 7:
                    item.setForeground(
                        __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                            CLR_POSITIVE if day_pl >= 0 else CLR_NEGATIVE
                        )
                    )
                self.pos_table.setItem(row, col, item)
