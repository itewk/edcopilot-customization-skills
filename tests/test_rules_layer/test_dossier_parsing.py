"""Guards for the extracted dossier parser (proposal 5)."""

from edcg.rules.dossier import extract_voices, known_token_names
from edcg.rules.validation import RULE_DATA_DIR, load_base_config


def test_vocabulary_token_is_not_a_voice():
    """<Nice> is an EDCoPilot substitution, so the voice list must drop it."""
    vocab = load_base_config(RULE_DATA_DIR)["vocab"]
    known_tokens = {name.lower() for name in known_token_names(vocab)}
    assert "nice" in known_tokens

    lines = [
        "### Voices used",
        "- [<Nice>] opens the greeting",
        "- [<Ada>] answers the hail",
    ]

    assert extract_voices(lines, known_tokens) == {"Ada"}


def test_voice_exclusion_comes_from_the_supplied_token_set():
    """Without the vocabulary set the token is legitimately a voice.

    This pins the extraction to the caller's rule data: hardcoding the token
    list inside the parser would make this assertion fail.
    """
    lines = ["### Voices used", "[<Nice>]"]

    assert extract_voices(lines, set()) == {"Nice"}
