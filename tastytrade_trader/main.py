"""
TastyTrade Algo Trader — entry point.

Run:
    python main.py

Build Windows .exe:
    pyinstaller --onefile --windowed --name "TastyTradeTrader" main.py
"""

import sys
import logging

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from config.settings import SettingsManager
from trading.engine  import TradingEngine
from ui.login_dialog import LoginDialog
from ui.main_window  import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TastyTrade Algo Trader")
    app.setOrganizationName("mcolgan79")

    # High-DPI on Windows
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    settings = SettingsManager()

    login = LoginDialog(settings)
    if login.exec() != LoginDialog.DialogCode.Accepted:
        sys.exit(0)

    session = login.session
    account = login.account

    engine = TradingEngine(session, account)

    window = MainWindow(session, account, settings, engine)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
