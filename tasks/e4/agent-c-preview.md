# E4-C-PREVIEW: independent synthetic acceptance pack

Base: coordinator task commit on `main`. Work in separate checkout and `agent-c/e4-preview` branch. Push QA artifact SHA and report to `reports/agent-c-preview.md`; no VM changes.

Prepare an executable, fully synthetic user acceptance pack for the preview stand using existing fixture contracts: first-run Moscow/MO choice, import two sample receipts, review/confirm, 200→270 comparison with 70/40/30 factors, FAQ known/unknown/out-of-scope, copy-only draft, history/deletion and isolation of two virtual guests. Use current fixtures and engine; do not introduce real resident data or unsupported local УК assertions. Distinguish API/engine checks from browser and VM evidence. Add a small command/checklist or script that A/B/coordinator can run against the isolated preview endpoint without changing production data. Verify engine/tests and report exact results; no claims of real receipt accuracy.
