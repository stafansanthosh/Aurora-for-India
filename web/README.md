# IndiaAQBench public interface

This directory contains the interactive product preview for IndiaAQBench.

The current interface deliberately uses **illustrative values**, not live
forecasts. Its purpose is to establish the public information design while the
159-station benchmark and live-cycle pipeline are completed.

## Product principles

- Lead with underserved cities rather than Delhi.
- Use rolling 24-hour PM2.5 categories for the public headline.
- Keep raw Aurora, local adjustment, CAMS, and persistence visible together.
- Show data freshness and data support, including missing-local-data fallbacks.
- Publish event counts beside POD, FAR, and CSI.
- Never present demonstration values as scientific results.
- Label the product as experimental research, not official health guidance.

The normative behavior and future live-data contract are defined in:

- [`../docs/PRODUCT_SPEC.md`](../docs/PRODUCT_SPEC.md)
- [`../docs/LIVE_FEED_SPEC.md`](../docs/LIVE_FEED_SPEC.md)

## Local development

Requirements:

- Node.js 22.13 or later

```bash
npm ci
npm run dev
npm test
```

`npm test` creates a deployment build and checks that the rendered page retains
its demonstration-data and research-use boundaries.

## Current data boundary

All values in `app/page.tsx` are interface fixtures. They must be removed when
the immutable live forecast ledger is connected. A live build must consume the
versioned schema in `docs/LIVE_FEED_SPEC.md` and must display a stale or
unavailable state when that feed cannot be validated.
