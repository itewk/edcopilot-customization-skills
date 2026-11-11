import sys
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "edcopilot-system-content" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))