# Issue #51230 discussion (fictional, summarised)

Product manager: Users keep asking why pipelines got slower after dependency updates. In most cases the cache key changed and every job missed the cache.

Engineer: We count a partial hit when a job restores a cache from `cache:fallback_keys`. Partial hits count as half a hit in the hit rate shown in the UI.

Engineer: The API returns raw counts; clients can compute their own rate.

Designer: The panel highlights jobs with a hit rate below 50% in red.
