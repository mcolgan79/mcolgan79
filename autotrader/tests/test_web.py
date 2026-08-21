"""The dashboard's HTTP surface: auth, the guards, and the trading actions."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from autotrader.config import Config
from autotrader.storage import Store
from autotrader.strategies.pair_zscore import PairZScore
from autotrader.web.server import create_app
from autotrader.web.service import MIN_LOOP_INTERVAL, TradingService
from conftest import position, spreads_for_z

LOOKBACK = 20
TOKEN = "test-token-value"


@pytest.fixture
def service(tmp_path, fake_broker_factory):
    def build(z: float = 2.4, **kwargs):
        broker = fake_broker_factory(spreads_for_z(z, LOOKBACK), **kwargs)
        config = Config()
        config.storage.path = tmp_path / "web.db"
        strategy = PairZScore(lookback=LOOKBACK, leg_weight=0.10)
        store = Store(tmp_path / "web.db", multithreaded=True)
        svc = TradingService(config, broker, strategy, store)
        return svc, broker

    built: list[TradingService] = []

    def factory(*args, **kwargs):
        svc, broker = build(*args, **kwargs)
        built.append(svc)
        return svc, broker

    yield factory
    for svc in built:
        svc.stop_loop()
        svc.store.close()


@pytest.fixture
def client(service):
    def make(*args, **kwargs):
        svc, broker = service(*args, **kwargs)
        # The Host guard only accepts loopback, so the test client must look
        # like a real browser on 127.0.0.1 rather than starlette's "testserver".
        return (
            TestClient(create_app(svc, TOKEN), base_url="http://127.0.0.1:8787"),
            svc,
            broker,
        )

    return make


def auth(**extra):
    return {"X-Auth-Token": TOKEN, **extra}


# -- access control -----------------------------------------------------


def test_the_page_loads_without_a_token_but_the_api_does_not(client):
    c, _, _ = client()
    assert c.get("/").status_code == 200
    assert c.get("/api/state").status_code == 401


def test_a_wrong_token_is_rejected(client):
    c, _, _ = client()
    assert c.get("/api/state", headers={"X-Auth-Token": "nope"}).status_code == 401


def test_the_right_token_works(client):
    c, _, _ = client()
    assert c.get("/api/state", headers=auth()).status_code == 200


def test_a_foreign_host_header_is_refused(client):
    """The DNS-rebinding guard: an attacker domain pointing at 127.0.0.1 still
    arrives carrying its own Host."""
    c, _, _ = client()
    res = c.get("/api/state", headers=auth(Host="evil.example.com"))
    assert res.status_code == 403
    assert c.get("/", headers={"Host": "evil.example.com"}).status_code == 403


def test_trading_endpoints_are_behind_the_token_too(client):
    c, _, broker = client()
    assert c.post("/api/run", json={"dry_run": False}).status_code == 401
    assert c.post("/api/flatten", json={}).status_code == 401
    assert c.post("/api/loop", json={"action": "start"}).status_code == 401
    assert broker.submitted == []


# -- state --------------------------------------------------------------


def test_state_carries_everything_the_dashboard_renders(client):
    c, _, _ = client(z=2.4)
    body = c.get("/api/state", headers=auth()).json()
    assert body["broker"]["paper"] is True
    assert body["strategy"]["symbols"] == ["GLD", "GDX"]
    assert body["strategy"]["params"]["entry_z"] == 2.0
    assert body["signal"]["action"] == "enter"
    assert body["signal"]["metrics"]["z"] == pytest.approx(2.4, abs=1e-6)
    assert body["market"]["is_open"] is True
    assert body["loop"]["running"] is False
    assert "activity" in body


def test_viewing_state_never_places_an_order(client):
    """Opening the dashboard must be side-effect free."""
    c, _, broker = client(z=2.4)
    for _ in range(3):
        c.get("/api/state", headers=auth())
    assert broker.submitted == []


def test_state_survives_a_broker_that_is_down(client, fake_broker_factory):
    from autotrader.brokers.base import BrokerError

    c, svc, broker = client(z=2.4)

    def boom():
        raise BrokerError("alpaca unreachable")

    broker.get_account = boom
    body = c.get("/api/state", headers=auth()).json()
    assert body["account"] is None
    assert any("unreachable" in e for e in body["errors"])


def test_positions_are_tagged_as_strategy_legs(client):
    held = {"GLD": position("GLD", -33, 300.0), "AAPL": position("AAPL", 10, 150.0)}
    c, _, _ = client(z=1.0, positions=held)
    rows = {p["symbol"]: p for p in c.get("/api/state", headers=auth()).json()["positions"]}
    assert rows["GLD"]["is_strategy_leg"] is True
    assert rows["AAPL"]["is_strategy_leg"] is False


# -- actions ------------------------------------------------------------


def test_dry_run_plans_without_submitting(client):
    c, _, broker = client(z=2.4)
    body = c.post("/api/run", json={"dry_run": True}, headers=auth()).json()
    assert body["executed"] is False
    assert len(body["orders"]) == 2
    assert broker.submitted == []


def test_executing_submits_both_legs(client):
    c, _, broker = client(z=2.4)
    body = c.post("/api/run", json={"dry_run": False}, headers=auth()).json()
    assert body["executed"] is True
    assert {o.symbol for o in broker.submitted} == {"GLD", "GDX"}


def test_a_rejected_order_is_reported_not_swallowed(client):
    c, _, _ = client(z=2.4, fail_symbols={"GLD"})
    body = c.post("/api/run", json={"dry_run": False}, headers=auth()).json()
    assert body["had_errors"] is True
    assert "simulated rejection" in body["error"]


def test_closed_market_blocks_the_run(client):
    c, _, broker = client(z=2.4, market_open=False)
    body = c.post("/api/run", json={"dry_run": False}, headers=auth()).json()
    assert "market is closed" in body["skipped_reason"]
    assert broker.submitted == []


def test_ignore_market_hours_lets_a_preview_through(client):
    c, _, broker = client(z=2.4, market_open=False)
    body = c.post(
        "/api/run",
        json={"dry_run": True, "ignore_market_hours": True},
        headers=auth(),
    ).json()
    assert len(body["orders"]) == 2
    assert broker.submitted == []


def test_flatten_closes_the_legs(client):
    held = {"GLD": position("GLD", -33, 300.0), "GDX": position("GDX", 166, 60.0)}
    c, _, broker = client(z=2.4, positions=held)
    body = c.post("/api/flatten", json={"dry_run": False}, headers=auth()).json()
    assert body["executed"] is True
    assert {o.symbol for o in broker.submitted} == {"GLD", "GDX"}


# -- the loop -----------------------------------------------------------


def test_loop_starts_and_stops(client):
    c, svc, _ = client(z=1.0)
    started = c.post(
        "/api/loop", json={"action": "start", "interval": 3600, "dry_run": True}, headers=auth()
    ).json()
    assert started["running"] is True and started["dry_run"] is True
    assert c.get("/api/state", headers=auth()).json()["loop"]["running"] is True

    stopped = c.post("/api/loop", json={"action": "stop"}, headers=auth()).json()
    assert stopped["running"] is False
    assert svc._thread is None


def test_the_loop_interval_has_a_floor(client):
    """A UI spinner must not be able to hammer the broker's API."""
    c, _, _ = client(z=1.0)
    body = c.post(
        "/api/loop", json={"action": "start", "interval": 1}, headers=auth()
    ).json()
    assert body["interval"] == MIN_LOOP_INTERVAL
    c.post("/api/loop", json={"action": "stop"}, headers=auth())


