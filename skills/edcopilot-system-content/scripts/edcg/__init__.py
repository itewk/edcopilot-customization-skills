"""EDCoPilot system-content skill scripts.

``__version__`` is the skill's release version; ``SKILL.md`` metadata and the
CLI's ``version`` subcommand both report it. The provenance string written into
the custom file carries the same release version (see
``edcg.content.custom_file.VERSION``); ``PROVENANCE_RE`` matches the comment
format, not the version, so markers from older builds still parse.
"""

__version__ = "1.0.0-alpha.3"
