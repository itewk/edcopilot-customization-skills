# EDCoPilot Customization Skills

A collection of Agent Skills (agentskills.io) for authoring and updating EDCoPilot speech content for Elite Dangerous colonisation systems — the agent interviews you, records the design as a dossier and rules, writes and validates the speech content, and walks the marker cycle that makes EDCoPilot pick it up. Link to the founding spec at docs/superpowers/specs/2026-11-10-repo-design.md.

## Available skills

### edcopilot-system-content

Author and update EDCoPilot speech content for colonisation systems: greetings, chatter, broadcasts, station facts. 

**Use when:**
- Create speech content for my new colonisation system <name>
- Update the station dialogue after the station finished construction  
- The broadcast mix for my system feels wrong — review and rewrite it
- Add a new station that just became landable

## Installation

Install the skill using:

```bash
npx skills add <your-github-owner>/edcopilot-customization-skills
```

> Note: The `<your-github-owner>` should be replaced with your actual GitHub username or organization name.

The CLI will ask which harness to enable (Claude Code, Cursor, Codex, OpenCode, Gemini CLI and others) and supports global vs project scope. For harnesses without skills-CLI support: copy `skills/edcopilot-system-content/` into the harness's skills directory.

## Requirements

- Windows with EDCoPilot installed and run at least once
- Python 3.12 or later
- `pip install httpx gitpython`
- Git with `user.name`/`user.email` configured
- A skills-compatible chat client

## Usage

Skills activate on relevant tasks. The skill walks two main flows:

1. **New System Flow**: The six-phase interview process to create new colonisation systems
2. **Update Flow**: The seven-phase flow to update existing systems after play

Each workflow includes human gates: preview, review choice, restart, and listening. The agent asks for your decision at each gate.

Refer to `skills/edcopilot-system-content/SKILL.md` as the full agent-facing documentation.

## Skill structure

```
.
├── skills/
│   └── edcopilot-system-content/            # Main skill folder
│       ├── SKILL.md                         # Skill main documentation
│       ├── references/                      # Detailed reference materials
│       ├── assets/                          # Supporting files
│       └── scripts/                         # Python implementation
└── CONTRIBUTING.md                          # Development guidelines
```

## License

GPL-3.0