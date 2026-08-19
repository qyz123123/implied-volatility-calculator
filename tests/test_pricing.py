from math import isclose, nan

import pytest

from pricing import (
    binomial_discrete,
    binomial_yield,
    black_scholes,
    solve_implied_volatility,
    volatility_assessment,
)


def test_black_scholes_known_values_and_parity():
    call = black_scholes(100, 100, 1, 0.05, 0.02, 0.20, "Call")
    put = black_scholes(100, 100, 1, 0.05, 0.02, 0.20, "Put")
    assert isclose(call.price, 9.227006, rel_tol=0, abs_tol=1e-6)
    assert isclose(put.price, 6.330081, rel_tol=0, abs_tol=1e-6)
    assert isclose(call.call_price, call.price, abs_tol=1e-12)
    assert isclose(call.put_price, put.price, abs_tol=1e-12)
    assert call.call_greeks == call.greeks
    assert put.put_greeks == put.greeks
    assert call.call_greeks is not None and call.put_greeks is not None


def test_black_scholes_workbook_greeks():
    call = black_scholes(100, 100, 1, 0.05, 0.02, 0.20, "Call")
    put = black_scholes(100, 100, 1, 0.05, 0.02, 0.20, "Put")
    assert isclose(call.greeks.delta, 0.5868511461, abs_tol=1e-10)
    assert isclose(put.greeks.delta, -0.3933475272, abs_tol=1e-10)
    assert isclose(call.greeks.gamma, 0.0189505788, abs_tol=1e-10)
    assert isclose(call.greeks.theta, -0.0139433395, abs_tol=1e-10)
    assert isclose(put.greeks.theta, -0.0062837511, abs_tol=1e-10)
    assert isclose(call.greeks.vega, 0.3790115751, abs_tol=1e-10)
    assert isclose(call.greeks.rho, 0.4945810911, abs_tol=1e-10)
    assert isclose(put.greeks.rho, -0.4566483334, abs_tol=1e-10)


def test_black_scholes_implied_vol_round_trip():
    target = black_scholes(125, 120, 0.4, 0.03, 0.01, 0.37, "Put").price
    solved = solve_implied_volatility(
        target, lambda vol: black_scholes(125, 120, 0.4, 0.03, 0.01, vol, "Put").price
    )
    assert isclose(solved.volatility, 0.37, rel_tol=0, abs_tol=1e-7)
    assert isclose(solved.model_price, target, rel_tol=0, abs_tol=1e-7)


def test_american_call_without_dividend_converges_to_black_scholes():
    analytic = black_scholes(100, 100, 1, 0.05, 0.0, 0.20, "Call").price
    tree = binomial_yield(100, 100, 1, 0.05, 0.0, 0.20, "Call", 500).price
    assert isclose(tree, analytic, rel_tol=0, abs_tol=0.01)


def test_yield_tree_exposes_workbook_american_and_european_prices():
    result = binomial_yield(90, 100, 1, 0.05, 0.02, 0.25, "Put", 300)
    assert result.american_price == result.price
    assert result.european_price is not None
    assert result.american_price >= result.european_price


def test_american_put_is_not_below_european_put():
    european = black_scholes(90, 100, 1, 0.05, 0.0, 0.25, "Put").price
    american = binomial_yield(90, 100, 1, 0.05, 0.0, 0.25, "Put", 500).price
    assert american >= european


def test_binomial_implied_vol_round_trip_skips_invalid_low_volatility():
    target = binomial_yield(100, 100, 0.15, 0.04, 0.01, 0.32, "Call", 100).price
    solved = solve_implied_volatility(
        target, lambda vol: binomial_yield(100, 100, 0.15, 0.04, 0.01, vol, "Call", 100).price
    )
    assert isclose(solved.volatility, 0.32, rel_tol=0, abs_tol=1e-6)


def test_binomial_solver_can_bracket_above_initial_high_volatility():
    def price_function(vol):
        return binomial_yield(100, 100, 1, 2.0, 0.0, vol, "Call", 2).price

    target = price_function(2.0)
    solved = solve_implied_volatility(target, price_function)
    assert isclose(solved.volatility, 2.0, rel_tol=0, abs_tol=1e-7)


def test_workbook_microsoft_example_reproduces_reported_iv():
    solved = solve_implied_volatility(
        8.70,
        lambda vol: binomial_yield(
            215.29, 215.0, 48 / 365, 0.0009, 0.0105, vol, "Call", 20
        ).price,
    )
    assert isclose(solved.volatility, 0.2814, rel_tol=0, abs_tol=5e-5)


def test_marketdata_microsoft_example_matches_independent_crr_calculation():
    solved = solve_implied_volatility(
        19.10,
        lambda vol: binomial_yield(
            480.58, 480.0, 46 / 365, 0.0380, 0.0105, vol, "Call", 20
        ).price,
    )
    assert isclose(solved.volatility, 0.267526638924, rel_tol=0, abs_tol=5e-9)
    assert isclose(solved.model_price, 19.10, rel_tol=0, abs_tol=2e-7)


@pytest.mark.parametrize(
    ("asset", "spot", "strike", "market_price", "expected_iv"),
    [
        ("GOOG", 1793.0, 1795.0, 69.50, 0.2742148354574256),
        ("TREX", 74.64, 75.0, 4.35, 0.4227513771378329),
        ("OLLI", 91.49, 92.5, 6.70, 0.5467547583913734),
    ],
)
def test_speech_black_scholes_examples(asset, spot, strike, market_price, expected_iv):
    del asset  # Included to make failures identify the worked example.
    solved = solve_implied_volatility(
        market_price,
        lambda vol: black_scholes(
            spot, strike, 47 / 365, 0.0009, 0.0, vol, "Call"
        ).price,
    )
    assert isclose(solved.volatility, expected_iv, rel_tol=0, abs_tol=5e-8)


