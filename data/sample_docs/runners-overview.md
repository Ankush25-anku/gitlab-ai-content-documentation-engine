---
title: GitLab Runner overview
slug: runners-overview
product_area: Verify
content_type: docs_page
owner: Runner group
updated_at: 2026-05-20
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# GitLab Runner overview

GitLab Runner is an application that works with GitLab CI/CD to run jobs in a pipeline.

## Runner scopes

Runners can be instance runners, group runners, or project runners. Instance runners are available to every project in a GitLab instance. Group runners are available to all projects in a group.

## Executors

The executor determines the environment each job runs in. Common executors are Docker, Shell, Kubernetes and Docker Autoscaler.

## Register a runner

To register a project runner, go to **Settings > CI/CD > Runners** and select **New project runner**. Copy the runner authentication token and run `gitlab-runner register` on the host.
