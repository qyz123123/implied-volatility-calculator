from datetime import date, datetime, timezone
from statistics import stdev

import pytest

import market_data
from market_data import (
    MarketDataError,
    calculate_realized_volatility,
    choose_atm_contract,
    choose_expiration,
    load_market_snapshot,
    load_realized_volatility,
    normalize_ticker,
    parse_daily_candles,
    parse_expirations,
    parse_treasury_rate,
)


def test_ticker_validation_and_expiration_selection():
    assert normalize_ticker(" brk.b ") == "BRK.B"
    for invalid in ("bad ticker!", "-", ".MSFT", "MSFT-"):
        with pytest.raises(MarketDataError, match="valid U.S. ticker"):
            normalize_ticker(invalid)

    valuation = date(2026, 8, 19)
    expirations = [date(2026, 8, 21), date(2026, 10, 2), date(2026, 12, 18)]
    assert choose_expiration(expirations, valuation) == date(2026, 10, 2)


def test_expiration_parser_accepts_singleton_and_list_payloads():
    assert parse_expirations({"expirations": "2026-10-02"}) == [date(2026, 10, 2)]
    assert parse_expirations(
        {"expirations": ["2026-12-18", "invalid", "2026-10-02"]}
    ) == [date(2026, 10, 2), date(2026, 12, 18)]


def test_daily_candle_parser_orders_deduplicates_and_rejects_bad_values():
    first = int(datetime(2026, 1, 2, 21, tzinfo=timezone.utc).timestamp())
    second = int(datetime(2026, 1, 5, 21, tzinfo=timezone.utc).timestamp())
    third = int(datetime(2026, 1, 6, 21, tzinfo=timezone.utc).timestamp())
    payload = {
        "s": "ok",
        "t": [second, first, second, third, third, "bad"],
        "c": [102.0, 100.0, 103.0, 104.0, 0.0, 999.0],
    }

    assert parse_daily_candles(payload) == [
        (date(2026, 1, 2), 100.0),
        (date(2026, 1, 5), 103.0),
        (date(2026, 1, 6), 104.0),
    ]


def test_realized_volatility_uses_period_end_closes_and_sample_stdev():
    dates = [
        date(2025, 1, 3),
        date(2025, 2, 3),
        date(2025, 3, 3),
        date(2025, 4, 3),
        date(2025, 5, 3),
        date(2025, 6, 3),
        date(2025, 7, 3),
        date(2025, 8, 3),
        date(2025, 9, 3),
    ]
    closes = [100.0, 104.0, 101.0, 110.0, 108.0, 115.0, 112.0, 120.0, 117.0]

    result = calculate_realized_volatility(list(zip(dates, closes, strict=True)))

    daily_returns = [current / previous - 1 for previous, current in zip(closes, closes[1:])]
    quarterly_closes = [101.0, 115.0, 117.0]
    quarterly_returns = [
        current / previous - 1
        for previous, current in zip(quarterly_closes, quarterly_closes[1:])
    ]
    assert result.daily == pytest.approx(stdev(daily_returns))
    assert result.weekly == pytest.approx(stdev(daily_returns))
    assert result.monthly == pytest.approx(stdev(daily_returns))
    assert result.quarterly == pytest.approx(stdev(quarterly_returns))
    assert result.daily_observations == 9
    assert result.as_of == date(2025, 9, 3)


