"""Trusted market-data adapters for the calculator.

MarketData.app supplies equity and listed-option quotes without requiring a
brokerage account. The U.S. Department of the Treasury supplies the official
daily par yield curve used to choose a risk-free rate close to the selected
option maturity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from json import JSONDecodeError, loads
from math import isfinite
from re import fullmatch
from statistics import stdev
from typing import Any, Mapping, Sequence, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from pricing import OptionType


MARKETDATA_URL = "https://api.marketdata.app"
TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "pages/xml"
)
REQUEST_TIMEOUT = 15
MARKET_TIMEZONE = ZoneInfo("America/New_York")


class MarketDataError(ValueError):
    """Raised when a provider cannot return a usable market-data snapshot."""


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    description: str
    spot: float
    expiry: date
    strike: float
    option_type: OptionType
    option_price: float
    option_symbol: str
    bid: float | None
    ask: float | None
    quote_time: datetime | None


@dataclass(frozen=True)
class TreasuryRate:
    rate_percent: float
    tenor: str
    as_of: date


@dataclass(frozen=True)
class RealizedVolatility:
    """Close-to-close sample volatility at the workbook's four horizons."""

    daily: float
    weekly: float
    monthly: float
    quarterly: float
    daily_observations: int
    as_of: date


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not fullmatch(r"[A-Z0-9](?:[A-Z0-9.\-]{0,10}[A-Z0-9])?", ticker):
        raise MarketDataError("Enter a valid U.S. ticker symbol.")
    return ticker


