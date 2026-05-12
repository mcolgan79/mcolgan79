from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox, QTextEdit,
)


def _import_session(use_sandbox: bool):
    """Return the appropriate tastytrade Session callable, regardless of library version."""
    import functools

    if use_sandbox:
        try:
            from tastytrade import CertificationSession
            return CertificationSession
        except ImportError:
            pass
        try:
            from tastytrade.session import CertificationSession
            return CertificationSession
        except ImportError:
            pass
        # v8+: single Session class; pass is_test=True for sandbox
        from tastytrade import Session
        return functools.partial(Session, is_test=True)
    else:
        try:
            from tastytrade import ProductionSession
            return ProductionSession
        except ImportError:
            pass
        # v8+: single Session class; is_test defaults to False for production
        from tastytrade import Session
        return Session


class LoginDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.session  = None
        self.account  = None

        self.setWindowTitle("TastyTrade Trader — Login")
        self.setMinimumWidth(440)          # allow height to grow with errors
        self.setSizeGripEnabled(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 24, 30, 24)

        title = QLabel("TastyTrade Algo Trader")
        title.setObjectName("header")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Sign in with your tastytrade account")
        sub.setObjectName("subheader")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        self.env_combo = QComboBox()
        self.env_combo.addItems(["Production", "Sandbox (certification)"])
        form.addRow("Environment:", self.env_combo)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("tastytrade username / email")
        form.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("password")
        form.addRow("Password:", self.password_edit)

        layout.addLayout(form)

        self.remember_chk = QCheckBox("Remember credentials (stored in OS keychain)")
        layout.addWidget(self.remember_chk)

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("Connect")
        self.login_btn.setObjectName("success")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self._do_login)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.login_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        # Scrollable error area — hidden until needed
        self.error_box = QTextEdit()
        self.error_box.setReadOnly(True)
        self.error_box.setFixedHeight(80)
        self.error_box.setStyleSheet(
            "background:#1a0000; color:#ff6b6b; border:1px solid #c0392b; "
            "border-radius:4px; font-size:12px; padding:4px;"
        )
        self.error_box.hide()
        layout.addWidget(self.error_box)

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

        self.password_edit.returnPressed.connect(self._do_login)

    def _prefill(self):
        username, password = self.settings.load_credentials()
        if username:
            self.username_edit.setText(username)
            self.remember_chk.setChecked(True)
        if password:
            self.password_edit.setText(password)
        use_sandbox = self.settings.get("use_sandbox", False)
        self.env_combo.setCurrentIndex(1 if use_sandbox else 0)

    def _show_error(self, msg: str):
        self.error_box.setPlainText(msg)
        self.error_box.show()
        self.status_lbl.setText("")
        self.adjustSize()

    def _do_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        use_sandbox = self.env_combo.currentIndex() == 1

        if not username or not password:
            self._show_error("Please enter your username and password.")
            return

        self.login_btn.setEnabled(False)
        self.error_box.hide()
        self.status_lbl.setText("Connecting…")

        try:
            SessionCls = _import_session(use_sandbox)
            session = SessionCls(username, password)

            from tastytrade import Account
            accounts = Account.get_accounts(session)
            if not accounts:
                raise RuntimeError("No accounts found for this login.")

            saved_acct_num = self.settings.get("account_number")
            account = next(
                (a for a in accounts if str(a.account_number) == str(saved_acct_num)),
                accounts[0],
            )

            if self.remember_chk.isChecked():
                self.settings.save_credentials(username, password)
            self.settings.set("use_sandbox", use_sandbox)
            self.settings.set("account_number", str(account.account_number))

            self.session = session
            self.account = account
            self.accept()

        except Exception as exc:
            self._show_error(f"Login failed:\n{exc}")
            self.login_btn.setEnabled(True)
