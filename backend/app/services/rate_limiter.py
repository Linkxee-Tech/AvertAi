"""
In-memory rate limiter (per the blueprint: 1000 reqs/hour per IP,
5 OTP requests/hour per phone, 3 feedback reports/day per phone).

In-memory storage is fine for a single-process dev deployment. In production
(multiple DigitalOcean droplets behind a load balancer) this MUST move to
Redis so limits are shared across instances — swap `_buckets` for
`redis_client.incr()` + `EXPIRE` calls; the public function signatures below
don't need to change.
"""
import time
from collections import defaultdict

_buckets: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
    now = time.time()
    bucket = _buckets[key]
    bucket[:] = [t for t in bucket if now - t < window_seconds]
    if len(bucket) >= max_requests:
        return True
    bucket.append(now)
    return False
