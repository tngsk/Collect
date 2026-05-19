## 2025-05-06 - [Performance Optimization] Caching static HTML content in memory
**Learning:** Serving static HTML content from disk on every request in a FastAPI async handler blocks the event loop and adds unnecessary latency.
**Action:** Read static HTML files into global variables at application startup and return the cached content from the routes.
