"""
Algorithmic trading engine for tastytrade.

Runs in a background thread with its own asyncio event loop.
Communicates back to the UI via Qt signals.
"""

import asyncio
import logging
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from trading.strategy import StrategyConfig, StrategyStatus, StrategyType
from trading.risk_manager import RiskManager

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Signals (must live in the main thread; engine emits across threads) #
# ------------------------------------------------------------------ #

class EngineSignals(QObject):
    status_changed   = pyqtSignal(str)          # plain status text
    log_message      = pyqtSignal(str, str)     # (message, level)
    positions_updated = pyqtSignal(list)        # list[dict]
    account_updated  = pyqtSignal(dict)         # balance dict
    order_event      = pyqtSignal(dict)         # placed / closed order info
    error_occurred   = pyqtSignal(str)


# ------------------------------------------------------------------ #
# Engine                                                             #
# ------------------------------------------------------------------ #

class TradingEngine:
    def __init__(self, session, account):
        self.session  = session
        self.account  = account
        self.signals  = EngineSignals()
        self.risk     = RiskManager()

        self.strategies: List[StrategyConfig] = []
        self._running   = False
        self._paused    = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        self._last_scan: Dict[str, datetime] = {}
        self._positions_cache: List[dict] = []
        self._balance_cache: dict = {}

    # ---------------------------------------------------------------- #
    # Lifecycle                                                         #
    # ---------------------------------------------------------------- #

    def start(self):
        if self._running:
            return
        self._running = True
        self._paused  = False
        self._thread  = threading.Thread(target=self._run_loop, daemon=True, name="TradingEngine")
        self._thread.start()
        self.signals.status_changed.emit("Running")
        self._log("Trading engine started", "INFO")

    def stop(self):
        self._running = False
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=10)
        self.signals.status_changed.emit("Stopped")
        self._log("Trading engine stopped", "INFO")

    def pause(self):
        self._paused = True
        self.signals.status_changed.emit("Paused")
        self._log("Trading engine paused", "INFO")

    def resume(self):
        self._paused = False
        self.signals.status_changed.emit("Running")
        self._log("Trading engine resumed", "INFO")

    def is_running(self) -> bool:
        return self._running and not self._paused

    # ---------------------------------------------------------------- #
    # Strategy management (can be called from main thread)             #
    # ---------------------------------------------------------------- #

    def add_strategy(self, strategy: StrategyConfig):
        self.strategies.append(strategy)

    def remove_strategy(self, strategy_id: str):
        self.strategies = [s for s in self.strategies if s.id != strategy_id]

    def update_strategy(self, updated: StrategyConfig):
        for i, s in enumerate(self.strategies):
            if s.id == updated.id:
                self.strategies[i] = updated
                return

    # ---------------------------------------------------------------- #
    # Internal async machinery                                          #
    # ---------------------------------------------------------------- #

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:
            logger.exception("Engine loop crashed")
            self.signals.error_occurred.emit(str(exc))
        finally:
            self._loop.close()

    async def _main(self):
        while self._running:
            if not self._paused:
                try:
                    await self._refresh_account()
                    await self._scan_entries()
                    await self._monitor_exits()
                except Exception as exc:
                    logger.error("Main-loop error: %s", exc)
                    self.signals.error_occurred.emit(str(exc))
            await asyncio.sleep(30)

    # ---------------------------------------------------------------- #
    # Account refresh                                                   #
    # ---------------------------------------------------------------- #

    async def _refresh_account(self):
        try:
            positions = self.account.get_positions(self.session)
            self._positions_cache = [self._position_to_dict(p) for p in positions]

            balances = self.account.get_balances(self.session)
            self._balance_cache = self._balances_to_dict(balances)

            self.signals.positions_updated.emit(self._positions_cache)
            self.signals.account_updated.emit(self._balance_cache)
        except Exception as exc:
            logger.warning("Account refresh failed: %s", exc)

    @staticmethod
    def _position_to_dict(pos) -> dict:
        """Convert a tastytrade Position object to a plain dict."""
        return {
            "symbol":             getattr(pos, "symbol", ""),
            "underlying_symbol":  getattr(pos, "underlying_symbol", ""),
            "instrument_type":    str(getattr(pos, "instrument_type", "")),
            "quantity":           float(getattr(pos, "quantity", 0) or 0),
            "average_open_price": float(getattr(pos, "average_open_price", 0) or 0),
            "close_price":        float(getattr(pos, "close_price", 0) or 0),
            "mark_price":         float(getattr(pos, "mark_price", 0) or 0),
            "multiplier":         float(getattr(pos, "multiplier", 100) or 100),
            "realized_day_gain":  float(getattr(pos, "realized_day_gain", 0) or 0),
            "unrealized_gain":    float(getattr(pos, "unrealized_gain", 0) or 0),
            "expires_at":         str(getattr(pos, "expires_at", "") or ""),
        }

    @staticmethod
    def _balances_to_dict(bal) -> dict:
        def _f(attr):
            return float(getattr(bal, attr, 0) or 0)
        return {
            "cash_balance":              _f("cash_balance"),
            "net_liquidating_value":     _f("net_liquidating_value"),
            "option_buying_power":       _f("option_buying_power"),
            "maintenance_excess":        _f("maintenance_excess"),
            "day_trading_buying_power":  _f("day_trading_buying_power"),
        }

    # ---------------------------------------------------------------- #
    # Entry scanning                                                    #
    # ---------------------------------------------------------------- #

    async def _scan_entries(self):
        for strategy in self.strategies:
            if not strategy.enabled or strategy.status != StrategyStatus.ACTIVE:
                continue
            last = self._last_scan.get(strategy.id)
            if last:
                elapsed_min = (datetime.now() - last).total_seconds() / 60
                if elapsed_min < strategy.scan_interval_minutes:
                    continue
            self._last_scan[strategy.id] = datetime.now()
            for symbol in strategy.underlyings:
                await self._process_entry(strategy, symbol)

    async def _process_entry(self, strategy: StrategyConfig, symbol: str):
        # Gate: don't add more positions than allowed
        existing = self._positions_for(strategy, symbol)
        if len(existing) >= strategy.max_positions_per_underlying:
            self._log(
                f"SKIP [{strategy.name}] {symbol}: at max positions "
                f"({len(existing)}/{strategy.max_positions_per_underlying})",
                "DEBUG",
            )
            return

        try:
            from tastytrade.instruments import NestedOptionChain
            chains = await asyncio.get_event_loop().run_in_executor(
                None, NestedOptionChain.get_chain, self.session, symbol
            )
            if not chains:
                self._log(f"No option chain returned for {symbol}", "WARNING")
                return
            chain = chains[0]
        except Exception as exc:
            self._log(f"Could not fetch chain for {symbol}: {exc}", "ERROR")
            return

        today = date.today()
        valid_exps = []
        for exp in chain.expirations:
            dte = (exp.expiration_date - today).days
            if strategy.dte_min <= dte <= strategy.dte_max:
                valid_exps.append((dte, exp))

        self._log(
            f"SCAN [{strategy.name}] {symbol}: chain has {len(chain.expirations)} expiration(s); "
            f"looking for {strategy.dte_min}–{strategy.dte_max} DTE",
            "INFO",
        )

        if not valid_exps:
            self._log(
                f"SKIP [{strategy.name}] {symbol}: no expirations in "
                f"{strategy.dte_min}–{strategy.dte_max} DTE window",
                "WARNING",
            )
            return

        # Choose expiration closest to the midpoint of the DTE window
        target_dte = (strategy.dte_min + strategy.dte_max) / 2
        valid_exps.sort(key=lambda x: abs(x[0] - target_dte))
        dte, best_exp = valid_exps[0]

        self._log(
            f"SCAN [{strategy.name}] {symbol}: selected {best_exp.expiration_date} "
            f"({dte} DTE) from {len(valid_exps)} valid expiration(s)",
            "INFO",
        )

        # Gather candidate OCC symbols by option type needed
        puts, calls = [], []
        for strike in best_exp.strikes:
            if strategy.strategy_type in (
                StrategyType.SHORT_PUT, StrategyType.SHORT_STRANGLE,
                StrategyType.IRON_CONDOR, StrategyType.BULL_PUT_SPREAD,
                StrategyType.SHORT_STRADDLE,
            ):
                if strike.put:
                    puts.append((float(strike.strike_price), strike.put))
            if strategy.strategy_type in (
                StrategyType.SHORT_CALL, StrategyType.SHORT_STRANGLE,
                StrategyType.IRON_CONDOR, StrategyType.BEAR_CALL_SPREAD,
                StrategyType.SHORT_STRADDLE,
            ):
                if strike.call:
                    calls.append((float(strike.strike_price), strike.call))

        # Get live Greeks for all candidates
        all_occ = [occ for _, occ in puts] + [occ for _, occ in calls]
        self._log(
            f"SCAN [{strategy.name}] {symbol}: fetching Greeks for "
            f"{len(puts)} put(s) and {len(calls)} call(s)",
            "INFO",
        )
        greeks_map = await self._fetch_greeks(all_occ)
        self._log(
            f"SCAN [{strategy.name}] {symbol}: received Greeks for {len(greeks_map)} contract(s)",
            "INFO",
        )

        best_put  = self._best_match(puts,  greeks_map, strategy.put_delta_target,  strategy.delta_tolerance, "put")
        best_call = self._best_match(calls, greeks_map, strategy.call_delta_target, strategy.delta_tolerance, "call")

        if puts and best_put is None:
            self._log(
                f"SKIP [{strategy.name}] {symbol}: no put within δ"
                f"{strategy.put_delta_target:.2f} ± {strategy.delta_tolerance:.2f}",
                "WARNING",
            )
        if calls and best_call is None:
            self._log(
                f"SKIP [{strategy.name}] {symbol}: no call within δ"
                f"{strategy.call_delta_target:.2f} ± {strategy.delta_tolerance:.2f}",
                "WARNING",
            )

        await self._build_and_place(strategy, symbol, best_exp.expiration_date, best_put, best_call, greeks_map)

    def _best_match(self, candidates, greeks_map, delta_target, tolerance, side):
        """Return (strike, occ, delta) closest to delta_target within tolerance."""
        best = None
        best_diff = float("inf")
        for strike, occ in candidates:
            g = greeks_map.get(occ)
            if g is None:
                continue
            raw_delta = g.get("delta")
            if raw_delta is None:
                continue
            delta = abs(float(raw_delta))
            diff = abs(delta - delta_target)
            if diff < best_diff and diff <= tolerance:
                best_diff = diff
                best = (strike, occ, delta)
        return best

    # ---------------------------------------------------------------- #
    # Greeks via DXLink                                                 #
    # ---------------------------------------------------------------- #

    async def _fetch_greeks(self, occ_symbols: List[str]) -> Dict[str, dict]:
        """Fetch live Greeks for a list of OCC symbols.  Returns {occ: {delta, gamma, ...}}."""
        if not occ_symbols:
            return {}
        try:
            from tastytrade.instruments import Option
            from tastytrade.streamer import DXLinkStreamer
            from tastytrade.dxfeed import Greeks

            # Map OCC → streamer symbol
            options = await asyncio.get_event_loop().run_in_executor(
                None, lambda: Option.get_options(self.session, occ_symbols)
            )
            streamer_to_occ: Dict[str, str] = {}
            streamer_syms: List[str] = []
            for opt in options:
                ss = getattr(opt, "streamer_symbol", None)
                if ss:
                    streamer_to_occ[ss] = opt.symbol
                    streamer_syms.append(ss)

            if not streamer_syms:
                return {}

            result: Dict[str, dict] = {}

            async with DXLinkStreamer(self.session) as streamer:
                await streamer.subscribe(Greeks, streamer_syms)
                received: set = set()

                async def _collect():
                    async for g in streamer.listen(Greeks):
                        occ = streamer_to_occ.get(g.event_symbol)
                        if occ:
                            result[occ] = {
                                "delta": g.delta,
                                "gamma": g.gamma,
                                "theta": g.theta,
                                "vega":  g.vega,
                                "iv":    g.volatility,
                            }
                            received.add(occ)
                        if len(received) >= len(streamer_syms):
                            return

                collect_task = asyncio.ensure_future(_collect())
                timeout_task = asyncio.ensure_future(asyncio.sleep(15))
                done, pending = await asyncio.wait(
                    [collect_task, timeout_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()

            return result

        except Exception as exc:
            self._log(f"Greeks fetch error: {exc}", "WARNING")
            return {}

    # ---------------------------------------------------------------- #
    # Order building & placement                                        #
    # ---------------------------------------------------------------- #

    async def _build_and_place(self, strategy, symbol, expiry, best_put, best_call, greeks_map):
        from tastytrade.order import (
            NewOrder, OrderAction, OrderTimeInForce, OrderType, Leg, PriceEffect
        )
        from tastytrade.instruments import InstrumentType

        legs = []
        total_credit = Decimal("0")
        max_risk = 0.0
        desc_parts = []

        st = strategy.strategy_type

        def _leg(occ, action):
            return Leg(
                instrument_type=InstrumentType.EQUITY_OPTION,
                symbol=occ,
                quantity=strategy.max_contracts,
                action=action,
            )

        if st in (StrategyType.SHORT_PUT, StrategyType.BULL_PUT_SPREAD):
            if not best_put:
                return
            strike, occ, delta = best_put
            price = await self._mid_price(occ)
            if price is None:
                self._log(f"SKIP [{strategy.name}] {symbol}: could not price {occ}", "WARNING")
                return
            if price < strategy.min_premium:
                self._log(
                    f"SKIP [{strategy.name}] {symbol}: {occ} mid ${price:.2f} "
                    f"< min premium ${strategy.min_premium:.2f}",
                    "INFO",
                )
                return
            if st == StrategyType.BULL_PUT_SPREAD:
                long_strike = strike - strategy.wing_width
                long_occ    = self._find_occ_for_strike(greeks_map, long_strike, "put")
                if not long_occ:
                    return
                legs += [_leg(occ, OrderAction.SELL_TO_OPEN), _leg(long_occ, OrderAction.BUY_TO_OPEN)]
                max_risk    = strategy.wing_width * 100 * strategy.max_contracts
                total_credit = Decimal(str(round(price * 0.95, 2)))
            else:
                legs.append(_leg(occ, OrderAction.SELL_TO_OPEN))
                max_risk    = strike * 100 * strategy.max_contracts
                total_credit = Decimal(str(round(price * 0.95, 2)))
            desc_parts.append(f"{strike}P δ{delta:.2f}")

        elif st in (StrategyType.SHORT_CALL, StrategyType.BEAR_CALL_SPREAD):
            if not best_call:
                return
            strike, occ, delta = best_call
            price = await self._mid_price(occ)
            if price is None:
                self._log(f"SKIP [{strategy.name}] {symbol}: could not price {occ}", "WARNING")
                return
            if price < strategy.min_premium:
                self._log(
                    f"SKIP [{strategy.name}] {symbol}: {occ} mid ${price:.2f} "
                    f"< min premium ${strategy.min_premium:.2f}",
                    "INFO",
                )
                return
            if st == StrategyType.BEAR_CALL_SPREAD:
                long_strike = strike + strategy.wing_width
                long_occ    = self._find_occ_for_strike(greeks_map, long_strike, "call")
                if not long_occ:
                    return
                legs += [_leg(occ, OrderAction.SELL_TO_OPEN), _leg(long_occ, OrderAction.BUY_TO_OPEN)]
                max_risk    = strategy.wing_width * 100 * strategy.max_contracts
            else:
                legs.append(_leg(occ, OrderAction.SELL_TO_OPEN))
                max_risk    = strike * 100 * strategy.max_contracts
            total_credit = Decimal(str(round(price * 0.95, 2)))
            desc_parts.append(f"{strike}C δ{delta:.2f}")

        elif st in (StrategyType.SHORT_STRANGLE, StrategyType.SHORT_STRADDLE):
            if not best_put or not best_call:
                return
            put_strike,  put_occ,  put_delta  = best_put
            call_strike, call_occ, call_delta = best_call
            put_price  = await self._mid_price(put_occ)
            call_price = await self._mid_price(call_occ)
            if not put_price or not call_price:
                self._log(f"SKIP [{strategy.name}] {symbol}: could not price legs", "WARNING")
                return
            combined = put_price + call_price
            if combined < strategy.min_premium:
                self._log(
                    f"SKIP [{strategy.name}] {symbol}: combined mid ${combined:.2f} "
                    f"< min premium ${strategy.min_premium:.2f}",
                    "INFO",
                )
                return
            legs += [
                _leg(put_occ,  OrderAction.SELL_TO_OPEN),
                _leg(call_occ, OrderAction.SELL_TO_OPEN),
            ]
            total_credit = Decimal(str(round(combined * 0.95, 2)))
            max_risk     = call_strike * 100 * strategy.max_contracts
            desc_parts.append(f"{put_strike}P/{call_strike}C")

        elif st == StrategyType.IRON_CONDOR:
            if not best_put or not best_call:
                return
            put_strike,  put_occ,  _  = best_put
            call_strike, call_occ, _  = best_call
            put_long_occ  = self._find_occ_for_strike(greeks_map, put_strike  - strategy.wing_width, "put")
            call_long_occ = self._find_occ_for_strike(greeks_map, call_strike + strategy.wing_width, "call")
            if not put_long_occ or not call_long_occ:
                return
            put_price  = await self._mid_price(put_occ)
            call_price = await self._mid_price(call_occ)
            if not put_price or not call_price:
                self._log(f"SKIP [{strategy.name}] {symbol}: could not price IC legs", "WARNING")
                return
            combined = put_price + call_price
            if combined < strategy.min_premium:
                self._log(
                    f"SKIP [{strategy.name}] {symbol}: IC combined mid ${combined:.2f} "
                    f"< min premium ${strategy.min_premium:.2f}",
                    "INFO",
                )
                return
            legs += [
                _leg(put_occ,       OrderAction.SELL_TO_OPEN),
                _leg(put_long_occ,  OrderAction.BUY_TO_OPEN),
                _leg(call_occ,      OrderAction.SELL_TO_OPEN),
                _leg(call_long_occ, OrderAction.BUY_TO_OPEN),
            ]
            total_credit = Decimal(str(round(combined * 0.95, 2)))
            max_risk     = strategy.wing_width * 100 * strategy.max_contracts
            desc_parts.append(f"IC {put_strike}P/{call_strike}C")

        if not legs:
            return

        # Risk check
        ok, reason = self.risk.check_entry(strategy, max_risk, self._positions_cache)
        if not ok:
            self._log(f"Risk block [{strategy.name}] {symbol}: {reason}", "WARNING")
            return

        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC,
            order_type=OrderType.LIMIT,
            legs=legs,
            price=total_credit,
            price_effect=PriceEffect.CREDIT,
        )

        desc = f"{symbol} {expiry} {' '.join(desc_parts)} @ ${total_credit}"

        if strategy.dry_run:
            self._log(f"[DRY RUN] Would place: {strategy.name} – {desc}", "INFO")
            self.signals.order_event.emit({
                "type": "dry_run", "strategy": strategy.name,
                "symbol": symbol, "description": desc,
                "price": float(total_credit), "timestamp": datetime.now().isoformat(),
            })
            return

        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.account.place_order(self.session, order, dry_run=False)
            )
            order_id = str(resp.order.id) if resp and resp.order else "?"
            self._log(f"Order placed [{order_id}]: {strategy.name} – {desc}", "INFO")
            self.signals.order_event.emit({
                "type": "entry", "order_id": order_id,
                "strategy": strategy.name, "symbol": symbol,
                "description": desc, "price": float(total_credit),
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as exc:
            self._log(f"Order failed [{strategy.name}] {symbol}: {exc}", "ERROR")

    # ---------------------------------------------------------------- #
    # Exit monitoring                                                   #
    # ---------------------------------------------------------------- #

    async def _monitor_exits(self):
        for pos in self._positions_cache:
            if pos.get("instrument_type") != "Equity Option":
                continue
            qty = float(pos.get("quantity", 0))
            if qty >= 0:
                continue  # only monitor short positions (qty < 0)

            open_price = pos.get("average_open_price", 0)
            if not open_price:
                continue

            occ = pos.get("symbol", "")
            strategy = self._strategy_for_position(pos)
            if not strategy:
                continue

            current = await self._mid_price(occ)
            if current is None:
                continue

            # DTE exit
            dte = self._dte_from_occ(occ)
            if dte is not None and dte <= strategy.dte_exit:
                await self._close_position(pos, occ, abs(int(qty)), "DTE_EXIT", strategy)
                continue

            # Profit target: current price ≤ open_price * (1 − profit_target_pct)
            if current <= open_price * (1.0 - strategy.profit_target_pct):
                await self._close_position(pos, occ, abs(int(qty)), "PROFIT_TARGET", strategy)
                continue

            # Stop loss: current price ≥ open_price * (1 + stop_loss_pct)
            if current >= open_price * (1.0 + strategy.stop_loss_pct):
                await self._close_position(pos, occ, abs(int(qty)), "STOP_LOSS", strategy)

    async def _close_position(self, pos: dict, occ: str, qty: int, reason: str, strategy: StrategyConfig):
        from tastytrade.order import (
            NewOrder, OrderAction, OrderTimeInForce, OrderType, Leg, PriceEffect
        )
        from tastytrade.instruments import InstrumentType

        current = await self._mid_price(occ)
        if current is None:
            return

        close_price = Decimal(str(round(current * 1.05, 2)))  # slight edge above mid
        leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=occ,
            quantity=qty,
            action=OrderAction.BUY_TO_CLOSE,
        )
        order = NewOrder(
            time_in_force=OrderTimeInForce.GTC,
            order_type=OrderType.LIMIT,
            legs=[leg],
            price=close_price,
            price_effect=PriceEffect.DEBIT,
        )

        self._log(f"Closing {occ} qty={qty} reason={reason} @ ${close_price}", "INFO")

        if strategy.dry_run:
            self._log(f"[DRY RUN] Would close {occ}", "INFO")
            return

        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.account.place_order(self.session, order, dry_run=False)
            )
            order_id = str(resp.order.id) if resp and resp.order else "?"
            self._log(f"Close order placed [{order_id}] {occ} – {reason}", "INFO")
            self.signals.order_event.emit({
                "type": "exit", "order_id": order_id,
                "symbol": occ, "reason": reason,
                "price": float(close_price), "timestamp": datetime.now().isoformat(),
            })
        except Exception as exc:
            self._log(f"Close order failed {occ}: {exc}", "ERROR")

    # ---------------------------------------------------------------- #
    # Helpers                                                           #
    # ---------------------------------------------------------------- #

    async def _mid_price(self, occ: str) -> Optional[float]:
        try:
            from tastytrade.instruments import Option
            from tastytrade.streamer import DXLinkStreamer
            from tastytrade.dxfeed import Quote

            opt = await asyncio.get_event_loop().run_in_executor(
                None, lambda: Option.get_option(self.session, occ)
            )
            if not opt:
                return None
            ss = getattr(opt, "streamer_symbol", None)
            if not ss:
                return None

            async with DXLinkStreamer(self.session) as streamer:
                await streamer.subscribe(Quote, [ss])
                async for q in streamer.listen(Quote):
                    bid = float(q.bid_price or 0)
                    ask = float(q.ask_price or 0)
                    if bid > 0 and ask > 0:
                        return (bid + ask) / 2
                    break
        except Exception as exc:
            logger.debug("mid_price error for %s: %s", occ, exc)
        return None

    def _find_occ_for_strike(self, greeks_map: dict, target_strike: float, side: str) -> Optional[str]:
        """Find the OCC symbol in greeks_map closest to target_strike."""
        # We don't have the full chain here; this is a simplification.
        # In production you'd pass the chain strikes alongside the greeks_map.
        return None  # implemented via chain lookup in extended version

    def _positions_for(self, strategy: StrategyConfig, symbol: str) -> List[dict]:
        return [
            p for p in self._positions_cache
            if p.get("underlying_symbol") == symbol
            and p.get("instrument_type") == "Equity Option"
            and p.get("quantity", 0) < 0
        ]

    def _strategy_for_position(self, pos: dict) -> Optional[StrategyConfig]:
        sym = pos.get("underlying_symbol", "")
        for s in self.strategies:
            if sym in s.underlyings and s.enabled:
                return s
        return None

    @staticmethod
    def _dte_from_occ(occ: str) -> Optional[int]:
        """Parse DTE from a standard OCC symbol (e.g. 'SPY   250117P00570000')."""
        try:
            stripped = occ.strip()
            # OCC format: 6-char symbol, 6-char date YYMMDD, 1-char type, 8-char strike
            date_str = stripped[6:12]
            exp = datetime.strptime(date_str, "%y%m%d").date()
            return (exp - date.today()).days
        except Exception:
            return None

    def _log(self, msg: str, level: str = "INFO"):
        self.signals.log_message.emit(msg, level)
        getattr(logger, level.lower(), logger.info)(msg)
