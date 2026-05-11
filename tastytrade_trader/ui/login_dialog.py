from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QMessageBox,
)


class LoginDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.session  = None
        self.account  = None

        self.setWindowTitle("TastyTrade Trader — Login")
        self.setFixedSize(420, 340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._build_ui()
        self._prefill()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
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

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

    def _do_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        use_sandbox = self.env_combo.currentIndex() == 1

        if not username or not password:
            self.status_lbl.setText("Please enter username and password.")
            return

        self.login_btn.setEnabled(False)
        self.status_lbl.setText("Connecting…")

        try:
            if use_sandbox:
                from tastytrade import CertificationSession as SessionCls
            else:
                from tastytrade import ProductionSession as SessionCls

            session = SessionCls(username, password)

            from tastytrade import Account
            accounts = Account.get_accounts(session)
            if not accounts:
                raise RuntimeError("No accounts found for this login.")

            # Use the account number from settings, or default to first
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
            self.status_lbl.setText(f"Login failed: {exc}")
            self.login_btn.setEnabled(True)
