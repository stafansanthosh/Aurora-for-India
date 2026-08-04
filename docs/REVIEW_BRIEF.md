# Adversarial review brief — IndiaAQBench

For a strong model doing a full-repo review. **Your job is to find mistakes, not
to validate work.** A review that returns "looks good" is a failed review; a
review that finds one real scientific error is worth more than twenty style
notes.

This project's headline output is a *benchmark*. Its value is entirely destroyed
by a silent methodological error — a leaked split, a miscomputed metric, a claim
the data does not support. Those are what you are hunting.

## 1. Get context first (do not skip)

Read in this order, then verify the code matches what they claim:

| File | What it tells you |
|---|---|
| `docs/AGENT_BRIEF.md` | Goal, ground rules, settled decisions, rejected paths |
| `docs/BENCHMARK_SPEC.md` | The benchmark definition — metrics, splits, cities |
| `docs/HANDOFF.md` | Current state, what is mid-flight |
| `JOURNAL.md` | Why each decision was made, in order |
| `src/splits.py` | The split contract (single source of truth) |
| `src/eval/aqi.py`, `src/eval/benchmark.py` | Metrics + scoring harness |
| `src/eval/audit.py` | The existing self-audit (39 checks) — **audit the auditor** |
| `src/data/openaq_client.py`, `archive_pull.py` | Ground-truth acquisition |
| `src/pipeline/orchestrate.py` | Aurora rollout → station samples |
| `src/model/calibrator.py` | The rejected v1 calibrator + guardrails |

Run `python -m src.eval.audit` yourself. Do not trust its PASSes — read what each
check actually asserts and look for what it *fails to* assert.

## 2. Already known — do not report these as new

Report them only if you find the stated fix is wrong or incomplete.

- **v1 calibrator collapsed the severe tail** (Very Poor+ POD 0.00, 0 of 99
  events, while MAE improved). Diagnosed, documented, kept as a negative
  baseline. **But do challenge the diagnosis if you think it is wrong.**
- **Registry-version skew**: the two Nov-2025 pilot dates used a 33-station
  registry, and three scheduled pilot dates used older registries. The 56
  scheduled dates have now been regenerated at 159 stations, while the strict
  loader still excludes the two out-of-schedule November files. Audit that
  protection rather than reporting the original skew as new.
- **OpenAQ serves nothing before ~Feb 2025** — verified at sensor level.
- **Temporal cutoff revised once** 2025-07-01 → 2025-12-01, under a
  pre-registered contingency, disclosed in spec §6 and `src/splits.py`.
- **The OpenAQ re-pull is complete** at 1,489,534 observations and 159 stations.
  Do not report the earlier partial state as current.
- **Raw OpenAQ files remain reachable in private Git history** even though they
  are not tracked at `HEAD`. Publication is still blocked on licensing and a
  clean-mirror or reviewed history decision.
- **The 56-date GPU artifact generation is complete** at 80,136 rows, but the
  four manifests are not yet merged and the post-rollout audit has not run.
  Treat the files as unaudited inputs, not final scientific results.

## 3. Where the real risk is — probe these hard

### 3a. Scientific validity (highest priority)
- **Leakage.** Can any test-period row, held-out station, or held-out city
  influence training — including through normalization stats, climatology, or
  feature engineering? `add_climatology` and `make_features` are the suspects.
- **Metric correctness.** Recompute POD/FAR/CSI and the AQI category mapping
  independently. Are boundary values (exactly 30 / 60 / 90 / 120 / 250) handled
  per CPCB? Is `event_far` denominator hits+false_alarms (correct) and not
  something else?
- **Baseline fairness.** Is persistence given a genuinely fair shot (obs at init
  carried forward)? Is climatology built from train only? Could any baseline be
  accidentally advantaged or handicapped?
- **The obs↔forecast join.** `merge_asof(direction="nearest", tolerance=90min)`
  — can this match the *wrong* hour, double-count, or bias results? What happens
  at gaps?
- **Claim vs evidence.** Go through `README.md` and `JOURNAL.md` and check every
  quantitative claim against what the code and data actually support. Flag any
  number that is not reproducible from the repo, or any claim whose sample size
  cannot support it. **Be merciless here** — overclaiming is the main reputational
  risk for a benchmark.

### 3b. Data integrity
- The **sensor-merge fix** (`find_pm25_stations` now returns all PM2.5 sensors
  per station, `fetch_city` merges them). Can merging two sensors at one station
  double-count, or average across genuinely different instruments in a way that
  corrupts the series?
- QC in `clean()`: range filter, stuck-sensor detection. Are the thresholds
  defensible? Does stuck-sensor removal delete legitimate sustained pollution
  plateaus during severe episodes (a real risk in Delhi winter)?
- Unit handling: kg/m³ → µg/m³ (1e9). Applied exactly once, everywhere?
- The resumable pull: can a partial/corrupt part file silently enter the dataset?

### 3c. Correctness of the modelling code
- `src/utils/geo.py` nearest-cell: independent-per-axis argmin. Where does that
  break, and does it matter at India's latitudes?
- `orchestrate.py`: is `valid_time` right? Is the lead-0 row genuinely the CAMS
  analysis input? Is memory bounded across the rollout?
- `calibrator.py`: is the split logic correct, and does the new no-harm event
  guardrail actually prevent the failure mode it was written for?

### 3d. Reproducibility
- Could a stranger reproduce the results table from a clean clone? What is
  missing, undocumented, or dependent on local state?
- Are random seeds fixed where they matter?

## 4. What to produce

For each finding:

1. **Severity** — Critical (invalidates results) / Major (misleads) / Minor.
2. **Location** — file and line.
3. **Why it is wrong** — the mechanism, not a vibe.
4. **How to verify** — a command or test that demonstrates it. If you cannot
   demonstrate it, label it clearly as *suspected* rather than confirmed.
5. **Proposed fix.**

Order by severity. Separate **confirmed** from **suspected**. Explicitly list
what you checked and found *clean* — that is how the reader knows your coverage.

## 5. Rules

- **Do not modify code.** This is a read-and-report pass. Running read-only
  commands and tests is expected and encouraged.
- Prefer verifying over speculating: run the check.
- If a design choice looks wrong but the journal explains why, engage with the
  stated reasoning rather than ignoring it.
- Say "I could not verify this" rather than guessing.
