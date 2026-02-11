# Post-Mortem Report: Site Outage — 2026-02-11

## Date

2026-02-11

## Incident Summary

The site returned **502 errors** to users due to database connection blocking. All incoming requests were unable to be served while the application workers waited on unresponsive database connections, resulting in a full outage.

## Root Cause Analysis

1. **Transient DB unavailability** caused connection attempts to block for 10–20 seconds per request.
2. **Low worker count** — only 2 synchronous Gunicorn workers were configured, meaning all serving capacity was quickly exhausted by the blocked connections.
3. **Lack of timeouts and circuit breakers** — without any connection timeout, retry budget, or circuit-breaker logic, each stalled connection held a worker indefinitely. This created a **"death spiral"** where every new request piled onto already-saturated workers, making recovery impossible without a restart.

## Resolution

| Change | Detail |
|--------|--------|
| **Hardened DB connections** | Added a circuit breaker, enforced a **5-second connection timeout**, and switched to non-blocking initialization so the app can start even if the DB is momentarily unreachable. |
| **Upgraded Gunicorn config** | Switched to the `gthread` worker class with **12 concurrent slots**, providing significantly more headroom during transient slowdowns. |
| **Added health checks** | Introduced a `/healthz` endpoint (and `/healthz/db` for database-specific probes) so the platform load balancer can detect and route around unhealthy instances. |
| **Implemented graceful degradation** | The application now serves cached or static fallback content when the database is unavailable, keeping the site partially functional instead of returning 502 errors. |

## Future Action Items

- [ ] **Monitor `/healthz/db`** for early warnings of database connectivity issues; wire alerts to the team's notification channel.
- [ ] **Consider read-replica scaling** if traffic increases, to reduce load on the primary database and improve resilience to single-node failures.
