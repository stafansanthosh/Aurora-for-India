# IndiaAQBench

**IndiaAQBench is an attempt to build advance warning of dangerous air-pollution episodes in Indian cities, and a benchmark strict enough to tell whether it works. The main finding so far: Microsoft's Aurora model, without local correction, was not reliable enough for a public warning service.**

The completed work is a nine-city evaluation system and a set of findings about where forecasts succeed and fail. The most useful signal turned out to come not from a bigger pollution model but from cheap, widely available inputs — recent station readings plus a free weather forecast — which is what the next stage tests before any live service.

**On city focus.** Delhi is the diagnostic environment, not the target: it has the most stations and supplies 89.1% of the benchmark's events, which makes it the place to debug a method. The intended beneficiaries are smaller Indo-Gangetic cities such as Patna, Lucknow, Kanpur and Varanasi. The project began by assuming those cities had no multi-day forecast; [that assumption was wrong and was retired](docs/TARGET_REEVALUATION.md). What survives is narrower and about cost, not absence: the method that works here needs a few monitors and a free weather feed, not a GPU or a national chemistry model.

## What the project found

The benchmark focuses on **PM2.5**: fine particles suspended in the air. An event means the average concentration over a 24-hour period reaches **121 micrograms per cubic metre (µg/m³) or more**, the benchmark's threshold for “Very Poor” or worse pollution.

Three approaches are compared below:

- **CAMS:** the Copernicus Atmosphere Monitoring Service's global air-pollution forecast, used as an existing forecast to compare against.
- **Aurora:** Microsoft's AI model for atmospheric forecasting, run here without a local correction.
- **Aurora with a local correction:** adjust Aurora using recent pollution readings at each station. The code calls this method **Component A**; it is a simple adjustment, not a separately trained Aurora model.

The following results use later dates kept separate from the training period—the **temporal test set**.

| Forecast | Events caught: POD ↑ | False-alarm ratio: FAR ↓ | Overall event score: CSI ↑ |
|---|---:|---:|---:|
| CAMS | 0.154 | 0.911 | 0.060 |
| Aurora without correction | 0.471 | 0.672 | 0.239 |
| Aurora with local correction | 0.582 | 0.441 | 0.399 |

**POD** is the fraction of observed events caught. **FAR** is the fraction of predicted events that did not happen. **CSI** combines both errors: hits divided by hits + misses + false alarms.

Put plainly, Aurora caught about **47%** of event windows, but about **67%** of its event predictions were false alarms. The local correction improved those figures to **58% caught** and **44% false alarms**. Substantial misses and false alarms remain.

These are forward-24-hour results pooled across **1,704 observed station–forecast event windows**, extending out to four days ahead. Windows overlap, so this is not a count of independent citywide pollution episodes. **Delhi supplies 89.1% of events across the full benchmark**, making it especially important to inspect individual cities.

The local correction is **not approved for public warning use**. Despite its pooled improvement, detection falls in cities excluded from model fitting, and one forecast lead worsens in the separate hourly evaluation. Details and counts appear below.

**Split disclosure:** the training/test cutoff was revised once, from 2025-07-01 to 2025-12-01, under a pre-registered contingency before adaptation was trained on the revised split. The original training period lacked adequate severe-season coverage.

## What I built

The evaluation uses **1,489,534 OpenAQ observations from 159 stations across nine cities**, with forecasts starting on **56 dates: 32 training dates and 24 test dates**. OpenAQ provides access to readings from ground-level pollution monitors.

The pipeline:

1. **Collect and check observations.** Download station readings, handle duplicates and missing data, and verify station identities and coordinates.
2. **Generate and collect forecasts.** Run Aurora and obtain actual CAMS forecasts for the same dates. Also compare against simple alternatives: carrying forward a recent reading, or using a historical seasonal average.
3. **Match predictions to observations.** Sample forecasts at station locations and compare the same places and time periods.
4. **Test beyond the fitting data.** Separate earlier from later dates, reserve some stations within familiar cities, and exclude entire cities from model fitting.
5. **Check the evaluation itself.** Run an integrity audit, prevent future observations from entering corrections, report event counts, and retain requests, file checksums, and execution records so results can be traced to their inputs.

The cities are Bangalore, Chennai, Delhi, Lucknow, Mumbai, Patna, Kanpur, Kolkata, and Varanasi. The last three are excluded from ordinary fitting. The local correction can still use earlier readings at those stations: it tests adaptation with local observations, not forecasting a new city without any local information.

