"""Append-only spend/income ledger in state/ledger.jsonl."""
import json
from datetime import datetime, timezone

from control import guard
from control.paths import STATE_DIR


class Ledger:
    def __init__(self, path=None):
        self.path = path or (STATE_DIR / "ledger.jsonl")

    @classmethod
    def for_wallet(cls, wallet):
        """One ledger per wallet backend so mock runs never touch testnet accounting."""
        return cls(STATE_DIR / f"ledger_{wallet.name}.jsonl")

    def _entries(self):
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def record(self, kind: str, amount_wei: int, memo: str) -> dict:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,  # "spend" | "income" | "payout"
            "amount_wei": int(amount_wei),
            "memo": memo,
        }
        guard.write_text(self.path, json.dumps(entry) + "\n", append=True)
        return entry

    def spent_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(e["amount_wei"] for e in self._entries() if e["kind"] == "spend" and e["ts"].startswith(today))

    def total(self, kind: str) -> int:
        return sum(e["amount_wei"] for e in self._entries() if e["kind"] == kind)

    def count_today(self, kind: str) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(1 for e in self._entries() if e["kind"] == kind and e["ts"].startswith(today))
