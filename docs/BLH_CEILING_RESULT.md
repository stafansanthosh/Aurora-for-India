# Option B kill-test result: boundary layer clears the bar

**Date:** 2026-08-11
**Reproduce:** `python -m src.eval.blh_ceiling_test`
**Pre-declared rule:** `docs/CODEX_BRIEF_OPTION_B.md` §3.3, committed in `2ab1c50`
**before** this result existed.
**Status:** **PROCEED** — but see §4 before spending anything.

---

## 1. What was tested

ERA5 reanalysis assimilates observations and is valid *at* the target window, so
ERA5 boundary-layer height is an **upper bound** on what any forecast of that
field could supply. If perfect-knowledge BLH did not move exceedance skill, then
Aurora 1.5's forecast BLH would move it less and Option B would be dead.

Train split, train_pool tier, out-of-fold by init date. n=18,934 windows,
2,167 Very Poor+ events, 32 dates. ERA5 covered **100%** of train windows.

Features added: 24-hour window minimum and mean of BLH, minimum and mean of the
ventilation coefficient (BLH × 10 m wind), and mean dew-point depression. The
window *minimum* matters because an episode is made by the worst mixing hour,
not the average one.

---

## 2. Result

### Pooled (89% Delhi — read §3 before drawing conclusions)

| Feature set | AUC | best CSI | ΔAUC | ΔCSI |
|---|---:|---:|---:|---:|
| baseline (persistence + season + lead) | 0.908 | 0.480 | | |
| current (+ Aurora + CAMS) | 0.927 | 0.476 | — | — |
| **+ ERA5 boundary layer** | **0.973** | **0.682** | **+0.046** | **+0.206** |
| ERA5 only (+ season + lead) | 0.960 | 0.637 | +0.033 | +0.161 |

### Per city — current vs +ERA5

| City | n | events | AUC cur | AUC +ERA5 | ΔAUC | CSI cur | CSI +ERA5 | ΔCSI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| delhi | 8,511 | 1,974 | 0.928 | 0.970 | +0.042 | 0.612 | 0.736 | +0.125 |
| **patna** | 1,393 | 111 | 0.745 | **0.928** | **+0.183** | 0.159 | **0.455** | **+0.296** |
| mumbai | 4,992 | 61 | 0.620 | 0.773 | +0.153 | 0.025 | 0.136 | +0.111 |
| lucknow | 1,060 | 16 | 0.827 | 0.911 | +0.084 | 0.065 | 0.133 | +0.069 |

### Verdict against the pre-declared rule

| Criterion | Required | Actual | Met |
|---|---|---:|---|
| ΔAUC | ≥ +0.020 | **+0.046** | yes |
| ΔCSI | ≥ +0.030 | **+0.206** | yes |
| Holds in a non-Delhi city with ≥50 train events | at least one | Patna and Mumbai both | yes |

**PROCEED.**

---

## 3. The two findings that matter most

**The gain is largest exactly where the project needs it.** Patna — a genuine
target city, not the Delhi diagnostic — goes from AUC 0.745 to 0.928 and from
CSI 0.159 to 0.455. That is the largest improvement of any city, and it directly
attacks the failure identified in `EPISODE_SKILL_DIAGNOSIS.md` §3, where Patna's
raw-Aurora AUC was 0.640. Every previous method improved Delhi most and the
target cities least; this one inverts that.

**Boundary-layer meteorology alone beats the current pollution setup.** ERA5 +
season + lead, with *no* Aurora and *no* CAMS, scores AUC 0.960 / CSI 0.637 —
against 0.927 / 0.476 for persistence + Aurora + CAMS. The boundary layer
carries more episode information than the pollution forecast does.

That reframes Option B. The question is no longer "can Aurora be fixed by adding
meteorology" but "is a pollution model needed at all, or is this a
boundary-layer problem with a local-observation anchor?"

---

## 4. What this does NOT establish — read before spending

1. **This is perfect prognosis, not skill.** ERA5 is analysis. Aurora 1.5's
   *forecast* BLH at +48–96 h will be worse, perhaps much worse. The honest
   reading is "the information is worth having", not "we will achieve AUC 0.973".
2. **The follow-on forecast-vs-analysis BLH test is complete.** Free NOAA GFS
   passed the pre-declared train-only gate; see `FORECAST_BLH_RESULT.md`.
3. **Still train-only.** Nothing here has touched the test split, and it must not
   until a validation design is pre-declared.
4. **Small event counts outside Delhi.** Patna 111, Mumbai 61, Lucknow 16. The
   Patna result is the most important number here and it rests on 111 events.
5. **Mumbai's absolute skill is still poor** (CSI 0.136) even after the gain.
6. **Varanasi and Kanpur are absent** — zero and too-few events (see
   `EPISODE_SKILL_DIAGNOSIS.md` §4). This result says nothing about them, and the
   Varanasi data question remains open.
7. **BLH is a reanalysis product, not an observation.** ERA5's boundary layer
   over the Indo-Gangetic Plain has its own biases; MAUSAM (arXiv:2509.01879)
   found AI models carry a cold bias over the IGP and that reanalysis-centric
   benchmarks overstate skill by 15–45%.

---

## 5. Follow-on result and next steps

1. **Use free GFS for forecast-time BLH.** It added +0.0336 AUC and +0.1620 CSI,
   retained about 76%/81% of the like-for-like ERA5 gain, and passed in Patna.
2. **Do not run Aurora 1.5 for BLH.** Its released weather checkpoint does
   expose `blh`, but requires a much larger HRES input contract and GFS already
   clears the absolute gate without a GPU.
3. **Pre-declare the validation design** for whatever learned method follows,
   before it touches test data.
4. Freeze/version the retrospective scorecards and preserve per-city counts.

The follow-on result confirms the implication: the *boundary layer*, not the
pollution model, carries the signal, and a free NWP forecast delivers most of
the ERA5 gain. The cheapest useful system does not require Aurora 1.5 inference.
