"""File-system guard: the ONLY way agent code writes files.

Rules
  * skills/  : agent may create NEW .md skill files; never overwrite/delete.
  * state/, logs/, output/ : agent working area.
  * SOUL.md  : append-only via `append_soul`, header must stay intact.
  * control/, config.yaml, .env, KILL and everything else: refused.
"""
from pathlib import Path

from control._frozen import freeze
from control.integrity import SOUL_HEADER_END, SOUL_HEADER_START, soul_header_ok
from control.paths import LOGS_DIR, OUTPUT_DIR, ROOT, SKILLS_DIR, SOUL_FILE, STATE_DIR

WORK_DIRS = (STATE_DIR, LOGS_DIR, OUTPUT_DIR)
SKILL_SUFFIXES = frozenset({".md"})
MAX_SKILL_BYTES = 20_000


class WriteDenied(PermissionError):
    pass


def _inside(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _resolve(path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def check_write(path, *, append: bool = False) -> Path:
    p = _resolve(path)
    if any(_inside(p, d) for d in WORK_DIRS):
        return p
    if _inside(p, SKILLS_DIR):
        if p.parent != SKILLS_DIR:
            raise WriteDenied("skills must be flat files directly in skills/")
        if p.suffix not in SKILL_SUFFIXES:
            raise WriteDenied(f"skill files must be one of {sorted(SKILL_SUFFIXES)}")
        if p.exists() or append:
            raise WriteDenied(f"skill {p.name} already exists; agent may only create NEW skills")
        return p
    rel = p.relative_to(ROOT) if _inside(p, ROOT) else p
    raise WriteDenied(f"agent is not allowed to write {rel}")


def write_text(path, content: str, *, append: bool = False) -> Path:
    p = check_write(path, append=append)
    if _inside(p, SKILLS_DIR) and len(content.encode()) > MAX_SKILL_BYTES:
        raise WriteDenied("skill too large")
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else ("x" if _inside(p, SKILLS_DIR) else "w")
    with open(p, mode, encoding="utf-8") as fh:
        fh.write(content)
    return p


def append_soul(entry: str) -> None:
    if SOUL_HEADER_START in entry or SOUL_HEADER_END in entry:
        raise WriteDenied("journal entries may not contain SOUL header markers")
    current = SOUL_FILE.read_text(encoding="utf-8")
    if not soul_header_ok(current):
        raise WriteDenied("SOUL.md header does not match owner seal; refusing to write")
    with open(SOUL_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry if entry.endswith("\n") else entry + "\n")


freeze(__name__)
