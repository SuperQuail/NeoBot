---
type: perf
scope: adapter
packages:
  python@neobot-adapter: patch
release: false
---

Parse each inbound model once when validation fails: the TypeAdapter retry re-ran the same validator, and the tolerant path no longer wraps conversions in no-op try/except blocks.
