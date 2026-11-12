# EDCoPilot System Content Skill Quality Proposals

**Date:** 2026-11-12  
**Status:** PROPOSAL — awaiting human accept/reject decisions; not authorized work  
**Review method:** Reviewed the skill-creator methodology, the Agent Skills specification, best practices, and description-optimization guidance; read `CONTRIBUTING.md`, the accepted-decisions section of `docs/backlog.md`, the founding design spec, the skill spine, its references, and its assets. **Model used:** GPT-6 Luna (review). No implementation or skill execution evals were performed.

## Global Constraints

- This document is a review proposal only. Do not implement any item until the human accepts it.
- Preserve the accepted decisions in `docs/backlog.md` and `docs/superpowers/specs/2026-11-10-repo-design.md`, including advisory gates, no state file, no MCP, byte-pinned provenance, agent-mediated house rules, and self-contained scripts. Do not re-open settled decisions without new evidence.
- Preserve the intentional recent fixes and known accepted deviations identified in the review request; none is a proposal in this document.
- Keep the skill's tested nine-section dossier structure, factual-source authority, validation behavior, user approval points, and marker-cycle safeguards intact. Improve agent guidance without silently changing workflow semantics.
- Keep `SKILL.md` under 500 lines, retain progressive disclosure, and keep all skill assets/references usable from the packaged skill directory.
- Any future implementation should add or update focused tests where skill instructions, references, or template invariants are guarded. Run `python -m pytest -q -m "not integration"` and `skills-ref validate skills/edcopilot-system-content` before claiming completion.

## Proposals

Ranked by expected effect on successful agent execution.

### 1. Repair the dossier template's stale and unfinished instructions

**Problem — evidence:** The template that both interview workflows call authoritative contains references outside the packaged skill and visible fragments that can be copied into generated dossiers. Examples: `assets/dossier-template.md:66-68` points at `tools/rules/INVENTORY.md`; `:81-92` points at `systems/DECISIONS.md` and `tools/rules/build_types.toml`; `:145-156` points at `tools/rules/raven.toml` and ends a sentence with `parentheses: .`; `:162-166` has an unfinished bridge-dossier reference and ends the broadcast sentence with `:`; `:187-196` includes incomplete text (`The  currently...`, `those 0 goes live`); and `:221-225` sends writers to `tools/README.md`. The skill directs agents to use this template (`SKILL.md:114`; `references/new-system-interview.md:120-121`; `references/update-interview.md:132-133`).

**Proposed change:** Rework the template into a clean, package-local output template: preserve the nine required section headings and validation-relevant structure, but replace unresolved placeholders with explicit fill-in prompts or concise agent instructions, remove or rewrite references to files that are not part of this skill, and finish or remove incomplete sentences. Add a guard test that flags known stale paths and unfinished template fragments while allowing intentional fill-in placeholders.

**Why it matters for an agent:** The dossier is a durable authored artifact and the template is presented as the source of truth. An agent can produce a dossier containing broken links, legacy implementation details, or accidental fragments even while following the interview correctly.

- [x] Accept
- [ ] Reject

### 2. Make the feature-branch offer discoverable in both workflow modes

**Problem — evidence:** The new-system interview explicitly offers a feature branch before Phase 1 and forbids creating one without user consent (`references/new-system-interview.md:12-15`). The update interview has no corresponding early offer. The shared branch guidance is only in `references/workflow-details.md:183-184`, while the spine starts the resume process at `SKILL.md:73` and routes updates at `:78`; an agent following only the named update reference can miss that branch workflow exists or encounter it after work has begun.

**Proposed change:** Put one shared, early branch decision in the spine's common workflow, applicable to both new and update paths: offer before interview/artifact work, start a branch only if the user accepts, and otherwise remain on the current branch. Keep mode-specific references focused on their interviews and link to the shared branch details. Ensure the offer remains before mutations or generated artifacts.

**Why it matters for an agent:** The workflow supports an optional isolation path, but asymmetric instructions make update work more likely to miss it. A single early default prevents late branch creation and ensures the user, not the agent, chooses whether to branch.

