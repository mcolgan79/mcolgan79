from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel,
    QMenuBar, QMessageBox,
)
from PyQt6.QtGui import QAction

from .dashboard_tab  import DashboardTab
from .strategy_tab   import StrategyTab
from .monitor_tab    import MonitorTab
from .log_tab        import LogTab
from .styles         import DARK_STYLE


class MainWindow(QMainWindow):
    def __init__(self, session, account, settings, engine):
        super().__init__()
        self.session  = session
        self.account  = account
        self.settings = settings
        self.engine   = engine

        self.setWindowTitle(
            f"TastyTrade Algo Trader  —  {account.account_number}"
        )
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(DARK_STYLE)

        self._build_menu()
        self._build_tabs()
        self._build_status_bar()
        self._wire_engine_signals()
        self._start_refresh_timer()

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def _build_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        logout_act = QAction("Log Out", self)
        logout_act.triggered.connect(self._logout)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(logout_act)
        file_menu.addSeparator()
        file_menu.addAction(quit_act)

        # Engine
        eng_menu = mb.addMenu("&Engine")
        start_act = QAction("Start", self)
        start_act.triggered.connect(self.engine.start)
        pause_act = QAction("Pause / Resume", self)
        pause_act.triggered.connect(self._toggle_pause)
        stop_act  = QAction("Stop", self)
        stop_act.triggered.connect(self.engine.stop)
        eng_menu.addAction(start_act)
        eng_menu.addAction(pause_act)
        eng_menu.addAction(stop_act)

        # Help
        help_menu = mb.addMenu("&Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _build_tabs(self):
        tabs = QTabWidget()

        self.dashboard_tab  = DashboardTab()
        self.strategy_tab   = StrategyTab(self.engine, self.settings)
        self.monitor_tab    = MonitorTab(self.engine)
        self.log_tab        = LogTab(self.settings)

        tabs.addTab(self.dashboard_tab, "📊  Dashboard")
        tabs.addTab(self.strategy_tab,  "⚙️  Strategies")
        tabs.addTab(self.monitor_tab,   "🤖  Monitor")
        tabs.addTab(self.log_tab,       "📋  Trade Log")

        self.setCentralWidget(tabs)

    def _build_status_bar(self):
        sb = self.statusBar()
        self.engine_status_lbl = QLabel("Engine: Stopped")
        self.account_lbl       = QLabel(f"Account: {self.account.account_number}")
        sb.addPermanentWidget(self.account_lbl)
        sb.addWidget(self.engine_status_lbl)

    # ------------------------------------------------------------------ #
    # Engine signal wiring                                                 #
    # ------------------------------------------------------------------ #

    def _wire_engine_signals(self):
        sig = self.engine.signals
        sig.status_changed.connect(self._on_engine_status)
        sig.positions_updated.connect(self.dashboard_tab.update_positions)
        sig.account_updated.connect(self.dashboard_tab.update_account)
        sig.order_event.connect(self._on_order_event)
        sig.error_occurred.connect(self._on_error)
        sig.log_message.connect(self._on_log)

    def _on_engine_status(self, status: str):
        self.engine_status_lbl.setText(f"Engine: {status}")
        self.monitor_tab.on_status_changed(status)

    def _on_order_event(self, event: dict):
        self.log_tab.add_trade(event)
        self.monitor_tab.add_activity(event)

    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"⚠  {msg}", 5000)

    def _on_log(self, msg: str, level: str):
        if level in ("ERROR", "WARNING"):
            self.statusBar().showMessage(f"[{level}] {msg}", 4000)

    # ------------------------------------------------------------------ #
    # Periodic UI refresh                                                  #
    # ------------------------------------------------------------------ #

    def _start_refresh_timer(self):
        timer = QTimer(self)
        timer.timeout.connect(self._refresh_monitor)
        timer.start(10_000)  # every 10 seconds

    def _refresh_monitor(self):
        self.monitor_tab.refresh_strategies(
            self.engine.strategies,
            self.engine._last_scan,
            self.engine._positions_cache,
        )

    # ------------------------------------------------------------------ #
    # Menu actions                                                         #
    # ------------------------------------------------------------------ #

    def _toggle_pause(self):
        if self.engine._paused:
            self.engine.resume()
        else:
            self.engine.pause()

    def _logout(self):
        reply = QMessageBox.question(
            self, "Log Out",
            "Stop the engine and log out?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.engine.stop()
            self.settings.clear_credentials()
            self.close()

    def _show_about(self):
        QMessageBox.information(
            self, "About",
            "TastyTrade Algo Trader\n\n"
            "Automated options trading for tastytrade.\n\n"
            "Supported strategies:\n"
            "  Short Put · Short Call · Short Strangle\n"
            "  Short Straddle · Bull Put Spread\n"
            "  Bear Call Spread · Iron Condor\n\n"
            "WARNING: Use at your own risk. Always test with\n"
            "Dry Run mode before live trading.",
        )

    def closeEvent(self, event):
        if self.engine.is_running():
            reply = QMessageBox.question(
                self, "Quit",
                "The trading engine is running. Stop it and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.engine.stop()
        event.accept()