def _request_json(
    path: str,
    params: Mapping[str, str],
    token: str,
) -> Mapping[str, Any]:
    url = f"{MARKETDATA_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Implied-Volatility-Calculator/1.0",
    }
    if token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    request = Request(
        url,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:  # noqa: S310
            payload = loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            raise MarketDataError(
                "A MarketData.app token is required for this ticker, or the configured token is invalid."
            ) from exc
        if exc.code == 402:
            raise MarketDataError(
                "The MarketData.app plan or remaining credits do not cover this request."
            ) from exc
        if exc.code == 403:
            raise MarketDataError("MarketData.app denied this request.") from exc
        if exc.code == 429:
            raise MarketDataError("The MarketData.app request limit has been reached.") from exc
        raise MarketDataError(f"MarketData.app returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise MarketDataError("MarketData.app is temporarily unavailable.") from exc
    except (JSONDecodeError, UnicodeDecodeError) as exc:
        raise MarketDataError("MarketData.app returned an unreadable response.") from exc
    if not isinstance(payload, dict):
        raise MarketDataError("MarketData.app returned an unexpected response.")
    if payload.get("s") != "ok":
        message = str(payload.get("errmsg") or "MarketData.app could not complete the request.")
        raise MarketDataError(message)
    return cast(Mapping[str, Any], payload)


def _request_treasury_xml(year: int) -> bytes:
    query = urlencode(
        {
            "data": "daily_treasury_yield_curve",
            "field_tdr_date_value": str(year),
        }
    )
    request = Request(
        f"{TREASURY_URL}?{query}",
        headers={"User-Agent": "Implied-Volatility-Calculator/1.0"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:  # noqa: S310
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise MarketDataError("The U.S. Treasury rate feed is temporarily unavailable.") from exc


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first(value: Any) -> Any:
    values = _as_list(value)
    return values[0] if values else None


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def _nonnegative_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number >= 0 else None


def _quote_price(quote: Mapping[str, Any]) -> float | None:
    bid = _positive_number(quote.get("bid"))
    ask = _positive_number(quote.get("ask"))
    if bid is not None and ask is not None and ask >= bid:
        return (bid + ask) / 2.0
    return _positive_number(quote.get("mid")) or _positive_number(quote.get("last"))


def parse_quote(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if payload.get("s") != "ok" or not _as_list(payload.get("symbol")):
        raise MarketDataError("No equity quote was returned for this ticker.")
    return {
        "symbol": _first(payload.get("symbol")),
        "last": _first(payload.get("last")),
        "mid": _first(payload.get("mid")),
        "bid": _first(payload.get("bid")),
        "ask": _first(payload.get("ask")),
        "updated": _first(payload.get("updated")),
    }


def parse_expirations(payload: Mapping[str, Any]) -> list[date]:
    parsed: list[date] = []
    for value in _as_list(payload.get("expirations")):
        try:
            parsed.append(date.fromisoformat(str(value)))
        except ValueError:
            continue
    if not parsed:
        raise MarketDataError("No option expirations were returned for this ticker.")
    return sorted(set(parsed))


def choose_expiration(
    expirations: Sequence[date],
    valuation_date: date,
    target_days: int = 45,
) -> date:
    future = [expiry for expiry in expirations if expiry > valuation_date]
    if not future:
        raise MarketDataError("No unexpired option contracts were returned for this ticker.")
    return min(future, key=lambda expiry: (abs((expiry - valuation_date).days - target_days), expiry))


def parse_chain(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    symbols = _as_list(payload.get("optionSymbol"))
    if payload.get("s") != "ok" or not symbols:
        raise MarketDataError("No option contracts were returned for the selected expiration.")
    fields = {
        "optionSymbol": "symbol",
        "side": "option_type",
        "expiration": "expiration",
        "strike": "strike",
        "bid": "bid",
        "ask": "ask",
        "mid": "mid",
        "last": "last",
        "openInterest": "open_interest",
        "underlyingPrice": "underlying_price",
        "updated": "updated",
    }
    columns = {source: _as_list(payload.get(source)) for source in fields}
    contracts: list[Mapping[str, Any]] = []
    for index in range(len(symbols)):
        contract = {
            destination: values[index] if index < len(values) else None
            for source, destination in fields.items()
            for values in [columns[source]]
        }
        contracts.append(contract)
    return contracts


def choose_atm_contract(
    contracts: Sequence[Mapping[str, Any]],
    spot: float,
    option_type: OptionType,
) -> Mapping[str, Any]:
    candidates: list[Mapping[str, Any]] = []
    for contract in contracts:
        if str(contract.get("option_type", "")).lower() != option_type.lower():
            continue
        strike = _positive_number(contract.get("strike"))
        if strike is None or _quote_price(contract) is None:
            continue
        candidates.append(contract)
    if not candidates:
        raise MarketDataError(f"No priced {option_type.lower()} contracts were returned.")

    def rank(contract: Mapping[str, Any]) -> tuple[float, float, float]:
        strike = float(contract["strike"])
        bid = _positive_number(contract.get("bid"))
        ask = _positive_number(contract.get("ask"))
        spread = ask - bid if bid is not None and ask is not None and ask >= bid else float("inf")
        open_interest = _positive_number(contract.get("open_interest")) or 0.0
        return abs(strike - spot), spread, -open_interest

    return min(candidates, key=rank)


def _trade_time(value: Any) -> datetime | None:
    try:
        seconds = int(value)
        return datetime.fromtimestamp(seconds, tz=MARKET_TIMEZONE)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def parse_daily_candles(payload: Mapping[str, Any]) -> list[tuple[date, float]]:
    """Return valid, ordered, split-adjusted daily closes from a candles payload."""

    timestamps = _as_list(payload.get("t"))
    closes = _as_list(payload.get("c"))
    if payload.get("s") != "ok" or not timestamps or not closes:
        raise MarketDataError("No historical prices were returned for this ticker.")

    # A provider correction can repeat a trading date. Keep the last value in
    # the response, then sort explicitly so return calculations are chronological.
    by_date: dict[date, float] = {}
    for raw_timestamp, raw_close in zip(timestamps, closes):
        close = _positive_number(raw_close)
        if close is None:
            continue
        try:
            trading_date = datetime.fromtimestamp(
                int(raw_timestamp),
                tz=MARKET_TIMEZONE,
            ).date()
        except (OSError, OverflowError, TypeError, ValueError):
            continue
        by_date[trading_date] = close
    candles = sorted(by_date.items())
    if len(candles) < 3:
        raise MarketDataError("Not enough historical prices are available to calculate RV.")
    return candles


def _period_closes(
    candles: Sequence[tuple[date, float]],
    period: str,
) -> list[float]:
    if period == "daily":
        return [close for _, close in candles]

    grouped: dict[tuple[int, int], float] = {}
    for trading_date, close in candles:
        if period == "weekly":
            iso_year, iso_week, _ = trading_date.isocalendar()
            key = (iso_year, iso_week)
        elif period == "monthly":
            key = (trading_date.year, trading_date.month)
        elif period == "quarterly":
            key = (trading_date.year, (trading_date.month - 1) // 3 + 1)
        else:  # Defensive: callers are internal and use the four named horizons.
            raise ValueError(f"Unsupported RV period: {period}")
        grouped[key] = close
    return list(grouped.values())


def _close_to_close_stdev(closes: Sequence[float], period: str) -> float:
    returns = [current / previous - 1.0 for previous, current in zip(closes, closes[1:])]
    if len(returns) < 2:
        raise MarketDataError(
            f"Not enough {period} history is available to calculate realized volatility."
        )
    return stdev(returns)


def calculate_realized_volatility(
    candles: Sequence[tuple[date, float]],
) -> RealizedVolatility:
    """Calculate unannualized simple-return RV matching the workbook horizons."""

    ordered = sorted(candles)
    if len(ordered) < 3:
        raise MarketDataError("Not enough historical prices are available to calculate RV.")
    return RealizedVolatility(
        daily=_close_to_close_stdev(_period_closes(ordered, "daily"), "daily"),
        weekly=_close_to_close_stdev(_period_closes(ordered, "weekly"), "weekly"),
        monthly=_close_to_close_stdev(_period_closes(ordered, "monthly"), "monthly"),
        quarterly=_close_to_close_stdev(_period_closes(ordered, "quarterly"), "quarterly"),
        daily_observations=len(ordered),
        as_of=ordered[-1][0],
    )


def load_realized_volatility(
    ticker: str,
    token: str,
    as_of_date: date,
    *,
    countback: int = 1261,
) -> RealizedVolatility:
    """Load roughly five years of closes and calculate the four RV horizons."""

    symbol = normalize_ticker(ticker)
    if not isinstance(countback, int) or isinstance(countback, bool) or countback < 3:
        raise MarketDataError("Historical-price countback must be an integer of at least 3.")
    payload = _request_json(
        f"/v1/stocks/candles/D/{symbol}/",
        {"to": as_of_date.isoformat(), "countback": str(countback)},
        token,
    )
    return calculate_realized_volatility(parse_daily_candles(payload))


def load_market_snapshot(
    ticker: str,
    option_type: OptionType,
    token: str,
    valuation_date: date,
    *,
    target_days: int = 45,
) -> MarketSnapshot:
    symbol = normalize_ticker(ticker)
    if option_type not in ("Call", "Put"):
        raise MarketDataError("Option type must be 'Call' or 'Put'.")
    if not isinstance(target_days, int) or isinstance(target_days, bool) or target_days < 1:
        raise MarketDataError("Target days must be a positive integer.")

    chain_payload = _request_json(
        f"/v1/options/chain/{symbol}/",
        {"dte": str(target_days), "side": option_type.lower(), "strikeLimit": "10"},
        token,
    )
    contracts = parse_chain(chain_payload)
    spot = next(
        (
            value
            for contract in contracts
            if str(contract.get("option_type", "")).lower() == option_type.lower()
            for value in [_positive_number(contract.get("underlying_price"))]
            if value is not None
        ),
        None,
    )
    quote: Mapping[str, Any] | None = None
    if spot is None:
        quote = parse_quote(_request_json(f"/v1/stocks/quotes/{symbol}/", {}, token))
        spot = _positive_number(quote.get("last"))
        if spot is None:
            spot = _positive_number(quote.get("mid")) or _quote_price(quote)
    if spot is None:
        raise MarketDataError("The market data does not contain a usable underlying price.")

    contract = choose_atm_contract(contracts, spot, option_type)
    # Prefer the selected contract's synchronized underlying snapshot if it is
    # present, rather than mixing an option quote with a separate equity quote.
    spot = _positive_number(contract.get("underlying_price")) or spot
    option_price = _quote_price(contract)
    strike = _positive_number(contract.get("strike"))
    if option_price is None or strike is None:  # Defensive; selection already checks both.
        raise MarketDataError("The selected option contract does not contain a usable quote.")
    try:
        expiry = datetime.fromtimestamp(
            int(contract["expiration"]),
            tz=MARKET_TIMEZONE,
        ).date()
    except (KeyError, OSError, OverflowError, TypeError, ValueError) as exc:
        raise MarketDataError("The selected option contract has an invalid expiration date.") from exc
    if expiry <= valuation_date:
        raise MarketDataError("No unexpired option contracts were returned for this ticker.")
    return MarketSnapshot(
        ticker=symbol,
        description=symbol,
        spot=spot,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        option_price=option_price,
        option_symbol=str(contract.get("symbol") or ""),
        bid=_positive_number(contract.get("bid")),
        ask=_positive_number(contract.get("ask")),
        quote_time=_trade_time(
            contract.get("updated") or (quote.get("updated") if quote is not None else None)
        ),
    )


TREASURY_TENORS: tuple[tuple[int, str, str], ...] = (
    (30, "1 month", "BC_1MONTH"),
    (45, "1.5 months", "BC_1_5MONTH"),
    (60, "2 months", "BC_2MONTH"),
    (91, "3 months", "BC_3MONTH"),
    (122, "4 months", "BC_4MONTH"),
    (182, "6 months", "BC_6MONTH"),
    (365, "1 year", "BC_1YEAR"),
    (730, "2 years", "BC_2YEAR"),
)


def parse_treasury_rate(
    xml: bytes | str,
    maturity_days: int,
    as_of_date: date | None = None,
) -> TreasuryRate:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise MarketDataError("The U.S. Treasury returned an unreadable rate feed.") from exc
    namespaces = {
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
        "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
    }
    rows: list[tuple[date, Mapping[str, float]]] = []
    for properties in root.findall(".//m:properties", namespaces):
        raw_date = properties.findtext("d:NEW_DATE", namespaces=namespaces)
        if not raw_date:
            continue
        try:
            as_of = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        rates: dict[str, float] = {}
        for _, _, field in TREASURY_TENORS:
            raw_rate = properties.findtext(f"d:{field}", namespaces=namespaces)
            rate = _nonnegative_number(raw_rate)
            if rate is not None:
                rates[field] = rate
        if rates:
            rows.append((as_of, rates))
    eligible_rows = [row for row in rows if as_of_date is None or row[0] <= as_of_date]
    if not eligible_rows:
        raise MarketDataError("The U.S. Treasury rate feed contains no usable observations.")
    as_of, latest_rates = max(eligible_rows, key=lambda row: row[0])
    available = [tenor for tenor in TREASURY_TENORS if tenor[2] in latest_rates]
    days, label, field = min(available, key=lambda tenor: abs(tenor[0] - maturity_days))
    del days
    return TreasuryRate(rate_percent=latest_rates[field], tenor=label, as_of=as_of)


def load_treasury_rate(valuation_date: date, expiry: date) -> TreasuryRate:
    maturity_days = (expiry - valuation_date).days
    if maturity_days < 1:
        raise MarketDataError("Expiry must be after the valuation date.")
    for year in (valuation_date.year, valuation_date.year - 1):
        try:
            return parse_treasury_rate(
                _request_treasury_xml(year),
                maturity_days,
                as_of_date=valuation_date,
            )
        except MarketDataError:
            continue
    raise MarketDataError("No recent U.S. Treasury rate is available.")
