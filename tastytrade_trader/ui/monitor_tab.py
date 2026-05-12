from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QTextEdit,
)
from PyQt6.QtGui import QColor
from datetime import datetime
from ui.styles import CLR_POSITIVE, CLR_NEGATIVE, CLR_ACCENT, CLR_NEUTRAL

_LOG_COLORS = {
    "DEBUG":   "#555570",
    "INFO":    "#a0e0a0",
    "WARNING": "#f39c12",
    "ERROR":   "#e94560",
}
_MAX_LOG_LINES = 500


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

        splitter = QSplitter(Qt.Orientation.Vertical)

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
        splitter.addWidget(act_box)

        # ---- Engine log ---- #
        log_box = QGroupBox("Engine Log")
        log_layout = QVBoxLayout(log_box)
        log_bar = QHBoxLayout()
        self._log_line_count = 0
        self._auto_scroll = True
        scroll_chk_label = QLabel("Auto-scroll")
        scroll_chk_label.setStyleSheet(f"color: {CLR_ACCENT}; font-size: 11px;")
        self._scroll_btn = QPushButton("Auto-scroll: ON")
        self._scroll_btn.setCheckable(True)
        self._scroll_btn.setChecked(True)
        self._scroll_btn.setFixedWidth(130)
        self._scroll_btn.clicked.connect(self._toggle_scroll)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(70)
        clear_btn.clicked.connect(self._clear_log)
        log_bar.addWidget(self._scroll_btn)
        log_bar.addStretch()
        log_bar.addWidget(clear_btn)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(_MAX_LOG_LINES)
        log_layout.addLayout(log_bar)
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_box)

        splitter.setSizes([200, 300])
        layout.addWidget(splitter, stretch=1)

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

    def add_log_message(self, msg: str, level: str):
        color = _LOG_COLORS.get(level, _LOG_COLORS["INFO"])
        ts = datetime.now().strftime("%H:%M:%S")
        # escape HTML special chars
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        line = (
            f'<span style="color:#555570">{ts}</span> '
            f'<span style="color:{color};font-weight:bold">[{level}]</span> '
            f'<span style="color:{color}">{safe}</span>'
        )
        self.log_view.append(line)
        if self._auto_scroll:
            sb = self.log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _toggle_scroll(self, checked: bool):
        self._auto_scroll = checked
        self._scroll_btn.setText("Auto-scroll: ON" if checked else "Auto-scroll: OFF")

    def _clear_log(self):
        self.log_view.clear()
