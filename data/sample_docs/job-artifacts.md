---
title: Job artifacts
slug: job-artifacts
product_area: Verify
content_type: docs_page
owner: Pipeline Execution group
updated_at: 2026-03-18
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# Job artifacts

Job artifacts are files and directories a job saves when it finishes. Use `artifacts:paths` to choose what to keep.

## Artifacts compared to cache

Use job artifacts to pass build results between stages. Use the cache for dependencies that jobs download from the internet. Artifacts are always uploaded to GitLab; the cache is stored by GitLab Runner.

## Expiry

Use `artifacts:expire_in` to set how long artifacts are kept. The default expiry on GitLab.com is 30 days.
