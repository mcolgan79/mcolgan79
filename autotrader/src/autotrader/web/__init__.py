"""Local web dashboard.

A small FastAPI app served on localhost. It reuses the same Engine, Strategy,
and Broker the CLI does -- the browser is another front end, not a second
implementation.
"""

from .service import LoopStatus, TradingService
from .server import DEFAULT_PORT, create_app, serve

__all__ = ["DEFAULT_PORT", "LoopStatus", "TradingService", "create_app", "serve"]
