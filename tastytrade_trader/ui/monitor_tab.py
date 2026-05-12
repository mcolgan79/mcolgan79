from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtGui import QColor
from datetime import datetime
from ui.styles import CLR_POSITIVE, CLR_NEGATIVE, CLR_ACCENT, CLR_NEUTRAL


class MonitorTab(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._build_ui()
        self._start_clock()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # ---- Engine status row ---- #
        status_box = QGroupBox("Engine Status")
        status_row = QHBoxLayout(status_box)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {CLR_NEGATIVE}; font-size: 20px;")
        self.status_lbl = QLabel("Stopped")
        self.status_lbl.setObjectName("header")

        self.clock_lbl = QLabel("")
        self.clock_lbl.setStyleSheet(f"color: {CLR_ACCENT}; font-size: 13px;")

        self.start_btn  = QPushButton("▶  Start Engine")
        self.start_btn.setObjectName("success")
        self.pause_btn  = QPushButton("⏸  Pause")
        self.stop_btn   = QPushButton("⏹  Stop Engine")
        self.stop_btn.setObjectName("danger")

        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_lbl)
        status_row.addStretch()
        status_row.addWidget(self.clock_lbl)
        status_row.addSpacing(20)
        status_row.addWidget(self.start_btn)
        status_row.addWidget(self.pause_btn)
        status_row.addWidget(self.stop_btn)
        layout.addWidget(status_box)

        # ---- Strategy status table ---- #
        strat_box = QGroupBox("Active Strategies")
        strat_layout = QVBoxLayout(strat_box)
        self.strat_table = QTableWidget()
        self.strat_table.setColumnCount(5)
        self.strat_table.setHorizontalHeaderLabels([
            "Strategy", "Symbols", "Last Scan", "Positions", "Status",
        ])
        self.strat_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.strat_table.setAlternatingRowColors(True)
        self.strat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.strat_table.verticalHeader().setVisible(False)
        strat_layout.addWidget(self.strat_table)
        layout.addWidget(strat_box)

        # ---- Recent activity ---- #
        act_box = QGroupBox("Recent Activity (last 50 events)")
        act_layout = QVBoxLayout(act_box)
        self.activity_table = QTableWidget()
        self.activity_table.setColumnCount(5)
        self.activity_table.setHorizontalHeaderLabels([
            "Time", "Strategy", "Symbol", "Type", "Details",
        ])
        self.activity_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.activity_table.verticalHeader().setVisible(False)
        act_layout.addWidget(self.activity_table)
        layout.addWidget(act_box, stretch=1)

        # Connections
        self.start_btn.clicked.connect(self._start_engine)
        self.pause_btn.clicked.connect(self._pause_engine)
        self.stop_btn.clicked.connect(self._stop_engine)

    def _start_clock(self):
        timer = QTimer(self)
        timer.timeout.connect(self._tick_clock)
        timer.start(1000)

    def _tick_clock(self):
        self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S  %Z"))

    # ------------------------------------------------------------------ #

    def _start_engine(self):
        self.engine.start()

    def _pause_engine(self):
        if self.engine._paused:
            self.engine.resume()
            self.pause_btn.setText("⏸  Pause")
        else:
            self.engine.pause()
            self.pause_btn.setText("▶  Resume")

    def _stop_engine(self):
        self.engine.stop()

    # ------------------------------------------------------------------ #
    # Called by main window when signals arrive                           #
    # ------------------------------------------------------------------ #

    def on_status_changed(self, status: str):
        running = status == "Running"
        paused  = status == "Paused"
        dot_color = CLR_POSITIVE if running else (CLR_ACCENT if paused else CLR_NEGATIVE)
        self.status_dot.setStyleSheet(f"color: {dot_color}; font-size: 20px;")
        self.status_lbl.setText(status)
        self.start_btn.setEnabled(not running and not paused)
        self.stop_btn.setEnabled(running or paused)

    def refresh_strategies(self, strategies: list, last_scans: dict, positions: list):
        self.strat_table.setRowCount(len(strategies))
        for row, s in enumerate(strategies):
            pos_count = sum(
                1 for p in positions
                if p.get("underlying_symbol") in s.underlyings
                and p.get("instrument_type") == "Equity Option"
            )
            last = last_scans.get(s.id)
            last_str = last.strftime("%H:%M:%S") if last else "—"
            cells = [
                s.name,
                ", ".join(s.underlyings),
                last_str,
                str(pos_count),
                "Active" if s.enabled else "Paused",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 4:
                    item.setForeground(QColor(CLR_POSITIVE if s.enabled else CLR_NEGATIVE))
                self.strat_table.setItem(row, col, item)

    def add_activity(self, event: dict):
        ts  = event.get("timestamp", "")[:19].replace("T", " ")
        row = 0
        self.activity_table.insertRow(row)

        etype = event.get("type", "")
        color = CLR_POSITIVE if etype == "entry" else (CLR_NEGATIVE if etype in ("exit","dry_run") else CLR_ACCENT)

        cells = [
            ts,
            event.get("strategy", ""),
            event.get("symbol", ""),
            etype.upper(),
            event.get("description", event.get("reason", "")),
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(color))
            self.activity_table.setItem(row, col, item)

        # Keep only 50 rows
        while self.activity_table.rowCount() > 50:
            self.activity_table.removeRow(self.activity_table.rowCount() - 1)
