# Market Flows and Sector Rotation

This feature publishes three separate evidence layers for the 11 Select Sector
SPDR ETFs: a price-based rotation rank, sponsor-reported ETF net issuance, and
OCC cleared options activity. Only the price layer determines the rank. Fund
issuance and options activity are displayed as context and cannot silently
change it.

Research and source checks in this document were completed on **2026-07-14**.
The output is labelled `descriptive_not_backtested`; leaders, laggards,
improving sectors, inflows, and unusual options activity are observations, not
trade recommendations or verified market tops and bottoms.

**Code:** [`src/indicators/sector_rotation.py`](../src/indicators/sector_rotation.py),
[`src/data_sources/state_street.py`](../src/data_sources/state_street.py), and
[`src/data_sources/occ.py`](../src/data_sources/occ.py)

## Evidence layers and labels

| Layer | What it measures | Product label | Changes the rank? |
|-------|------------------|---------------|-------------------|
| Price rotation | Relative and risk-adjusted ETF performance | Price leadership | Yes |
| ETF net issuance | Split-adjusted change in sponsor-reported shares outstanding | Estimated net issuance | No |
| Options activity | OCC-cleared call and put contract volume | Cleared options activity | No |

The universe is XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, and XLY,
with SPY as the price benchmark. This is a consistent, single-sponsor view of
S&P 500 sectors. It is not a complete measure of every US sector ETF or every
investor's sector exposure.

## ETF net issuance

