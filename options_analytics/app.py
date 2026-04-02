"""
Options Portfolio Analytics Dashboard
Run with: streamlit run app.py
"""

import json
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analytics

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Options Portfolio Analytics",
    page_icon="📊",
    layout="wide",
)

SAVE_FILE = Path(__file__).parent / "positions.json"

# ---------------------------------------------------------------------------
# Helpers: persist positions to disk
# ---------------------------------------------------------------------------

def load_positions() -> list[dict]:
    if SAVE_FILE.exists():
        raw = json.loads(SAVE_FILE.read_text())
        for p in raw:
            p["expiry"] = date.fromisoformat(p["expiry"])
        return raw
    return []


def save_positions(positions: list[dict]):
    serializable = []
    for p in positions:
        entry = dict(p)
        entry["expiry"] = entry["expiry"].isoformat()
        serializable.append(entry)
    SAVE_FILE.write_text(json.dumps(serializable, indent=2))


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "positions" not in st.session_state:
    st.session_state.positions = load_positions()

if "edit_idx" not in st.session_state:
    st.session_state.edit_idx = None


# ---------------------------------------------------------------------------
# Sidebar – Add / Edit position
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📋 Position Entry")

    editing = st.session_state.edit_idx is not None
    prefill = (
        st.session_state.positions[st.session_state.edit_idx] if editing else {}
    )

    st.caption("All greeks are **per share** (as shown in Robinhood)")

    with st.form("position_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        symbol = col1.text_input(
            "Ticker", value=prefill.get("symbol", ""), placeholder="e.g. AAPL"
        ).upper()
        option_type = col2.selectbox(
            "Type", ["Call", "Put"],
            index=0 if prefill.get("option_type", "call").lower() == "call" else 1,
        )

        col3, col4 = st.columns(2)
        strike = col3.number_input(
            "Strike ($)", min_value=0.0, value=float(prefill.get("strike", 0.0)),
            step=0.5, format="%.2f",
        )
        default_expiry = prefill.get("expiry", date.today() + timedelta(days=30))
        expiry = col4.date_input("Expiry", value=default_expiry)

        contracts = st.number_input(
            "Contracts  (negative = short)",
            value=int(prefill.get("contracts", 1)),
            step=1,
        )

        st.markdown("**Greeks (per share, from Robinhood)**")
        gc1, gc2 = st.columns(2)
        delta = gc1.number_input(
            "Delta", value=float(prefill.get("delta", 0.0)),
            min_value=-1.0, max_value=1.0, step=0.001, format="%.3f",
        )
        gamma = gc2.number_input(
            "Gamma", value=float(prefill.get("gamma", 0.0)),
            min_value=0.0, step=0.0001, format="%.4f",
        )
        gc3, gc4 = st.columns(2)
        theta = gc3.number_input(
            "Theta (neg = decay)", value=float(prefill.get("theta", 0.0)),
            step=0.01, format="%.2f",
        )
        vega = gc4.number_input(
            "Vega", value=float(prefill.get("vega", 0.0)),
            min_value=0.0, step=0.01, format="%.2f",
        )

        iv_pct = st.number_input(
            "IV (%)", value=float(prefill.get("iv", 0.30)) * 100,
            min_value=0.0, max_value=500.0, step=0.1, format="%.1f",
        )

        st.markdown("**Optional overrides** (leave 0 to auto-fetch)")
        ov1, ov2 = st.columns(2)
        stock_price_override = ov1.number_input(
            "Stock Price ($)", value=float(prefill.get("stock_price") or 0.0),
            min_value=0.0, step=0.01, format="%.2f",
        )
        beta_override = ov2.number_input(
            "Beta", value=float(prefill.get("beta") or 0.0),
            min_value=0.0, step=0.01, format="%.2f",
        )

        btn_label = "💾 Update Position" if editing else "➕ Add Position"
        submitted = st.form_submit_button(btn_label, use_container_width=True)

    if submitted:
        if not symbol:
            st.sidebar.error("Ticker is required.")
        elif strike <= 0:
            st.sidebar.error("Strike must be > 0.")
        else:
            pos = {
                "symbol": symbol,
                "option_type": option_type.lower(),
                "strike": strike,
                "expiry": expiry,
                "contracts": contracts,
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega,
                "iv": iv_pct / 100.0,
                "stock_price": stock_price_override if stock_price_override > 0 else None,
                "beta": beta_override if beta_override > 0 else None,
            }
            if editing:
                st.session_state.positions[st.session_state.edit_idx] = pos
                st.session_state.edit_idx = None
                st.sidebar.success("Position updated.")
            else:
                st.session_state.positions.append(pos)
                st.sidebar.success(f"{symbol} position added.")
            save_positions(st.session_state.positions)
            analytics.refresh_cache()
            st.rerun()

    if editing:
        if st.sidebar.button("✖ Cancel edit", use_container_width=True):
            st.session_state.edit_idx = None
            st.rerun()

    st.divider()

    # CSV import/export
    st.markdown("**Import / Export**")
    uploaded = st.file_uploader("Upload CSV", type="csv", label_visibility="collapsed")
    if uploaded:
        try:
            df_up = pd.read_csv(uploaded)
            df_up["expiry"] = pd.to_datetime(df_up["expiry"]).dt.date
            df_up["stock_price"] = df_up.get("stock_price", pd.Series([None] * len(df_up)))
            df_up["beta"] = df_up.get("beta", pd.Series([None] * len(df_up)))
            imported = df_up.to_dict("records")
            st.session_state.positions.extend(imported)
            save_positions(st.session_state.positions)
            st.sidebar.success(f"Imported {len(imported)} positions.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Import failed: {e}")

    if st.session_state.positions:
        export_rows = []
        for p in st.session_state.positions:
            row = dict(p)
            row["expiry"] = row["expiry"].isoformat()
            row["iv"] = row["iv"] * 100
            export_rows.append(row)
        csv_str = pd.DataFrame(export_rows).to_csv(index=False)
        st.download_button(
            "⬇ Export CSV",
            data=csv_str,
            file_name="options_positions.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    if st.button("🔄 Refresh Market Data", use_container_width=True):
        analytics.refresh_cache()
        st.rerun()

    if st.button("🗑 Clear All Positions", use_container_width=True, type="secondary"):
        st.session_state.positions = []
        save_positions([])
        st.rerun()


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("📊 Options Portfolio Analytics")

positions = st.session_state.positions

if not positions:
    st.info(
        "No positions yet. Use the sidebar to add your first option position.\n\n"
        "**Tip:** Enter greeks exactly as shown in Robinhood (per share). "
        "Stock price and beta will be fetched automatically from Yahoo Finance."
    )
    st.stop()

# Build enriched dataframe
with st.spinner("Fetching market data…"):
    df = analytics.build_positions_df(positions)
    summary = analytics.portfolio_summary(df)

spy_px = summary["spy_price"]

# ---------------------------------------------------------------------------
# Top-level KPI cards
# ---------------------------------------------------------------------------
st.subheader("Portfolio Summary")

k1, k2, k3, k4, k5 = st.columns(5)

bw_delta = summary["net_bw_delta"]
bw_color = "normal" if abs(bw_delta) < 5 else ("inverse" if bw_delta < 0 else "off")
k1.metric(
    "Beta-Weighted Δ (vs SPY)",
    f"{bw_delta:+.2f}",
    help=(
        "Net delta normalized to SPY shares. "
        "+1 ≈ equivalent to owning 1 share of SPY. "
        "Closer to 0 = more market-neutral."
    ),
)

theta_val = summary["net_theta"]
k2.metric(
    "Daily Theta ($/day)",
    f"${theta_val:+.2f}",
    help="Total daily time-decay P&L across all positions. Negative = you are net long premium.",
)

k3.metric(
    "Net Vega ($ per 1% IV)",
    f"${summary['net_vega']:+.2f}",
    help="How much your portfolio gains/loses per 1% rise in implied volatility.",
)

k4.metric(
    "Portfolio IV",
    f"{summary['portfolio_iv']:.1f}%",
    help="Vega-weighted average implied volatility across all positions.",
)

tdr = summary["theta_delta_ratio"]
k5.metric(
    "Theta / BW-Delta",
    f"${tdr:.4f}" if tdr else "—",
    help="Daily income per unit of beta-weighted delta exposure. Higher = more income-efficient.",
)

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_pos, tab_greeks, tab_corr, tab_scenario, tab_help = st.tabs(
    ["📋 Positions", "📐 Greeks Breakdown", "🔗 Correlation Risk", "📈 Scenario P&L", "❓ Help"]
)

# ── Positions tab ─────────────────────────────────────────────────────────
with tab_pos:
    st.subheader("Current Positions")

    display_cols = [
        "Symbol", "Type", "Strike", "Expiry", "DTE", "Contracts",
        "Stock $", "Beta", "IV (%)",
        "Delta", "Gamma", "Theta", "Vega",
    ]
    st.dataframe(
        df[display_cols].style
            .format({
                "Strike": "${:.2f}", "Stock $": "${:.2f}",
                "IV (%)": "{:.1f}%", "Delta": "{:.3f}",
                "Gamma": "{:.4f}", "Theta": "{:.2f}", "Vega": "{:.2f}",
                "Beta": "{:.2f}",
            })
            .map(
                lambda v: "color: red" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Delta", "Theta"],
            ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Edit / Remove Positions")
    for i, p in enumerate(positions):
        col_a, col_b, col_c = st.columns([5, 1, 1])
        label = (
            f"{p['symbol']} "
            f"{'C' if p['option_type']=='call' else 'P'}"
            f"{p['strike']:.0f} "
            f"{p['expiry']} "
            f"× {p['contracts']}"
        )
        col_a.write(label)
        if col_b.button("✏️", key=f"edit_{i}"):
            st.session_state.edit_idx = i
            st.rerun()
        if col_c.button("🗑", key=f"del_{i}"):
            st.session_state.positions.pop(i)
            save_positions(st.session_state.positions)
            st.rerun()


# ── Greeks Breakdown tab ───────────────────────────────────────────────────
with tab_greeks:
    st.subheader("Position-Level Greeks (Dollar Values)")

    greek_cols = [
        "Symbol", "Type", "Strike", "Expiry", "Contracts",
        "Pos Delta", "BW Delta", "Pos Theta", "Pos Gamma", "Pos Vega",
    ]
    st.dataframe(
        df[greek_cols].style.format({
            "Pos Delta": "{:+.2f}", "BW Delta": "{:+.2f}",
            "Pos Theta": "${:+.2f}", "Pos Gamma": "{:+.4f}",
            "Pos Vega": "${:+.2f}",
        }).map(
            lambda v: "color: green" if isinstance(v, (int, float)) and v > 0
            else ("color: red" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["BW Delta", "Pos Theta", "Pos Vega"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    # Totals row
    totals = {
        "BW Delta": df["BW Delta"].sum(),
        "Pos Theta": df["Pos Theta"].sum(),
        "Pos Gamma": df["Pos Gamma"].sum(),
        "Pos Vega": df["Pos Vega"].sum(),
    }
    tc = st.columns(4)
    tc[0].metric("Net BW Delta", f"{totals['BW Delta']:+.2f}")
    tc[1].metric("Net Theta", f"${totals['Pos Theta']:+.2f}/day")
    tc[2].metric("Net Gamma", f"{totals['Pos Gamma']:+.4f}")
    tc[3].metric("Net Vega", f"${totals['Pos Vega']:+.2f}")

    st.divider()
    st.subheader("Dollar Delta by Underlying")
    exp_by_sym = summary["exposure_by_symbol"].reset_index()
    exp_by_sym.columns = ["Symbol", "$ Delta"]
    fig_exp = px.bar(
        exp_by_sym,
        x="Symbol",
        y="$ Delta",
        color="$ Delta",
        color_continuous_scale=["red", "lightgray", "green"],
        color_continuous_midpoint=0,
        title="Net Dollar Delta per Underlying",
    )
    fig_exp.update_layout(showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig_exp, use_container_width=True)

    st.subheader("Theta by Position")
    fig_theta = px.bar(
        df,
        x=df["Symbol"] + " " + df["Type"] + " " + df["Strike"].astype(str),
        y="Pos Theta",
        color="Pos Theta",
        color_continuous_scale=["red", "lightgray", "green"],
        color_continuous_midpoint=0,
        labels={"x": "Position", "Pos Theta": "Daily Theta ($)"},
        title="Daily Theta per Position (positive = you collect)",
    )
    fig_theta.update_layout(xaxis_title="Position", coloraxis_showscale=False)
    st.plotly_chart(fig_theta, use_container_width=True)


# ── Correlation Risk tab ────────────────────────────────────────────────────
with tab_corr:
    st.subheader("Underlying Correlation Risk")
    st.caption(
        "Correlation of daily returns over the past 6 months. "
        "High positive correlation = positions move together (concentrated risk). "
        "Negative correlation = natural hedge."
    )

    tickers = df["Symbol"].unique().tolist()
    if len(tickers) < 2:
        st.info("Add at least 2 different underlyings to see correlation.")
    else:
        with st.spinner("Computing correlations…"):
            corr = analytics.get_correlation_matrix(tickers)

        if corr.empty:
            st.warning("Could not fetch historical data for correlation.")
        else:
            fig_corr = go.Figure(
                data=go.Heatmap(
                    z=corr.values,
                    x=corr.columns.tolist(),
                    y=corr.index.tolist(),
                    colorscale="RdBu",
                    zmid=0,
                    zmin=-1,
                    zmax=1,
                    text=np.round(corr.values, 2),
                    texttemplate="%{text}",
                    hoverongaps=False,
                )
            )
            fig_corr.update_layout(
                title="Return Correlation Matrix (6-month daily)",
                xaxis_nticks=len(corr),
                yaxis_nticks=len(corr),
            )
            st.plotly_chart(fig_corr, use_container_width=True)

            # Risk flags
            st.subheader("Risk Flags")
            high_corr_pairs = []
            cols = corr.columns.tolist()
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    c = corr.iloc[i, j]
                    if abs(c) >= 0.75:
                        high_corr_pairs.append(
                            (cols[i], cols[j], round(c, 2))
                        )

            if not high_corr_pairs:
                st.success("No high-correlation pairs found (|ρ| < 0.75). Good diversification.")
            else:
                for a, b, c in high_corr_pairs:
                    direction = "positively" if c > 0 else "negatively"
                    st.warning(
                        f"**{a} & {b}** are highly {direction} correlated (ρ = {c:.2f}). "
                        "These positions may not provide the diversification you expect."
                    )


# ── Scenario P&L tab ───────────────────────────────────────────────────────
with tab_scenario:
    st.subheader("Scenario P&L Estimator")
    st.caption(
        "Estimates position P&L using **delta + gamma approximation** for a given SPY move. "
        "Does **not** account for IV changes or time decay — use as a directional guide only."
    )

    move_pct = st.slider(
        "SPY Move (%)",
        min_value=-15.0,
        max_value=15.0,
        value=0.0,
        step=0.5,
        format="%.1f%%",
    )

    spy_dollar_move = spy_px * move_pct / 100.0
    st.markdown(
        f"SPY at **${spy_px:.2f}** → move of **${spy_dollar_move:+.2f}** "
        f"({move_pct:+.1f}%)"
    )

    scen_df = analytics.scenario_pnl(df, move_pct)
    total_pnl = scen_df["Est P&L"].sum()

    st.dataframe(
        scen_df.style.format({"Est P&L": "${:+.2f}"}).map(
            lambda v: "color: green" if isinstance(v, (int, float)) and v > 0
            else ("color: red" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["Est P&L"],
        ),
        use_container_width=True,
        hide_index=True,
    )
    color = "green" if total_pnl >= 0 else "red"
    st.markdown(
        f"**Estimated Portfolio P&L: "
        f"<span style='color:{color}'>${total_pnl:+,.2f}</span>**",
        unsafe_allow_html=True,
    )

    # Sweep chart
    st.subheader("P&L Sweep (−15% to +15% SPY)")
    sweep_moves = np.linspace(-15, 15, 61)
    sweep_pnl = [analytics.scenario_pnl(df, m)["Est P&L"].sum() for m in sweep_moves]
    fig_sweep = px.line(
        x=sweep_moves,
        y=sweep_pnl,
        labels={"x": "SPY Move (%)", "y": "Est Portfolio P&L ($)"},
        title="Portfolio P&L vs SPY Move",
    )
    fig_sweep.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_sweep.add_vline(x=move_pct, line_dash="dot", line_color="blue",
                        annotation_text=f"{move_pct:+.1f}%")
    st.plotly_chart(fig_sweep, use_container_width=True)


# ── Help tab ────────────────────────────────────────────────────────────────
with tab_help:
    st.subheader("How to use this dashboard")

    st.markdown("""
### Finding greeks in Robinhood

1. Open the **Robinhood app** or website
2. Go to your **Portfolio → Options positions**
3. Tap/click any position to see its detail page
4. The greeks (Delta, Gamma, Theta, Vega) and IV are shown in the **"Greeks"** section
5. Enter them **exactly as shown** — they are per-share values (Robinhood already normalizes them)
6. **Contracts**: use negative numbers for short positions (e.g. -1 for a sold call)

---

### What each metric means

| Metric | What it tells you |
|---|---|
| **Beta-Weighted Delta** | Your portfolio's directional exposure in SPY-equivalent shares. +10 = you profit like owning 10 SPY shares if SPY rises. |
| **Daily Theta** | How much your portfolio gains (positive) or loses (negative) each calendar day from time decay. |
| **Net Vega** | How much you gain/lose per 1% rise in implied volatility. |
| **Portfolio IV** | Vega-weighted average IV — a rough measure of how "expensive" the options you hold are. |
| **Theta / BW-Delta** | Income efficiency: daily theta earned per unit of directional exposure. |
| **Correlation matrix** | How much your underlyings move together. High correlation = concentrated risk. |

---

### Beta-weighted delta formula

```
BW Delta = (option_delta × contracts × 100 × stock_price × beta) / SPY_price
```

This normalizes all your positions into a common unit (SPY shares), letting you
see your true net directional bias regardless of how many different tickers you hold.

---

### Tips
- **Income strategies** (short puts, iron condors, covered calls): aim for **positive theta**, **near-zero BW delta**
- **Watch correlation risk**: if all your underlyings are tech stocks, you have concentrated sector risk even if they look like different tickers
- **Scenario tab**: use the sweep chart to see where your max loss/gain zones are
- Prices and betas are fetched from **Yahoo Finance** — click **Refresh Market Data** to update
    """)
