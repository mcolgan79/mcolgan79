"""
TastyTrade Algo Trader — entry point.

Run:
    python main.py

Build Windows .exe:
    pyinstaller --onefile --windowed --name "TastyTradeTrader" main.py
"""

import sys
import os
import logging

# When frozen by PyInstaller (--onefile), _MEIPASS is the temp extraction dir.
# Inserting it ensures absolute imports like "from trading.X" resolve correctly.
if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(__file__))

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