State Street publishes daily NAV, shares outstanding, and total net assets in
its official NAV-history workbooks. The [XLC product page](https://www.ssga.com/us/en/intermediary/etfs/state-street-communication-services-select-sector-spdr-etf-xlc)
links the sponsor's NAV history, holdings, and fund information. The client
uses the corresponding workbook URL for each ticker; an
[XLC workbook](https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-xlc.xlsx)
is a direct example.

For ETF `i` on session `t`, let `Q` be shares outstanding, `N` be NAV per
share, and `S` be the share-split factor effective on that session. `S = 1`
when no split occurs. Estimated net issuance is:

```text
issuance_usd_i,t = (Q_i,t - S_i,t * Q_i,t-1) * N_i,t
```

A positive value is estimated net creation; a negative value is estimated net
redemption. The adjustment is essential because an unadjusted 2-for-1 split
would resemble a fund-sized creation. The current split table recognizes
2-for-1 adjustments visible in the sponsor histories on 2025-12-05 for XLB,
XLE, XLK, XLU, and XLY. Any other split-like inverse jump in NAV and shares
fails closed until it is reviewed and added explicitly.

The pipeline validates that `NAV * shares outstanding` reconciles to total net
assets and independently checks the issuance estimate against the change in
total net assets after the split-adjusted NAV return. It publishes:

```text
flow_1d_usd       = issuance_usd
flow_5d_usd       = sum of daily issuance over 5 sessions
flow_20d_usd      = sum of daily issuance over 20 sessions
flow_5d_pct_aum   = flow_5d_usd / AUM from 5 sessions earlier
flow_20d_pct_aum  = flow_20d_usd / AUM from 20 sessions earlier
```

The 20-session percentage is also standardized against its own prior 252
observations. The current observation is excluded from the reference window:

```text
flow_20d_z_t = (x_t - median(x_t-252 ... x_t-1))
               / (1.4826 * MAD(x_t-252 ... x_t-1))
```

The result is clipped to `[-3, 3]` and remains null when 252 prior observations
or non-zero robust dispersion are unavailable.

### Issuance limitations

- Net issuance estimates primary-market creations and redemptions. ETF
  creations can be in kind, so it is not literal cash transferred into or out
  of the underlying companies.
- Secondary-market ETF volume and price times volume are not fund flow and are
  not used in this calculation.
- The sponsor workbooks are current-vintage files and may be revised. They do
  not reconstruct exactly what was available to an investor on every past
  date.
- The measure covers the Select Sector SPDR family, not the full sector ETF
  industry.

## Price-based sector rotation

Price ranking uses complete adjusted-close histories from Yahoo Finance via
`yfinance` for SPY and all 11 sectors, aligned to their latest common session.
It fails closed if the complete cross-section or sufficient history is
unavailable. Sponsor NAV is not a price fallback because NAV history is not a
dividend-adjusted total-return series.

Let `P_i,t` be the adjusted close for sector `i`, `P_m,t` the SPY adjusted
close, and `h` a trading-session horizon:

```text
r_i,h  = ln(P_i,t / P_i,t-h)
rs_i,h = r_i,h - r_SPY,h

relative_strength_i = 0.5 * rs_i,63 + 0.5 * rs_i,126
acceleration_i      = rs_i,21 - rs_i,63 / 3
absolute_trend_i    = r_i,126 / (sigma_i,63 * sqrt(126))
```

`sigma_i,63` is the sample standard deviation of daily log returns over the
latest 63 sessions. Relative strength and absolute trend are each converted
to cross-sectional percentile ranks across the 11 sectors:

```text
price_score_i = 0.65 * percentile(relative_strength_i)
              + 0.35 * percentile(absolute_trend_i)
```

The score is descriptive and ranges from 0 to 100. Fund issuance, options
activity, the 200-session moving-average flag, and the GLCI regime do not enter
it. Keeping those layers separate prevents an unvalidated auxiliary input from
changing the ordering.

The rotation phase is a sign map, not a forecast:

| Relative strength | Acceleration | Phase |
|-------------------|--------------|-------|
| Non-negative | Non-negative | `leading` |
| Non-negative | Negative | `weakening` |
| Negative | Non-negative | `improving` |
| Negative | Negative | `lagging` |

The opportunity lists expose the three highest price scores, three lowest
price scores, up to three improving sectors, strongest 20-session issuance
z-scores, and highest options activity ratios. "Leading" and "lagging" are
cross-sectional descriptions. They do not establish an overbought top, a
washout bottom, or a profitable rotation rule.

### Price-source limitation

The [`yfinance` project](https://ranaroussi.github.io/yfinance/) states that it
is not affiliated with or vetted by Yahoo, uses publicly available Yahoo APIs,
is intended for research and education, and directs users to Yahoo's terms for
rights to downloaded data. Its README also describes the Yahoo Finance API as
intended for personal use. The tracker therefore treats this as a best-effort
research source, not a licensed redistribution feed. Usage rights must be
reviewed before commercial use or redistribution.

The implementation was exercised with `yfinance` 1.3.0 on 2026-07-14. The
dependency is constrained to the 1.x line because its download shape is part
of this source contract.

## OCC cleared options activity

The options layer uses OCC's no-key
[Volume Query](https://marketdata.theocc.com/volume-query) according to the
official [batch-processing parameters](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/volume-query-batch-processing).
It requests weekly and monthly reports by underlying for ETF stock options,
both calls and puts, and all account types.

The OCC response reports account-side quantities. For each standard ETF root,
the pipeline sums the account-side call or put quantity and divides by two so
one cleared contract is not counted once for each side. Adjusted option roots
are excluded and disclosed separately. It publishes:

```text
put_call_ratio = cleared put contracts / cleared call contracts

activity_ratio = latest completed week's contracts per session
                 / prior calendar month's contracts per session
```

A null put/call ratio is reported when call volume is zero. Missing or partial
OCC data does not alter the price score.

### Why this is activity, not directional options flow

OCC volume shows how many contracts cleared and whether they were calls or
puts. It does not identify the aggressing buyer, trade direction, or whether a
position was opened or closed. A purchased put, written put, spread leg, and
hedge can have very different implications but all contribute to volume.
Calling the result bullish or bearish premium flow would overstate the data.

Cboe's licensed
[Open-Close Volume Summary](https://datashop.cboe.com/cboe-options-open-close-volume-summary)
does classify Cboe-exchange trades by participant type, buy/sell action, and
open/close position. The page checked on 2026-07-14 describes the data as Cboe
proprietary, licenses raw data for internal use, and requires additional fees
and approval for external distribution of derived data. It is not ingested by
this project, and it would cover Cboe exchanges rather than prove aggressor
direction across the full consolidated US options market.

## Timing, status, and failure policy

Price, fund, and options evidence retain separate `as_of` dates. A fresh price
rank must not make older sponsor or OCC observations appear contemporaneous.
The price and fund universes must contain all 11 sectors. The computation
records partial or unavailable OCC coverage with per-ticker errors because it
is a separate context layer. The scheduled production export is stricter: it
rejects the new payload unless all 11 options summaries are present, leaving
the prior published artifact in place.

The current status is `descriptive_not_backtested`. A predictive label would
require point-in-time source vintages, next-session or next-week execution,
transaction costs, comparison with simple momentum baselines, parameter
sensitivity, and out-of-sample evidence with the repository's existing
multiple-testing controls. Until then, the feature supports monitoring and
hypothesis formation only.

Offline checks in
[`tests/test_sector_rotation.py`](../tests/test_sector_rotation.py) cover the
State Street workbook parser, OCC aggregation and adjusted-root exclusion,
known and unknown split behavior, exclusion of the current observation from
the robust z-score history, complete 11-sector ranking, and independence of
the price score from fund and options evidence.

## Open-source reference projects

The following repositories were reviewed on 2026-07-14. They informed design
patterns only and are not dependencies of this feature.

- [OpenBB](https://github.com/OpenBB-finance/OpenBB): its README describes an
  integration layer for proprietary, licensed, and public providers that can
  expose data to Python, APIs, and other surfaces. The tracker's design
  takeaway is to keep provider adapters, stable output schemas, and provenance
  separate from indicator logic.
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean): its README
  describes a modular, event-driven engine for research, backtesting, and live
  trading. The tracker's design takeaway is to keep data acquisition,
  indicators, and reproducible evaluation as separate concerns.

This was a README-level architecture survey, not a code audit or benchmark. It
does not claim that either project implements the same sector-flow methodology
or validates this tracker's signals.
