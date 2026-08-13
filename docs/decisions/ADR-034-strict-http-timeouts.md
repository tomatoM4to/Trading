# ADR-034: Explicit HTTP Timeouts for External API Calls

## Status
Accepted

## Date
2026-08-13

## Context
During a comprehensive code audit, it was discovered that some `requests.post` and `requests.get` calls within `kis_auth.py` and `kis_fetch.py` were missing explicit `timeout` parameters. 
In Python's `requests` library, if a timeout is not specified, the request will hang indefinitely if the remote server fails to respond or if the TCP connection drops silently. Given our 1 OCPU/1GB RAM limitation and the background asyncio queue architecture (`_kis_worker_task`), a hanging synchronous request inside `asyncio.to_thread` or the main thread could exhaust thread pools, lock up the scheduler, and eventually cause the entire FastAPI server to become unresponsive.

## Decision
We enforce a strict rule that **every single HTTP request made to an external service (especially KIS OpenAPI) must have an explicit `timeout` parameter.**
- `timeout=10` for general fast-path data fetching (like OHLCV and ranking).
- `timeout=30` for critical but potentially slow authentication routines (like `oauth2/tokenP`).

## Consequences
- Guaranteed fail-fast behavior. If KIS API goes down, our threads will be freed after 10-30 seconds, allowing the app to log the error and stay alive (or retry safely).
- Eliminates the risk of silent thread starvation.
- Must be actively enforced in code reviews and future integrations.
