"""Dialog for creating and editing a StrategyConfig."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QGroupBox, QTabWidget, QWidget,
    QDialogButtonBox, QMessageBox,
)
from trading.strategy import StrategyConfig, StrategyType, StrategyStatus


class StrategyDialog(QDialog):
    def __init__(self, strategy: StrategyConfig = None, parent=None):
        super().__init__(parent)
        self._strategy = strategy
        self.setWindowTitle("Edit Strategy" if strategy else "New Strategy")
        self.setMinimumWidth(560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._build_ui()
        if strategy:
            self._populate(strategy)

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(18, 18, 18, 18)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(),  "General")
        tabs.addTab(self._build_entry_tab(),    "Entry Rules")
        tabs.addTab(self._build_exit_tab(),     "Exit Rules")
        tabs.addTab(self._build_risk_tab(),     "Risk Limits")
        root.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------ General tab ------

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(10)
        f.setContentsMargins(14, 14, 14, 14)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. SPY 30Δ Short Put")
        f.addRow("Strategy name:", self.name_edit)

        self.type_combo = QComboBox()
        for st in StrategyType:
            self.type_combo.addItem(st.value, st)
        f.addRow("Strategy type:", self.type_combo)

        self.symbols_edit = QLineEdit()
        self.symbols_edit.setPlaceholderText("SPY, QQQ, SPX  (comma-separated)")
        f.addRow("Underlyings:", self.symbols_edit)

        self.scan_spin = QSpinBox()
        self.scan_spin.setRange(1, 1440)
        self.scan_spin.setSuffix(" min")
        self.scan_spin.setValue(5)
        f.addRow("Scan interval:", self.scan_spin)

        self.enabled_chk = QCheckBox("Enabled")
        self.enabled_chk.setChecked(True)
        f.addRow("", self.enabled_chk)

        self.dry_run_chk = QCheckBox("Dry run (simulate orders, don't submit)")
        f.addRow("", self.dry_run_chk)

        return w

    # ------ Entry tab ------

    # Which strategy types use each leg / parameter
    _USES_PUTS = {
        StrategyType.SHORT_PUT, StrategyType.BULL_PUT_SPREAD,
        StrategyType.SHORT_STRANGLE, StrategyType.SHORT_STRADDLE,
        StrategyType.IRON_CONDOR,
    }
    _USES_CALLS = {
        StrategyType.SHORT_CALL, StrategyType.BEAR_CALL_SPREAD,
        StrategyType.SHORT_STRANGLE, StrategyType.SHORT_STRADDLE,
        StrategyType.IRON_CONDOR,
    }
    _USES_WING = {
        StrategyType.BULL_PUT_SPREAD, StrategyType.BEAR_CALL_SPREAD,
        StrategyType.IRON_CONDOR,
    }

    def _build_entry_tab(self) -> QWidget:
        w = QWidget()
        self._entry_form = QFormLayout(w)
        f = self._entry_form
        f.setSpacing(10)
        f.setContentsMargins(14, 14, 14, 14)

        self.dte_min_spin = QSpinBox()
        self.dte_min_spin.setRange(1, 730)
        self.dte_min_spin.setSuffix(" days")
        self.dte_min_spin.setValue(30)
        f.addRow("DTE minimum:", self.dte_min_spin)

        self.dte_max_spin = QSpinBox()
        self.dte_max_spin.setRange(1, 730)
        self.dte_max_spin.setSuffix(" days")
        self.dte_max_spin.setValue(60)
        f.addRow("DTE maximum:", self.dte_max_spin)

        self.put_delta_spin = QDoubleSpinBox()
        self.put_delta_spin.setRange(0.01, 0.99)
        self.put_delta_spin.setSingleStep(0.01)
        self.put_delta_spin.setDecimals(2)
        self.put_delta_spin.setValue(0.30)
        f.addRow("Short put δ target (|δ|):", self.put_delta_spin)

        self.call_delta_spin = QDoubleSpinBox()
        self.call_delta_spin.setRange(0.01, 0.99)
        self.call_delta_spin.setSingleStep(0.01)
        self.call_delta_spin.setDecimals(2)
        self.call_delta_spin.setValue(0.30)
        f.addRow("Short call δ target (|δ|):", self.call_delta_spin)

        self.delta_tol_spin = QDoubleSpinBox()
        self.delta_tol_spin.setRange(0.00, 0.20)
        self.delta_tol_spin.setSingleStep(0.01)
        self.delta_tol_spin.setDecimals(2)
        self.delta_tol_spin.setValue(0.05)
        f.addRow("Delta tolerance (±):", self.delta_tol_spin)

        self.min_prem_spin = QDoubleSpinBox()
        self.min_prem_spin.setRange(0.01, 100.0)
        self.min_prem_spin.setPrefix("$")
        self.min_prem_spin.setDecimals(2)
        self.min_prem_spin.setValue(0.50)
        f.addRow("Min premium (total credit):", self.min_prem_spin)

        self.wing_spin = QDoubleSpinBox()
        self.wing_spin.setRange(1.0, 200.0)
        self.wing_spin.setPrefix("$")
        self.wing_spin.setSingleStep(1.0)
        self.wing_spin.setValue(5.0)
        f.addRow("Spread width (long leg distance):", self.wing_spin)

        # Update visibility whenever strategy type changes
        self.type_combo.currentIndexChanged.connect(self._update_entry_fields)
        self._update_entry_fields()

        return w

    def _update_entry_fields(self):
        st = self.type_combo.currentData()
        f = self._entry_form

        show_put  = st in self._USES_PUTS
        show_call = st in self._USES_CALLS
        show_wing = st in self._USES_WING

        f.setRowVisible(self.put_delta_spin,  show_put)
        f.setRowVisible(self.call_delta_spin, show_call)
        f.setRowVisible(self.wing_spin,       show_wing)

        # Relabel put delta row to reflect its role in this strategy
        put_label = f.labelForField(self.put_delta_spin)
        if put_label:
            if st == StrategyType.SHORT_STRADDLE:
                put_label.setText("ATM delta target (|δ|):")
            elif st in (StrategyType.SHORT_STRANGLE, StrategyType.IRON_CONDOR):
                put_label.setText("Put δ target (|δ|):")
            else:
                put_label.setText("Short put δ target (|δ|):")

        call_label = f.labelForField(self.call_delta_spin)
        if call_label:
            if st == StrategyType.SHORT_STRADDLE:
                call_label.setText("Call δ target (|δ|):")
            elif st in (StrategyType.SHORT_STRANGLE, StrategyType.IRON_CONDOR):
                call_label.setText("Call δ target (|δ|):")
            else:
                call_label.setText("Short call δ target (|δ|):")

        wing_label = f.labelForField(self.wing_spin)
        if wing_label:
            if st == StrategyType.IRON_CONDOR:
                wing_label.setText("Wing width (each side):")
            else:
                wing_label.setText("Spread width (long leg distance):")

    # ------ Exit tab ------

    def _build_exit_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(10)
        f.setContentsMargins(14, 14, 14, 14)

        self.profit_spin = QDoubleSpinBox()
        self.profit_spin.setRange(0.05, 1.00)
        self.profit_spin.setSingleStep(0.05)
        self.profit_spin.setDecimals(2)
        self.profit_spin.setSuffix("  ×  credit (e.g. 0.50 = take 50%)")
        self.profit_spin.setValue(0.50)
        f.addRow("Profit target:", self.profit_spin)

        self.stop_spin = QDoubleSpinBox()
        self.stop_spin.setRange(0.50, 10.0)
        self.stop_spin.setSingleStep(0.25)
        self.stop_spin.setDecimals(2)
        self.stop_spin.setSuffix("  ×  credit (e.g. 2.0 = stop at 200%)")
        self.stop_spin.setValue(2.0)
        f.addRow("Stop loss:", self.stop_spin)

        self.dte_exit_spin = QSpinBox()
        self.dte_exit_spin.setRange(0, 60)
        self.dte_exit_spin.setSuffix(" days")
        self.dte_exit_spin.setValue(21)
        f.addRow("DTE exit (close at):", self.dte_exit_spin)

        note = QLabel(
            "Profit target: close when the option can be bought back for\n"
            "  credit × (1 − profit_target_pct).\n"
            "Stop loss: close when the option costs\n"
            "  credit × (1 + stop_loss_pct) to buy back."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #909090; font-size: 11px;")
        f.addRow("", note)

        return w

    # ------ Risk tab ------

    def _build_risk_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(10)
        f.setContentsMargins(14, 14, 14, 14)

        self.max_contracts_spin = QSpinBox()
        self.max_contracts_spin.setRange(1, 1000)
        self.max_contracts_spin.setValue(1)
        f.addRow("Max contracts / trade:", self.max_contracts_spin)

        self.max_pos_spin = QSpinBox()
        self.max_pos_spin.setRange(1, 100)
        self.max_pos_spin.setValue(1)
        f.addRow("Max positions / underlying:", self.max_pos_spin)

        self.max_risk_trade_spin = QDoubleSpinBox()
        self.max_risk_trade_spin.setRange(100, 1_000_000)
        self.max_risk_trade_spin.setPrefix("$")
        self.max_risk_trade_spin.setSingleStep(500)
        self.max_risk_trade_spin.setDecimals(0)
        self.max_risk_trade_spin.setValue(5000)
        f.addRow("Max risk / trade:", self.max_risk_trade_spin)

        self.max_risk_total_spin = QDoubleSpinBox()
        self.max_risk_total_spin.setRange(100, 10_000_000)
        self.max_risk_total_spin.setPrefix("$")
        self.max_risk_total_spin.setSingleStep(1000)
        self.max_risk_total_spin.setDecimals(0)
        self.max_risk_total_spin.setValue(20000)
        f.addRow("Max total strategy risk:", self.max_risk_total_spin)

        return w

    # ------------------------------------------------------------------ #
    # Populate from existing strategy                                      #
    # ------------------------------------------------------------------ #

    def _populate(self, s: StrategyConfig):
        self.name_edit.setText(s.name)

        idx = self.type_combo.findData(s.strategy_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        self.symbols_edit.setText(", ".join(s.underlyings))
        self.scan_spin.setValue(s.scan_interval_minutes)
        self.enabled_chk.setChecked(s.enabled)
        self.dry_run_chk.setChecked(s.dry_run)

        self.dte_min_spin.setValue(s.dte_min)
        self.dte_max_spin.setValue(s.dte_max)
        self.put_delta_spin.setValue(s.put_delta_target)
        self.call_delta_spin.setValue(s.call_delta_target)
        self.delta_tol_spin.setValue(s.delta_tolerance)
        self.min_prem_spin.setValue(s.min_premium)
        self.wing_spin.setValue(s.wing_width)

        self.profit_spin.setValue(s.profit_target_pct)
        self.stop_spin.setValue(s.stop_loss_pct)
        self.dte_exit_spin.setValue(s.dte_exit)

        self.max_contracts_spin.setValue(s.max_contracts)
        self.max_pos_spin.setValue(s.max_positions_per_underlying)
        self.max_risk_trade_spin.setValue(s.max_risk_per_trade)
        self.max_risk_total_spin.setValue(s.max_total_risk)

    # ------------------------------------------------------------------ #
    # Validation & accept                                                  #
    # ------------------------------------------------------------------ #

    def _accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Strategy name is required.")
            return

        raw_symbols = [s.strip().upper() for s in self.symbols_edit.text().split(",") if s.strip()]
        if not raw_symbols:
            QMessageBox.warning(self, "Validation", "At least one underlying symbol is required.")
            return

        if self.dte_min_spin.value() >= self.dte_max_spin.value():
            QMessageBox.warning(self, "Validation", "DTE minimum must be less than DTE maximum.")
            return

        self.accept()

    def get_strategy(self) -> StrategyConfig:
        """Build (or update) a StrategyConfig from the form values."""
        raw_symbols = [s.strip().upper() for s in self.symbols_edit.text().split(",") if s.strip()]
        st = self.type_combo.currentData()

        # Unified delta_target mirrors put_delta_target for compatibility
        put_d  = self.put_delta_spin.value()
        call_d = self.call_delta_spin.value()

        kwargs = dict(
            name              = self.name_edit.text().strip(),
            strategy_type     = st,
            underlyings       = raw_symbols,
            scan_interval_minutes = self.scan_spin.value(),
            enabled           = self.enabled_chk.isChecked(),
            dry_run           = self.dry_run_chk.isChecked(),
            dte_min           = self.dte_min_spin.value(),
            dte_max           = self.dte_max_spin.value(),
            dte_exit          = self.dte_exit_spin.value(),
            delta_target      = put_d,
            put_delta_target  = put_d,
            call_delta_target = call_d,
            delta_tolerance   = self.delta_tol_spin.value(),
            min_premium       = self.min_prem_spin.value(),
            wing_width        = self.wing_spin.value(),
            profit_target_pct = self.profit_spin.value(),
            stop_loss_pct     = self.stop_spin.value(),
            max_contracts     = self.max_contracts_spin.value(),
            max_positions_per_underlying = self.max_pos_spin.value(),
            max_risk_per_trade  = self.max_risk_trade_spin.value(),
            max_total_risk      = self.max_risk_total_spin.value(),
        )

        if self._strategy:
            # Keep the existing id and status
            kwargs["id"]     = self._strategy.id
            kwargs["status"] = self._strategy.status

        return StrategyConfig(**kwargs)
