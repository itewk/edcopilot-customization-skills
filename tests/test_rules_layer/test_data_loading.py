from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "scripts"
ASSETS = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "assets"

def test_rule_data_lives_in_package():
    data = SCRIPTS / "edcg" / "rules" / "data"
    for name in ("base.toml", "build_types.toml", "raven.toml"):
        assert (data / name).is_file(), name

def test_no_script_references_assets():
    for py in SCRIPTS.rglob("*.py"):
        assert "assets" not in py.read_text(encoding="utf-8"), py

def test_loader_is_module_relative():
    for name in ("engine.py", "validation.py"):
        text = (SCRIPTS / "edcg" / "rules" / name).read_text(encoding="utf-8")
        assert "assets" not in text, name
        assert "parents[3]" not in text, name

def test_assets_is_agent_facing_only():
    assert sorted(p.name for p in ASSETS.iterdir()) == [
        "all.rules.toml.example", "dossier-template.md"]