"""Journal entries appended to SOUL.md (header is protected by control.guard)."""
from datetime import datetime, timezone

from control import guard


def log(event: str, **fields) -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    details = "; ".join(f"{k}={v}" for k, v in fields.items())
    line = f"- `{ts}` **{event}** — {details}"
    guard.append_soul(line)
    return line
