# Calculator code audit

Audit date: 2026-08-20

## Scope and references

The audit covered every executable line in `app.py`, `pricing.py`,
`market_data.py`, and `transcript_cleanup.py`, plus all automated tests.
Requirements and formulas were checked against:

- `Implied_Volatility_Calculator_IPLT.xlsm`
- `speech.txt` and `speech_revised.txt`
- the official MarketData.app option-chain field documentation
- the official U.S. Treasury yield-curve feed and methodology

No PDF file is present in the workspace. The workbook contains a historical
link to an exchange-specification PDF, but that document does not define the
calculator formulas.

## Result

All three workbook pricing engines, the implied-volatility inversion, the
Greeks exposed by the workbook, ACT/365 date handling, volatility scaling, and
the one-/two-standard-deviation ranges are implemented. Confirmed defects found
during this audit were corrected and protected with regression tests.

## Workbook-to-code coverage

| Workbook/speech requirement | Implementation | Verification |
| --- | --- | --- |
| Black–Scholes call/put values | `black_scholes` | Benchmarks, parity, IV round trips |
| Call/put delta, theta, gamma, vega, rho | `black_scholes` | Exact workbook-convention regressions |
| American CRR tree with dividend yield | `binomial_yield` | Independent recurrence, convergence, early exercise |
| American/European cash-dividend CRR tree | `binomial_discrete` | Both styles and sides, dividend regressions |
| Prepaid-forward dividend adjustment | `_tree_price` | Formula-level comparison with the worksheet |
| Lattice delta/theta/gamma | `_tree_greeks` | Exact node-definition comparison |
| Solver-based implied volatility | `solve_implied_volatility` | Analytic/tree round trips and boundary tests |
| Manual volatility-to-price mode | Streamlit calculation mode | UI tests for all engines |
| ACT/365 maturity | App date calculation | Date and worked-example tests |
| Annual to quarter/month/week/day scaling | `volatility_assessment` | Exact square-root-of-time tests |
| Indicative 1σ/2σ price ranges | `volatility_assessment` | Exact bound tests |
| Editable comparison and ticker upsert | `upsert_comparison` and editor state | Existing/new ticker and live-update tests |
| Bid/ask midpoint market price | `_quote_price` | Bid/ask and provider-midpoint tests |
| Close-to-close realized volatility | `calculate_realized_volatility` | Daily/period-end formula and live-provider tests |

## Corrected defects

1. **Asynchronous underlying and option inputs.** The downloader used a
   separate equity endpoint for spot while pricing an option-chain snapshot.
   It now uses the chain's `underlyingPrice`, which is synchronized to that
   option quote; the stock endpoint is only a fallback.
2. **Quote-date mismatch.** Delayed quotes were initially valued on the local
   current date. The option snapshot's U.S. Eastern market date now becomes the
   valuation date.
3. **Treasury look-ahead.** A Treasury observation later than the quote date
   could be selected. The rate is now the latest observation on or before the
   valuation date.
4. **Timestamp labeling.** Provider timestamps were labeled UTC despite the
   provider's U.S. market-time convention. They are now converted and displayed
   in `America/New_York` time.
5. **Incomplete midpoint handling.** A valid provider `mid` value was ignored
   when usable bid/ask fields were absent. It is now used before falling back to
   the last trade.
6. **Zero Treasury rates.** A valid 0.00% observation was treated as missing.
   Treasury parsing now permits zero while price fields remain strictly
   positive.
7. **IV solver upper bound.** Expansion could evaluate and return a volatility
   over the documented 1,000% limit. Expansion is now capped exactly at 1,000%.
8. **IV solver CRR bracket.** If low volatilities generated invalid CRR
   probabilities above the initial 50% bracket, a valid higher-volatility root
   was missed. The domain boundary is now located before bisection.
9. **Non-unique minimum-price IV.** A market price numerically equal to the
   model's minimum returned an arbitrary near-zero IV. It now reports that a
   unique IV cannot be inferred.
10. **Stale comparison values.** Streamlit editor state could repaint an old
    MSFT row after recalculation. Fresh calculation state now clears only the
    stale editor overlay.
11. **Ambiguous comparison metadata.** The workbook's `Class` and `Notes`
    fields did not identify which calculator produced each IV result. They have
    been replaced by a `Pricing model` column that updates on recalculation.
12. **Stale download status.** A failed ticker request could leave the prior
    ticker's success caption visible. The previous status is cleared before a
    new request.
13. **Transcript cleanup instability.** Reprocessing could produce
    `forward-forward-looking`, and several worked-example numbers remained
    mistranscribed. Cleanup is now idempotent for that term and preserves the
    verified 1.05%, 0.09%, and $8.70 values.
14. **Local secret permissions.** `.streamlit/secrets.toml` was readable by
    other local users. Its permissions are now owner-only (`0600`), and the file
    remains excluded by `.gitignore`.
15. **Downloaded RV left blank.** Only MSFT had the static RV values copied
    from the workbook. Downloads now retrieve about five years of split-adjusted
    closes, calculate daily/weekly/monthly/quarterly close-to-close RV, and
    insert or refresh all four RV columns for that ticker.
16. **Pricing model stored under an ambiguous heading.** New rows wrote values
    such as `Binomial · dividend yield` into `Class`. The comparison schema now
    names this field `Pricing model`, removes `Class` and `Notes`, and migrates
    existing sessions without resetting their calculated rows.

## Independently verified current MSFT result

The synchronized option-chain snapshot returned:

- spot at the option snapshot: $480.58
- strike: $480.00
- call midpoint: $19.10
- quote time: 2026-08-17 16:00 EDT
- expiry: 2026-10-02 (46 calendar days)
- Treasury proxy: 3.80%
- dividend yield input: 1.05%
- CRR steps: 20

An independent CRR implementation gives 26.752664% and reprices the call to
$19.10000000. The production calculator gives the same value within numerical
tolerance.

The previously reported 25.778599% used a $481.63 spot from a separate, later
equity quote. Its mathematics was correct for those inputs, but the inputs were
not time-aligned with the $19.10 option snapshot.

The historical-price adapter was also checked against a live MSFT daily-candle
response through 2026-08-17. It returned 1,261 valid closes through 2026-08-14
and produced finite RV values at all four comparison horizons.

## Reference limitations retained intentionally

- The workbook and speech use a quoted short-term Treasury CMT directly as a
  risk-free proxy. CMT is a bond-equivalent par yield, not a zero-coupon
  continuously compounded rate. The app preserves the workbook convention.
- Volatility ranges preserve the workbook's zero-mean, normally distributed
  simple-return approximation and can produce negative lower bounds at very
  high volatility.
- The discrete-dividend engine supports one announced cash dividend, matching
  the worksheet.
- The workbook's discrete-dividend sheet contains five literal `#REF!` cells.
  The application implements the intended recurrence instead of those broken
  references.
- Downloaded quotes may be delayed according to the configured data plan.

## Verification commands

```bash
python -m pytest -q
python -m ruff check .
python -m mypy pricing.py market_data.py app.py transcript_cleanup.py
python -m compileall -q app.py pricing.py market_data.py transcript_cleanup.py tests
```
