# Release summary: Pipeline cache analytics (GitLab 18.6)

- New: cache analytics panel on the pipeline details page shows the cache hit rate for the last 30 days.
- New: REST API endpoint GET /projects/:id/pipelines/:pipeline_id/cache_stats.
- Tier: Premium and Ultimate. Offerings: GitLab.com, GitLab Self-Managed, GitLab Dedicated.
- Deprecated: the cache_hits field in the job JSON, to be removed in GitLab 19.0.
- Audience: developers and platform engineers who maintain CI/CD pipelines.
