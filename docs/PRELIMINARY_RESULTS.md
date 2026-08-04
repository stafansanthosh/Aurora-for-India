# Preliminary retrospective results

**Run date:** 2026-08-04
**Registry:** `159:4c0b55ad238f`
**Forecast dates:** 56 frozen initializations
**Status:** preliminary retrospective evidence; 24-hour headline and hourly sensitivity separated

These are the first results from the complete 159-station Aurora rollout. The
headline path applies CPCB thresholds to forward 24-hour station means. A
separate section retains the instantaneous/hourly-threshold sensitivity
analysis; the two populations are never pooled.

The full audit still reports one failure: 463 of 80,730 stored rows violate
`PM1 <= PM2.5 <= PM10`. Raw Aurora, persistence, CAMS, and Component A consume
only PM2.5, so their values below are unaffected by those auxiliary channels.
PM1 and PM10 were removed from the calibrator before its full-registry fit. The
audit failure remains visible and is not reclassified or waived.

## Forward-24-hour headline

Forecast windows use the predeclared trapezoidal approximation
`(value_s + 2*value_s+12 + value_s+24) / 4` for starts from 0 through +72
hours. Observed targets average the corresponding 24 hourly observations and
require at least 12 available hours. Windows crossing the temporal cutoff are
excluded. The evaluator built 62,010 station windows, of which 51,566 meet the
observation-coverage rule.

| Scope and method | Matched windows | MAE | POD | FAR | CSI | Events |
|---|---:|---:|---:|---:|---:|---:|
| Pooled test — Persistence | 22,767 | 21.59 | 0.466 | 0.371 | 0.365 | 1,682 |
| Pooled test — Actual CAMS | 23,422 | 31.85 | 0.154 | 0.911 | 0.060 | 1,704 |
| Pooled test — Raw Aurora | 23,422 | 28.22 | 0.471 | 0.672 | 0.239 | 1,704 |
| Pooled test — Component A | 23,422 | 21.26 | 0.582 | 0.441 | 0.399 | 1,704 |
| L1 — Raw Aurora | 3,018 | 28.90 | 0.400 | 0.569 | 0.262 | 275 |
| L1 — Component A | 3,018 | 21.11 | 0.578 | 0.236 | 0.491 | 275 |
| L2 — Raw Aurora | 3,483 | 30.22 | 0.798 | 0.874 | 0.122 | 94 |
| L2 — Component A | 3,483 | 21.31 | 0.755 | 0.801 | 0.187 | 94 |

Component A improves L1 POD at every 24-hour window start and materially
improves CSI. However, pooled L2 POD falls from 0.798 to 0.755. Under the
no-harm rule it remains **uncertified**; raw Aurora is the safe public fallback.

## Instantaneous/hourly-threshold sensitivity

### Pooled temporal test

| Method | Matched rows | MAE | POD | FAR | CSI | Observed events |
|---|---:|---:|---:|---:|---:|---:|
| Persistence | 26,135 | 24.54 | 0.369 | 0.489 | 0.273 | 2,075 |
| CAMS lead-zero fixed | 26,953 | 42.79 | 0.123 | 0.936 | 0.044 | 2,113 |
| Actual CAMS forecast | 26,953 | 35.29 | 0.236 | 0.863 | 0.095 | 2,113 |
| Raw Aurora | 26,953 | 32.76 | 0.483 | 0.721 | 0.215 | 2,113 |
| Component A | 26,953 | 26.52 | 0.566 | 0.585 | 0.315 | 2,113 |

Climatology is omitted from this compact comparison because its missing-support
pattern leaves only 16,245 matched rows and 543 observed events; it must not be
compared as if it used the same sample. Its available-row MAE is 21.21.

### L1 — held-out stations in seen cities

| Method | Matched rows | MAE | POD | FAR | CSI | Observed events |
|---|---:|---:|---:|---:|---:|---:|
| Persistence | 3,373 | 24.28 | 0.414 | 0.436 | 0.314 | 319 |
| Actual CAMS forecast | 3,474 | 37.77 | 0.218 | 0.836 | 0.103 | 321 |
| Raw Aurora | 3,474 | 33.87 | 0.474 | 0.669 | 0.242 | 321 |
| Component A | 3,474 | 26.85 | 0.579 | 0.519 | 0.356 | 321 |

Component A improves the pooled L1 result, but its +84-hour POD is 0.688 versus
raw Aurora's 0.750 across 64 observed events. Because event skill is required
per lead, Component A is **not certified as the public correction** in its
current form.

### L2 — held-out-city transfer with trailing local observations

| Method | Matched rows | MAE | POD | FAR | CSI | Observed events |
|---|---:|---:|---:|---:|---:|---:|
| Persistence | 3,970 | 18.43 | 0.234 | 0.659 | 0.161 | 124 |
| Actual CAMS forecast | 4,014 | 23.27 | 0.551 | 0.778 | 0.188 | 127 |
| Raw Aurora | 4,014 | 34.23 | 0.748 | 0.859 | 0.134 | 127 |
| Component A | 4,014 | 25.58 | 0.756 | 0.776 | 0.209 | 127 |

Component A uses observations available before initialization at the target
station. This is not zero-shot city transfer. The correct label is
**held-out-city transfer with trailing local observations**.

## Calibrator decision

The pooled direct-target calibrator was refit after removing PM1 and PM10 from
its features. It again improved MAE but failed the Very Poor+ no-harm gate:

| Scope | Raw MAE | Calibrated MAE | Raw POD | Calibrated POD |
|---|---:|---:|---:|---:|
| L1 | 33.9 | 24.5 | 0.474 | 0.125 |
| L2 | 34.2 | 20.2 | 0.748 | 0.299 |

The guardrail refused to save an accepted model. The earlier binary is retained
only as `results/models/rejected_pilot_calibrator.joblib`; no accepted
calibrator artifact exists.

## What these results support

- Aurora adds substantial event detection over the actual CAMS forecast, but
  produces many false alarms, especially in L2 cities.
- Persistence remains a strong MAE and FAR baseline and cannot be treated as a
  token comparator.
- Component A is promising and materially improves pooled CSI, but needs a
  lead-specific safety rule or revised configuration before public selection.
- The direct-target tree calibrator remains rejected; its failure persists
  after removing the inconsistent auxiliary particulate channels.

These results do not establish year-round utility, do not include an
independent post-monsoon test, and are not an operational forecast claim.
