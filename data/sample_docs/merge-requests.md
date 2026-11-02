---
title: Merge requests
slug: merge-requests
product_area: Create
content_type: docs_page
owner: Code Review group
updated_at: 2026-06-11
note: Written for this capstone in the style of GitLab documentation. Not official GitLab content.
---

# Merge requests

A merge request is a proposal to merge changes from a source branch into a target branch.

## Create a merge request

Push a branch, then go to **Code > Merge requests** and select **New merge request**. Choose the source and target branch, add a title and description, and assign reviewers.

## Approvals

Approval rules define how many approvals a merge request needs and who can approve it. Approval rules are available in Premium and Ultimate.

## Merge trains

A merge train queues merge requests and verifies each one against the changes ahead of it before merging. Merge trains require merged results pipelines.
