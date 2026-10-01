"""Skills are prompt templates (Markdown) in skills/. They are never executed
as code. The agent may add NEW skill files; existing ones are immutable for it."""
import re

from control import guard
from control.paths import SKILLS_DIR

NAME_RE = re.compile(r"^[a-z0-9_]{3,48}$")


def load(name: str) -> str:
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"skill {name} not found")
    return path.read_text(encoding="utf-8")


def exists(name: str) -> bool:
    return (SKILLS_DIR / f"{name}.md").exists()


def render(template: str, **values) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def create(name: str, content: str):
    if not NAME_RE.match(name):
        raise guard.WriteDenied("skill name must match [a-z0-9_]{3,48}")
    return guard.write_text(SKILLS_DIR / f"{name}.md", content)