Separate evaluators score **24-hour averages** (the headline) and **individual hours** (a timing sensitivity check). The [benchmark specification](docs/BENCHMARK_SPEC.md) explains the design; [src/splits.py](src/splits.py) defines the data partitions.

### Why test Aurora this way?

Microsoft's [original Aurora paper, *A foundation model for the Earth system*](https://www.nature.com/articles/s41586-025-09005-y), demonstrates global forecasting, including air-pollution examples in East Asia. Its pollution model is trained on CAMS analysis and reanalysis—estimates of atmospheric conditions—and largely evaluated against CAMS analysis. The [official repository](https://github.com/microsoft/aurora) provides the model implementation.

IndiaAQBench asks a complementary question: **how do these forecasts perform against actual Indian surface stations when the priority is catching dangerous episodes, rather than minimizing average error across a global grid?**

## What failed, and why the approach changed

I also tested a learned correction that predicted the pollution concentration directly. It made the average error smaller while missing far more dangerous events.

For stations excluded from fitting within familiar cities, mean absolute error improved from **33.9 to 24.5 µg/m³**, but event detection fell from **47.4% to 12.5%**. In entirely excluded cities, error improved from **34.2 to 20.2**, while detection fell from **74.8% to 29.9%**. These are hourly evaluation results, not the 24-hour table above.

The automatic acceptance check rejected that correction. This was a failure of the tested approach, not a claim that reducing average error always harms warnings. It showed why average accuracy alone was the wrong success criterion here.

The [subsequent investigation](docs/EPISODE_SKILL_DIAGNOSIS.md) led to a different question: **instead of predicting an exact concentration, can a model estimate the chance that the next 24 hours will cross the dangerous-pollution threshold?**

## Two experiments that shaped the next step

The investigation suggested adding information about the **boundary layer**: the lowest part of the atmosphere, where surface emissions mix. Its depth, together with wind, helps describe how readily pollution can disperse.

Both experiments below used only training-period data. Each group of dates was evaluated with a model fitted on other groups (**out-of-fold evaluation**): 18,934 windows containing 2,167 events. **The new probability model has not been evaluated on the later temporal test set**; the earlier forecast comparisons have.

### First: would better weather information help at all?

I used **ERA5**, a reconstruction of past weather, to estimate how much boundary-layer information could help. Because it incorporates information about weather at the time being predicted, this is a hindsight experiment—called a *perfect-prognosis ceiling*—not a usable forecast result.

Adding these features improved the model's ability to rank dangerous windows above non-dangerous ones: **AUC**, a measure of that ranking, rose from **0.927 to 0.973**. The best event score, CSI, rose from **0.476 to 0.682**. “Best” here means selecting an alert threshold on development predictions, not validating an alert policy for public use.

The experiment passed criteria written into Git before the result existed. That justified testing weather information that would actually be available in advance. [ERA5 experiment and pre-declared rule](docs/BLH_CEILING_RESULT.md).

### Second: would a free weather forecast retain the benefit?

I replaced the hindsight information with forecasts from **GFS**, the U.S. National Oceanic and Atmospheric Administration's free global weather model.

GFS retained about **76% of the ranking improvement and 81% of the event-score improvement** in a comparison using the same sampling times. The gains, **+0.0336 AUC and +0.1620 CSI**, passed the second pre-declared test.

Per city, the picture is uneven, and the unevenness is the point:

| City | events | CSI before → after | Note |
|---|---:|---|---|
| Delhi | 1,974 | 0.612 → **0.705** | best absolute skill; the diagnostic city |
| Patna | 111 | 0.159 → **0.260** | **largest gain**, and a target city |
| Mumbai | 61 | 0.025 → **0.100** | improved, but still weak in absolute terms |
| Lucknow | 16 | 0.065 → **0.057** | **regressed**, on 16 events |
| Bangalore / Chennai | 0 / 5 | — | too few events to score |

Kanpur, Kolkata and Varanasi are absent from this table by design: they are the fully held-out cities, excluded from the fitting tier these scores come from. Varanasi additionally has **zero events anywhere in the benchmark**, so no method can be scored there at all.

Patna gaining most matters, because every earlier method improved Delhi and left the target cities behind. But the system still performs *best* in Delhi, Lucknow got worse, and the held-out target cities have too little event evidence to judge. Nothing here supports a claim that this works especially well in smaller cities — only that the largest single improvement landed in one of them.

