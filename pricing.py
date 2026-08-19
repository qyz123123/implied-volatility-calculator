"""Option-pricing engines used by the Streamlit application.

The implementations mirror the three calculation sheets in
Implied_Volatility_Calculator_IPLT.xlsm while replacing Excel Solver with a
bounded numerical root finder.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, isfinite, log, pi, sqrt
from typing import Callable, Literal

import numpy as np


OptionType = Literal["Call", "Put"]
ExerciseStyle = Literal["American", "European"]


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    theta: float
    vega: float | None = None
    rho: float | None = None


@dataclass(frozen=True)
class PriceResult:
    price: float
    greeks: Greeks
    call_price: float | None = None
    put_price: float | None = None
    call_greeks: Greeks | None = None
    put_greeks: Greeks | None = None
    american_price: float | None = None
    european_price: float | None = None


@dataclass(frozen=True)
class ImpliedVolResult:
    volatility: float
    model_price: float
    iterations: int


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _normal_pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2.0 * pi)


def _validate_common(spot: float, strike: float, time: float, volatility: float) -> None:
    if not all(isfinite(value) for value in (spot, strike, time, volatility)):
        raise ValueError("Spot, strike, time, and volatility must be finite numbers.")
    if spot <= 0 or strike <= 0:
        raise ValueError("Spot and strike must both be greater than zero.")
    if time <= 0:
        raise ValueError("Expiry must be after the valuation date.")
    if volatility <= 0:
        raise ValueError("Volatility must be greater than zero.")


def black_scholes(
    spot: float,
    strike: float,
    time: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
    option_type: OptionType,
) -> PriceResult:
    """Price a European option and calculate workbook-compatible Greeks.

    Theta is returned per calendar day. Vega and rho are returned per one
    percentage-point change, matching the workbook's division by 100.
    """

    _validate_common(spot, strike, time, volatility)
    if option_type not in ("Call", "Put"):
        raise ValueError("Option type must be 'Call' or 'Put'.")
    if not isfinite(rate) or not isfinite(dividend_yield):
        raise ValueError("Rate and dividend yield must be finite numbers.")
    vol_sqrt_time = volatility * sqrt(time)
    d1 = (
        log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time
    ) / vol_sqrt_time
    d2 = d1 - vol_sqrt_time
    discount_r = exp(-rate * time)
    discount_q = exp(-dividend_yield * time)
    pdf_d1 = _normal_pdf(d1)

    call_price = (
        spot * discount_q * _normal_cdf(d1)
        - strike * discount_r * _normal_cdf(d2)
    )
    put_price = (
        strike * discount_r * _normal_cdf(-d2)
        - spot * discount_q * _normal_cdf(-d1)
    )

    gamma = discount_q * pdf_d1 / (spot * vol_sqrt_time)
    vega = spot * discount_q * pdf_d1 * sqrt(time) / 100.0

    call_greeks = Greeks(
        delta=discount_q * _normal_cdf(d1),
        gamma=gamma,
        theta=(
            -(spot * discount_q * pdf_d1 * volatility) / (2.0 * sqrt(time))
            - rate * strike * discount_r * _normal_cdf(d2)
            + dividend_yield * spot * discount_q * _normal_cdf(d1)
        )
        / 365.0,
        vega=vega,
        rho=strike * time * discount_r * _normal_cdf(d2) / 100.0,
    )
    put_greeks = Greeks(
        delta=discount_q * (_normal_cdf(d1) - 1.0),
        gamma=gamma,
        theta=(
            -(spot * discount_q * pdf_d1 * volatility) / (2.0 * sqrt(time))
            + rate * strike * discount_r * _normal_cdf(-d2)
            - dividend_yield * spot * discount_q * _normal_cdf(-d1)
        )
        / 365.0,
        vega=vega,
        rho=-strike * time * discount_r * _normal_cdf(-d2) / 100.0,
    )
    if option_type == "Call":
        price = call_price
        greeks = call_greeks
    else:
        price = put_price
        greeks = put_greeks

    return PriceResult(
        price=price,
        greeks=greeks,
        call_price=call_price,
        put_price=put_price,
        call_greeks=call_greeks,
        put_greeks=put_greeks,
    )


def _tree_price(
    spot: float,
    strike: float,
    time: float,
    rate: float,
    volatility: float,
    option_type: OptionType,
    steps: int,
    exercise_style: ExerciseStyle,
    dividend_yield: float = 0.0,
    dividend_amount: float = 0.0,
    dividend_time: float | None = None,
) -> tuple[float, dict[int, tuple[np.ndarray, np.ndarray]]]:
    _validate_common(spot, strike, time, volatility)
    if option_type not in ("Call", "Put"):
        raise ValueError("Option type must be 'Call' or 'Put'.")
    if exercise_style not in ("American", "European"):
        raise ValueError("Exercise style must be 'American' or 'European'.")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 2:
        raise ValueError("The binomial models require at least two steps.")
    if not all(isfinite(value) for value in (rate, dividend_yield, dividend_amount)):
        raise ValueError("Rates, yields, and dividend amounts must be finite numbers.")
    if dividend_time is not None and not isfinite(dividend_time):
        raise ValueError("Dividend time must be a finite number.")
    if dividend_amount < 0:
        raise ValueError("The dividend amount cannot be negative.")
    if dividend_amount and (dividend_time is None or not 0 < dividend_time < time):
        raise ValueError("The ex-dividend date must fall between valuation and expiry.")

    dt = time / steps
    up = exp(volatility * sqrt(dt))
    down = 1.0 / up
    growth = exp((rate - dividend_yield) * dt)
    probability = (growth - down) / (up - down)
    if not 0.0 <= probability <= 1.0:
        raise ValueError(
            "The chosen step count produces an invalid risk-neutral probability. "
            "Increase the number of steps or review the rate and volatility."
        )
    discount = exp(-rate * dt)
    sign = 1.0 if option_type == "Call" else -1.0

    if dividend_amount:
        if dividend_time is None:  # Narrowed explicitly for static type checkers.
            raise ValueError("Dividend time is required for a positive cash dividend.")
        dividend_time_value = dividend_time
        uncertain_spot = spot - dividend_amount * exp(-rate * dividend_time_value)
        if uncertain_spot <= 0:
            raise ValueError("The dividend's present value must be smaller than spot.")
    else:
        dividend_time_value = 0.0
        uncertain_spot = spot

    def stock_layer(step: int) -> np.ndarray:
        up_moves = np.arange(step + 1, dtype=float)
        uncertain = uncertain_spot * (up ** up_moves) * (down ** (step - up_moves))
        current_time = step * dt
        if dividend_amount and current_time < dividend_time_value:  # cum-dividend value
            uncertain += dividend_amount * exp(-rate * (dividend_time_value - current_time))
        return uncertain

    stocks = stock_layer(steps)
    values = np.maximum(sign * (stocks - strike), 0.0)
    snapshots: dict[int, tuple[np.ndarray, np.ndarray]] = {
        steps: (stocks.copy(), values.copy())
    }

    for step in range(steps - 1, -1, -1):
        continuation = discount * (
            probability * values[1:] + (1.0 - probability) * values[:-1]
        )
        stocks = stock_layer(step)
        if exercise_style == "American":
            intrinsic = np.maximum(sign * (stocks - strike), 0.0)
            values = np.maximum(continuation, intrinsic)
        else:
            values = continuation
        if step <= 2:
            snapshots[step] = (stocks.copy(), values.copy())

    return float(values[0]), snapshots


def _tree_greeks(
    root_price: float,
    snapshots: dict[int, tuple[np.ndarray, np.ndarray]],
    time: float,
    steps: int,
) -> Greeks:
    stocks_1, values_1 = snapshots[1]
    stocks_2, values_2 = snapshots[2]
    delta = (values_1[1] - values_1[0]) / (stocks_1[1] - stocks_1[0])
    delta_up = (values_2[2] - values_2[1]) / (stocks_2[2] - stocks_2[1])
    delta_down = (values_2[1] - values_2[0]) / (stocks_2[1] - stocks_2[0])
    gamma = (delta_up - delta_down) / ((stocks_2[2] - stocks_2[0]) / 2.0)
    theta = (values_2[1] - root_price) / (2.0 * (time / steps) * 365.0)
    return Greeks(delta=delta, gamma=gamma, theta=theta)


def binomial_yield(
    spot: float,
    strike: float,
    time: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
    option_type: OptionType,
    steps: int = 20,
) -> PriceResult:
    """CRR price for an American option paying a continuous dividend yield."""

    american_price, snapshots = _tree_price(
        spot,
        strike,
        time,
        rate,
        volatility,
        option_type,
        steps,
        "American",
        dividend_yield=dividend_yield,
    )
    european_price, _ = _tree_price(
        spot,
        strike,
        time,
        rate,
        volatility,
        option_type,
        steps,
        "European",
        dividend_yield=dividend_yield,
    )
    return PriceResult(
        price=american_price,
        greeks=_tree_greeks(american_price, snapshots, time, steps),
        american_price=american_price,
        european_price=european_price,
    )


def binomial_discrete(
    spot: float,
    strike: float,
    time: float,
    rate: float,
    volatility: float,
    option_type: OptionType,
    steps: int,
    dividend_amount: float,
    dividend_time: float,
    exercise_style: ExerciseStyle,
) -> PriceResult:
    """CRR prepaid-forward tree for one known discrete cash dividend."""

    price, snapshots = _tree_price(
        spot,
        strike,
        time,
        rate,
        volatility,
        option_type,
        steps,
        exercise_style,
        dividend_amount=dividend_amount,
        dividend_time=dividend_time,
    )
    if exercise_style == "American":
        american_price = price
        european_price, _ = _tree_price(
            spot, strike, time, rate, volatility, option_type, steps, "European",
            dividend_amount=dividend_amount, dividend_time=dividend_time,
        )
    else:
        european_price = price
        american_price, _ = _tree_price(
            spot, strike, time, rate, volatility, option_type, steps, "American",
            dividend_amount=dividend_amount, dividend_time=dividend_time,
        )
    return PriceResult(
        price=price,
        greeks=_tree_greeks(price, snapshots, time, steps),
        american_price=american_price,
        european_price=european_price,
    )


def solve_implied_volatility(
    observed_price: float,
    price_function: Callable[[float], float],
    tolerance: float = 1e-8,
    max_iterations: int = 160,
) -> ImpliedVolResult:
    """Invert a pricing function using an expanding bracket and bisection."""

    if not isfinite(observed_price) or observed_price <= 0:
        raise ValueError("Observed option price must be greater than zero.")
    if not isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Tolerance must be a finite number greater than zero.")
    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool) or max_iterations < 1:
        raise ValueError("Maximum iterations must be a positive integer.")

    low = 1e-6
    high = 0.50
    maximum_volatility = 10.0

    def objective(volatility: float) -> float:
        value = price_function(volatility)
        if not isfinite(value):
            raise ValueError("The pricing model returned a non-finite value.")
        return value - observed_price

    # A CRR tree can have an invalid risk-neutral probability when volatility
    # is extremely close to zero. Move the lower bracket upward until the
    # lattice is defined; analytic models normally succeed on the first try.
    invalid_low = 0.0
    while True:
        try:
            low_value = objective(low)
            break
        except ValueError as exc:
            if "risk-neutral probability" not in str(exc) or low >= maximum_volatility:
                raise
            invalid_low = low
            low = min(low * 2.0, maximum_volatility)
    if invalid_low:
        # The geometric search can jump past the actual IV. Tighten back to the
        # first valid CRR volatility so the subsequent interval still brackets
        # every attainable solution.
        valid_low = low
        valid_low_value = low_value
        for _ in range(60):
            candidate = 0.5 * (invalid_low + valid_low)
            try:
                candidate_value = objective(candidate)
            except ValueError as exc:
                if "risk-neutral probability" not in str(exc):
                    raise
                invalid_low = candidate
            else:
                valid_low = candidate
                valid_low_value = candidate_value
        low = valid_low
        low_value = valid_low_value
    if abs(low_value) <= tolerance:
        raise ValueError(
            "Observed price is indistinguishable from the model's minimum value; "
            "a unique implied volatility cannot be inferred."
        )
    if low_value > 0:
        raise ValueError(
            "Observed price is below the model's minimum value. Check spot, strike, "
            "exercise style, dividends, and the market price."
        )

    high = max(high, min(low * 2.0, maximum_volatility))
    high_value = objective(high)
    while high_value < 0 and high < maximum_volatility:
        high = min(high * 2.0, maximum_volatility)
        high_value = objective(high)
    if high_value < 0:
        raise ValueError("No implied volatility was found below 1,000%.")

    for iteration in range(1, max_iterations + 1):
        middle = 0.5 * (low + high)
        middle_value = objective(middle)
        if abs(middle_value) <= tolerance:
            return ImpliedVolResult(
                volatility=middle,
                model_price=middle_value + observed_price,
                iterations=iteration,
            )
        if middle_value > 0:
            high = middle
        else:
            low = middle

    middle = 0.5 * (low + high)
    return ImpliedVolResult(
        volatility=middle,
        model_price=price_function(middle),
        iterations=max_iterations,
    )


def volatility_assessment(spot: float, annual_volatility: float, option_time: float):
    """Return the horizon scaling and simple-return ranges used by the workbook."""

    if not all(isfinite(value) for value in (spot, annual_volatility, option_time)):
        raise ValueError("Spot, volatility, and option time must be finite numbers.")
    if spot <= 0 or annual_volatility < 0 or option_time < 0:
        raise ValueError("Spot must be positive; volatility and option time cannot be negative.")

    horizons = [
        ("Annual", 1.0),
        ("Quarterly", 1.0 / 4.0),
        ("Monthly", 1.0 / 12.0),
        ("Weekly", 1.0 / 52.0),
        ("Daily", 1.0 / 365.0),
        ("Option horizon", option_time),
    ]
    rows = []
    for label, fraction in horizons:
        scaled = annual_volatility * sqrt(fraction)
        rows.append(
            {
                "Timeframe": label,
                "Implied volatility": scaled,
                "1σ lower": spot * (1.0 - scaled),
                "1σ upper": spot * (1.0 + scaled),
                "2σ lower": spot * (1.0 - 2.0 * scaled),
                "2σ upper": spot * (1.0 + 2.0 * scaled),
            }
        )
    return rows
