# Workbook analysis

## Structure

`Implied_Volatility_Calculator_IPLT.xlsm` contains four worksheets. The first
three are the pricing/calculation panels discussed in the recording; the fourth
is a cross-asset summary.

1. **Implied Vol - Black-Scholes**
   - Intended for European calls and puts, with or without a continuous
     dividend yield.
   - Also valid for an American call on a non-dividend-paying share, because
     early exercise is not optimal under the model assumptions.
   - Inputs: spot, strike, volatility, risk-free rate, dividend yield, expiry,
     observed option price, and call/put.
   - Outputs: call and put prices, delta, theta, gamma, vega, rho, implied
     volatility, time-scaled volatility, and one-/two-standard-deviation price
     ranges.

2. **Implied Vol - Binomial (yield)**
   - A 20-step Cox–Ross–Rubinstein lattice by default.
   - Intended for American calls or puts with a continuous annual dividend
     yield.
   - Uses `u = exp(σ√Δt)`, `d = 1/u`,
     `p = (exp((r−q)Δt)−d)/(u−d)`, and early-exercise checks at every node.
   - Outputs the American option value, lattice delta/theta/gamma, implied
     volatility, scaled volatility, and price ranges.

3. **Implied Vol-Binomial (discrete)**
   - A CRR lattice for one announced cash dividend whose ex-dividend date falls
     before option expiry.
   - Supports American or European exercise and calls or puts.
   - Uses a prepaid-forward adjustment: the uncertain stock component begins at
     `S − D exp(−r t_div)`, while the remaining present value of the dividend is
     added back to pre-ex-dividend stock nodes.
   - Produces American and European model values, inferred volatility, scaled
     volatility, and price ranges.

4. **Summary Worksheet**
   - Compares close-to-close realized volatility and implied volatility for
     MSFT, GOOG, TREX, and OLLI at daily, weekly, monthly, and quarterly
     horizons.

## Solver behavior

Each calculator changes the annual volatility cell until squared error between
the model value and observed market price is minimized. The workbook relies on
Excel Solver, not VBA. Although the file has an `.xlsm` extension, it contains
no `vbaProject.bin`.

The web implementation replaces Solver with a bounded numerical inversion. It
also validates impossible inputs and model domains instead of silently
returning spreadsheet errors.

## Workbook issues found

The discrete-dividend worksheet contains five literal broken references:
`R106`, `S106`, `T140`, `U140`, and `V140`. These interrupt parts of its
American and European rollback trees. The Streamlit version implements the
intended recurrence programmatically, so those broken references are not
carried forward.

The workbook uses `TODAY()` and ACT/365 for time to expiry. Its indicative price
ranges assume zero mean simple returns and a normal distribution, scaling
annual volatility by the square root of time. The web version preserves these
conventions and labels the ranges as indicative rather than forecasts.
