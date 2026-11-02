---
title: Pipelines API
slug: pipelines-api
product_area: Verify
content_type: api_reference
owner: Pipeline Execution group
updated_at: 2026-07-02
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# Pipelines API

Use this API to interact with CI/CD pipelines. All endpoints require authentication with a personal access token, project access token, or OAuth token that has the `read_api` scope.

## List project pipelines

```plaintext
GET /projects/:id/pipelines
```

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | integer or string | Yes | The ID or URL-encoded path of the project. |
| `status` | string | No | Filter by status: `running`, `pending`, `success`, `failed`, `canceled`. |
| `ref` | string | No | Filter by branch or tag name. |

## Get a single pipeline

```plaintext
GET /projects/:id/pipelines/:pipeline_id
```

Returns the pipeline with its `id`, `status`, `ref`, `sha`, `created_at`, `duration` and `web_url`.

## Errors

The API returns `404 Not Found` when the project or pipeline does not exist or you do not have access. It returns `401 Unauthorized` when the token is missing or invalid.
