# Implied Volatility Lab

A deployable Streamlit implementation of the three calculators in
`Implied_Volatility_Calculator_IPLT.xlsm`.

## Workbook mapping

| Workbook sheet | Web implementation | Purpose |
| --- | --- | --- |
| Implied Vol - Black-Scholes | Black–Scholes | European calls/puts with optional continuous dividend yield; American calls without dividends |
| Implied Vol - Binomial (yield) | Binomial · dividend yield | American calls/puts with a continuous dividend yield |
| Implied Vol-Binomial (discrete) | Binomial · discrete dividend | American or European calls/puts with one known cash dividend before expiry |
| Summary Worksheet | Comparison workspace | Cross-asset daily, weekly, monthly, and quarterly RV/IV comparison |

The `.xlsm` contains worksheet formulas and Solver settings, but no VBA
project. The web app replaces manual Solver operation with a bounded implied
volatility root finder. The discrete-dividend sheet's intended prepaid-forward
tree is implemented directly, without its broken `#REF!` cells.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Then open `http://localhost:8501`.

The calculator runs without credentials using the workbook examples. To enable
the ticker downloader, create `.streamlit/secrets.toml`:

```toml
MARKETDATA_TOKEN = "your-token"
```

MarketData.app supplies listed-option quotes without requiring a brokerage
account. AAPL can be tested without a token; other tickers require a
MarketData.app token. Its Free Forever plan provides 100 requests per day with
delayed data. The downloader requests the expiration nearest 45 days and the
closest at-the-money call or put, uses the option-chain bid/ask midpoint, and
uses the chain's synchronized underlying price and U.S. Eastern quote time. A
separate equity quote is used only when the chain omits its underlying price.
The risk-free rate comes from the official U.S. Treasury daily par-yield XML
feed at the tenor closest to the option maturity and with no look-ahead beyond
the quote date. The downloader also requests about five years (1,261 trading
closes) of split-adjusted daily history. It calculates unannualized
close-to-close sample standard deviations from daily returns and from
period-ending weekly, monthly, and quarterly closes, then writes those RV
values to the downloaded ticker's comparison row. New downloaded tickers use
the active calculator in the comparison table's `Pricing model` column.
Dividend yield or announced cash-dividend inputs remain user-editable because
they are not included in the quote response.

## Deploy on Streamlit Community Cloud

1. Push this directory to a GitHub repository.
2. Create a Streamlit Community Cloud app for the repository.
3. Set the main file path to `app.py`.
4. Add `MARKETDATA_TOKEN` under the app's **Secrets** settings to enable
   market-data downloads for tickers other than AAPL.

The pricing calculators remain available when market-data credentials are not
configured.

## Validation

```bash
python -m pip install -r requirements-dev.txt
ruff check app.py pricing.py market_data.py tests
mypy app.py pricing.py market_data.py
pytest -q
```

The app is an educational calculator. Market data may be delayed depending on
the configured MarketData.app plan and entitlements. Its price-range output
preserves the workbook's simplifying assumptions: zero expected return,
normally distributed simple returns, and square-root-of-time scaling.
