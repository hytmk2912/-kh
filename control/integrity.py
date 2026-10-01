"""Tamper evidence for the control layer, config.yaml and the SOUL.md header.

The OWNER seals the current files with `python main.py owner-seal`, which
writes control/MANIFEST.sha256. The agent verifies the manifest on every
start-up and refuses to work if anything changed.
"""
import hashlib

from control._frozen import freeze
from control.paths import CONFIG_FILE, CONTROL_DIR, ROOT, SOUL_FILE

MANIFEST = CONTROL_DIR / "MANIFEST.sha256"
SOUL_HEADER_START = "<!-- SOUL-HEADER-START -->"
SOUL_HEADER_END = "<!-- SOUL-HEADER-END -->"
SOUL_HEADER_KEY = "SOUL.md#header"


class IntegrityError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def soul_header(text: str) -> str:
    start = text.find(SOUL_HEADER_START)
    end = text.find(SOUL_HEADER_END)
    if start != 0 or end < 0:
        raise IntegrityError("SOUL.md header markers missing or moved")
    return text[: end + len(SOUL_HEADER_END)]


def current_hashes() -> dict:
    hashes = {}
    for path in sorted(CONTROL_DIR.glob("*.py")):
        hashes[str(path.relative_to(ROOT))] = _sha(path.read_bytes())
    hashes[str(CONFIG_FILE.relative_to(ROOT))] = _sha(CONFIG_FILE.read_bytes())
    hashes[SOUL_HEADER_KEY] = _sha(soul_header(SOUL_FILE.read_text(encoding="utf-8")).encode())
    return hashes


def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise IntegrityError("control/MANIFEST.sha256 missing - owner must run `python main.py owner-seal`")
    entries = {}
    for line in MANIFEST.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split(None, 1)
            entries[name.strip()] = digest
    return entries


def problems() -> list:
    expected = load_manifest()
    actual = current_hashes()
    out = []
    for name in sorted(set(expected) | set(actual)):
        if expected.get(name) != actual.get(name):
            out.append(f"{name}: expected {expected.get(name, 'absent')[:12]} got {actual.get(name, 'absent')[:12]}")
    return out


def verify() -> None:
    found = problems()
    if found:
        raise IntegrityError("control layer tampered: " + "; ".join(found))


def soul_header_ok(text: str) -> bool:
    expected = load_manifest().get(SOUL_HEADER_KEY)
    return expected == _sha(soul_header(text).encode())


def seal() -> dict:
    """OWNER ONLY. Never called by agent code."""
    hashes = current_hashes()
    lines = ["# sha256  path  (owner-sealed; regenerate with `python main.py owner-seal`)"]
    lines += [f"{digest}  {name}" for name, digest in hashes.items()]
    MANIFEST.write_text("\n".join(lines) + "\n")
    return hashes


freeze(__name__)
