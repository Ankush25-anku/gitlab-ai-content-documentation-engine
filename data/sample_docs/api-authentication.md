---
title: REST API authentication
slug: api-authentication
product_area: General
content_type: docs_page
owner: Authentication group
updated_at: 2026-09-01
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# REST API authentication

Most REST API requests require authentication. Pass a personal access token or project access token in the `PRIVATE-TOKEN` header.

## Token scopes

The `read_api` scope grants read access to the API. The `api` scope grants read and write access. Use the smallest scope that works.

## Rate limits

GitLab.com applies rate limits to authenticated API requests. When you exceed a limit, the API returns `429 Too Many Requests`.
