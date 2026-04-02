"""
Options Portfolio Analytics Engine
Computes beta-weighted delta, theta balance, IV summary, and correlation risk.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, date
from functools import lru_cache


BENCHMARK = "SPY"
BETA_LOOKBACK = "1y"
CORR_LOOKBACK = "6mo"

# Tickers that yfinance doesn't carry directly.
# Maps ticker -> (yfinance_symbol, price_multiplier)
# e.g. XSP = 1/10 of SPX (^GSPC), beta vs SPY treated as 1.0
TICKER_ALIASES: dict[str, tuple[str, float]] = {
    "XSP":  ("^GSPC", 0.1),
    "SPX":  ("^GSPC", 1.0),
    "SPXW": ("^GSPC", 1.0),
    "NDX":  ("^NDX",  1.0),
    "RUT":  ("^RUT",  1.0),
    "VIX":  ("^VIX",  1.0),
}


# ---------------------------------------------------------------------------
# Market data helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def get_stock_price(ticker: str) -> float:
    """Fetch latest close price for a ticker, handling index aliases."""
    yt, mult = TICKER_ALIASES.get(ticker.upper(), (ticker, 1.0))
    try:
        t = yf.Ticker(yt)
        hist = t.history(period="5d")
        if hist.empty:
            return 0.0
        return float(hist["Close"].iloc[-1]) * mult
    except Exception:
        return 0.0


@lru_cache(maxsize=64)
def get_beta(ticker: str) -> float:
    """Compute beta vs SPY using 1-year daily returns."""
    upper = ticker.upper()
    # Index-based underlyings are by definition ~1.0 beta vs SPY
    if upper in TICKER_ALIASES or upper == BENCHMARK:
        return 1.0
    try:
        data = yf.download(
            [ticker, BENCHMARK],
            period=BETA_LOOKBACK,
            auto_adjust=True,
            progress=False,
        )["Close"].dropna()
        if data.empty or len(data) < 20:
            return 1.0
        returns = data.pct_change().dropna()
        cov = returns.cov()
        beta = cov.loc[ticker, BENCHMARK] / returns[BENCHMARK].var()
        return float(beta)
    except Exception:
        return 1.0


def get_correlation_matrix(tickers: list[str]) -> pd.DataFrame:
    """Return a correlation matrix of daily returns for the given tickers."""
    if len(tickers) < 2:
        return pd.DataFrame()
    unique = list(dict.fromkeys(t.upper() for t in tickers))
    try:
        data = yf.download(
            unique,
            period=CORR_LOOKBACK,
            auto_adjust=True,
            progress=False,
        )["Close"].dropna()
        if isinstance(data, pd.Series):
            data = data.to_frame()
        return data.pct_change().dropna().corr()
    except Exception:
        return pd.DataFrame()


def refresh_cache():
    """Clear cached market data so fresh prices are fetched."""
    get_stock_price.cache_clear()
    get_beta.cache_clear()


# ---------------------------------------------------------------------------
# Portfolio analytics
# ---------------------------------------------------------------------------

def days_to_expiry(expiry: date) -> int:
    return max(0, (expiry - date.today()).days)


def build_positions_df(positions: list[dict]) -> pd.DataFrame:
    """
    Enrich raw position dicts with market data and derived fields.

    Each position dict must have:
        symbol        str       underlying ticker
        option_type   str       'call' or 'put'
        strike        float
        expiry        date
        contracts     int       number of contracts (positive=long, negative=short)
        delta         float     per-share delta (call: 0 to 1, put: -1 to 0)
        gamma         float     per-share gamma
        theta         float     per-share theta (usually negative)
        vega          float     per-share vega
        iv            float     implied volatility as a decimal (e.g. 0.35 = 35%)
        stock_price   float|None  override; None = fetch from market
        beta          float|None  override; None = fetch from market
    """
    rows = []
    spy_price = get_stock_price(BENCHMARK)

    for p in positions:
        sym = p["symbol"].upper()
        stock_px = p.get("stock_price") or get_stock_price(sym)
        beta = p.get("beta") or get_beta(sym)
        contracts = int(p["contracts"])
        delta = float(p["delta"])
        theta = float(p["theta"])
        gamma = float(p["gamma"])
        vega = float(p["vega"])
        iv = float(p["iv"])
        dte = days_to_expiry(p["expiry"])

        # Dollar greeks (per position, 100 shares per contract)
        multiplier = contracts * 100
        pos_delta = delta * multiplier               # shares of underlying equiv
        pos_dollar_delta = pos_delta * stock_px       # $ delta
        pos_theta = theta * multiplier               # $/day
        pos_gamma = gamma * multiplier               # delta change per $1 move
        pos_vega = vega * multiplier                 # $ per 1% IV move

        # Beta-weighted delta: equivalent SPY shares
        bw_delta = (pos_dollar_delta * beta) / spy_price if spy_price else 0.0

        rows.append(
            {
                "Symbol": sym,
                "Type": p["option_type"].capitalize(),
                "Strike": p["strike"],
                "Expiry": p["expiry"],
                "DTE": dte,
                "Contracts": contracts,
                "Stock $": round(stock_px, 2),
                "Beta": round(beta, 2),
                "IV (%)": round(iv * 100, 1),
                "Delta": round(delta, 3),
                "Gamma": round(gamma, 4),
                "Theta": round(theta, 2),
                "Vega": round(vega, 2),
                "Pos Delta": round(pos_delta, 2),
                "$ Delta": round(pos_dollar_delta, 2),
                "BW Delta": round(bw_delta, 2),
                "Pos Theta": round(pos_theta, 2),
                "Pos Gamma": round(pos_gamma, 4),
                "Pos Vega": round(pos_vega, 2),
            }
        )

    return pd.DataFrame(rows)


def portfolio_summary(df: pd.DataFrame) -> dict:
    """Compute aggregate portfolio-level metrics."""
    if df.empty:
        return {}

    spy_price = get_stock_price(BENCHMARK)
    net_bw_delta = df["BW Delta"].sum()
    net_theta = df["Pos Theta"].sum()
    net_vega = df["Pos Vega"].sum()
    net_gamma = df["Pos Gamma"].sum()

    # Vega-weighted average IV
    total_abs_vega = df["Pos Vega"].abs().sum()
    if total_abs_vega > 0:
        portfolio_iv = (df["IV (%)"] * df["Pos Vega"].abs()).sum() / total_abs_vega
    else:
        portfolio_iv = df["IV (%)"].mean()

    # Theta/delta ratio (income per unit of market exposure)
    theta_delta_ratio = (
        (net_theta / abs(net_bw_delta)) if abs(net_bw_delta) > 0.01 else None
    )

    # Notional exposure per symbol
    exposure_by_sym = (
        df.groupby("Symbol")["$ Delta"].sum().sort_values(key=abs, ascending=False)
    )

    return {
        "net_bw_delta": round(net_bw_delta, 2),
        "net_theta": round(net_theta, 2),
        "net_vega": round(net_vega, 2),
        "net_gamma": round(net_gamma, 4),
        "portfolio_iv": round(portfolio_iv, 1),
        "theta_delta_ratio": round(theta_delta_ratio, 4) if theta_delta_ratio else None,
        "spy_price": round(spy_price, 2),
        "exposure_by_symbol": exposure_by_sym,
        "num_positions": len(df),
    }


def scenario_pnl(df: pd.DataFrame, spy_move_pct: float) -> pd.Series:
    """
    Estimate P&L for each position given a % move in SPY.
    Uses delta + gamma approximation for the underlying's move.
    """
    spy_price = get_stock_price(BENCHMARK)
    spy_move = spy_price * spy_move_pct / 100.0

    results = []
    for _, row in df.iterrows():
        # Approximate underlying move = (beta * spy_move_pct%) * stock price
        stock_move = row["Beta"] * row["Stock $"] * spy_move_pct / 100.0
        # dP ≈ delta*dS + 0.5*gamma*dS^2  (per share), scaled to position
        contracts = row["Contracts"]
        dP = (row["Delta"] * stock_move + 0.5 * row["Gamma"] * stock_move**2) * contracts * 100
        results.append({"Symbol": row["Symbol"], "Strike": row["Strike"],
                        "Type": row["Type"], "Est P&L": round(dP, 2)})

    return pd.DataFrame(results)
