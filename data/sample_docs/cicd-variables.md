---
title: CI/CD variables
slug: cicd-variables
product_area: Verify
content_type: docs_page
owner: Pipeline Authoring group
updated_at: 2026-04-03
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# CI/CD variables

CI/CD variables are environment variables that jobs can use. Define them in the `.gitlab-ci.yml` file, in project settings, or in group settings.

## Protected and masked variables

A protected variable is only passed to pipelines that run on protected branches or tags. A masked variable is hidden in job logs. Store secrets as masked and protected variables, never in the `.gitlab-ci.yml` file.

## Predefined variables

GitLab provides predefined variables such as `CI_COMMIT_SHA`, `CI_PIPELINE_ID` and `CI_PROJECT_PATH` in every job.
