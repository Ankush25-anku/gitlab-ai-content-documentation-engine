# Add pipeline cache analytics (fictional MR !4821 for the capstone demo)

## What does this MR do?

This MR adds cache analytics for CI/CD pipelines. Each job now records whether its cache was a hit, a partial hit, or a miss.
The new Cache analytics panel shows the cache hit rate for the last 30 days on the pipeline details page.
The new REST API endpoint `GET /projects/:id/pipelines/:pipeline_id/cache_stats` returns cache statistics for a single pipeline.

## Availability

Cache analytics is available in GitLab 18.6 for Premium and Ultimate on GitLab.com, GitLab Self-Managed and GitLab Dedicated.
The feature is behind the feature flag `ci_cache_analytics`, which is enabled by default.

## Why

Teams told us they cannot see whether their cache configuration works. Slow pipelines are often caused by cache misses after a lock file changes.

## How to use it

1. Go to Build > Pipelines and select a pipeline.
2. Select the Cache analytics tab.
3. Review the hit rate and the list of jobs with cache misses.

## Deprecation

The `cache_hits` field in the job JSON is deprecated and will be removed in GitLab 19.0. Use the new `cache_stats` endpoint instead.

## Permissions

Users need at least the Reporter role in the project to view cache analytics.
