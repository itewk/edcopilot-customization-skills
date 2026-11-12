# Contributing

This file is for people changing the package's rules, validation, tests or
dossier templates. For using the tool, read [`README.md`](README.md) and
the skill documentation.

## Running the tests

```powershell
# Full test suite (from repository root)
python -m pytest tests/ -q
```

The 10 integration tests are part of the full suite and skip unless their
environment variables are set (see Test Constraints below).

```powershell
# Hermetic subset (no network, no real EDCoPilot folders)
python -m pytest -q -m "not integration"
```

CI runs the hermetic subset and validates all skills:

```powershell
python -m pytest -q -m "not integration"
skills-ref validate skills/*
```

## Modifying a skill

Each skill is completely self-contained. The structure follows:
- `SKILL.md` - Main documentation (agent-facing)
- `references/` - Detailed materials  
- `assets/` - Supporting files
- `scripts/` - Implementation code

Rules that guard changes:
- `SKILL.md` should be under 500 lines
- No `assets` references under `scripts/`
- Hermetic tests only (no network, no real EDCoPilot folders)
- `skills-ref validate` is run automatically

Run the suite before opening a PR.

## Adding a new skill

To add a new skill to this repository:

1. Create a new folder under `skills/` with the same structure as existing skills
2. Include `SKILL.md`, `references/`, `assets/`, and `scripts/` folders
3. The `scripts/` directory should contain Python code implementing the skill's functionality
4. Run `skills-ref validate skills/<skill-name>` to ensure the new skill is valid
5. The tool-wide rules in the skill's `scripts/edcg/rules/data/base.toml` define the rules for all systems

## Commit Conventions

- Use conventional commit subjects (e.g., `feat: add new rule`, `docs: update README`)
- Include a `Models:` trailer with the model and role used for implementation:
  ```
  Models: lmstudio/qwen/qwen3-coder-30b (implementation)
  ```
- Include a `Co-authored-by:` trailer with the tool and model that produced the commit:
  ```
  Co-authored-by: 🤖 OpenCode (Qwen3 Coder 30B) <noreply@opencode.ai>
  ```

The trailers must be adjacent in the commit message.

### Test Constraints

- No network access; no real EDCoPilot folders may be read or written.
- Use `tmp_path` fixture for temporary directories.
- Use the fixtures provided in `tests/fixtures/`.
- Integration tests require the test-only `INARA_API_KEY` environment variable
  (not `EDCG_INARA_API_KEY`); they skip when it is not set.
- Unit tests must stay offline and must not read or write the developer's real
  content roots.
- Live fixtures require `EDCP_TEST_LIVE_ROOT` (live content repo, read-only),
  `EDCP_TEST_EDCOPILOT_ROOT` (runtime custom file), and companion template sibling path.