from pathlib import Path

def test_package_dir_will_exist():
    skill = Path(__file__).resolve().parents[1] / "skills" / "edcopilot-system-content"
    assert (skill / "scripts" / "edcg" / "__init__.py").exists()
    assert skill.name == "edcopilot-system-content"