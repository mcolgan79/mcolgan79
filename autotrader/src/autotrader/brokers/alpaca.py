"""Alpaca adapter -- the only fully implemented broker today.

Uses the official ``alpaca-py`` SDK. Trading goes through ``TradingClient`` and
market data through ``StockHistoricalDataClient``; both are constructed lazily
so importing this module never costs a network round trip.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

from ..models import (
    Account,
    Bar,
    MarketStatus,
    OrderRequest,
    OrderResult,
    OrderSide,
    Position,
)
from ..config import normalize_base_url
from ..timeframes import (
    BARS_PER_SESSION,
    SESSIONS_PER_YEAR,
    TimeframeError,
    parse_timeframe_parts,
)
from .base import Broker, BrokerError

log = logging.getLogger(__name__)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class AlpacaBroker(Broker):
    name = "alpaca"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        paper: bool = True,
        data_feed: str = "iex",
        data_adjustment: str = "split",
        url_override: str | None = None,
    ) -> None:
        self.paper = paper
        self.data_feed = data_feed.lower()
        self.data_adjustment = data_adjustment.lower()
        self._api_key = api_key
        self._api_secret = api_secret
        self._url_override = normalize_base_url(url_override)
        self._trading = None
        self._data = None

    # -- clients --------------------------------------------------------

    @property
    def trading(self):
        if self._trading is None:
            from alpaca.trading.client import TradingClient

            self._trading = TradingClient(
                api_key=self._api_key,
                secret_key=self._api_secret,
                paper=self.paper,
                url_override=self._url_override,
            )
        return self._trading

    @property
    def data(self):
        if self._data is None:
            from alpaca.data.historical import StockHistoricalDataClient

            self._data = StockHistoricalDataClient(
                api_key=self._api_key, secret_key=self._api_secret
            )
        return self._data

    # -- account --------------------------------------------------------

    def get_account(self) -> Account:
        try:
            acct = self.trading.get_account()
        except Exception as exc:  # noqa: BLE001 - surface a clean error either way
            raise BrokerError(f"could not fetch Alpaca account: {exc}") from exc
        return Account(
            equity=_to_float(acct.equity),
            cash=_to_float(acct.cash),
            buying_power=_to_float(acct.buying_power),
            currency=getattr(acct, "currency", "USD") or "USD",
        )

    def get_positions(self) -> dict[str, Position]:
        try:
            raw = self.trading.get_all_positions()
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(f"could not fetch Alpaca positions: {exc}") from exc

        positions: dict[str, Position] = {}
        for item in raw:
            qty = _to_float(item.qty)
            side = str(getattr(item, "side", "")).lower()
            # Alpaca reports shorts with a negative qty; normalize defensively.
            if "short" in side and qty > 0:
                qty = -qty
            positions[item.symbol] = Position(
                symbol=item.symbol,
                qty=qty,
                avg_entry_price=_to_float(item.avg_entry_price),
                market_value=_to_float(item.market_value),
            )
        return positions

    # -- market data ----------------------------------------------------

    @staticmethod
    def parse_timeframe(timeframe: str):
        """'15Min' -> (TimeFrame(15, Minute), 15, 'minute')."""
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        try:
            amount, unit_name = parse_timeframe_parts(timeframe)
        except TimeframeError as exc:
            raise BrokerError(str(exc)) from exc
        unit = {
            "minute": TimeFrameUnit.Minute,
            "hour": TimeFrameUnit.Hour,
            "day": TimeFrameUnit.Day,
            "week": TimeFrameUnit.Week,
            "month": TimeFrameUnit.Month,
        }[unit_name]
        return TimeFrame(amount, unit), amount, unit_name

    @staticmethod
    def history_window(amount: int, unit_name: str, limit: int) -> timedelta:
        """Calendar span to request so ``limit`` bars actually come back.

        Sessions are ~6.5h and there are ~252 trading days a year, so the wall
        clock always has to be stretched well past the raw bar count.
        """
        per_session = BARS_PER_SESSION[unit_name] / max(amount, 1)
        sessions_needed = limit / max(per_session, 1e-9)
        calendar_days = sessions_needed * (365 / SESSIONS_PER_YEAR)
        return timedelta(days=math.ceil(calendar_days * 1.3) + 10)

    def get_bars(
        self,
        symbols: list[str],
        timeframe: str,
        limit: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, list[Bar]]:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest

        tf, amount, unit_name = self.parse_timeframe(timeframe)
        if end is None:
            end = datetime.now(timezone.utc)
            # The free plan cannot read the most recent 15 minutes of SIP data.
            if self.data_feed == "sip":
                end -= timedelta(minutes=16)
        if start is None:
            start = end - self.history_window(amount, unit_name, limit)

        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=tf,
            start=start,
            end=end,
            feed=DataFeed(self.data_feed),
            adjustment=Adjustment(self.data_adjustment),
        )
        try:
            barset = self.data.get_stock_bars(request)
        except Exception as exc:  # noqa: BLE001
            hint = ""
            if "subscription" in str(exc).lower():
                hint = (
                    " -- your Alpaca plan may not include this data feed; try "
                    'data_feed = "iex" in config.toml'
                )
            raise BrokerError(f"could not fetch bars: {exc}{hint}") from exc

        raw = getattr(barset, "data", {}) or {}
        out: dict[str, list[Bar]] = {}
        for symbol in symbols:
            series = [
                Bar(
                    timestamp=b.timestamp,
                    open=_to_float(b.open),
                    high=_to_float(b.high),
                    low=_to_float(b.low),
                    close=_to_float(b.close),
                    volume=_to_float(b.volume),
                )
                for b in raw.get(symbol, [])
            ]
            series.sort(key=lambda bar: bar.timestamp)
            out[symbol] = series[-limit:]
            if not series:
                log.warning("no %s bars returned for %s", timeframe, symbol)
        return out

    # -- calendar -------------------------------------------------------

    def get_market_status(self) -> MarketStatus:
        try:
            clock = self.trading.get_clock()
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(f"could not fetch market clock: {exc}") from exc
        detail = (
            "regular session open"
            if clock.is_open
            else f"closed; next open {clock.next_open:%Y-%m-%d %H:%M %Z}"
        )
        return MarketStatus(
            is_open=bool(clock.is_open),
            next_open=clock.next_open,
            next_close=clock.next_close,
            detail=detail,
        )

    def is_trading_day(self, day: datetime | None = None) -> bool:
        """True when the calendar has a session on this date (holidays excluded)."""
        from alpaca.trading.requests import GetCalendarRequest

        target = (day or datetime.now(timezone.utc)).date()
        try:
            sessions = self.trading.get_calendar(
                GetCalendarRequest(start=target, end=target)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("calendar lookup failed (%s); assuming a trading day", exc)
            return True
        return bool(sessions)

    # -- orders ---------------------------------------------------------

    def is_shortable(self, symbol: str) -> bool:
        try:
            asset = self.trading.get_asset(symbol)
        except Exception as exc:  # noqa: BLE001
            # Reporting a check that never ran as "passed" is worse than
            # reporting nothing; let the caller show it as a failure.
            raise BrokerError(
                f"could not check whether {symbol} is shortable: {exc}"
            ) from exc
        return bool(getattr(asset, "shortable", False))

    def submit_order(self, request: OrderRequest) -> OrderResult:
        from alpaca.trading.enums import OrderSide as AlpacaSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        if request.order_type != "market":
            return OrderResult(
                request=request,
                status="rejected",
                error=f"unsupported order type {request.order_type!r}",
            )

        payload = MarketOrderRequest(
            symbol=request.symbol,
            qty=request.qty,
            side=AlpacaSide.BUY if request.side is OrderSide.BUY else AlpacaSide.SELL,
            time_in_force=TimeInForce(request.time_in_force),
        )
        try:
            order = self.trading.submit_order(order_data=payload)
        except Exception as exc:  # noqa: BLE001 - a rejection is data, not a crash
            log.error("order rejected: %s (%s)", request, exc)
            return OrderResult(request=request, status="rejected", error=str(exc))

        return OrderResult(
            request=request,
            status=str(getattr(order, "status", "accepted")).split(".")[-1].lower(),
            broker_order_id=str(order.id),
            filled_qty=_to_float(getattr(order, "filled_qty", 0)),
            filled_avg_price=(
                _to_float(order.filled_avg_price)
                if getattr(order, "filled_avg_price", None)
                else None
            ),
            submitted_at=getattr(order, "submitted_at", None),
        )

    def cancel_open_orders(self, symbols: list[str] | None = None) -> int:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        try:
            orders = self.trading.get_orders(
                filter=GetOrdersRequest(
                    status=QueryOrderStatus.OPEN, symbols=list(symbols or [])
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(f"could not list open orders: {exc}") from exc

        cancelled = 0
        for order in orders:
            try:
                self.trading.cancel_order_by_id(order.id)
                cancelled += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("could not cancel order %s: %s", order.id, exc)
        return cancelled
