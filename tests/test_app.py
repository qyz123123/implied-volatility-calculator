from datetime import date, datetime, timedelta, timezone
from json import loads
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from market_data import MarketDataError, MarketSnapshot, RealizedVolatility, TreasuryRate


def test_all_calculators_and_modes_render_without_errors():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    assert app.radio[0].value == "Binomial · dividend yield"
    assert app.metric[2].value == "28.14%"
    assert "American:" in app.caption[0].value
    assert app.dataframe[1].key == "comparison_editor"
    assert len(app.dataframe[1].value) == 1
    assert app.dataframe[1].value.iloc[0]["Pricing model"] == "Binomial · dividend yield"
    assert "Class" not in app.dataframe[1].value
    assert "Notes" not in app.dataframe[1].value
    comparison_columns = loads(app.dataframe[1].proto.columns)
    for column in ["RV · Daily", "RV · Weekly", "RV · Monthly", "RV · Quarterly"]:
        assert comparison_columns[column]["hidden"] is True

    for model in [
        "Black–Scholes",
        "Binomial · dividend yield",
        "Binomial · discrete dividend",
    ]:
        app.radio[0].set_value(model).run()
        assert not app.exception
        assert not app.error

        if model == "Black–Scholes":
            assert "Call:" in app.caption[0].value and "Put:" in app.caption[0].value
        else:
            assert "American:" in app.caption[0].value
            assert "European:" in app.caption[0].value

        app.radio[1].set_value("Price from volatility").run()
        assert not app.exception
        assert not app.error
        app.radio[1].set_value("Infer implied volatility").run()


def test_ui_reports_invalid_contract_dates():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.date_input[1].set_value(date.today() - timedelta(days=1)).run()
    assert len(app.error) == 1
    assert "Expiry must be after" in app.error[0].value


def test_ui_reports_invalid_discrete_dividend_date():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.radio[0].set_value("Binomial · discrete dividend").run()
    expiry = app.date_input[1].value
    app.date_input[2].set_value(expiry + timedelta(days=1)).run()
    assert len(app.error) == 1
    assert "ex-dividend date" in app.error[0].value


def test_comparison_upserts_existing_ticker_and_appends_new_ticker():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    comparison = app.dataframe[1].value
    assert len(comparison) == 1
    assert list(comparison["Asset"]).count("MSFT") == 1

    old_quarterly_iv = comparison.loc[comparison["Asset"] == "MSFT", "IV · Quarterly"].item()
    observed_price = next(
        widget for widget in app.number_input if widget.label == "Observed option price"
    )
    observed_price.set_value(12.0).run()
    comparison = app.dataframe[1].value
    new_quarterly_iv = comparison.loc[comparison["Asset"] == "MSFT", "IV · Quarterly"].item()
    assert new_quarterly_iv != pytest.approx(old_quarterly_iv)
    assert new_quarterly_iv == pytest.approx(0.1945196343)
    assert (
        comparison.loc[comparison["Asset"] == "MSFT", "Pricing model"].item()
        == "Binomial · dividend yield"
    )

    app.text_input[1].set_value("AAPL").run()
    comparison = app.dataframe[1].value
    assert len(comparison) == 2
    assert list(comparison["Asset"]).count("AAPL") == 1
    assert (
        comparison.loc[comparison["Asset"] == "AAPL", "Pricing model"].item()
        == "Binomial · dividend yield"
    )

    app.radio[0].set_value("Black–Scholes").run()
    comparison = app.dataframe[1].value
    assert comparison.loc[comparison["Asset"] == "AAPL", "Pricing model"].item() == "Black–Scholes"

    spot_input = next(widget for widget in app.number_input if widget.label == "Spot price")
    spot_input.set_value(220.0).run()
    comparison = app.dataframe[1].value
    assert len(comparison) == 2
    assert list(comparison["Asset"]).count("AAPL") == 1


def test_market_download_reports_provider_error_without_breaking_calculator():
    with patch(
        "market_data.load_market_snapshot",
        side_effect=MarketDataError("Market-data request failed."),
    ):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        app.button[0].click().run()
    assert any("Market-data request failed" in error.value for error in app.error)
    assert not app.exception


def test_market_download_populates_inputs_recalculates_and_upserts_comparison():
    today = date.today()
    quote_date = today - timedelta(days=2)
    snapshot = MarketSnapshot(
        ticker="AAPL",
        description="Apple Inc.",
        spot=200.0,
        expiry=today + timedelta(days=45),
        strike=200.0,
        option_type="Call",
        option_price=10.0,
        option_symbol="AAPLTEST",
        bid=9.9,
        ask=10.1,
        quote_time=datetime.combine(quote_date, datetime.min.time(), tzinfo=timezone.utc),
    )
    treasury = TreasuryRate(rate_percent=4.25, tenor="2 months", as_of=quote_date)
    realized = RealizedVolatility(
        daily=0.012,
        weekly=0.026,
        monthly=0.051,
        quarterly=0.088,
        daily_observations=1261,
        as_of=quote_date,
    )
    with (
        patch.dict("os.environ", {"MARKETDATA_TOKEN": "test-token"}),
        patch("market_data.load_market_snapshot", return_value=snapshot),
        patch("market_data.load_realized_volatility", return_value=realized) as rv_loader,
        patch("market_data.load_treasury_rate", return_value=treasury) as treasury_loader,
    ):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        app.text_input[0].set_value("AAPL").run()
        app.button[0].click().run()

    assert next(widget for widget in app.text_input if widget.label == "Asset label").value == "AAPL"
    assert next(widget for widget in app.number_input if widget.label == "Spot price").value == 200.0
    assert next(widget for widget in app.number_input if widget.label == "Strike price").value == 200.0
    assert next(
        widget for widget in app.number_input if widget.label == "Observed option price"
    ).value == 10.0
    assert next(widget for widget in app.number_input if widget.label == "Risk-free rate (%)").value == 4.25
    assert next(widget for widget in app.date_input if widget.label == "Valuation date").value == quote_date
    treasury_loader.assert_called_once_with(quote_date, snapshot.expiry)
    rv_loader.assert_called_once()
    rv_args = rv_loader.call_args.args
    assert rv_args[0] == "AAPL"
    assert rv_args[2] == quote_date
    comparison = app.dataframe[1].value
    assert len(comparison) == 2
    assert list(comparison["Asset"]).count("AAPL") == 1
    aapl = comparison.loc[comparison["Asset"] == "AAPL"].iloc[0]
    assert aapl["Pricing model"] == "Binomial · dividend yield"
    assert aapl["RV · Daily"] == pytest.approx(0.012)
    assert aapl["RV · Weekly"] == pytest.approx(0.026)
    assert aapl["RV · Monthly"] == pytest.approx(0.051)
    assert aapl["RV · Quarterly"] == pytest.approx(0.088)
    comparison_columns = loads(app.dataframe[1].proto.columns)
    for column in ["RV · Daily", "RV · Weekly", "RV · Monthly", "RV · Quarterly"]:
        assert comparison_columns[column].get("hidden") is not True
    assert not app.exception
