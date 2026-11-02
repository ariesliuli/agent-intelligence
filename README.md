# Agent Intelligence

A versioned, evidence-first archive for daily AI Agent engineering and productivity-gap research.

## Layout
- `daily/YYYY-MM-DD/codex-evolution.md`: qualifying engineering developments.
- `daily/YYYY-MM-DD/productivity-gap.md`: qualifying productivity-gap signals.
- `hints/HINT-XXX.md`: reusable, numbered engineering proposals.
- `state/processed.json`: deduplication index (not an execution log).
- `templates/`: reporting formats.
- `scripts/`: local import and validation utilities.

**Publishing rule:** No qualifying evidence = no daily report, no new Hint. Keep sources, dates, confidence and limitations explicit. Never commit secrets, customer data, device credentials, private IPs or proprietary records. Repository visibility should be Private before storing internal information.

**Automation status:** Repository scaffolding does not itself connect ChatGPT scheduled tasks to GitHub writes. A separate supported ingest mechanism must be configured and verified.
