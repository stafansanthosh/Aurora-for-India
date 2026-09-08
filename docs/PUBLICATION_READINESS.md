# Publication readiness and read-only audit

**Verified 2026-09-08 against `d879a67e970e6814403f2f4d21aeba2cbe0a4578`.**
The repository is already **PUBLIC**. Earlier private-repository statements in
historical documents are obsolete. No visibility or history change was made.
Software licensing is resolved; historical data redistribution is not.

## Repository and access

- GitHub API: `stafansanthosh/Aurora-for-India`, public, default branch `master`,
  MIT licence detected, size 338,272 KB; homepage unset.
- Anonymous raw README request returned HTTP 200 (22,042 bytes before this edit).
- Description: “Open benchmark testing whether a cheap global forecast can warn
  of dangerous PM2.5 episodes in Indian cities — scored on event detection, not
  average error”. Topics: air-quality, cams, environmental-data, forecasting,
  india, machine-learning, openaq, pm25, research, benchmark,
  reproducible-research, microsoft-aurora. No metadata changes were needed.
- Starting tree: 276 tracked files, no tracked edits, 72 reachable commits and
  698 unique reachable blobs. Local master and origin/master pointed to d879a67.
- Six untracked SILAM directories were left untouched and must never be staged
  with this work: `20260730`, `20260807`, `20260808`, `20260809`, `20260810`,
  `20260812` under `data/silam/`.
- Current tree still includes the 35.71 MiB GFS station CSV, pilot NetCDF fields,
  and a rejected calibrator binary. Removing OpenAQ/ERA5 bulk files from HEAD
  did not remove their historical copies.

## Secret scan

Gitleaks **8.30.1**, official Windows x64 release verified against its published
SHA-256 checksum, scanned all reachable history using:

```text
gitleaks git . --log-opts="--all --full-history" --redact=100 --report-format json
```

Result: **72 commits, 469,871,767 bytes scanned, no leaks found**. The scan used
the default rules without custom exclusions or size limits. A supplementary
tracked-filename check found no `.env`, `.pem`, `id_rsa`, `.cdsapirc`, or
credential-named file. Local acquisition credentials and ignored dependency
folders are not public release inputs. A clean scanner result is evidence from
these rules, not proof that no conceivable secret exists. Re-scan the final
release commit after any later changes or history operation.

## Reachable large artifacts and rights

`git rev-list --objects --all` with `git cat-file --batch-check` found **16 blobs
over 10 MiB**. Representative objects:

| Historical path | MiB | Blob |
|---|---:|---|
| `data/era5_blh/era5_blh_202503.nc` | 84.22 | `fe2b2476140750db9cda3aaffe6fb6d48bf40054` |
| `data/era5_blh/era5_blh_202511.nc` | 45.45 | `1fdee1e681662e4a5ecabd9e0f8793e735f3efbd` |
| `data/era5_blh/era5_blh_202506.nc` | 45.08 | `a92210d37fc0a1bdca3d3073e97eb4e38b0f61e7` |
| `data/openaq/_backup_pre_sensorfix/delhi_pm25.csv` | 41.60 | `30b4b6c6a10beadd569b259815b0724cebc8c914` |
| `data/openaq/archive/mumbai_2024-10-01_2026-07-22.csv` | 39.77 | `a76e586df1e9421897474266a4c1fcebb639fd6f` |
| `data/era5_blh/era5_blh_stations.csv` | 37.88 | `e9237c870e2466847a6149a589520cc62bbb8864` |

These artifacts are reachable in an already-public repository. [NOTICE](../NOTICE.md)
distinguishes authored MIT software from upstream terms, but does not establish
bulk redistribution rights. Provider-specific OpenAQ permissions and applicable
Copernicus redistribution/attribution requirements remain unresolved here.
This audit makes no legal determination.

## Owner decision required before any publication restructuring

