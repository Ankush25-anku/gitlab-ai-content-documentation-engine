---
title: Caching in GitLab CI/CD
slug: ci-caching
product_area: Verify
content_type: docs_page
owner: Pipeline Execution group
updated_at: 2026-08-14
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# Caching in GitLab CI/CD

A cache is one or more files a job downloads and saves. Later jobs that use the same cache key reuse the files instead of downloading dependencies again.

## How caching works

Define a cache with the `cache` keyword in your `.gitlab-ci.yml` file. GitLab Runner stores the cache locally on the runner host or in a distributed cache such as an object storage bucket.

A job restores the cache before the `script` runs and saves it after the job finishes. The cache is shared between pipelines and between jobs in the same project that use the same cache key.

## Cache keys

Use `cache:key` to give each cache a unique identifying key. The default cache key is `default`. Use `cache:key:files` to generate a new key when a lock file such as `package-lock.json` or `Gemfile.lock` changes.

## Cache policy

The `cache:policy` keyword controls when a job downloads and uploads the cache. The default policy is `pull-push`. Use `pull` for jobs that only read the cache and `push` for jobs that only build it.

## Clear the cache

To clear the cache for a project, go to **Build > Pipelines** and select **Clear runner caches**. The next pipeline creates a new cache.

## Troubleshooting

If a job reports `No URL provided, cache will not be downloaded from shared cache server`, the runner has no distributed cache configured. Check the runner's `[runners.cache]` configuration.
