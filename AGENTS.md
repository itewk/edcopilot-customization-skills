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
- End the commit message with exactly one attribution trailer, in the final
  paragraph separated by one blank line:

  ```
  Co-authored-by: 🤖 OpenCode (<model(s)>) <noreply@opencode.ai>
  ```

  The parenthesised value names the tool's contributing model(s), using the
  provider/model id actually in use for the session (e.g.
  `Co-authored-by: 🤖 OpenCode (opencode-go/deepseek-v4.1-flash) <noreply@opencode.ai>`).
  There is no separate `Models:` trailer — model and role attribution live
  inside that value. Never add the trailer twice if the message already
  carries one.

## References

- CONTRIBUTING.md for the full workflow
- docs/superpowers/specs/2026-11-10-repo-design.md as the architecture statement
- docs/backlog.md for open work