| Option | Concrete work required | History and scientific evidence | Remaining cost/risk |
|---|---|---|---|
| Rights confirmation | Inventory each source/version/provider; obtain or locate permission for the actual historical files; document attribution and terms, including derived tables | Keeps existing hashes, links, and both pre-declaration sequences intact | Public files remain accessible during review; permission may be unavailable; repository stays large |
| Reviewed history rewrite | Approve exact paths/blobs; preserve a private backup; dry-run filtering in an isolated copy; compare scientific source/provenance; approve ref changes before any force-push | Retain contracts and results in chronological ancestry, publish old-to-new commit mapping and content hashes; original commit IDs change | Disrupts clones and links; needs coordinated ref/cache/fork handling; cannot retract copies already downloaded |
| Clean public mirror | Approve an allowlisted snapshot and destination; retain original research history privately only if separately authorized; review every included artifact | Publish contracts, result hashes, and an independently verifiable chronology package; a new snapshot alone does not prove pre-registration | New URL and split issue history; creating a mirror alone leaves the currently public historical data exposed |

No option has been selected or executed. Do not rewrite, force-push, change
visibility, delete data, or create a mirror without explicit owner approval.

Preserve these verified ancestry sequences, not merely editable timestamps:

- ERA5 contract **2ab1c50** → result **e0a3487**.
- GFS contract **b78479b** → acquisition/result **bcef006**.

The commits are ordered on the current history on 2026-08-12. Some result
headings say 2026-08-11; those labels are not the evidence for commit order.
Before restructuring, retain full commit objects privately plus independently
verifiable public attestations or archived contract snapshots where appropriate.
Do not publish a backup bundle containing the very data being removed.

## Verification and remaining scientific boundaries

The latest remote Actions run, [34198698268](https://github.com/stafansanthosh/Aurora-for-India/actions/runs/34198698268),
failed on d879a67 solely at the production audit: `nanoid <3.3.18`,
[GHSA-2v37-7h3g-55p8](https://github.com/advisories/GHSA-2v37-7h3g-55p8).
The build and two rendered-HTML tests passed in that run. The local fix changes
only nanoid's lockfile version, tarball URL and integrity, from 3.3.16 to 3.3.18;
existing dependency ranges already permit it. No manifest override or weakened
audit gate is needed. Remote CI on the new commit remains pending an explicitly
authorized push; local checks cannot establish green GitHub Actions.

Local Python verification: **108 passed**, one existing NumPy binary-size
warning. Integrity audit: **39 checks, 36 pass, two expected legacy warnings,
one retained PM-bin failure**. Its process exits zero despite the printed
failure; this is not a clean scientific audit. The README discloses the 463 of
80,730 inconsistent stored rows and the PM2.5-only scoring boundary.

The README headline was checked against local event counts: each of CAMS,
raw Aurora and Component A has 1,704 temporal-test event windows. The GFS JSON
confirms gains +0.033606 AUC/+0.161971 CSI and 75.8%/80.9% retention. These are
different populations: the new boundary-layer experiments remain train-only.

Unresolved scientific release items: freeze/version retrospective tables and
wire the 24-hour report; preserve the cutoff revision and absent post-monsoon
test; retain Delhi dominance, sparse city counts and the Varanasi data question;
keep Component A uncertified; pre-declare future classifier validation and
incumbent comparison. An illustrative interface is not a live forecast service.

Local web verification after the minimal lockfile fix: `npm ci`, `npm test`
(production build plus 2/2 rendered-HTML tests), and `npm audit --omit=dev`
all passed; production audit reports **zero vulnerabilities**. Used official
Node 22.14.0 x64 (archive SHA-256 verified) because the bundled Windows ARM64
Node cannot install workerd. The install still reports 19 issues when development
dependencies are included; those are outside this production-only nanoid fix
and no audit gate was weakened. The temporary runtime is not a repo change.
The regenerated 24-hour anchored CSV exactly equals the existing local table,
including every numeric value. All local README links resolve; diff whitespace
checks pass. The proposed README diff was shown through the app review panel.
