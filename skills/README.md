# Skills Directory

Place each skill in `skills/<skill-name>/SKILL.md`.

`SKILL.md` should use YAML frontmatter and include at least:

```yaml
---
name: your-skill-name
description: Short description for tool registration
---
```

The `skill` tool only exposes `name + description` to the model during registration.
When the model calls `skill({"name": "..."})`, the backend lazily returns the full
content of the corresponding `SKILL.md`.
