import importlib.util
import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "scripts"
ASSETS = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "assets"
RULES = SCRIPTS / "edcg" / "rules"

def test_rule_data_lives_in_package():
    data = RULES / "data"
    for name in ("base.toml", "build_types.toml", "raven.toml"):
        assert (data / name).is_file(), name

def test_no_script_references_assets():
    # assets/ is agent-facing only: no script may load rule data or templates
    # from it. The single permitted mention lives in cli.py - the init command's
    # next-step hint, which is prose telling the agent to copy the example rules
    # file, not a path this package reads. It must appear exactly once there and
    # nowhere else.
    permitted = "assets/all.rules.toml.example"
    cli_py = SCRIPTS / "edcg" / "cli.py"
    assert cli_py.read_text(encoding="utf-8").count(permitted) == 1
    for py in SCRIPTS.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if py == cli_py:
            text = text.replace(permitted, "")
        assert "assets" not in text, py

def test_loader_is_module_relative():
    for name in ("engine.py", "validation.py"):
        text = (RULES / name).read_text(encoding="utf-8")
        assert "assets" not in text, name
        assert "parents[3]" not in text, name

def test_loader_finds_data_beside_relocated_module(tmp_path):
    """A copy of the engine, moved anywhere, still loads the data beside it."""
    relocated = tmp_path / "relocated" / "edcg" / "rules"
    relocated.mkdir(parents=True)
    for name in ("engine.py", "validation.py"):
        shutil.copy2(RULES / name, relocated / name)
    shutil.copytree(RULES / "data", relocated / "data")

    module_name = "relocated_engine_test"
    spec = importlib.util.spec_from_file_location(module_name, relocated / "engine.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)

        # The module must resolve its data to the relocated tree, not the original.
        assert module.RULE_DATA_DIR == relocated / "data"

        rules = module.get_base_rules()
        assert rules, "relocated loader returned no rules"
        assert {"version", "content", "rules", "provenance", "vocab", "kinds"} <= set(rules)
    finally:
        sys.modules.pop(module_name, None)

def test_assets_is_agent_facing_only():
    assert sorted(p.name for p in ASSETS.iterdir()) == [
        "all.rules.toml.example", "dossier-template.md"]