def test_discrete_dividend_american_value_not_below_european():
    american = binomial_discrete(100, 95, 0.5, 0.03, 0.30, "Call", 300, 2.0, 0.2, "American")
    assert american.european_price is not None
    assert american.price >= american.european_price


def test_discrete_dividend_exposes_both_prices_for_european_selection():
    result = binomial_discrete(
        100, 95, 0.5, 0.03, 0.30, "Call", 300, 2.0, 0.2, "European"
    )
    assert result.european_price == result.price
    assert result.american_price is not None
    assert result.american_price >= result.european_price


def test_zero_discrete_dividend_matches_continuous_zero_yield_tree():
    discrete = binomial_discrete(
        100, 105, 0.5, 0.03, 0.25, "Put", 200, 0.0, 0.2, "American"
    )
    yield_tree = binomial_yield(100, 105, 0.5, 0.03, 0.0, 0.25, "Put", 200)
    assert isclose(discrete.price, yield_tree.price, abs_tol=1e-12)
    assert isclose(discrete.european_price, yield_tree.european_price, abs_tol=1e-12)


@pytest.mark.parametrize("option_type", ["Call", "Put"])
@pytest.mark.parametrize("exercise_style", ["American", "European"])
def test_discrete_dividend_implied_vol_round_trip(option_type, exercise_style):
    expected_volatility = 0.41
    target = binomial_discrete(
        80, 85, 0.35, 0.02, expected_volatility, option_type, 100, 0.75, 0.12,
        exercise_style,
    ).price
    solved = solve_implied_volatility(
        target,
        lambda vol: binomial_discrete(
            80, 85, 0.35, 0.02, vol, option_type, 100, 0.75, 0.12,
            exercise_style,
        ).price,
    )
    assert isclose(solved.volatility, expected_volatility, abs_tol=1e-6)


def test_tree_prices_respect_intrinsic_value_and_volatility_monotonicity():
    volatilities = [0.10, 0.20, 0.40, 0.80]
    results = [
        binomial_yield(90, 100, 0.75, 0.04, 0.01, vol, "Put", 200)
        for vol in volatilities
    ]
    prices = [result.price for result in results]
    assert prices == sorted(prices)
    assert all(result.price >= 10.0 for result in results)
    assert all(result.american_price >= result.european_price for result in results)


def test_workbook_horizon_scaling():
    rows = volatility_assessment(100, 0.30, 48 / 365)
    values = {row["Timeframe"]: row["Implied volatility"] for row in rows}
    assert isclose(values["Quarterly"], 0.15)
    assert isclose(values["Monthly"], 0.30 / (12**0.5))
    assert isclose(values["Option horizon"], 0.30 * ((48 / 365) ** 0.5))
    annual = rows[0]
    assert annual["1σ lower"] == 70
    assert annual["1σ upper"] == 130
    assert annual["2σ lower"] == 40
    assert annual["2σ upper"] == 160


@pytest.mark.parametrize(
    "function",
    [
        lambda: black_scholes(100, 100, 1, 0.05, 0.0, 0.2, "Invalid"),
        lambda: black_scholes(nan, 100, 1, 0.05, 0.0, 0.2, "Call"),
        lambda: binomial_yield(100, 100, 1, nan, 0.0, 0.2, "Call", 20),
        lambda: binomial_yield(100, 100, 1, 0.05, 0.0, 0.2, "Invalid", 20),
        lambda: binomial_yield(100, 100, 1, 0.05, 0.0, 0.2, "Call", True),
        lambda: binomial_discrete(100, 100, 1, 0.05, 0.2, "Call", 20, 1, 0.5, "Invalid"),
        lambda: binomial_discrete(100, 100, 1, 0.05, 0.2, "Call", 20, 1, 2, "American"),
        lambda: volatility_assessment(100, -0.2, 1),
    ],
)
def test_invalid_model_inputs_are_rejected(function):
    with pytest.raises(ValueError):
        function()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"observed_price": nan},
        {"observed_price": 10, "tolerance": 0},
        {"observed_price": 10, "max_iterations": 0},
    ],
)
def test_invalid_solver_controls_are_rejected(kwargs):
    with pytest.raises(ValueError):
        solve_implied_volatility(price_function=lambda vol: vol, **kwargs)


def test_solver_rejects_prices_outside_model_range():
    with pytest.raises(ValueError, match="below the model's minimum"):
        solve_implied_volatility(
            1.0, lambda vol: black_scholes(120, 100, 1, 0.0, 0.0, vol, "Call").price
        )
    with pytest.raises(ValueError, match="No implied volatility"):
        solve_implied_volatility(
            101.0, lambda vol: black_scholes(100, 100, 1, 0.0, 0.0, vol, "Call").price
        )

    minimum = black_scholes(120, 100, 1, 0.0, 0.0, 1e-6, "Call").price
    with pytest.raises(ValueError, match="unique implied volatility"):
        solve_implied_volatility(
            minimum,
            lambda vol: black_scholes(120, 100, 1, 0.0, 0.0, vol, "Call").price,
        )


def test_solver_does_not_return_volatility_above_documented_limit():
    with pytest.raises(ValueError, match="below 1,000%"):
        solve_implied_volatility(12.0, lambda volatility: volatility)
