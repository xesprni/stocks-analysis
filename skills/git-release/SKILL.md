---
name: git-release
description: Release workflow checklist for preparing changelog, tagging versions, and validating rollout steps.
---

# Git Release Skill

## Goal

Provide a practical release checklist with clear pre-flight, release, and post-release steps.

## Workflow

1. Confirm branch status is clean and all CI checks pass.
2. Generate a user-facing changelog from merged commits.
3. Bump version and create a signed git tag.
4. Verify release artifacts and rollback instructions.
5. Announce release notes and monitor issues.

## Guardrails

- Never force-push to protected branches.
- Never skip release validation checks.
- Keep release notes focused on user impact.