- [x] Accept
- [ ] Reject

### 3. De-duplicate the spine and add a compact reference-loading map

**Problem — evidence:** `SKILL.md:63-91` gives the full 16-step process; `:103-129` restates the new/update interview routes; `:131-159` repeats preview, review, restart, logs, and marker guidance; and `:179-192` repeats human-gate principles. Similar detail is also in the interview and workflow references. The information is valuable, but repeated rules make it harder to distinguish the canonical sequence from reminders and consume context on every activation.

**Proposed change:** Retain one concise, canonical process in the spine. Make the new/update sections short routing summaries that identify the relevant interview and key mode-specific difference. Keep fragile operational detail in its relevant reference. Add a small “Read this when” map for the interview references, writing brief, rules, and workflow details; include workflow details early enough to surface root setup and branch guidance. Remove repeated text only after checking that every critical constraint still has one clear home and a direct loading cue.

**Why it matters for an agent:** The skill is already within size limits, but context efficiency and instruction precedence matter for a long, multi-stage workflow. A clear spine lets the agent identify the next step and load only the details needed for that mode without reconciling repeated versions.

- [x] Accept
- [ ] Reject

### 4. Validate description triggering with realistic positive and near-miss prompts

**Problem — evidence:** The description at `SKILL.md:3` meets the specification's basic requirement by naming the work and contexts, but it is descriptive rather than a direct “Use this skill when…” instruction. No trigger-evaluation set or recorded trigger results were found in the reviewed skill materials. The description-optimization guidance identifies triggering as the description's primary job and recommends testing realistic positive and near-miss prompts rather than relying on wording judgment alone.

**Proposed change:** Create a small, versioned trigger-evaluation set (about 16–20 realistic prompts) split between should-trigger cases (new system/station, existing-content refresh, fact-driven updates, StationFact/greeting/chatter/broadcast authoring) and hard should-not-trigger near-misses (adjacent EDCoPilot configuration or unrelated speech-content requests). Run it using the actual target agent's observable skill-loading path. Revise the description only if results show missed or excessive activation; keep the domain boundary explicit and stay within the 1,024-character limit.

**Why it matters for an agent:** A sound workflow has no benefit if the skill is not selected, while an overbroad description adds irrelevant procedure to unrelated requests. Measurement distinguishes a real trigger gap from a stylistic preference and reduces overfitting to a few obvious phrases.

- [x] Accept
- [ ] Reject

## Standards Conformance — Already Met; No Action Proposed

- **Specification structure and metadata:** `SKILL.md` has YAML frontmatter with required `name` and non-empty `description`; its name matches the lowercase skill directory. The optional license, compatibility, and string-valued version metadata are used, and the body is under 500 lines.
- **Progressive disclosure:** Detailed interviews, writing/rule guidance, and operational details are split into focused references and are linked from the spine. Templates are in `assets/`, executable tooling is in `scripts/`.
- **Procedural guidance:** The spine provides a sequential workflow. Definition and content authoring both have explicit validate/fix/re-validate loops before persistence; the update workflow reads exact existing content and limits writes to changed tags. User approval and restart/log/test steps are represented rather than left implicit.
- **Control calibration:** The workflow is prescriptive around fragile file writes, validation, marker handling, and user-consent points, while house rules, content choices, and accepted failures remain user decisions. Defaults are provided for section sizes and environment roots.
- **Gotchas and references:** Non-obvious rules (source authority, landability, exact tag names, marker behavior, staged rewrites, failure cases) are documented in the references used for those phases. No separate global Gotchas section is required merely for its heading; the proposal above addresses the more material issue of the template itself carrying stale guidance.
- **Known accepted deviations:** Reference-internal bare-sibling links, ASCII epilog examples for console compatibility, and configured-root `is_dir` behavior were treated as accepted, not proposed for change.

**Compliance verdict:** Core Agent Skills structure and most best-practice patterns are present. The proposals target output-template correctness, one mode-specific discovery gap, avoidable repetition, and unmeasured description triggering; no spec-mandated metadata or directory-structure defect was identified. This was a static review, not a runtime validation or trigger benchmark.
