---
type: fix
scope: logging
packages:
  python@neobot-app: patch
---

Downgrade per-request HTTP INFO logs (httpx, aiohttp access) to DEBUG so AI and media calls stop flooding the console and dashboard log view.
