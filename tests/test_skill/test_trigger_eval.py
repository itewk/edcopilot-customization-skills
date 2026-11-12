"""Trigger-evaluation tests for the skill description.

The description has one primary job: selection. The optimization methodology
says to test it with realistic positive prompts and hard near-misses rather than
to judge the wording by eye, and to revise it only when the results show a
missed or an excessive activation.

``trigger_eval_cases.json`` is that evaluation set: ten should-trigger prompts
(new system, new station, refresh, fact-driven update, and each content kind)
and ten should-not-trigger prompts. Three of the negatives are *hard*
near-misses: they name the domain and the artefacts ("our EDCoPilot chatter
file", "the dossier files", "the broadcast file") but ask for a different job
(proofreading, renaming, reading a diff), so they test over-triggering rather
than mere absence of vocabulary.

The set has two halves, recorded separately:

- **Static grading** (``static_run``) runs here and is deterministic: a prompt
  grades as a trigger when it names the domain, names one of the artefacts, and
  asks for authoring or updating work. That is a vocabulary-and-intent check
  against the description, not a measurement of the agent.
- **Live activation** (``live_run``) needs the target agent's observable
  skill-loading path: feed each prompt to the agent and record whether this
  skill loaded. It is explicitly ``pending_live_run``; the tests assert that
  state rather than pretending the run happened, and they reject a completed
  record that contains a miss or an over-trigger.

The description itself is left alone unless a recorded live run shows a failure.
"""

import json
import re
from pathlib import Path

import pytest

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "edcopilot-system-content"
)
SKILL_MD = SKILL_DIR / "SKILL.md"
CASES = Path(__file__).parent / "trigger_eval_cases.json"

# The three conditions a request must meet to be this skill's work.
#   domain   — what the skill is about;
#   content  — the artefacts it produces;
#   authoring — the job: write, refresh, update, author. Review, rename,
#               proofread, install, configure and summarise are deliberately
#               absent, because those are the near-misses' jobs.
DOMAIN_TERMS = ("edcopilot", "elite dangerous", "colonis")
CONTENT_TERMS = (
    "speech extension",
    "greeting",
    "chatter",
    "broadcast",
    "stationfact",
    "dossier",
    "content",
)
AUTHORING_RE = re.compile(
    r"\b(write|add|update|refresh|draft|author|rewrite|generate)\b|set up"
)


def _data() -> dict:
    return json.loads(CASES.read_text(encoding="utf-8"))


def _cases() -> list[dict]:
    return _data()["cases"]


def _prompts(should_trigger: bool) -> list[dict]:
    return [case for case in _cases() if case["should_trigger"] is should_trigger]


def _description() -> str:
    """The single-line description value from the SKILL.md frontmatter."""
    text = SKILL_MD.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            return line.partition(":")[2].strip()
    raise AssertionError("SKILL.md frontmatter has no description")


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_trigger(case: dict) -> bool:
    """Grade one prompt: domain + artefact + authoring intent."""
    prompt = case["prompt"].lower()
    return (
        _has_any(prompt, DOMAIN_TERMS)
        and _has_any(prompt, CONTENT_TERMS)
        and bool(AUTHORING_RE.search(prompt))
    )


def _is_hard_near_miss(case: dict) -> bool:
    """A near-miss that names the domain and an artefact, but not the job."""
    prompt = case["prompt"].lower()
    return (
        not case["should_trigger"]
        and _has_any(prompt, DOMAIN_TERMS)
        and _has_any(prompt, CONTENT_TERMS)
    )


class TestEvaluationSet:
    """The set has to stay realistic, balanced and versioned."""

    def test_set_is_versioned_for_the_skill(self):
        data = _data()
        assert data["version"] == 1
        assert data["skill"] == SKILL_DIR.name
        assert "positive" in data["method"] and "near-miss" in data["method"]

    def test_set_size_is_in_the_methodology_range(self):
        cases = _cases()
        assert 16 <= len(cases) <= 20, f"{len(cases)} cases; the set wants 16-20"
        assert 8 <= len(_prompts(True)) <= 12
        assert 6 <= len(_prompts(False)) <= 10

    def test_case_ids_are_unique(self):
        ids = [case["id"] for case in _cases()]
        assert len(ids) == len(set(ids))
        for case in _cases():
            assert isinstance(case["should_trigger"], bool)

    def test_prompts_are_not_copied_from_the_description(self):
        """A prompt lifted from the description measures nothing."""
        description = _description().lower()
        for case in _cases():
            assert case["prompt"].lower() not in description, case["id"]

    def test_positive_prompts_span_both_workflows_and_every_content_kind(self):
        prompts = " ".join(case["prompt"].lower() for case in _prompts(True))
        assert "new" in prompts and "update" in prompts
        for mention in ("greeting", "chatter", "broadcast", "stationfact"):
            assert mention in prompts, f"no positive prompt asks for {mention}"

    def test_the_set_carries_three_hard_near_misses(self):
        """Over-triggering needs prompts that share the vocabulary, not just lack it."""
        hard = [case for case in _cases() if _is_hard_near_miss(case)]
        assert len(hard) >= 3, [case["id"] for case in hard]