As a result, the planned **Aurora 1.5 GPU run to obtain boundary-layer forecasts was cancelled**. GFS supplied enough useful information for this next research stage. This does not mean its boundary-layer heights are physically interchangeable with ERA5. [GFS experiment and pre-declared rule](docs/FORECAST_BLH_RESULT.md).

## What I’m working toward

The goal is useful advance warning, with an inspectable track record.

The next steps are:

1. **Make the completed results easier to inspect and reproduce.** Release fixed versions of the 24-hour tables with their inputs, city counts, and forecast horizons, and connect them to the reporting pages.
2. **Develop and test the probability-based warning model.** Combine recent station readings with GFS weather features. Decide the validation rules and alert threshold before evaluating it on later dates. Check whether Aurora adds value beyond those cheaper inputs.
3. **Compare against forecasts people already have.** Review the captured SILAM archive—another existing air-quality forecast—and compare predictions issued at matching times. Resolve the Varanasi observation question before drawing conclusions about that city.
4. **Only if the evidence supports it, try a live system privately.** Save each forecast before observations arrive, verify it afterward, and track misses, false alarms, missing data, and cost. This is often called *shadow mode*.
5. **Consider a public experimental feed after those checks.** Show the forecast, its age, the method behind it, and the track record—including failures.

These are planned steps, not delivered capabilities. The current web interface uses illustrative data; **there is no live warning feed**. No further Aurora GPU spending is justified merely to obtain boundary-layer height.

## What the evidence cannot yet establish

- **Reliable performance across cities.** Delhi dominates the sample. The excluded-city test has 94 events: 92 in Kolkata, two in Kanpur, and none in Varanasi. The local correction reduces detection there from 0.798 to 0.755. Patna has only five temporal-test events.
- **A Varanasi warning claim.** It has zero events in 1,516 benchmark windows. Its unusually low readings and frequency of exact zeros need an independent check against pollution-control-board records.
- **Year-round reliability.** There is no independent post-monsoon test. Overlapping windows and repeated stations also limit how much independent evidence the counts represent.
- **An improvement at every forecast horizon.** The hourly evaluation finds worse detection at +84 hours for stations excluded from fitting, despite the local correction's pooled gains.
- **Fully consistent model outputs.** The audit retains a failure: PM1 ≤ PM2.5 ≤ PM10 is violated on 463 of 80,730 stored rows. Those particle-size bins should be ordered consistently. The scored paths use only PM2.5, but the other outputs are not physically clean. Two older pilot dates remain excluded from evaluation.

The project also corrected its founding assumption that Patna, Varanasi, Kanpur, and Lucknow lacked forecasts. National/regional forecast products exist; exact city coverage and comparative performance still need verification. [Why the premise changed](docs/TARGET_REEVALUATION.md).

## Why I started, and how to contribute

Air pollution was changing places I knew, and I wanted to contribute something practical. I began with limited compute and learned the acquisition, modelling, and evaluation work as it became necessary. I publish failures so others can challenge and improve the work.

Contributions are especially useful on independent observation checks, city-level evaluation, probability calibration and uncertainty, existing-forecast comparisons, and reproducible reporting. The linked documents contain the technical constraints.

## Run the checks or explore further

Use Python 3.11 in a virtual environment. On Windows, substitute `.venv/Scripts/python.exe` for `python`:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.eval.audit
```

Inspect the audit's printed results, not just its exit status: the known particle-bin failure remains. Full reproduction needs upstream data access and appropriate credentials and terms. Bulk observations are absent from the current tracked files, so a fresh clone cannot regenerate every result by itself.

| Read | Purpose |
|---|---|
| [Benchmark specification](docs/BENCHMARK_SPEC.md) | Metrics, data partitions, and evaluation rules |
| [Current handoff](docs/HANDOFF.md) | Verified state and next technical actions |
| [Reproduction runbook](scripts/setup_gpu.md) | Controlled forecast generation |
| [Live-system design](docs/LIVE_FEED_SPEC.md) | Proposed forecast records and later verification; not a deployed service |
| [Journal](JOURNAL.md) | Decisions, bugs, and negative results |
| [Publication audit](docs/PUBLICATION_READINESS.md) / [NOTICE](NOTICE.md) | Unresolved historical-data redistribution and third-party terms |

Authored code and documentation use the [MIT licence](LICENSE); third-party data and models retain their own terms. Historical OpenAQ and ERA5 files remain in public Git history, with redistribution review unresolved.

**Research use only.** This is not an official air-quality warning service or a validated operational forecast. Do not use it as the sole basis for health or emergency decisions.
