"""Canonical project paths used by the control layer."""
from pathlib import Path

from control._frozen import freeze

ROOT = Path(__file__).resolve().parent.parent
CONTROL_DIR = ROOT / "control"
CONFIG_FILE = ROOT / "config.yaml"
SOUL_FILE = ROOT / "SOUL.md"
ENV_FILE = ROOT / ".env"
KILL_FILE = ROOT / "KILL"
SKILLS_DIR = ROOT / "skills"
STATE_DIR = ROOT / "state"
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"

freeze(__name__)