class TestStaticRun:
    """The deterministic half of the evaluation: grade every case, as designed."""

    def test_every_case_grades_as_labelled(self):
        wrong = [
            case["id"]
            for case in _cases()
            if _is_trigger(case) is not case["should_trigger"]
        ]
        assert not wrong, f"the grading rule disagrees with the set: {wrong}"

    def test_static_run_record_matches_a_fresh_grading(self):
        data = _data()
        record = data["static_run"]
        assert record["performed"] is True
        assert record["version"] == data["version"]
        failed = [
            case["id"]
            for case in data["cases"]
            if _is_trigger(case) is not case["should_trigger"]
        ]
        assert record["graded"] == len(data["cases"])
        assert record["failed"] == failed


class TestPositiveTriggerVocabulary:
    """Every should-trigger prompt is domain plus content plus authoring."""

    @pytest.mark.parametrize("case", _prompts(True), ids=lambda case: case["id"])
    def test_positive_prompt_names_the_domain_and_the_content(self, case):
        prompt = case["prompt"].lower()
        assert _has_any(prompt, DOMAIN_TERMS), "not an in-domain prompt"
        assert _has_any(prompt, CONTENT_TERMS), "prompt asks for none of the skill's output"

    def test_description_covers_every_keyword_the_positives_use(self):
        """Each trigger word a positive relies on must appear in the description.

        This is per-keyword, not per-case: if a positive says "chatter" and
        "broadcast", the description must name both. It measures vocabulary
        coverage only; activation is the live run's job.
        """
        description = _description().lower()
        for case in _prompts(True):
            prompt = case["prompt"].lower()
            for term in DOMAIN_TERMS + CONTENT_TERMS:
                if term in prompt:
                    assert term in description, (
                        f"{case['id']} uses {term!r}, "
                        "which the description never names"
                    )


class TestNearMisses:
    """A near-miss shares vocabulary and still asks for a different job."""

    @pytest.mark.parametrize("case", _prompts(False), ids=lambda case: case["id"])
    def test_near_miss_shares_skill_vocabulary(self, case):
        prompt = case["prompt"].lower()
        assert _has_any(prompt, DOMAIN_TERMS) or _has_any(prompt, CONTENT_TERMS), (
            "a near-miss needs skill vocabulary, or it tests nothing"
        )

    @pytest.mark.parametrize("case", _prompts(False), ids=lambda case: case["id"])
    def test_near_miss_lacks_a_trigger_condition(self, case):
        """No near-miss may satisfy all three conditions at once.

        A near-miss is allowed to name the domain *and* the artefacts, as the
        proofread/rename/diff cases do; what it must not do is ask for the
        authoring work. The description's keyword coverage alone must therefore
        not be read as activation.
        """
        assert not _is_trigger(case), (
            f"{case['id']} asks for the skill's work, so it is not a near-miss"
        )

    @pytest.mark.parametrize(
        "case",
        [case for case in _cases() if _is_hard_near_miss(case)],
        ids=lambda case: case["id"],
    )
    def test_hard_near_miss_differs_by_intent_not_vocabulary(self, case):
        prompt = case["prompt"].lower()
        assert _has_any(prompt, DOMAIN_TERMS) and _has_any(prompt, CONTENT_TERMS)
        assert not AUTHORING_RE.search(prompt), (
            "a hard near-miss must ask for review/rename/diff/configuration "
            "work, not authoring work"
        )

    def test_description_states_the_domain_boundary(self):
        """Exclusion has to be written down, not left to the reader."""
        description = _description().lower()
        assert "colonisation systems" in description
        assert "elite dangerous" in description
        assert "speech extensions" in description
        assert len(description) <= 1024


class TestLiveRunRecord:
    """The agent half is tracked explicitly, and a completed run must be clean."""

    def test_live_run_state_is_explicit(self):
        run = _data()["live_run"]
        assert run["performed"] in ("pending_live_run", True, False)
        if run["performed"] == "pending_live_run":
            assert run["results"] == []
            assert run["agent"] is None
            assert "pending" in run["note"].lower()
            return
        if run["performed"] is False:
            assert run["results"] == []
            return
        assert run["agent"], "a performed run names the agent it was run against"
        expected = {case["id"]: case["should_trigger"] for case in _cases()}
        recorded = {result["id"]: result["fired"] for result in run["results"]}
        assert set(recorded) == set(expected)

    def test_completed_live_run_has_no_misses_or_over_triggers(self):
        run = _data()["live_run"]
        if run["performed"] is not True:
            pytest.skip(f"live agent run is {run['performed']!r}")
        expected = {case["id"]: case["should_trigger"] for case in _cases()}
        wrong = [
            result["id"]
            for result in run["results"]
            if result["fired"] is not expected[result["id"]]
        ]
        assert not wrong, (
            "the description needs revising before this run can be recorded: "
            f"wrong activation for {wrong}"
        )
