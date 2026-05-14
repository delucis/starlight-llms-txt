---
'starlight-llms-txt': patch
---

Delay creating the Astro container until it is actually needed. This avoids
eager `experimental_AstroContainer.create()` calls when `rawContent: true` is
enabled, which can fail during Cloudflare prerender builds even though the raw
content path does not need the container.
