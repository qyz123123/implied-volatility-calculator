from __future__ import annotations

from datetime import date, timedelta
import os
from typing import Any, Mapping, cast

import pandas as pd
import streamlit as st

from market_data import (
    MarketDataError,
    load_market_snapshot,
    load_realized_volatility,
    load_treasury_rate,
)
from pricing import (
    ExerciseStyle,
    OptionType,
    PriceResult,
    binomial_discrete,
    binomial_yield,
    black_scholes,
    solve_implied_volatility,
    volatility_assessment,
)


st.set_page_config(
    page_title="Implied Volatility Calculator",
    page_icon="σ",
    layout="wide",
    initial_sidebar_state="collapsed",
)


STYLE = """
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
[data-testid="stHeader"], [data-testid="stToolbar"] {
  background: #ffffff !important;
  color: #000000 !important;
}
* {
  color: #000000 !important;
  border-color: transparent !important;
  box-shadow: none !important;
}
.block-container {
  max-width: 1180px;
  padding-top: 2.25rem;
  padding-bottom: 4rem;
}
[data-testid="stSidebar"] { border: none !important; }
[data-testid="stSidebarContent"] { padding-top: 2rem; }
[data-testid="stForm"], [data-testid="stMetric"], [data-testid="stAlert"],
[data-testid="stDataFrame"], [data-testid="stTable"],
[data-testid="stVerticalBlockBorderWrapper"] {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
[data-testid="stMetric"] { padding: 0 !important; }
[data-testid="stAlert"] { padding: .35rem 0 !important; }
[data-testid="stAlert"] svg { display: none !important; }
[data-baseweb="input"], [data-baseweb="select"] > div,
[data-baseweb="textarea"], [data-baseweb="datepicker"] {
  background: #ffffff !important;
  border: 1px solid #d2d6dc !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  transition: border-color .15s ease !important;
}
[data-baseweb="base-input"] {
  background: #ffffff !important;
  border: none !important;
  border-radius: inherit !important;
  box-shadow: none !important;
}
[data-baseweb="input"]:focus-within,
[data-baseweb="select"] > div:focus-within,
[data-baseweb="textarea"]:focus-within,
[data-baseweb="datepicker"]:focus-within {
  border-color: #000000 !important;
}
[data-baseweb="popover"], [data-baseweb="menu"], [data-baseweb="calendar"] {
  background: #ffffff !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
[data-baseweb="calendar"] [role="gridcell"]::before,
[data-baseweb="calendar"] [role="gridcell"]::after {
  background: #ffffff !important;
  border-color: transparent !important;
  box-shadow: none !important;
}
[data-baseweb="calendar"] [role="gridcell"][aria-label^="Selected"] {
  background: #ffffff !important;
  color: #000000 !important;
  font-weight: 700 !important;
  text-decoration: underline !important;
  text-underline-offset: .2rem;
}
[data-baseweb="calendar"] [role="gridcell"]:hover {
  background: #ffffff !important;
  font-weight: 700 !important;
  text-decoration: underline !important;
}
input, textarea {
  background: #ffffff !important;
  color: #000000 !important;
  caret-color: #000000 !important;
}
button, [role="button"] {
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
div.stButton > button, div.stDownloadButton > button,
[data-testid="stFormSubmitButton"] button {
  background: transparent !important;
  color: #000000 !important;
  font-weight: 700 !important;
  text-decoration: underline !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
}
div.stButton > button:hover, div.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] button:hover {
  background: transparent !important;
}
[data-baseweb="tab-list"] { gap: 1.5rem; border: none !important; }
[data-baseweb="tab"] {
  background: transparent !important;
  padding-left: 0;
  padding-right: 0;
}
[data-baseweb="tab"][aria-selected="true"] {
  font-weight: 700;
  text-decoration: underline;
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {
  display: none !important;
}
[role="tablist"]::after, hr { display: none !important; }
a {
  color: #000000 !important;
  text-decoration: underline !important;
}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {
  opacity: 1 !important;
}
[data-testid="stDataFrame"] > div, [data-testid="stDataFrameResizable"] {
  border: none !important;
  border-radius: 0 !important;
}
.stDataFrameGlideDataEditor {
  --gdg-bg-header: #ffffff !important;
  --gdg-bg-group-header: #ffffff !important;
  --gdg-border-color: transparent !important;
  --gdg-horizontal-border-color: transparent !important;
}
h1, h2, h3 { letter-spacing: -.025em; }
.st-key-output_panel [data-testid="stMetricValue"] {
  font-size: 1.875rem !important;
  line-height: 1.2 !important;
}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


def percent_input(label: str, value: float, key: str, help_text: str | None = None) -> float:
    input_kwargs: dict = {
        "step": 0.01,
        "format": "%.3f",
        "key": key,
        "help": help_text,
    }
    if key not in st.session_state:
        input_kwargs["value"] = value
    return st.number_input(label, **input_kwargs) / 100.0


def metric_value(value: float | None, digits: int = 4) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def _render_results_content(
    result: PriceResult,
    annual_vol: float,
    spot: float,
    time: float,
    observed_price: float | None,
) -> pd.DataFrame:
    st.markdown("### Results")
    columns = st.columns(3)
    columns[0].metric("Implied volatility", f"{annual_vol:.2%}")
    columns[1].metric("Model price", f"${result.price:,.4f}")
    difference = None if observed_price is None else result.price - observed_price
    columns[2].metric("Model − market", "—" if difference is None else f"${difference:+,.6f}")

    st.markdown("#### Greeks")
    greek_columns = st.columns(5)
    greek_columns[0].metric("Delta", metric_value(result.greeks.delta))
    greek_columns[1].metric("Gamma", metric_value(result.greeks.gamma, 6))
    greek_columns[2].metric("Theta / day", metric_value(result.greeks.theta))
    greek_columns[3].metric("Vega / 1 vol pt", metric_value(result.greeks.vega))
    greek_columns[4].metric("Rho / 1 rate pt", metric_value(result.greeks.rho))
    if result.call_price is not None and result.put_price is not None:
        st.caption(f"Call: \\${result.call_price:,.4f} · Put: \\${result.put_price:,.4f}")
    if result.american_price is not None and result.european_price is not None:
        st.caption(
            f"American: \\${result.american_price:,.4f} · "
            f"European: \\${result.european_price:,.4f}"
        )

    rows = volatility_assessment(spot, annual_vol, time)
    frame = pd.DataFrame(rows)
    st.markdown("### Volatility assessment")
    display = frame.copy()
    display["Implied volatility"] = display["Implied volatility"].map(lambda x: f"{x:.2%}")
    for column in ["1σ lower", "1σ upper", "2σ lower", "2σ upper"]:
        display[column] = display[column].map(lambda x: f"${x:,.2f}")
    st.dataframe(display, hide_index=True, width="stretch")
    st.caption(
        "Uses square-root-of-time scaling, zero expected return, and normally "
        "distributed simple returns. Price ranges are indicative."
    )
    return frame


def render_results(
    result: PriceResult,
    annual_vol: float,
    spot: float,
    time: float,
    observed_price: float | None,
) -> pd.DataFrame:
    with st.container(key="output_panel"):
        return _render_results_content(result, annual_vol, spot, time, observed_price)


def workbook_examples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["MSFT", "Binomial · dividend yield", 0.021524580377421443, 0.04472242222087947, 0.0972745440186476, 0.1638938742803825, 0.014730437931511643, 0.03902657319643608, 0.08124029049869728, 0.14071231076539883],
        ],
        columns=[
            "Asset", "Pricing model", "RV · Daily", "RV · Weekly", "RV · Monthly", "RV · Quarterly",
            "IV · Daily", "IV · Weekly", "IV · Monthly", "IV · Quarterly",
        ],
    )


PERCENTAGE_COLUMNS = [
    "RV · Daily",
    "RV · Weekly",
    "RV · Monthly",
    "RV · Quarterly",
    "IV · Daily",
    "IV · Weekly",
    "IV · Monthly",
    "IV · Quarterly",
]

RV_COLUMNS = [
    "RV · Daily",
    "RV · Weekly",
    "RV · Monthly",
    "RV · Quarterly",
]

PRICING_ENGINES = [
    "Black–Scholes",
    "Binomial · dividend yield",
    "Binomial · discrete dividend",
]


def upsert_comparison(
    comparison: pd.DataFrame,
    asset: str,
    model: str,
    assessment: pd.DataFrame,
    realized_volatility: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    updated = comparison.copy()
    for column in workbook_examples().columns:
        if column not in updated:
            updated[column] = None
    updated = updated.loc[:, workbook_examples().columns]
    ticker = asset.strip().upper() or "CURRENT"
    current = assessment.set_index("Timeframe")["Implied volatility"]
    values = {
        "Asset": ticker,
        "Pricing model": model,
        "IV · Daily": current["Daily"],
        "IV · Weekly": current["Weekly"],
        "IV · Monthly": current["Monthly"],
        "IV · Quarterly": current["Quarterly"],
    }
    if realized_volatility is not None:
        values.update(
            {
                "RV · Daily": realized_volatility["daily"],
                "RV · Weekly": realized_volatility["weekly"],
                "RV · Monthly": realized_volatility["monthly"],
                "RV · Quarterly": realized_volatility["quarterly"],
            }
        )
    matches = updated["Asset"].fillna("").astype(str).str.strip().str.upper() == ticker
    if matches.any():
        row_index = updated.index[matches][0]
        for column, value in values.items():
            updated.at[row_index, column] = value
        return updated.reset_index(drop=True)
    new_row: dict[str, object] = {column: None for column in updated.columns}
    new_row.update(values)
    records = updated.to_dict(orient="records")
    return pd.DataFrame.from_records([*records, cast(dict, new_row)], columns=updated.columns)


def market_data_token() -> str:
    token = os.environ.get("MARKETDATA_TOKEN", "")
    try:
        token = str(st.secrets.get("MARKETDATA_TOKEN", token))
    except FileNotFoundError:
        pass
    return token.strip()


st.title("Implied Volatility Calculator")
model = st.radio(
    "Pricing engine",
    PRICING_ENGINES,
    horizontal=True,
    index=1,
    label_visibility="collapsed",
)

today = date.today()
default_expiry = today + timedelta(days=48)

input_defaults: dict[str, object] = {
    "asset": "MSFT",
    "option_type": "Call",
    "spot": 215.29,
    "strike": 215.0,
    "valuation_date": today,
    "expiry_date": default_expiry,
    "rate": 0.09,
    "mode": "Infer implied volatility",
    "observed_price": 8.70,
}
for state_key, default_value in input_defaults.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value

st.markdown("### Market data")
market_a, market_b = st.columns([3, 1], vertical_alignment="bottom")
with market_a:
    market_ticker = st.text_input("Ticker", "MSFT", key="market_ticker")
with market_b:
    download_market_data = st.button("Download data")

if download_market_data:
    st.session_state.pop("market_data_status", None)
    try:
        selected_type = cast(OptionType, st.session_state["option_type"])
        token = market_data_token()
        snapshot = load_market_snapshot(
            market_ticker,
            selected_type,
            token,
            today,
        )
        market_valuation_date = (
            snapshot.quote_time.date() if snapshot.quote_time is not None else today
        )
        st.session_state["asset"] = snapshot.ticker
        st.session_state["spot"] = snapshot.spot
        st.session_state["strike"] = snapshot.strike
        st.session_state["valuation_date"] = market_valuation_date
        st.session_state["expiry_date"] = snapshot.expiry
        st.session_state["mode"] = "Infer implied volatility"
        st.session_state["observed_price"] = snapshot.option_price
        rate_note = ""
        try:
            treasury = load_treasury_rate(market_valuation_date, snapshot.expiry)
            st.session_state["rate"] = treasury.rate_percent
            rate_note = f" · Treasury {treasury.tenor}: {treasury.rate_percent:.2f}%"
        except MarketDataError:
            rate_note = " · Treasury rate unavailable; existing rate retained"
        rv_note = ""
        try:
            realized = load_realized_volatility(
                snapshot.ticker,
                token,
                market_valuation_date,
            )
            realized_by_asset = dict(
                cast(
                    dict[str, dict[str, float]],
                    st.session_state.get("realized_volatility_by_asset", {}),
                )
            )
            realized_by_asset[snapshot.ticker] = {
                "daily": realized.daily,
                "weekly": realized.weekly,
                "monthly": realized.monthly,
                "quarterly": realized.quarterly,
            }
            st.session_state["realized_volatility_by_asset"] = realized_by_asset
            rv_note = (
                f" · RV through {realized.as_of:%Y-%m-%d} "
                f"({realized.daily_observations} closes)"
            )
        except MarketDataError:
            rv_note = " · Historical RV unavailable"
        quote_time = (
            f" · {snapshot.quote_time:%Y-%m-%d %H:%M %Z}" if snapshot.quote_time else ""
        )
        st.session_state["market_data_status"] = (
            f"MarketData.app: {snapshot.option_type} {snapshot.expiry:%Y-%m-%d} "
            f"${snapshot.strike:,.2f} at ${snapshot.option_price:,.2f}"
            f"{rate_note}{rv_note}{quote_time}"
        )
    except MarketDataError as exc:
        st.error(str(exc))

if "market_data_status" in st.session_state:
    st.caption(str(st.session_state["market_data_status"]))

with st.container():
    st.markdown("### Inputs")
    common_a, common_b, common_c, common_d = st.columns(4)
    with common_a:
        asset = st.text_input("Asset label", key="asset")
        option_type = cast(OptionType, st.selectbox("Option type", ["Call", "Put"], key="option_type"))
    with common_b:
        spot = st.number_input("Spot price", min_value=0.01, step=1.0, format="%.4f", key="spot")
        strike = st.number_input("Strike price", min_value=0.01, step=1.0, format="%.4f", key="strike")
    with common_c:
        valuation_date = st.date_input("Valuation date", key="valuation_date")
        expiry_date = st.date_input("Expiry date", key="expiry_date")
    with common_d:
        rate = percent_input("Risk-free rate (%)", 0.09, "rate", "Annual, continuously compounded.")
        mode = st.radio(
            "Calculation",
            ["Infer implied volatility", "Price from volatility"],
            key="mode",
        )

    time = (expiry_date - valuation_date).days / 365.0
    model_kwargs: dict = {}
    extra_a, extra_b, extra_c, extra_d = st.columns(4)
    if model == "Black–Scholes":
        with extra_a:
            dividend_yield = percent_input("Dividend yield (%)", 1.05, "bs_q")
        model_kwargs["dividend_yield"] = dividend_yield
    elif model == "Binomial · dividend yield":
        with extra_a:
            dividend_yield = percent_input("Dividend yield (%)", 1.05, "tree_q")
        with extra_b:
            steps = st.number_input("Tree steps", min_value=2, max_value=1000, value=20, step=10)
        model_kwargs.update(dividend_yield=dividend_yield, steps=int(steps))
    else:
        with extra_a:
            dividend_amount = st.number_input("Cash dividend", min_value=0.0, value=0.56, step=0.05, format="%.4f")
        with extra_b:
            ex_dividend_date = st.date_input("Ex-dividend date", today + timedelta(days=25))
        with extra_c:
            steps = st.number_input("Tree steps", min_value=2, max_value=1000, value=20, step=10, key="discrete_steps")
        with extra_d:
            exercise_style = cast(
                ExerciseStyle,
                st.selectbox("Exercise style", ["American", "European"]),
            )
        dividend_time = (ex_dividend_date - valuation_date).days / 365.0
        model_kwargs.update(
            dividend_amount=dividend_amount,
            dividend_time=dividend_time,
            steps=int(steps),
            exercise_style=exercise_style,
        )

    market_a, market_b, market_c, _ = st.columns(4)
    observed_price: float | None = None
    assumed_vol: float | None = None
    with market_a:
        if mode == "Infer implied volatility":
            observed_price = st.number_input(
                "Observed option price",
                min_value=0.0001,
                step=0.1,
                format="%.4f",
                key="observed_price",
            )
        else:
            assumed_vol = percent_input("Assumed volatility (%)", 28.14, "assumed_vol")
    with market_b:
        st.metric("Days to expiry", max((expiry_date - valuation_date).days, 0))
    with market_c:
        st.metric("Moneyness (S/K)", f"{spot / strike:.4f}")


def price_at(volatility: float) -> PriceResult:
    if model == "Black–Scholes":
        return black_scholes(spot, strike, time, rate, volatility=volatility, option_type=option_type, **model_kwargs)
    if model == "Binomial · dividend yield":
        return binomial_yield(spot, strike, time, rate, volatility=volatility, option_type=option_type, **model_kwargs)
    return binomial_discrete(spot, strike, time, rate, volatility=volatility, option_type=option_type, **model_kwargs)


assessment_frame: pd.DataFrame | None
try:
    if mode == "Infer implied volatility":
        if observed_price is None:
            raise ValueError("Observed option price is required.")
        solved = solve_implied_volatility(observed_price, lambda volatility: price_at(volatility).price)
        annual_vol = solved.volatility
    else:
        if assumed_vol is None:
            raise ValueError("Assumed volatility is required.")
        annual_vol = assumed_vol
    priced = price_at(annual_vol)
    assessment_frame = render_results(priced, annual_vol, spot, time, observed_price)
    calculation_error = None
except ValueError as exc:
    calculation_error = str(exc)
    st.error(calculation_error)
    assessment_frame = None

with st.expander("Model guide"):
    st.markdown(
        """
        - **Black–Scholes:** European options with or without a continuous dividend yield; also suitable for American calls on non-dividend-paying shares.
        - **Binomial · dividend yield:** American calls or puts when dividends are represented as a continuous annual yield.
        - **Binomial · discrete dividend:** American or European calls or puts with one announced cash dividend before expiry. It uses the workbook's prepaid-forward adjustment.

        The workbook's manual Solver step is replaced by a bounded numerical inversion. Rates, yields, and volatility are annualized decimals internally; dates use ACT/365.
        """
    )

st.markdown("## Comparison")
comparison_data_version = 4
if "comparison_data" not in st.session_state or not isinstance(
    st.session_state["comparison_data"], pd.DataFrame
):
    st.session_state["comparison_data"] = workbook_examples()
elif st.session_state.get("comparison_data_version", 0) < comparison_data_version:
    migrated_comparison = cast(pd.DataFrame, st.session_state["comparison_data"]).copy()
    migrated_comparison = migrated_comparison.drop(
        columns=["Class", "Notes"],
        errors="ignore",
    )
    if "Pricing model" not in migrated_comparison:
        migrated_comparison.insert(1, "Pricing model", None)
    st.session_state["comparison_data"] = migrated_comparison
    st.session_state.pop("comparison_calculation_signature", None)
    st.session_state.pop("comparison_editor", None)
if st.session_state.get("comparison_data_version") != comparison_data_version:
    st.session_state["comparison_data_version"] = comparison_data_version
comparison = cast(pd.DataFrame, st.session_state["comparison_data"]).copy()
if calculation_error is None and assessment_frame is not None:
    ticker_key = asset.strip().upper()
    realized_by_asset = cast(
        dict[str, dict[str, float]],
        st.session_state.get("realized_volatility_by_asset", {}),
    )
    ticker_rv = realized_by_asset.get(ticker_key)
    calculation_signature = (
        ticker_key,
        model,
        tuple(
            zip(
                assessment_frame["Timeframe"].astype(str),
                assessment_frame["Implied volatility"].astype(float),
                strict=True,
            )
        ),
        None if ticker_rv is None else tuple(sorted(ticker_rv.items())),
    )
    if st.session_state.get("comparison_calculation_signature") != calculation_signature:
        comparison = upsert_comparison(
            comparison,
            asset,
            model,
            assessment_frame,
            realized_volatility=ticker_rv,
        )
        st.session_state["comparison_data"] = comparison
        st.session_state["comparison_calculation_signature"] = calculation_signature
        # The editor keeps a positional change-set under its widget key. Clear
        # that overlay when fresh calculator values arrive so it cannot paint
        # stale values over the newly upserted ticker row.
        if "comparison_editor" in st.session_state:
            del st.session_state["comparison_editor"]

column_config: dict[str, Any] = {
    column: st.column_config.NumberColumn(column, format="percent")
    for column in PERCENTAGE_COLUMNS
}
complete_rv_rows = comparison[RV_COLUMNS].notna().all(axis=1).sum()
if complete_rv_rows < 2:
    for column in RV_COLUMNS:
        column_config[column] = None
edited_comparison = st.data_editor(
    comparison,
    hide_index=True,
    width="stretch",
    num_rows="dynamic",
    column_config=column_config,
    key="comparison_editor",
)
st.session_state["comparison_data"] = edited_comparison

if calculation_error is None and assessment_frame is not None:
    st.download_button(
        "Download comparison CSV",
        edited_comparison.to_csv(index=False).encode("utf-8"),
        file_name="implied_volatility_comparison.csv",
        mime="text/csv",
    )
