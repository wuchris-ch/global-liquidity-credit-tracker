# Sample Output

Real payloads captured from the published GitHub Pages data
(`https://wuchris-ch.github.io/global-liquidity-credit-tracker/latest`) on
2026-06-11. The full artifact layout is documented in the
[README deployment section](../README.md#deployment).

## `api/glci/latest/index.json`

The headline composite index value, regime, and momentum.

```json
{
  "date": "2026-06-12",
  "value": 83.45,
  "zscore": 0.175,
  "regime": 0,
  "regime_label": "neutral",
  "momentum": 0.336
}
```

## `api/glci/pillars/index.json`

Latest pillar factor values, configured weights, and weighted contributions.

```json
{
  "date": "2026-06-12",
  "pillars": {
    "liquidity": { "value": -3.472, "weight": 0.40, "contribution": -1.389 },
    "credit":    { "value":  0.472, "weight": 0.35, "contribution":  0.165 },
    "stress":    { "value": -2.807, "weight": 0.25, "contribution": -0.702 }
  }
}
```

## `api/series/fed_total_assets/latest/index.json`

Per-series latest observation with week-over-week change.

```json
{
  "id": "fed_total_assets",
  "date": "2026-06-03",
  "value": 6711495.0,
  "change": 0.09,
  "unit": "millions_usd"
}
```

## `api/risk/sp500_price/index.json` (rolling series truncated)

Risk metrics conditioned on GLCI regime for one asset. `rolling_sharpe`
contains the full one-year rolling Sharpe history on the asset's observation
clock (252 observations for this equity, 365 for calendar-daily crypto); only
the last two points are shown here.

```json
{
  "id": "sp500_price",
  "name": "S&P 500",
  "category": "Large Cap Equities",
  "current_sharpe": 0.65,
  "annualized_return": 14.2,
  "annualized_volatility": 18.09,
  "max_drawdown": -33.92,
  "sharpe_by_regime": { "tight": 1.22, "neutral": 0.56, "loose": 0.46 },
  "return_by_regime": { "tight": 17.67, "neutral": 11.28, "loose": 16.1 },
  "correlation_with_glci": -0.101,
  "rolling_sharpe": [
    { "date": "2026-06-09", "value": 1.449 },
    { "date": "2026-06-10", "value": 1.295 }
  ]
}
```

## Regenerating

These files are rebuilt every 12 hours by the scheduled workflow. To
reproduce locally (requires a free `FRED_API_KEY`):

```bash
make update                       # fetch + compute indices
python cli.py backtest --save     # track record
make export                       # write data/export/latest
make smoke                        # validate what you just built
```
