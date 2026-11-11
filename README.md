# EDCoPilot Customization Skills

A collection of Agent Skills for authoring and updating EDCoPilot speech content.

## Requirements

- Windows with EDCoPilot installed and run at least once
- Python 3.12 or later
- `pip install httpx gitpython`
- Git with `user.name`/`user.email` configured
- A skills-compatible chat client

## What This Repository Contains

This repository contains the `edcopilot-system-content` skill, which enables users to:
- Create new system content for EDCoPilot using a structured interview process
- Update existing system content with new information
- Manage custom speech content through provenance tracking and marker operations

## Installation and Setup

Install the skill using:

```bash
npx skills add <your-github-owner>/edcopilot-customization-skills
```

> Note: The `<your-github-owner>` should be replaced with your actual GitHub username or organization name.

Update the skill with:

```bash
npx skills update
```

## First Run Experience

When running the skill for the first time:
1. `edcg.py doctor` verifies the environment (Python ≥3.12, required packages, git identity)
2. The content repository root is the agent's current working directory
3. If it's blank, the user confirms and `edcg.py init` scaffolds it (`git init` unless `--no-git`,
   the config file, `systems/`, the house-rules example)
4. The EDCoPilot root is asked once and stored in the content repository configuration
5. Subsequent runs will use the stored path, re-asking only if the path becomes stale

## Quickstart Guides

### New System Flow
Install the skill, then ask your agent to "design a new colonisation system for <system name>".
Refer to `references/new-system-interview.md` for the six-phase design interview process.

### Update Flow
Install the skill, then ask your agent to "update my systems after play".
Refer to `references/update-interview.md` for the seven-phase update interview process.

## Repository Layout

```
.
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-11-10-repo-design.md    # Founding specification
├── skills/
│   └── edcopilot-system-content/            # Main skill folder
│       ├── SKILL.md                         # Skill main documentation
│       ├── references/                      # Detailed reference materials
│       ├── assets/                          # Supporting files
│       └── scripts/                         # Python implementation
├── tests/
├── requirements-dev.txt                     # Development dependencies
├── pytest.ini                               # Test configuration
├── .github/workflows/ci.yml                 # Continuous integration workflow
├── docs/live-run-checklist.md               # Live run checklist
└── CONTRIBUTING.md                          # Development guidelines
```

## Adding a Second Skill

To add another skill to this repository, create a new folder under `skills/` with the same structure:
- `SKILL.md` - Main documentation (lowercase a-z0-9-, no consecutive hyphens, must match the folder name)
- `references/` - Detailed materials
- `assets/` - Supporting files
- `scripts/` - Implementation code

Each skill is completely self-contained. The repository's CI automatically validates every folder under `skills/` without needing changes to CI configuration.

## Human Gates

All workflows include human gates:
- Preview before full generation
- Review choice before marking
- Restart confirmation before log check and marker removal
- Listening after restart

The skill never refuses to proceed; all human gates are advisory.
>>>>>>> f795e1f (docs: standalone readme, contributing guide and founding spec)
