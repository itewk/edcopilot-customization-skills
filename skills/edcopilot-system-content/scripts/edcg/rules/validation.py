"""Validation engine for EDCoPilot customization content.

Implements all rules from base.toml + all.rules.toml + system.rules.toml.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edcg.common.config import get_config
from edcg.common.layout import PROVENANCE_RE, systems_dir as layout_systems_dir
from edcg.rules.dossier import (
    _parse_dossier_sections,
    _extract_site_table,
    _get_landable_build_types,
    _extract_voices_from_section_8,
    _normalize_station_name,
    _is_descriptive,
    _parse_station_list,
    _starts_simple_station_list,
    _extract_stations_from_section_7
)

# Rule data ships beside the validation module as package data.
RULE_DATA_DIR = Path(__file__).resolve().parent / "data"

# ---------------------------------------------------------------------------
# Constants and regex patterns
# ---------------------------------------------------------------------------

SEV_ORDER = {"error": 0, "warn": 1, "info": 2}

TAG_RE = re.compile(r"^@(?P<kind>[A-Za-z_]+)(?P<rest>.*)$")
TOKEN_RE = re.compile(r"<([A-Za-z][A-Za-z0-9_]*)>")
VOICE_RE = re.compile(r"\[<([^>]+)>\]")
MARKER_RE = re.compile(r"\(([A-Za-z_]+)\)")
# Where a filter marker may sit: leading the line, or leading a character's
# chunk after a voice tag. A marker anywhere else is not a filter, it is text.
FILTER_CHUNK_RE = re.compile(r"(?:^|(?<=\]))\s*((?:\([A-Za-z_]+\))+)")
URL_RE = re.compile(r"(?i)\b(?:https?://|ftp://|www\.)\S+")
COMMANDER_WORD = re.compile(r"\bCommanders?\b")
TOKEN_SPAN = re.compile(r"<[^>]*>")
SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
CELL_TOKEN_RE = re.compile(r"^\s*\**\s*`([^`]+)`")
BUILD_TYPE_CELL_RE = re.compile(r"^\s*\**\s*`([a-z][a-z0-9_]*)`")

POLICY = "policy"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Kind:
    """A tag kind as declared in [kinds]."""
    parts: tuple[str, ...] = ()
    spoken: bool = False


@dataclass
class Phrase:
    """A single phrase line under a tag."""
    line: int
    raw: str

    @property
    def filters(self) -> list[str]:
        """The filter markers the phrase carries."""
        return [
            name
            for chunk in FILTER_CHUNK_RE.findall(self.raw)
            for name in MARKER_RE.findall(chunk)
        ]

    @property
    def voices(self) -> list[str]:
        return VOICE_RE.findall(self.raw)

    @property
    def tokens(self) -> list[str]:
        return TOKEN_RE.findall(self.raw)

    @property
    def plain(self) -> str:
        """Phrase text with filters, voice tags and tokens removed."""
        s = FILTER_CHUNK_RE.sub("", self.raw)
        s = VOICE_RE.sub(" ", s)
        s = re.sub(r"<[^>]+>", " ", s)
        return s


@dataclass
class Tag:
    """A tag and its associated phrases."""
    kind: str
    parts: list[str]
    line: int
    decl: Kind | None = None
    phrases: list[Phrase] = field(default_factory=list)
    marker_line: int | None = None
    imports: list[tuple[int, str]] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def _part(self, role: str) -> str | None:
        """The field this kind declares for `role`, when the tag carries it."""
        roles = self.decl.parts if self.decl else ()
        if role not in roles:
            return None
        idx = roles.index(role)
        return self.parts[idx] if idx < len(self.parts) else None

    @property
    def system(self) -> str | None:
        return self._part("system")

    @property
    def station(self) -> str | None:
        return self._part("station")

    @property
    def spoken(self) -> bool:
        return bool(self.decl and self.decl.spoken)

    @property
    def label(self) -> str:
        bits = [b for b in (self.system, self.station) if b]
        return " / ".join(bits) if bits else self.kind

    @property
    def allbusiness(self) -> int:
        return sum(1 for p in self.phrases if "allbusiness" in p.filters)


@dataclass
class Finding:
    """A validation finding."""
    rule: str
    severity: str
    line: int | None
    message: str


@dataclass
class ValidationResult:
    """Result of validation."""
    findings: list[Finding]
    passed: bool
    rule_summary: list[dict] = field(default_factory=list)
    rule_table: str = ""


@dataclass
class SaveResult:
    """Result of saving a system definition."""
    commit_hash: str | None
    files_changed: list[str]


@dataclass
class Content:
    """Parsed content file."""
    path: Path
    lines: list[str]
    line_ending: str | None
    bom: bool
    provenance: list[tuple[int, dict]]
    tags: list[Tag]
    unknown_kinds: list[tuple[int, str]] = field(default_factory=list)

    @property
    def authored_from(self) -> int | None:
        return self.provenance[0][0] if self.provenance else None

    def in_scope(self, line: int | None) -> bool:
        if line is None:
            return True
        return self.authored_from is None or line >= self.authored_from

    def authored_tags(self) -> list[Tag]:
        return [t for t in self.tags if self.in_scope(t.line)]


@dataclass
class Context:
    """Validation context passed to rule functions."""
    base: dict
    per_system: dict[str, dict]
    content: Content
    rules: dict[str, dict]
    findings: list[Finding] = field(default_factory=list)

    def dossier_paths(self) -> list[Path]:
        """Every dossier a per-system file declares, in a stable order."""
        declared: dict[str, Path] = {}
        for cfg in self.per_system.values():
            # Prefer pre-resolved _dossier_path from load_all_system_rules
            if "_dossier_path" in cfg:
                declared[cfg.get("system", {}).get("dossier", "")] = cfg["_dossier_path"]
            else:
                rel = cfg.get("system", {}).get("dossier")
                if rel:
                    declared[rel] = Path(rel)
        return [declared[rel] for rel in sorted(declared)]

    def rule(self, rule_id: str, system: str | None = None) -> dict:
        """Get rule config with per-system overrides applied."""
        cfg = dict(self.rules.get(rule_id, {}))
        if system and system in self.per_system:
            patch = self.per_system[system].get("overrides", {}).get(rule_id)
            if patch:
                cfg.update(patch)
        return cfg

    def add(self, rule_id: str, severity: str, line: int | None, message: str) -> None:
        """Add a finding if rule is not retired (severity != off)."""
        if self.rule(rule_id).get("severity", "error") == "off":
            return
        self.findings.append(Finding(rule=rule_id, severity=severity, line=line, message=message))

    def vocab(self, key: str) -> list[str]:
        return self.base.get("vocab", {}).get(key, [])

    def known_tokens(self) -> dict[str, str]:
        """{lower-cased token -> canonical spelling}, documented and not."""
        vocab = self.base.get("vocab", {})
        names = list(vocab.get("documented", {})) + list(vocab.get("undocumented", []))
        return {name.lower(): name for name in names}

    def known_filters(self) -> set[str]:
        """Every filter the content may carry, documented or merely in use."""
        cfg = self.rule("syntax.filter_known")
        return set(cfg.get("filters", {})) | set(cfg.get("undocumented", []))


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------

def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _flatten_rules(tree: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    """Flatten nested rule tables into dotted rule IDs.
    
    A table declares a rule when it names an implementation, `impl = "rule_..."`
    for a check or `impl = "policy"` for a requirement a reader checks. A table
    with no `impl` and a plain value of its own changes the rule named by its
    path, giving only the keys that change.
    """
    rules: dict[str, dict] = {}
    patches: dict[str, dict] = {}

    def walk(path: str, node: dict) -> None:
        if "impl" in node:
            rules[path] = node
            return
        if any(not isinstance(v, dict) for v in node.values()):
            if path:
                patches[path] = node
            return
        for key, child in node.items():
            walk(f"{path}.{key}" if path else key, child)

    for key, node in tree.items():
        if isinstance(node, dict):
            walk(key, node)
    return rules, patches


def _reject_patches(known: set[str], patches: dict[str, dict], where: str) -> None:
    """A patch naming no rule is a typo."""
    unknown = sorted(set(patches) - known)
    if unknown:
        raise ValueError(
            f"{where} changes {', '.join(unknown)}, which no rule declares"
        )


ALL_RULES = "all.rules.toml"


def load_base_config(rules_dir: Path) -> dict:
    """Load base.toml and build_types.toml from the rules directory."""
    base = _load_toml(rules_dir / "base.toml")
    rules, patches = _flatten_rules(base.get("rules", {}))
    _reject_patches(set(rules), patches, "base.toml")
    base["rules"] = rules
    base["build_types"] = _load_toml(rules_dir / "build_types.toml")
    return base


def load_house_rules(house_path: Path | None, base_rules: dict[str, dict]) -> tuple[dict, dict[str, dict]]:
    """Load house rules (all.rules.toml) and return (declared_rules, patches)."""
    if not house_path or not house_path.exists():
        return {}, {}
    
    overlay = _load_toml(house_path)
    declared, patches = _flatten_rules(overlay.get("rules", {}))
    _reject_patches(set(base_rules) | set(declared), patches, "house rules")
    return declared, patches


def load_system_rules(system_path: Path | None, base_rules: dict[str, dict]) -> dict[str, dict]:
    """Load system rules and return per-system config with overrides."""
    if not system_path or not system_path.exists():
        return {}
    
    cfg = _load_toml(system_path)
    declared, patches = _flatten_rules(cfg.get("rules", {}))
    if declared:
        raise ValueError(f"System rules may not declare new rules: {', '.join(declared)}")
    _reject_patches(set(base_rules), patches, "system rules")
    
    per_system: dict[str, dict] = {}
    for name in cfg.get("system", {}).get("names", []):
        per_system[name] = {"overrides": patches, "system": cfg.get("system", {})}
    return per_system


def load_all_system_rules(systems_dir: Path, base_rules: dict[str, dict]) -> dict[str, dict]:
    """Load all system rules from every systems/*.rules.toml file."""
    paths = sorted(systems_dir.glob("*.rules.toml"))
    system_paths = [p for p in paths if p.name != ALL_RULES]
    if not system_paths:
        return {}
    
    per_system: dict[str, dict] = {}
    for path in system_paths:
        cfg = _load_toml(path)
        declared, patches = _flatten_rules(cfg.get("rules", {}))
        if declared:
            raise ValueError(f"{path.name} declares {', '.join(sorted(declared))}: a rule that "
                          f"applies to every system belongs in systems/{ALL_RULES}")
        _reject_patches(set(base_rules), patches, path.name)
        cfg["overrides"] = patches
        for name in cfg.get("system", {}).get("names", []):
            per_system[name] = cfg
    for name, cfg in per_system.items():
        rel = cfg.get("system", {}).get("dossier")
        if not rel:
            raise ValueError(f"{cfg.get('_path', path.name)} declares no dossier for {name}")
        # Resolve dossier path: try systems_dir first (for test setups), then parent (for production)
        dossier_path = systems_dir / rel
        if not dossier_path.exists():
            # Fall back to parent directory (production layout: systems/ under repo root)
            dossier_path = systems_dir.parent / rel
        if not dossier_path.exists():
            raise ValueError(f"dossier for {name} not found at {systems_dir / rel} or {systems_dir.parent / rel}")
        cfg["_dossier_path"] = dossier_path
    return per_system


def merge_rules(
    base_rules: dict[str, dict],
    house_declared: dict[str, dict],
    house_patches: dict[str, dict],
    system_overrides: dict[str, dict]
) -> dict[str, dict]:
    """Merge base, house, and system rules following precedence order.
    
    Precedence: base.toml → house (all.rules.toml) → system (system.rules.toml)
    House rules can declare new rules (with impl) and override.
    System rules can only override (no new impl).
    """
    import copy
    merged = copy.deepcopy(base_rules)
    
    # Apply house declared rules (new rules)
    for rule_id, rule_cfg in house_declared.items():
        merged[rule_id] = rule_cfg
    
    # Apply house patches (overrides)
    for rule_id, patch in house_patches.items():
        if rule_id in merged:
            merged[rule_id] = {**merged[rule_id], **patch}
    
    # Apply system patches (overrides only)
    for system_name, system_cfg in system_overrides.items():
        for rule_id, patch in system_cfg.get("overrides", {}).items():
            if rule_id in merged:
                merged[rule_id] = {**merged[rule_id], **patch}
    
    return merged


# ---------------------------------------------------------------------------
# Content parsing
# ---------------------------------------------------------------------------

def parse_kv(body: str) -> dict:
    """Parse key=value pairs from provenance body."""
    out = {}
    for m in re.finditer(r"([A-Za-z_]+)\s*=\s*([^,]+)", body):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def load_kinds(base: dict) -> dict[str, Kind]:
    """Load tag kinds from base config."""
    return {
        name: Kind(parts=tuple(cfg.get("parts", [])), spoken=bool(cfg.get("spoken", False)))
        for name, cfg in base.get("kinds", {}).items()
    }


def parse_content(path: Path, prov_pattern: re.Pattern, kinds: dict[str, Kind]) -> Content:
    """Parse content file into structured representation."""
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    # A single unterminated line carries no line ending to judge, so it must not
    # be reported as LF (which would fail a CRLF-required rule).
    if "\r\n" in text:
        ending = "crlf"
    elif "\n" in text:
        ending = "lf"
    else:
        ending = None
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    provenance: list[tuple[int, dict]] = []
    tags: list[Tag] = []
    unknown: list[tuple[int, str]] = []
    current: Tag | None = None
    
    for idx, line in enumerate(lines, start=1):
        m = prov_pattern.match(line)
        if m:
            provenance.append((idx, parse_kv(m.group("body"))))
            continue
        tm = TAG_RE.match(line)
        if tm:
            rest = tm.group("rest")
            parts = [p.strip() for p in rest.split("<~>") if p.strip()] if "<~>" in rest else []
            kind = tm.group("kind")
            if kind in kinds:
                current = Tag(kind=kind, parts=parts, line=idx, decl=kinds[kind])
                tags.append(current)
            else:
                unknown.append((idx, kind))
                current = None
            continue
        if current is None:
            continue
        if not line.strip():
            current = None
            continue
        if line.startswith("<!--"):
            continue
        if line.strip() == "UPDATEDB":
            current.marker_line = idx
            continue
        if line.startswith("img_url="):
            current.imports.append((idx, line.strip()[len("img_url="):].strip()))
            continue
        current.phrases.append(Phrase(line=idx, raw=line))

    for tag in tags:
        for pln, pv in provenance:
            if pln < tag.line:
                tag.provenance = pv
            else:
                break
                
    return Content(
        path=path, lines=lines, line_ending=ending, bom=bom,
        provenance=provenance, tags=tags, unknown_kinds=unknown
    )


# ---------------------------------------------------------------------------
# Build type utilities
# ---------------------------------------------------------------------------

def build_type_classes(base: dict) -> dict[str, tuple[str, str]]:
    """{build type -> (class, facility name)}, from the Raven facility table."""
    out: dict[str, tuple[str, str]] = {}
    for cls, tokens in base.get("build_types", {}).get("classes", {}).items():
        for token, facility in tokens.items():
            out[token] = (cls, facility)
    return out


def _cell_name(cell: str) -> str:
    m = CELL_TOKEN_RE.match(cell)
    return (m.group(1) if m else cell).strip().strip("*").strip()


def _site_rows(ctx: Context):
    """Every dossier table row that classifies exactly one site."""
    for path in ctx.dossier_paths():
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            hits = [(i, m.group(1)) for i, c in enumerate(cells)
                    if (m := BUILD_TYPE_CELL_RE.match(c))]
            if len(hits) == 1:
                yield cells, hits[0][0], hits[0][1], path.name


def dossier_build_types(ctx: Context, wanted: set[str]) -> dict[str, tuple[str, str]]:
    """{station name -> (build type, dossier)} for the stations that have content."""
    found: dict[str, tuple[str, str]] = {}
    for cells, _idx, build_type, dossier in _site_rows(ctx):
        for name in {_cell_name(c) for c in cells} & wanted:
            found.setdefault(name, (build_type, dossier))
    return found


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------

def rule_syntax_filter_known(ctx: Context) -> None:
    cfg = ctx.rule("syntax.filter_known")
    known = ctx.known_filters()
    for idx, line in enumerate(ctx.content.lines, start=1):
        found = [name for chunk in FILTER_CHUNK_RE.findall(line)
                 for name in MARKER_RE.findall(chunk)]
        unknown = [name for name in found if name not in known]
        if not unknown:
            continue
        token = unknown[0]
        if ctx.content.in_scope(idx):
            ctx.add("syntax.filter_known", cfg["severity"], idx,
                    f"unknown filter ({token}) - not stripped, and spoken aloud")
        else:
            ctx.add("syntax.filter_known", cfg.get("severity_outside_scope", "warn"), idx,
                    f"unknown filter ({token}) in EDCoPilot's default content - left alone deliberately")


def rule_syntax_filter_leads(ctx: Context) -> None:
    """A filter marker in front of a character line's first voice tag."""
    cfg = ctx.rule("syntax.filter_leads")
    known = ctx.known_filters()
    for tag in ctx.content.authored_tags():
        for p in tag.phrases:
            voice = VOICE_RE.search(p.raw)
            if not voice:
                continue
            ahead = [m.group(1) for m in MARKER_RE.finditer(p.raw[:voice.start()])]
            if any(name in known for name in ahead):
                ctx.add("syntax.filter_leads", cfg["severity"], p.line,
                        "filter marker before the first voice tag - it is spoken "
                        "as a phrase of its own; put it after the tag")


def rule_syntax_voice_name(ctx: Context) -> None:
    """A voice name is one token: whitespace ends the tag."""
    cfg = ctx.rule("syntax.voice_name")
    severity = cfg.get("severity", "warn")

    reported: set[tuple[int, str]] = set()
    systems_in_content: set[str] = set()
    for tag in ctx.content.authored_tags():
        if tag.system:
            systems_in_content.add(tag.system)
        for phrase in tag.phrases:
            for voice in phrase.voices:
                if not any(ch.isspace() for ch in voice):
                    continue
                if (phrase.line, voice) in reported:
                    continue
                reported.add((phrase.line, voice))
                ctx.add(
                    "syntax.voice_name",
                    severity,
                    phrase.line,
                    f"voice name {voice!r} contains whitespace - "
                    "a voice name is one token",
                )

    for system in sorted(systems_in_content):
        system_cfg = ctx.per_system.get(system, {})
        for voice in system_cfg.get("system", {}).get("voices", []):
            if not any(ch.isspace() for ch in voice):
                continue
            ctx.add(
                "syntax.voice_name",
                severity,
                None,
                f"declared voice {voice!r} for {system} contains whitespace - "
                "a voice name is one token",
            )


def rule_syntax_tokens(ctx: Context) -> None:
    """Checks both token_known and token_case in one pass."""
    known_cfg = ctx.rule("syntax.token_known")
    case_cfg = ctx.rule("syntax.token_case")
    builtin = ctx.known_tokens()
    unknown: dict[str, list[int]] = {}
    miscased: dict[str, list[int]] = {}
    
    for tag in ctx.content.authored_tags():
        voices = {v.lower() for v in ctx.per_system.get(tag.system or "", {}).get("system", {}).get("voices", [])}
        for p in tag.phrases:
            for tok in p.tokens:
                low = tok.lower()
                canon = builtin.get(low)
                if canon is None and low not in voices:
                    unknown.setdefault(tok, []).append(p.line)
                elif canon is not None and tok != canon:
                    miscased.setdefault(tok, []).append(p.line)
    
    for tok, lines in sorted(unknown.items()):
        ctx.add("syntax.token_known", known_cfg["severity"], lines[0],
                f"<{tok}> is neither a built-in token nor a declared voice "
                f"({len(lines)} uses); declare the voice in the dossier's "
                "Voices section and in the system rules file")
    for tok, lines in sorted(miscased.items()):
        ctx.add("syntax.token_case", case_cfg["severity"], lines[0],
                f"<{tok}> is a built-in token written in another case; write "
                f"<{builtin[tok.lower()]}> ({len(lines)} uses)")


def rule_syntax_encoding(ctx: Context) -> None:
    cfg = ctx.rule("syntax.encoding")
    want = ctx.base.get("content", {})
    c = ctx.content
    if c.line_ending is not None and c.line_ending != want.get("line_ending", "crlf"):
        ctx.add("syntax.encoding", cfg["severity"], None,
                f"content line ending is {c.line_ending}, expected {want.get('line_ending')}")
    if c.bom != want.get("bom", False):
        ctx.add("syntax.encoding", cfg["severity"], None, "content file has a BOM")


def rule_syntax_no_example_wrapper(ctx: Context) -> None:
    cfg = ctx.rule("syntax.no_example_wrapper")
    pat = re.compile(r"\[example\]|\[\\example\]", re.IGNORECASE)
    for idx, line in enumerate(ctx.content.lines, start=1):
        if line.startswith("<!--"):
            continue
        if pat.search(line):
            ctx.add("syntax.no_example_wrapper", cfg["severity"], idx,
                    "[example] wrapper belongs to the chatter files, not here")


def rule_format_tag_shape(ctx: Context) -> None:
    """The tag line itself: a kind the rules know, carrying the fields it declares."""
    cfg = ctx.rule("format.tag_shape")
    for line, kind in ctx.content.unknown_kinds:
        ctx.add("format.tag_shape", cfg["severity"], line,
                f"@{kind} is a tag kind the rule set does not know - add it to [kinds] "
                f"in the base rule set, or every line under it goes unchecked")
    for tag in ctx.content.tags:
        roles = tag.decl.parts if tag.decl else ()
        if len(tag.parts) != len(roles):
            shape = ", ".join(roles) if roles else "no fields"
            ctx.add("format.tag_shape", cfg["severity"], tag.line,
                    f"@{tag.kind} carries {len(tag.parts)} <~> field(s); its shape is "
                    f"{len(roles)} ({shape})")


def rule_filters_banned(ctx: Context) -> None:
    """A filter the declaring rule forbids, wherever it appears in scope."""
    cfg = ctx.rule("filters.banned")
    banned = set(cfg.get("tokens", []))
    for tag in ctx.content.authored_tags():
        for p in tag.phrases:
            hit = banned.intersection(p.filters)
            if hit:
                ctx.add("filters.banned", cfg["severity"], p.line,
                        f"banned filter ({sorted(hit)[0]}) - content this rule forbids")


def rule_filters_allbusiness(ctx: Context) -> None:
    cfg = ctx.rule("filters.allbusiness")
    applies = set(cfg.get("applies_to", []))
    for tag in ctx.content.authored_tags():
        if tag.kind not in applies:
            continue
        n = tag.allbusiness
        target = ctx.rule("filters.allbusiness", tag.system)
        threshold = int(target.get("warn_below_by_kind", {}).get(
            tag.kind, target.get("warn_below", 1)))
        if n == 0:
            ctx.add("filters.allbusiness", target["severity"], tag.line,
                    f"{tag.label} has no (allbusiness) line - silent in All Business mode")
        elif n < threshold:
            ctx.add("filters.allbusiness", "warn", tag.line,
                    f"{tag.label} has {n} (allbusiness) line(s); {threshold} is the pattern for {tag.kind}")


def rule_filters_fallback(ctx: Context) -> None:
    """Whatever a tag's filters are, every player must still hear something."""
    cfg = ctx.rule("filters.fallback")
    for tag in ctx.content.authored_tags():
        if not tag.spoken:
            continue
        if not [p for p in tag.phrases if not p.filters]:
            ctx.add("filters.fallback", cfg["severity"], tag.line,
                    f"{tag.label} filters every line - a player with that mode set "
                    f"hears nothing here")
        elif cfg.get("require_allbusiness_clean", True) and \
                not [p for p in tag.phrases if set(p.filters) == {"allbusiness"}]:
            ctx.add("filters.fallback", cfg["severity"], tag.line,
                    f"{tag.label} has no line carrying (allbusiness) alone - a player in "
                    f"All Business mode with any mode set hears nothing")


def rule_content_fact_image(ctx: Context) -> None:
    cfg = ctx.rule("content.fact_image")
    expected = cfg.get("expected")
    for tag in ctx.content.authored_tags():
        if tag.kind != "StationFact":
            continue
        if not tag.imports:
            ctx.add("content.fact_image", cfg["severity"], tag.line,
                    f"{tag.label} has no img_url line - the fact page renders as text alone")
            continue
        if not expected:
            continue
        for line_no, url in tag.imports:
            if url != expected:
                ctx.add("content.fact_image", "warn", line_no,
                        f"img_url is not the shared logo: {url}")


def rule_content_no_links(ctx: Context) -> None:
    """No link in the text the copilot speaks or puts on a fact page."""
    cfg = ctx.rule("content.no_links")
    for tag in ctx.content.authored_tags():
        for p in tag.phrases:
            m = URL_RE.search(p.raw)
            if m:
                ctx.add("content.no_links", cfg["severity"], p.line,
                        f"a link ({m.group(0)[:48]}) is spoken as text - a picture belongs on "
                        f"a Station Fact's img_url= line")


def rule_content_fact_no_filters(ctx: Context) -> None:
    cfg = ctx.rule("content.fact_no_filters")
    for tag in ctx.content.authored_tags():
        if tag.kind != "StationFact":
            continue
        for p in tag.phrases:
            if p.filters:
                ctx.add("content.fact_no_filters", cfg["severity"], p.line,
                        f"fact text carries ({p.filters[0]}), and a fact takes no filters - "
                        f"it is a page, so nothing strips it")


def rule_content_station_landable(ctx: Context) -> None:
    cfg = ctx.rule("content.station_landable")
    classes = build_type_classes(ctx.base)
    not_landable = set(cfg.get("not_landable_classes", ["hub", "installation"]))

    by_station: dict[str, list[Tag]] = {}
    for tag in ctx.content.authored_tags():
        if tag.station:
            by_station.setdefault(tag.station, []).append(tag)

    sites = dossier_build_types(ctx, set(by_station))

    for station, tags in by_station.items():
        kinds = " and ".join(sorted({t.kind for t in tags}))
        hit = sites.get(station)
        if not hit:
            ctx.add("content.station_landable", cfg["severity"], tags[0].line,
                    f"{station} is classified in no dossier site table ({kinds}) - "
                    f"its landability is unknown, so nothing checks it")
            continue
        build_type, dossier = hit
        entry = classes.get(build_type)
        if entry is None:
            ctx.add("content.station_landable", "warn", tags[0].line,
                    f"{station} has build type {build_type}, which is not in the Raven "
                    f"facility table ({dossier}) - confirm whether it can be landed at")
        elif entry[0] in not_landable:
            ctx.add("content.station_landable", cfg["severity"], tags[0].line,
                    f"{station} is a {build_type} {entry[1]} ({entry[0]}, no landing "
                    f"pads): EDCoPilot plays no {kinds} for it, so this content can "
                    f"never be heard")


def rule_content_commander_token(ctx: Context) -> None:
    cfg = ctx.rule("content.commander_token")
    for tag in ctx.content.authored_tags():
        for p in tag.phrases:
            prose = TOKEN_SPAN.sub(" ", p.raw)  # <Commander> is the fix, not the fault
            hits = COMMANDER_WORD.findall(prose)
            if not hits:
                continue
            count = "" if len(hits) == 1 else f" ({len(hits)} times)"
            ctx.add("content.commander_token", cfg["severity"], p.line,
                    f'hardcoded "{hits[0]}"{count} - address the player with <Commander>, '
                    f"<cmdrname> or <Commander> <cmdrname>, and the ship with <myshipname>")


def rule_db_placement(ctx: Context) -> None:
    cfg = ctx.rule("db.placement")
    for idx, line in enumerate(ctx.content.lines, start=1):
        if line.strip() != "UPDATEDB":
            continue
        if not ctx.content.in_scope(idx):
            continue
        prev = ctx.content.lines[idx - 2].strip() if idx >= 2 else ""
        if not prev.startswith("@"):
            ctx.add("db.placement", cfg["severity"], idx,
                    "database marker is not on the line after an @tag")


def rule_dossier_spine(ctx: Context) -> None:
    cfg = ctx.rule("dossier.spine")
    expected = cfg.get("sections", [])
    for path in ctx.dossier_paths():
        if not path.exists():
            continue
        numbers, titles = [], []
        for line in path.read_text(encoding="utf-8").splitlines():
            m = SECTION_RE.match(line)
            if m:
                numbers.append(int(m.group(1)))
                titles.append(m.group(2))
        if numbers != list(range(1, len(expected) + 1)):
            ctx.add("dossier.spine", cfg["severity"], None,
                    f"{path.name}: sections are {numbers}, expected 1..{len(expected)} in order")
            continue
        for n, (got, want) in enumerate(zip(titles, expected), start=1):
            if got != want:
                ctx.add("dossier.spine", cfg.get("title_severity", "warn"), None,
                        f'{path.name}: section {n} is "{got}", expected "{want}"')


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

def resolve_bounds(base_config: dict, system_config: dict | None = None):
    """Effective section bounds: base defaults overlaid by a system's own.

    Args:
        base_config: The loaded base config (contains [content.bounds]).
        system_config: The loaded system rules, when there is one.

    Returns:
        (kind -> (min, max), station -> kind -> (min, max))
    """
    kinds: dict[str, tuple[int, int]] = {}
    for kind, pair in base_config.get("content", {}).get("bounds", {}).items():
        if isinstance(pair, list) and len(pair) == 2:
            kinds[kind] = (int(pair[0]), int(pair[1]))

    stations: dict[str, dict[str, tuple[int, int]]] = {}
    bounds = (system_config or {}).get("content", {}).get("bounds", {})
    for key, value in bounds.items():
        if key == "stations":
            for station, kind_cfg in value.items():
                stations[station] = {
                    kind: (int(pair[0]), int(pair[1]))
                    for kind, pair in kind_cfg.items()
                    if isinstance(pair, list) and len(pair) == 2
                }
            continue
        if isinstance(value, list) and len(value) == 2:
            kinds[key] = (int(value[0]), int(value[1]))
    return kinds, stations


def _resolved_bounds(ctx: Context, system: str | None):
    """Effective bounds for a system inside a validation context."""
    system_cfg = ctx.per_system.get(system or "") if system else None
    return resolve_bounds(ctx.base, system_cfg)


def rule_content_bounds(ctx: Context) -> None:
    """Each section must carry at least (and at most) its number of examples."""
    cfg = ctx.rule("content.bounds")
    severity = cfg.get("severity", "error")
    max_severity = cfg.get("max_severity", "warn")

    base_kinds, _ = _resolved_bounds(ctx, None)
    seen_stations: set[str] = set()

    # A bounds key that names no tag kind can never match, so the override is
    # silently inert. The known kinds come from the base config alone: a typo in
    # one system's bounds must still be reported in that system, so another
    # system's keys must never make it look known.
    known_kinds = set(ctx.base.get("kinds", {}))
    known_list = ", ".join(sorted(known_kinds))

    # The base's own bounds are the same trap one level up: a key there that
    # names no kind changes nothing.
    for key in ctx.base.get("content", {}).get("bounds", {}):
        if key != "stations" and key not in known_kinds:
            ctx.add(
                "content.bounds", "warn", None,
                f"base bounds key {key!r} does not match any known tag kind ({known_list})",
            )

    for tag in ctx.content.authored_tags():
        if tag.station:
            seen_stations.add(tag.station)

        kinds, stations = _resolved_bounds(ctx, tag.system) if tag.system else (base_kinds, {})

        bound = None
        if tag.station:
            bound = stations.get(tag.station, {}).get(tag.kind)
        if bound is None:
            bound = kinds.get(tag.kind)
        if bound is None:
            continue

        low, high = bound
        count = len(tag.phrases)
        unit = "line(s)"
        if tag.kind == "StationFact":
            count = max(count - 1, 0)
            unit = "paragraph(s)"
        if count < low:
            ctx.add(
                "content.bounds", severity, tag.line,
                f"{tag.label} has {count} {unit}; the minimum for {tag.kind} is {low}",
            )
        elif count > high:
            ctx.add(
                "content.bounds", max_severity, tag.line,
                f"{tag.label} has {count} {unit}; the maximum for {tag.kind} is {high}",
            )

    # A station named in the bounds with no content behind it is a rename or a
    # typo; silence would leave the override doing nothing at all.
    for system, system_cfg in ctx.per_system.items():
        bounds = system_cfg.get("content", {}).get("bounds", {})
        for station in bounds.get("stations", {}):
            if station not in seen_stations:
                ctx.add(
                    "content.bounds", "warn", None,
                    f"bounds name station {station!r}, which has no content for {system}",
                )

        # A bounds key that names no tag kind is just as inert.
        for key in bounds:
            if key != "stations" and key not in known_kinds:
                ctx.add(
                    "content.bounds", "warn", None,
                    f"bounds key {key!r} does not match any known tag kind ({known_list})",
                )

        # ... and the same is true of a station's kind sub-keys.
        for station, kind_cfg in bounds.get("stations", {}).items():
            for kind_key in kind_cfg:
                if kind_key not in known_kinds:
                    ctx.add(
                        "content.bounds", "warn", None,
                        f"bounds key {kind_key!r} for station {station!r} does not "
                        f"match any known tag kind ({known_list})",
                    )


def _tag_block_range(lines: list[str], tag_index: int) -> tuple[int, int]:
    """The half-open range of a tag's body lines (excludes the tag line)."""
    start = tag_index + 1
    end = start
    while end < len(lines):
        candidate = lines[end]
        if not candidate.strip() or candidate.strip().startswith("@"):
            break
        if PROVENANCE_RE.match(candidate):
            break
        end += 1
    return start, end


def rewrite_tag_lines(
    lines: list[str],
    tag: str,
    *,
    remove: list[str] | None = None,
    replace: dict[str, str] | None = None,
    add: list[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """Rewrite one tag's dialog in place, carrying every other line forward.

    Removals and replacements apply to every authored occurrence of the tag,
    because appended provenance blocks leave earlier copies of a tag playing.
    Additions go to the latest occurrence only, so new lines cannot duplicate.

    Args:
        lines: The file's lines (LF, no trailing newline element).
        tag: The exact tag line, e.g. "@StationChatter<~>Sys<~>Example Station (AB-1)".
        remove: Exact lines to delete; each entry removes one occurrence.
        replace: Exact line -> replacement line.
        add: Lines to append to the latest occurrence's body.

    Returns:
        (new lines, counts of removed/replaced/added)

    Raises:
        ValueError: On an unknown tag, or a line that is not there.
    """
    remove = list(remove or [])
    replace = dict(replace or {})
    add = [line for line in (add or []) if line.strip()]
    if not remove and not replace and not add:
        raise ValueError("nothing to change: give remove, replace or add")

    first_authored = next(
        (idx for idx, line in enumerate(lines) if PROVENANCE_RE.match(line)), 0
    )
    occurrences = [
        idx for idx, line in enumerate(lines)
        if idx >= first_authored and line.strip() == tag.strip()
    ]
    if not occurrences:
        raise ValueError(f"tag not found in authored content: {tag}")

    missing_remove = set(remove)
    missing_replace = dict(replace)
    removed = replaced = 0

    for idx in reversed(occurrences):
        start, end = _tag_block_range(lines, idx)
        body = lines[start:end]
        rebuilt: list[str] = []
        for line in body:
            if line.strip() == "UPDATEDB":
                if line.strip() in missing_remove:
                    raise ValueError("refusing to remove the UPDATEDB marker")
                rebuilt.append(line)
                continue
            if line in missing_remove:
                missing_remove.discard(line)
                removed += 1
                continue
            if line in missing_replace:
                rebuilt.append(missing_replace.pop(line))
                replaced += 1
                continue
            rebuilt.append(line)
        if idx == occurrences[-1]:
            rebuilt.extend(add)
        lines[start:end] = rebuilt

    if missing_remove:
        raise ValueError(f"line(s) not found under {tag}: {sorted(missing_remove)}")
    if missing_replace:
        raise ValueError(
            f"line(s) not found under {tag}: {list(missing_replace)}"
        )

    return lines, {"removed": removed, "replaced": replaced, "added": len(add)}


RULE_FUNCTIONS: dict[str, Any] = {
    "rule_syntax_filter_known": rule_syntax_filter_known,
    "rule_syntax_filter_leads": rule_syntax_filter_leads,
    "rule_syntax_voice_name": rule_syntax_voice_name,
    "rule_syntax_tokens": rule_syntax_tokens,
    "rule_syntax_encoding": rule_syntax_encoding,
    "rule_syntax_no_example_wrapper": rule_syntax_no_example_wrapper,
    "rule_format_tag_shape": rule_format_tag_shape,
    "rule_filters_banned": rule_filters_banned,
    "rule_filters_allbusiness": rule_filters_allbusiness,
    "rule_filters_fallback": rule_filters_fallback,
    "rule_content_fact_image": rule_content_fact_image,
    "rule_content_no_links": rule_content_no_links,
    "rule_content_bounds": rule_content_bounds,
    "rule_content_fact_no_filters": rule_content_fact_no_filters,
    "rule_content_station_landable": rule_content_station_landable,
    "rule_content_commander_token": rule_content_commander_token,
    "rule_db_placement": rule_db_placement,
    "rule_dossier_spine": rule_dossier_spine,
}


def implementations(rules: dict[str, dict]) -> list[tuple[str, list[str], Any]]:
    """(impl, [rule ids], function) per implementation, in declaration order."""
    grouped: dict[str, list[str]] = {}
    for rule_id, cfg in rules.items():
        impl = cfg.get("impl")
        if impl == POLICY:
            continue
        if not impl:
            raise ValueError(f"rule {rule_id} names no implementation")
        fn = RULE_FUNCTIONS.get(impl)
        if not callable(fn):
            raise ValueError(f"rule {rule_id} names impl {impl!r}, which is not a rule function")
        grouped.setdefault(impl, []).append(rule_id)
    return [(impl, ids, RULE_FUNCTIONS[impl]) for impl, ids in grouped.items()]


def policy_rules(rules: dict[str, dict]) -> list[str]:
    """The rules a reader checks, not this program."""
    return sorted(rid for rid, cfg in rules.items() if cfg.get("impl") == POLICY)


# ---------------------------------------------------------------------------
# RuleEngine class
# ---------------------------------------------------------------------------

def _first_sentence(text: str) -> str:
    """The first sentence of a rule's why, flattened to one line."""
    flat = " ".join((text or "").split())
    if not flat:
        return ""
    match = re.search(r"^(.+?[.!?])(?:\s|$)", flat)
    return match.group(1) if match else flat


def _build_rule_summary(rules: dict[str, dict], findings: list[Finding]) -> list[dict]:
    """One row per active rule: what it checks and how it fared."""
    by_rule: dict[str, list[Finding]] = {}
    for finding in findings:
        by_rule.setdefault(finding.rule, []).append(finding)

    summary: list[dict] = []
    for rule_id in sorted(rules):
        cfg = rules[rule_id]
        if cfg.get("severity", "error") == "off":
            continue
        description = cfg.get("summary") or _first_sentence(cfg.get("why", ""))
        description = (description or rule_id).replace("|", "\\|")
        if cfg.get("impl") == POLICY:
            summary.append({
                "rule": rule_id,
                "description": description,
                "status": "manual",
                "findings": 0,
            })
            continue
        hits = by_rule.get(rule_id, [])
        if any(f.severity == "error" for f in hits):
            status = "error"
        elif any(f.severity == "warn" for f in hits):
            status = "warn"
        else:
            status = "pass"
        summary.append({
            "rule": rule_id,
            "description": description,
            "status": status,
            "findings": len(hits),
        })
    return summary


def _render_rule_table(summary: list[dict]) -> str:
    symbols = {"pass": "✅ pass", "warn": "⚠️ warn", "error": "❌ error"}
    checked = [row for row in summary if row["status"] != "manual"]
    manual = [row for row in summary if row["status"] == "manual"]

    lines = ["| Rule | What it checks | Result |", "|---|---|---|"]
    for row in checked:
        result = symbols.get(row["status"], row["status"])
        if row["findings"] and row["status"] != "pass":
            result = f"{result} ({row['findings']} finding(s))"
        lines.append(f"| `{row['rule']}` | {row['description']} | {result} |")

    if manual:
        lines += [
            "",
            "**Policy rules (confirm manually):**",
            "",
            "| Rule | What it checks |",
            "|---|---|",
        ]
        for row in manual:
            lines.append(f"| `{row['rule']}` | {row['description']} |")
    return "\n".join(lines)


class RuleEngine:
    """Main validation engine.
    
    Loads base, house, and system rules, parses content and dossiers,
    runs all rule implementations, and returns findings.
    """
    
    def __init__(
        self,
        base_rules_path: Path,
        house_rules_path: Path | None = None,
        system_rules_path: Path | None = None,
        systems_dir: Path | None = None,
    ):
        self.base_rules_path = base_rules_path
        self.house_rules_path = house_rules_path
        self.system_rules_path = system_rules_path
        self.systems_dir = systems_dir
        
        # Load base configuration
        self.base = load_base_config(base_rules_path.parent)
        self.base_rules = self.base["rules"]
        
        # Load house rules
        house_declared, house_patches = load_house_rules(house_rules_path, self.base_rules)
        
        # Load system rules - either single file or all from systems_dir
        if systems_dir and systems_dir.exists():
            system_overrides = load_all_system_rules(systems_dir, self.base_rules)
        else:
            system_overrides = load_system_rules(system_rules_path, self.base_rules)
        
        # Merge all rules
        self.rules = merge_rules(
            self.base_rules,
            house_declared,
            house_patches,
            system_overrides
        )
        
        # Load kinds
        self.kinds = load_kinds(self.base)
        
        # Load per-system configs
        self.per_system = system_overrides

    def validate(self, content_path: Path, dossier_path: Path | None = None) -> ValidationResult:
        """Validate content file against all rules.
        
        Args:
            content_path: Path to the content file (EDCoPilot.SpeechExtensions.Custom.txt)
            dossier_path: Optional path to a dossier file. If not provided, uses dossiers from system rules.
            
        Returns:
            ValidationResult with findings and passed status.
        """
        # Parse content
        content = parse_content(content_path, PROVENANCE_RE, self.kinds)
        
        # If dossier_path provided, use it; otherwise use from per_system
        if dossier_path:
            # Create a context with just this dossier
            per_system_with_dossier = {}
            # We need to temporarily override dossier_paths to return this path
            # For simplicity, we'll add a dummy system entry
            dummy_system = {"overrides": {}, "system": {"dossier": str(dossier_path)}}
            # Extract system name from dossier path or use a default
            system_name = dossier_path.stem
            per_system_with_dossier[system_name] = dummy_system
            # Merge with existing per_system
            merged_per_system = {**self.per_system, **per_system_with_dossier}
        else:
            merged_per_system = self.per_system
        
        # Create context
        ctx = Context(
            base=self.base,
            per_system=merged_per_system,
            content=content,
            rules=self.rules,
        )
        
        # Run all rule implementations
        for _impl, rule_ids, fn in implementations(self.rules):
            # Only run if at least one rule using this impl is not retired
            if any(ctx.rule(rule_id).get("severity", "error") != "off" for rule_id in rule_ids):
                fn(ctx)
        
        # Sort findings by severity, then rule, then line
        findings = sorted(ctx.findings, key=lambda f: (
            SEV_ORDER.get(f.severity, 9), f.rule, f.line or 0
        ))
        
        # Passed = no error findings
        passed = not any(f.severity == "error" for f in findings)

        rule_summary = _build_rule_summary(self.rules, findings)
        return ValidationResult(
            findings=findings,
            passed=passed,
            rule_summary=rule_summary,
            rule_table=_render_rule_table(rule_summary),
        )


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def validate(
    content_path: Path,
    dossier_path: Path | None,
    base_rules_path: Path,
    house_rules_path: Path | None = None,
    system_rules_path: Path | None = None,
) -> ValidationResult:
    """Convenience function for one-off validation."""
    engine = RuleEngine(base_rules_path, house_rules_path, system_rules_path)
    return engine.validate(content_path, dossier_path)


def validate_content(
    content: str,
    system_name: str,
    base_rules_path: Path | None = None,
    house_rules_path: Path | None = None,
    systems_dir: Path | None = None,
) -> ValidationResult:
    """Validate a content string against all rules for a given system.
    
    This function extracts the latest provenance block (or uses the full content
    if no provenance marker exists) and validates it against the complete rule
    set (base + house + system rules).
    
    Args:
        content: The content string to validate (e.g., from EDCoPilot.SpeechExtensions.Custom.txt)
        system_name: The name of the system to validate against (used to find system rules)
        base_rules_path: Optional path to base.toml (defaults to package rules)
        house_rules_path: Optional path to all.rules.toml (defaults to the
            configured content definitions root's systems/all.rules.toml)
        systems_dir: Optional path to systems directory (defaults to the
            configured content definitions root's systems/)
        
    Returns:
        ValidationResult with findings. Line numbers in findings are relative to
        the start of the validated block (1 = first line of block).
    """
    # Rule data ships beside the validation module as package data.
    rules_dir = RULE_DATA_DIR
    if base_rules_path is None:
        base_rules_path = rules_dir / "base.toml"

    # The author's house and system rules live in the configured content
    # definitions repository, not beside the installed package. The content
    # root defaults to the working directory, so an unconfigured run simply
    # finds no systems/ directory and validates against the base rules. A
    # configuration that cannot be loaded is a bug and must not be hidden, so
    # get_config's exception propagates.
    if systems_dir is None:
        systems_dir = layout_systems_dir(get_config())
    if house_rules_path is None:
        house_rules_path = systems_dir / "all.rules.toml"
    
    # --- Extract the latest provenance block ---
    # Keep the payload's own line endings: syntax.encoding must judge the input
    # the caller sent, not a normalised copy of it.
    lines = content.splitlines(keepends=True)
    provenance_indices = []
    
    for idx, line in enumerate(lines):
        if PROVENANCE_RE.match(line.rstrip("\r\n")):
            provenance_indices.append(idx)
    
    if provenance_indices:
        # Use content from the LAST provenance marker onwards
        block_start = provenance_indices[-1]
        block_lines = lines[block_start:]
        # Line offset for converting absolute to relative line numbers
        line_offset = block_start + 1  # 1-indexed
    else:
        # No provenance marker - validate entire content
        block_lines = lines
        line_offset = 1
    
    block_content = "".join(block_lines)
    
    # --- Load rules and create engine ---
    # Load base config
    base = load_base_config(base_rules_path.parent)
    base_rules = base["rules"]
    
    # Load house rules
    house_declared, house_patches = load_house_rules(house_rules_path, base_rules)
    
    # Load all system rules
    system_overrides = load_all_system_rules(systems_dir, base_rules)
    
    # Merge all rules
    merged_rules = merge_rules(
        base_rules,
        house_declared,
        house_patches,
        system_overrides
    )
    
    # Load kinds
    kinds = load_kinds(base)
    
    # Find the system config for the given system_name
    per_system = {}
    if system_name in system_overrides:
        per_system[system_name] = system_overrides[system_name]
    
    # Also include any system that has this name in its names list
    for name, cfg in system_overrides.items():
        sys_names = cfg.get("system", {}).get("names", [])
        if system_name in sys_names:
            per_system[name] = cfg
            break
    
    # Parse the block content
    # We need to write to a temp file for parse_content, or adapt it
    # Let's create a temporary file
    import tempfile
    # newline="" preserves the payload's own endings; the default (or "\r\n")
    # would translate them and hide a real LF payload from syntax.encoding.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8', newline='') as tmp:
        tmp.write(block_content)
        tmp_path = Path(tmp.name)
    
    try:
        block_parsed = parse_content(tmp_path, PROVENANCE_RE, kinds)
    finally:
        tmp_path.unlink(missing_ok=True)
    
    # Create context
    ctx = Context(
        base=base,
        per_system=per_system,
        content=block_parsed,
        rules=merged_rules,
    )
    
    # Run all rule implementations
    for _impl, rule_ids, fn in implementations(merged_rules):
        if any(ctx.rule(rule_id).get("severity", "error") != "off" for rule_id in rule_ids):
            fn(ctx)
    
    # Adjust line numbers to be relative to block start
    for finding in ctx.findings:
        if finding.line is not None:
            finding.line = finding.line - line_offset + 1
    
    # Sort findings by severity, then rule, then line
    findings = sorted(ctx.findings, key=lambda f: (
        SEV_ORDER.get(f.severity, 9), f.rule, f.line or 0
    ))
    
    # Passed = no error findings
    passed = not any(f.severity == "error" for f in findings)

    rule_summary = _build_rule_summary(merged_rules, findings)
    return ValidationResult(
        findings=findings,
        passed=passed,
        rule_summary=rule_summary,
        rule_table=_render_rule_table(rule_summary),
    )


# ---------------------------------------------------------------------------
# Definition validation (Story 3.2)
# ---------------------------------------------------------------------------

DOSSIER_SECTIONS = [
    "Identity and canon",
    "Lore and theme",
    "Tone rules (hard constraints)",
    "Canon site table",
    "Corrections log (do not reintroduce these)",
    "Site list maintenance",
    "Coverage",
    "Writing rules",
    "Open threads (TODO)",
]

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
VOICE_TAG_RE = re.compile(r"\[<([^>]+)>\]")


def _parse_dossier_sections(dossier: str) -> tuple[dict[int, tuple[str, list[str]]], list[int]]:
    """Parse dossier into sections: {section_num: (title, lines)}, and section_order list."""
    sections: dict[int, tuple[str, list[str]]] = {}
    section_order: list[int] = []
    lines = dossier.splitlines()
    current_num = None
    current_title = None
    current_lines: list[str] = []
    
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            if current_num is not None:
                sections[current_num] = (current_title, current_lines)
            current_num = int(m.group(1))
            current_title = m.group(2).strip()
            current_lines = []
            section_order.append(current_num)
        else:
            current_lines.append(line)
    
    if current_num is not None:
        sections[current_num] = (current_title, current_lines)
    
    return sections, section_order


def _extract_site_table(lines: list[str]) -> list[dict]:
    """Extract site table rows from section 4 lines.
    
    Returns list of {name, build_type, body, status} dicts.
    Looks for tables with "Build type" column and a site name column.
    Handles variations like "Site | Build type | Body" or "System | Site | Build type | Orbits".
    Status is one of: complete, build, plan, tentative.
    """
    sites = []
    i = 0
    current_status = "unknown"
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Track subsection status
        if line.startswith("### Complete"):
            current_status = "complete"
        elif line.startswith("### Under construction"):
            current_status = "build"
        elif line.startswith("### Definitely planned"):
            current_status = "plan"
        elif line.startswith("### Tentatively planned"):
            current_status = "tentative"
        
        # Look for the header row - must have "Build type" column
        if line.startswith("|") and "Build type" in line:
            # Found a potential site table header, check for separator row next
            if i + 1 < len(lines):
                sep_line = lines[i + 1].strip()
                if sep_line.startswith("|") and all(c.startswith("-") or c.startswith(":") for c in [c.strip() for c in sep_line.strip("|").split("|")]):
                    # This is a site table, parse header to find column indices
                    header_cells = [c.strip() for c in line.strip("|").split("|")]
                    name_col = None
                    build_type_col = None
                    body_col = None
                    
                    for idx, cell in enumerate(header_cells):
                        cell_lower = cell.lower()
                        if "site" in cell_lower and name_col is None:
                            name_col = idx
                        elif "build type" in cell_lower:
                            build_type_col = idx
                        elif "body" in cell_lower or "orbits" in cell_lower:
                            body_col = idx
                    
                    # If we can't find columns by name, use positional defaults
                    if name_col is None:
                        name_col = 0 if "system" not in header_cells[0].lower() else 1
                    if build_type_col is None:
                        build_type_col = 1 if name_col == 0 else 2
                    if body_col is None:
                        body_col = 2 if build_type_col == 1 else 3
                    
                    # Parse data rows
                    i += 2
                    while i < len(lines):
                        data_line = lines[i].strip()
                        if not data_line.startswith("|"):
                            break
                        cells = [c.strip() for c in data_line.strip("|").split("|")]
                        max_col = max(name_col, build_type_col, body_col)
                        if len(cells) > max_col:
                            name = cells[name_col].strip().strip("`").strip("*").strip("**").strip()
                            build_type_cell = cells[build_type_col].strip()
                            body = cells[body_col].strip().strip("`").strip() if body_col < len(cells) else ""
                            
                            # Extract build type from backticks
                            build_type_match = re.search(r"`([a-z][a-z0-9_]*)`", build_type_cell)
                            build_type = build_type_match.group(1) if build_type_match else ""
                            
                            if name and build_type:
                                sites.append({"name": name, "build_type": build_type, "body": body, "status": current_status})
                        i += 1
                    continue  # Continue looking for more tables
        i += 1
    
    return sites


def _get_landable_build_types() -> set[str]:
    """Get set of landable build types from build_types.toml."""
    build_types_data = _load_toml(RULE_DATA_DIR / "build_types.toml")
    build_types = build_types_data.get("classes", {})
    
    landable = set()
    for cls in ["starport", "outpost", "settlement"]:
        for bt in build_types.get(cls, {}):
            landable.add(bt)
    return landable


def _extract_voices_from_section_8(lines: list[str]) -> set[str]:
    """Extract voice names from dossier section 8 (Writing rules).
    
    Only extracts from the "Voices used" subsection, and excludes known tokens.
    """
    # Known tokens that are not voices (from base.toml vocab)
    known_tokens = {
        "commander", "cmdrname", "cmdraddress", "myshipname", "fuellevels", "fuellevels",
        "starsystem", "randomstarsystem", "stationname", "fccaptain", "shipainame",
        "mycallsign", "callsign", "othercallsign", "flightnum", "shipcorporation",
        "shipcorpshiptype", "localdestination", "systemname", "bodyname", "bodytype",
        "greeting", "ship1", "ship2", "ship3", "anyship", "shipvessel",
        "famousstarsystem", "prisonstarsystem", "thargoidsystem", "stationfaction",
        "stationnick", "stationpart", "stationevent",
    }
    
    voices = set()
    in_voices_used = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check for "Voices used" header
        if stripped.startswith("###") and "Voices used" in stripped:
            in_voices_used = True
            continue
        
        # Stop at next subsection header
        if in_voices_used and stripped.startswith("###"):
            break
        
        if in_voices_used:
            for match in VOICE_TAG_RE.finditer(line):
                voice = match.group(1)
                # Exclude known tokens (case-insensitive)
                if voice.lower() not in known_tokens:
                    voices.add(voice)
    
    return voices


def _normalize_station_name(name: str) -> str:
    """Normalize station name for comparison: strip markdown formatting."""
    # Remove backticks and asterisks
    name = name.strip("`").strip("*").strip()
    return name


_DESCRIPTIVE_PREFIXES = (
    "Built", "Tentative", "and ", "so ", "the ", "a ", "an ",
)


def _is_descriptive(line: str) -> bool:
    """True when a coverage line is prose rather than a station name."""
    stripped = line.strip()
    return (
        stripped.startswith(_DESCRIPTIVE_PREFIXES)
        or "deliberately excluded" in stripped
        or "sites with no pads" in stripped
    )


def _parse_station_list(text: str) -> set[str]:
    """Split one coverage line on its separators and keep station-like names."""
    stations: set[str] = set()
    for part in re.split(r"[·•,\n]", text):
        part = part.strip().strip("`").strip("*").strip()
        if part and len(part) > 2 and not part.lower().startswith(
            ("the ", "a ", "an ")
        ):
            stations.add(_normalize_station_name(part))
    return stations


def _starts_simple_station_list(stripped: str) -> bool:
    """True when a line without the header looks like the simple list format."""
    return (
        ("·" in stripped or "•" in stripped)
        and not stripped.startswith(("Built", "Tentative"))
        and "deliberately" not in stripped
    )


def _extract_stations_from_section_7(lines: list[str]) -> set[str]:
    """Station names from section 7: a ``### Stations covered`` list or a simple one."""
    stations: set[str] = set()
    in_station_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("###") and "Stations covered" in stripped:
            in_station_list = True
            continue
        if in_station_list and stripped.startswith("###"):
            break
        if in_station_list:
            if stripped and not _is_descriptive(stripped):
                stations |= _parse_station_list(stripped)
            continue
        if stripped and _starts_simple_station_list(stripped):
            in_station_list = True
            if not _is_descriptive(stripped):
                stations |= _parse_station_list(stripped)
    return stations


def _parse_rules_toml(rules: str) -> tuple[dict, list[Finding]]:
    """Parse rules TOML and validate required fields."""
    findings: list[Finding] = []
    
    try:
        parsed = tomllib.loads(rules)
    except tomllib.TOMLDecodeError as e:
        findings.append(Finding(
            rule="rules.toml_syntax",
            severity="error",
            line=e.lineno if hasattr(e, 'lineno') else None,
            message=f"Invalid TOML syntax: {e}"
        ))
        return {}, findings
    
    system = parsed.get("system", {})
    
    # Check system.names
    names = system.get("names")
    if not names or not isinstance(names, list) or len(names) == 0:
        findings.append(Finding(
            rule="rules.system_names",
            severity="error",
            line=None,
            message="rules TOML missing or empty system.names array"
        ))
    
    # Check system.dossier
    dossier = system.get("dossier")
    if not dossier or not isinstance(dossier, str):
        findings.append(Finding(
            rule="rules.system_dossier",
            severity="error",
            line=None,
            message="rules TOML missing system.dossier string"
        ))
    
    # Check voices
    voices = system.get("voices")
    if not voices or not isinstance(voices, list) or len(voices) == 0:
        findings.append(Finding(
            rule="rules.voices",
            severity="error",
            line=None,
            message="rules TOML missing or empty voices array"
        ))
    
    return parsed, findings


def validate_definition(
    dossier: str,
    rules: str,
    system_name: str,
    all_rules: str | None = None,
) -> ValidationResult:
    """Validate a dossier and rules pair for cross-references.
    
    Args:
        dossier: Dossier markdown content as string.
        rules: System rules TOML content as string.
        system_name: Expected system name (must match rules.system.names).
        all_rules: Optional all.rules.toml content for fact_image check.
        
    Returns:
        ValidationResult with findings and passed status.
    """
    findings: list[Finding] = []
    
    # 1. Parse and validate rules TOML
    parsed_rules, rule_findings = _parse_rules_toml(rules)
    findings.extend(rule_findings)
    
    # Check system name matches
    if not rule_findings:  # Only check if basic parsing succeeded
        system = parsed_rules.get("system", {})
        names = system.get("names", [])
        if system_name not in names:
            findings.append(Finding(
                rule="rules.system_names",
                severity="error",
                line=None,
                message=f"system_name '{system_name}' not in rules.system.names: {names}"
            ))
    
    # 2. Parse dossier sections
    sections, section_order = _parse_dossier_sections(dossier)
    
    # Check all 9 spine sections present and in order
    section_numbers = sorted(sections.keys())
    expected_numbers = list(range(1, 10))
    
    if section_numbers != expected_numbers:
        findings.append(Finding(
            rule="dossier.spine",
            severity="error",
            line=None,
            message=f"Dossier sections are {section_numbers}, expected 1..9 in order"
        ))
    elif section_order != expected_numbers:
        findings.append(Finding(
            rule="dossier.spine",
            severity="error",
            line=None,
            message=f"Dossier sections are in wrong order: {section_order}, expected 1..9"
        ))
    else:
        # Check titles match
        for n, expected_title in enumerate(DOSSIER_SECTIONS, start=1):
            if n in sections:
                got_title = sections[n][0]
                if got_title != expected_title:
                    findings.append(Finding(
                        rule="dossier.spine",
                        severity="warn",
                        line=None,
                        message=f'Dossier section {n} is "{got_title}", expected "{expected_title}"'
                    ))
    
    # 3. Section 4: Parse site table
    sites: list[dict] = []
    if 4 in sections:
        sites = _extract_site_table(sections[4][1])
        if not sites:
            findings.append(Finding(
                rule="dossier.site_table",
                severity="error",
                line=None,
                message="Section 4 (Canon site table) has no parseable site table rows"
            ))
    else:
        findings.append(Finding(
            rule="dossier.site_table",
            severity="error",
            line=None,
            message="Dossier missing section 4 (Canon site table)"
        ))
    
    # 4. Section 8: Extract voices and cross-reference with rules
    if 8 in sections:
        dossier_voices = _extract_voices_from_section_8(sections[8][1])
    else:
        dossier_voices = set()
        findings.append(Finding(
            rule="dossier.voice_coverage",
            severity="error",
            line=None,
            message="Dossier missing section 8 (Writing rules) - no voices to cross-reference"
        ))
    
    # Cross-reference voices if rules parsed successfully
    if not rule_findings:
        rules_voices = set(system.get("voices", []))
        
        # Voices in rules but not in dossier §8
        missing_in_dossier = rules_voices - dossier_voices
        for voice in sorted(missing_in_dossier):
            findings.append(Finding(
                rule="dossier.voice_coverage",
                severity="error",
                line=None,
                message=f"Voice '{voice}' declared in rules but not used in dossier §8"
            ))
        
        # Voices in dossier §8 but not in rules
        missing_in_rules = dossier_voices - rules_voices
        for voice in sorted(missing_in_rules):
            findings.append(Finding(
                rule="dossier.voice_coverage",
                severity="error",
                line=None,
                message=f"Voice '{voice}' used in dossier §8 but not declared in rules"
            ))
    
    # 5. Section 7: Extract stations and cross-reference with landable sites from §4
    if 7 in sections:
        coverage_stations = _extract_stations_from_section_7(sections[7][1])
    else:
        coverage_stations = set()
        findings.append(Finding(
            rule="dossier.coverage_match",
            severity="error",
            line=None,
            message="Dossier missing section 7 (Coverage)"
        ))
    
    # Get landable stations from section 4 (excluding tentative/placeholder sites)
    landable_build_types = _get_landable_build_types()
    # Build mapping from normalized name to site info for matching
    # Only include sites that are not tentative (placeholder) status
    landable_sites_map = {
        _normalize_station_name(s["name"]): s 
        for s in sites 
        if s["build_type"] in landable_build_types and s.get("status") != "tentative"
    }
    landable_sites_normalized = set(landable_sites_map.keys())
    
    # Cross-reference coverage vs landable sites (using normalized names)
    # Stations in coverage but not landable in §4
    for station in sorted(coverage_stations - landable_sites_normalized):
        # Check if it exists in §4 but is non-landable
        site_info = next((s for s in sites if _normalize_station_name(s["name"]) == station), None)
        if site_info and site_info["build_type"] not in landable_build_types:
            findings.append(Finding(
                rule="dossier.coverage_match",
                severity="error",
                line=None,
                message=f"Station '{station}' listed in §7 coverage but is {site_info['build_type']} (not landable) in §4"
            ))
        elif station:  # Only report if station name is not empty
            findings.append(Finding(
                rule="dossier.coverage_match",
                severity="error",
                line=None,
                message=f"Station '{station}' listed in §7 coverage but not found as landable in §4"
            ))
    
    # Landable stations in §4 but missing from coverage
    for station in sorted(landable_sites_normalized - coverage_stations):
        # Find original name for error message
        original_name = landable_sites_map[station]["name"]
        findings.append(Finding(
            rule="dossier.coverage_match",
            severity="error",
            line=None,
            message=f"Landable station '{original_name}' in §4 missing from §7 coverage"
        ))
    
    # 6. Check img_url in §7 matches all.rules.toml fact_image (if provided)
    if all_rules and 7 in sections:
        try:
            all_parsed = tomllib.loads(all_rules)
            expected_img = all_parsed.get("rules", {}).get("content", {}).get("fact_image", {}).get("expected")
            if expected_img:
                # Check if dossier §7 mentions an img_url with actual URL
                section_7_text = "\n".join(sections[7][1])
                # Match img_url= followed by a URL (http/https)
                img_urls = re.findall(r"img_url\s*=\s*(https?://\S+)", section_7_text)
                for url in img_urls:
                    if url != expected_img:
                        findings.append(Finding(
                            rule="dossier.fact_image_match",
                            severity="warn",
                            line=None,
                            message=f"img_url in §7 ({url}) does not match all.rules.toml fact_image ({expected_img})"
                        ))
        except tomllib.TOMLDecodeError:
            pass  # Ignore parse errors in all_rules
    
    # Sort findings by severity, then rule
    findings.sort(key=lambda f: (SEV_ORDER.get(f.severity, 9), f.rule))
    
    passed = not any(f.severity == "error" for f in findings)
    return ValidationResult(findings=findings, passed=passed)