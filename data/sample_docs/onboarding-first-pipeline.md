---
title: Tutorial - Create your first pipeline
slug: onboarding-first-pipeline
product_area: Verify
content_type: onboarding_guide
owner: Technical Writing team
updated_at: 2026-06-25
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# Tutorial: Create your first pipeline

This tutorial shows you how to configure and run your first CI/CD pipeline.

## Before you begin

You need a project in GitLab and the Maintainer or Owner role for the project. You also need a runner; GitLab.com provides instance runners.

## Create a .gitlab-ci.yml file

In your project, create a file named `.gitlab-ci.yml` in the root of the repository. Add a job with a `script` section.

## View the pipeline

Commit the file. Go to **Build > Pipelines** to see the pipeline run. Select a job to see its log.
