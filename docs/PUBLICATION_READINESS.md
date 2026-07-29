# Publication readiness

**Snapshot:** 2026-07-29
**Decision:** keep the repository private until every blocking item below is
resolved.

This checklist covers repository publication, not scientific validation. The
current scientific state is tracked in
[`PROJECT_STATUS.md`](PROJECT_STATUS.md).

## Verified now

- The GitHub repository exists at
  `https://github.com/stafansanthosh/Aurora-for-India`.
- GitHub reports the repository as **private**; an unauthenticated request
  returns 404.
- `master` is the default branch.
- `.env` is ignored and is not present in reachable Git history.
- No private-key, certificate, or Copernicus credential file was found in
  reachable Git history by the local filename audit.
- The only source-tree credential-pattern hit is placeholder documentation in
  `COPILOT_CONTEXT.md`, not a real token.
- Local Claude permissions are excluded through
  `.claude/settings.local.json` in `.gitignore`.
- Public-facing documentation and the interactive UI preview completed
  independent integration review.
- GitHub Actions run `30473089540` passed all 26 Python tests and the web
  install/build/render checks on integration commit `48135cc`.

## Publication blockers

### 1. Raw observation files remain in Git history

Although the large OpenAQ CSVs are no longer tracked at `HEAD`, earlier commits
contain hundreds of megabytes of raw archive and backup files. Examples include
historical blobs for Delhi, Mumbai, Bangalore, and per-month archive parts.

Making the repository public in its current form would make those historical
files downloadable. Publication therefore requires one of:

1. written confirmation that historical redistribution is permitted, plus an
   explicit data licence and attribution; or
2. a reviewed history rewrite that removes the raw archive paths before the
   visibility change; or
3. a new clean public repository containing only the approved current source
   snapshot, while retaining this repository privately.

History rewriting and force-pushing are destructive operations and require an
explicit owner decision.

### 2. No repository licence

The repository currently has no `LICENSE`. Public visibility alone does not
grant reuse rights.

The owner must select the software licence. Data and third-party model
artefacts must retain their own terms and attribution rather than being
implicitly covered by the software licence.

### 3. The local data-dependent audit still needs to run

The source-only checks are green in GitHub Actions. The local Python
environment still points to a missing base interpreter, so the integrity audit
has not been rerun after the registry-fingerprint and exact-completeness
changes. That audit needs the complete local archive and a repaired local
environment.

### 4. Scientific outputs are not final

The repository has zero valid current-registry forecast-pair files. The five
legacy pilot pair files must remain clearly labeled and must not appear as the
current benchmark result.

The repository may be shared as an active research project after the software
publication gates pass. It must not be presented as a validated forecast
service until the scientific and operational gates in
[`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) pass.

## Safe publication sequence

1. Finish independent review of the current uncommitted work.
2. Reconcile `HANDOFF.md`, `WORKSTREAMS.md`, and the public status page.
3. Commit only reviewed source and documentation; exclude local configuration.
4. Push while the repository remains private.
5. Require the Python and web CI jobs to pass. **Passed on `48135cc`.**
6. Repair the local Python environment and rerun the integrity audit.
7. Resolve the software licence.
8. Resolve the historical raw-data choice: rights confirmation, history
   rewrite, or clean public mirror.
9. Re-run the secret and large-history audits on the exact publication commit.
10. Set the GitHub description and topics.
11. Change visibility only after the owner approves the final gate.
12. Verify the repository and every README link in an unauthenticated browser.

## Recommended posting sequence

- **Private applications now:** a PDF or selected code sample may be shared
  privately with accurate status language.
- **Public building-in-progress post:** after the repository publication gates
  above pass.
- **Main technical post:** after the 56-date, 159-station benchmark and a
  versioned scorecard exist.
- **Product launch post:** after the live feed completes shadow-mode gates.
