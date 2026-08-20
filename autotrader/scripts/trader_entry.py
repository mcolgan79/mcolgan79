"""PyInstaller entry point.

PyInstaller needs a real script to freeze, not a console-script entry point, so
this file exists purely to call into the CLI.
"""

from autotrader.cli import main

if __name__ == "__main__":
    main()
