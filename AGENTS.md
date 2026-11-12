# EDCoPilot Customization Skills

This repository contains skills for authoring and updating EDCoPilot speech content for Elite Dangerous colonisation systems. Before working in this repository, read CONTRIBUTING.md.

## Running tests

```powershell
python -m pytest tests/ -q
python -m pytest -q -m "not integration"
```

The hermetic test suite runs without network access or real EDCoPilot folders, using only `tmp_path` fixtures.

## Commit conventions

- Use conventional commit subjects
- Include a `Models:` trailer with the model and role used for implementation
- Include a `Co-authored-by:` trailer with the tool and model that produced the commit
- The trailers must be adjacent in the commit message

## References

- CONTRIBUTING.md for the full workflow
- docs/superpowers/specs/2026-11-10-repo-design.md as the architecture statement
- docs/backlog.md for open work