def test_realized_volatility_loader_requests_history_through_quote_date(monkeypatch):
    dates = [date(2025, month, 3) for month in range(1, 10)]
    timestamps = [
        int(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        for day in dates
    ]

    def fake_request(path, params, token):
        assert path == "/v1/stocks/candles/D/AAPL/"
        assert params == {"to": "2025-09-03", "countback": "1261"}
        assert token == "secret"
        return {"s": "ok", "t": timestamps, "c": list(range(100, 109))}

    monkeypatch.setattr(market_data, "_request_json", fake_request)
    result = load_realized_volatility("aapl", "secret", date(2025, 9, 3))

    assert result.daily_observations == 9


def test_atm_contract_selection_uses_requested_type_and_usable_quote():
    contracts = [
        {"option_type": "call", "strike": 100, "bid": 4.0, "ask": 4.4},
        {"option_type": "call", "strike": 105, "bid": 1.8, "ask": 2.0},
        {"option_type": "put", "strike": 100, "bid": 3.8, "ask": 4.2},
        {"option_type": "put", "strike": 105, "bid": 0, "ask": 0, "last": 0},
    ]
    selected = choose_atm_contract(contracts, 103.0, "Call")
    assert selected["strike"] == 105
    selected_put = choose_atm_contract(contracts, 103.0, "Put")
    assert selected_put["strike"] == 100


def test_market_snapshot_maps_marketdata_payloads(monkeypatch):
    expiration = int(datetime(2026, 10, 2, 20, tzinfo=timezone.utc).timestamp())
    payloads = {
        "/v1/stocks/quotes/AAPL/": {
            "s": "ok",
            "symbol": ["AAPL"],
            "last": [203.25],
            "bid": [203.20],
            "ask": [203.30],
            "updated": [1_787_071_200],
        },
        "/v1/options/chain/AAPL/": {
            "s": "ok",
            "optionSymbol": ["AAPL261002C00200000", "AAPL261002C00205000"],
            "side": ["call", "call"],
            "expiration": [expiration, expiration],
            "strike": [200.0, 205.0],
            "bid": [8.0, 5.5],
            "ask": [8.4, 5.9],
            "last": [8.1, 5.7],
            "openInterest": [100, 200],
            "underlyingPrice": [202.75, 202.75],
            "updated": [1_787_071_200, 1_787_071_200],
        },
    }
    requested_paths = []

    def fake_request(path, params, token):
        requested_paths.append(path)
        assert token == "secret"
        if path == "/v1/options/chain/AAPL/":
            assert params == {"dte": "45", "side": "call", "strikeLimit": "10"}
        return payloads[path]

    monkeypatch.setattr(market_data, "_request_json", fake_request)
    snapshot = load_market_snapshot(
        "aapl",
        "Call",
        "secret",
        date(2026, 8, 19),
    )
    assert snapshot.ticker == "AAPL"
    assert snapshot.spot == pytest.approx(202.75)
    assert snapshot.expiry == date(2026, 10, 2)
    assert snapshot.strike == pytest.approx(205.0)
    assert snapshot.option_price == pytest.approx(5.7)
    assert snapshot.quote_time is not None
    assert snapshot.quote_time.tzinfo == market_data.MARKET_TIMEZONE
    assert requested_paths == ["/v1/options/chain/AAPL/"]


def test_market_snapshot_falls_back_to_equity_quote_without_chain_spot(monkeypatch):
    expiration = int(datetime(2026, 10, 2, 16, tzinfo=timezone.utc).timestamp())
    payloads = {
        "/v1/options/chain/AAPL/": {
            "s": "ok",
            "optionSymbol": ["AAPL261002C00200000"],
            "side": ["call"],
            "expiration": [expiration],
            "strike": [200.0],
            "mid": [8.2],
        },
        "/v1/stocks/quotes/AAPL/": {
            "s": "ok",
            "symbol": ["AAPL"],
            "last": [203.25],
        },
    }
    monkeypatch.setattr(
        market_data,
        "_request_json",
        lambda path, params, token: payloads[path],
    )

    snapshot = load_market_snapshot("AAPL", "Call", "secret", date(2026, 8, 19))

    assert snapshot.spot == pytest.approx(203.25)
    assert snapshot.option_price == pytest.approx(8.2)


def test_treasury_parser_uses_latest_observation_and_closest_tenor():
    xml = b"""<?xml version="1.0"?>
    <feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
          xmlns="http://www.w3.org/2005/Atom">
      <entry><content><m:properties>
        <d:NEW_DATE>2026-08-17T00:00:00</d:NEW_DATE>
        <d:BC_1MONTH>3.60</d:BC_1MONTH><d:BC_2MONTH>3.70</d:BC_2MONTH>
      </m:properties></content></entry>
      <entry><content><m:properties>
        <d:NEW_DATE>2026-08-18T00:00:00</d:NEW_DATE>
        <d:BC_1MONTH>3.61</d:BC_1MONTH><d:BC_2MONTH>3.71</d:BC_2MONTH>
      </m:properties></content></entry>
    </feed>"""
    result = parse_treasury_rate(xml, maturity_days=55)
    assert result.as_of == date(2026, 8, 18)
    assert result.tenor == "2 months"
    assert result.rate_percent == pytest.approx(3.71)

    historical = parse_treasury_rate(
        xml,
        maturity_days=55,
        as_of_date=date(2026, 8, 17),
    )
    assert historical.as_of == date(2026, 8, 17)
    assert historical.rate_percent == pytest.approx(3.70)


def test_treasury_parser_keeps_zero_rates_and_rejects_invalid_maturity():
    xml = b"""<feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
          xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
      <entry><content><m:properties>
        <d:NEW_DATE>2026-08-18T00:00:00</d:NEW_DATE>
        <d:BC_1MONTH>0.00</d:BC_1MONTH>
      </m:properties></content></entry>
    </feed>"""
    result = parse_treasury_rate(xml, maturity_days=30)
    assert result.rate_percent == 0.0

    with pytest.raises(MarketDataError, match="Expiry must be after"):
        market_data.load_treasury_rate(date(2026, 8, 19), date(2026, 8, 19))


@pytest.mark.parametrize("target_days", [0, -1, True])
def test_market_snapshot_rejects_invalid_target_days(target_days):
    with pytest.raises(MarketDataError, match="Target days"):
        load_market_snapshot(
            "AAPL",
            "Call",
            "secret",
            date(2026, 8, 19),
            target_days=target_days,
        )


def test_market_snapshot_rejects_invalid_option_type_before_request():
    with pytest.raises(MarketDataError, match="Option type"):
        load_market_snapshot(
            "AAPL",
            "Invalid",
            "secret",
            date(2026, 8, 19),
        )