def test_starting_a_running_loop_twice_is_a_no_op(client):
    c, svc, _ = client(z=1.0)
    c.post("/api/loop", json={"action": "start", "interval": 3600}, headers=auth())
    first = svc._thread
    c.post("/api/loop", json={"action": "start", "interval": 60}, headers=auth())
    assert svc._thread is first
    assert svc.loop.interval == 3600  # the second call did not change it
    c.post("/api/loop", json={"action": "stop"}, headers=auth())


def test_the_loop_actually_trades_on_its_first_pass(client):
    c, svc, broker = client(z=2.4)
    c.post(
        "/api/loop", json={"action": "start", "interval": 3600, "dry_run": False}, headers=auth()
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not broker.submitted:
        time.sleep(0.05)
    c.post("/api/loop", json={"action": "stop"}, headers=auth())
    assert {o.symbol for o in broker.submitted} == {"GLD", "GDX"}
    assert svc.loop.runs >= 1


def test_a_dry_run_loop_places_nothing(client):
    c, svc, broker = client(z=2.4)
    c.post(
        "/api/loop", json={"action": "start", "interval": 3600, "dry_run": True}, headers=auth()
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and svc.loop.runs < 1:
        time.sleep(0.05)
    c.post("/api/loop", json={"action": "stop"}, headers=auth())
    assert broker.submitted == []
    assert svc.loop.runs >= 1


def test_an_unknown_loop_action_is_rejected(client):
    c, _, _ = client()
    assert c.post("/api/loop", json={"action": "wiggle"}, headers=auth()).status_code == 400


# -- the page itself ----------------------------------------------------


def test_the_page_is_self_contained():
    """A trading dashboard must not fetch anything off the machine."""
    from autotrader.web.server import STATIC_DIR

    html = (STATIC_DIR / "index.html").read_text()
    for marker in ("http://", "https://", "cdn.", "<script src="):
        assert marker not in html, f"page reaches outside for {marker!r}"


def test_action_lock_does_not_disable_the_confirm_dialog():
    """Regression: locking every button on the page during an action also
    disabled the dialog's own Cancel/Confirm, deadlocking every confirmed
    action (trade, flatten, start loop)."""
    from autotrader.web.server import STATIC_DIR

    html = (STATIC_DIR / "index.html").read_text()
    assert 'querySelectorAll("button")' not in html
    assert 'querySelectorAll(".controls button")' in html
