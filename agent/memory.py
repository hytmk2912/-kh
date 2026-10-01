"""Long-term work memory (SQLite, state/memory.db).

Every lead the scout sees, every proposal, every job and its real outcome is
stored here. `stats()` turns that history into per-(category, source)
numbers that the scout uses to rank new leads and to avoid losing work.
"""
import sqlite3
import time
from contextlib import closing

from control import guard
from control.paths import STATE_DIR

DB = STATE_DIR / "memory.db"

# Priors used until there is enough history (hours per job, win chance).
PRIOR_HOURS = {"translate": 2.0, "proofread": 1.0, "write": 3.0}
PRIOR_WIN, PRIOR_WEIGHT = 0.15, 5          # behaves like 5 past bids at 15% wins
AVOID_MIN_SAMPLES = 5                       # judge a category only after this many outcomes
MARKET_USD_PER_HOUR = 25                    # bigger budgets mean proportionally more work

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads(
  id TEXT PRIMARY KEY, source TEXT, category TEXT, title TEXT, url TEXT,
  budget_usd REAL, competition INTEGER, posted_ts INTEGER, seen_ts INTEGER,
  score REAL, status TEXT DEFAULT 'new', proposal_path TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS outcomes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT, category TEXT, source TEXT,
  status TEXT, revenue_usd REAL DEFAULT 0, cost_usd REAL DEFAULT 0, hours REAL DEFAULT 0, ts INTEGER);
"""


class Memory:
    def __init__(self, path=None):
        self.path = path or DB
        guard.check_write(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path)

    # ---- leads -------------------------------------------------------------
    def known(self, lead_id: str) -> bool:
        with closing(self._conn()) as c:
            return c.execute("SELECT 1 FROM leads WHERE id=?", (lead_id,)).fetchone() is not None

    def add_lead(self, lead: dict, score: float, status: str = "new") -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                "INSERT OR IGNORE INTO leads(id,source,category,title,url,budget_usd,competition,posted_ts,seen_ts,score,status)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (lead["id"], lead["source"], lead["category"], lead["title"][:300], lead["url"], lead.get("budget_usd"),
                 lead.get("competition"), lead.get("posted_ts"), int(time.time()), score, status))

    def set_lead(self, lead_id: str, **fields) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        with closing(self._conn()) as c, c:
            c.execute(f"UPDATE leads SET {cols} WHERE id=?", (*fields.values(), lead_id))

    def lead(self, lead_id: str) -> dict | None:
        with closing(self._conn()) as c:
            c.row_factory = sqlite3.Row
            row = c.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
            return dict(row) if row else None

    def leads(self, status: str | None = None, limit: int = 20) -> list:
        q, args = "SELECT * FROM leads", ()
        if status:
            q, args = q + " WHERE status=?", (status,)
        with closing(self._conn()) as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(q + " ORDER BY score DESC LIMIT ?", (*args, limit))]

    # ---- outcomes ------------------------------------------------------------
    def record_outcome(self, ref: str, category: str, source: str, status: str,
                       revenue_usd: float = 0.0, cost_usd: float = 0.0, hours: float = 0.0) -> None:
        with closing(self._conn()) as c, c:
            c.execute("INSERT INTO outcomes(ref,category,source,status,revenue_usd,cost_usd,hours,ts) VALUES(?,?,?,?,?,?,?,?)",
                      (ref, category, source, status, revenue_usd, cost_usd, hours, int(time.time())))

    def stats(self) -> dict:
        """{(category, source): {...}} from real outcomes."""
        out = {}
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT category, source, COUNT(*), SUM(status='won' OR status='done'), SUM(status='lost'),"
                " SUM(revenue_usd), SUM(cost_usd), SUM(hours) FROM outcomes"
                " WHERE status IN ('won','lost','done') GROUP BY category, source").fetchall()
        for cat, src, n, wins, losses, rev, cost, hours in rows:
            wins, rev, cost, hours = wins or 0, rev or 0.0, cost or 0.0, hours or 0.0
            profit = rev - cost
            out[(cat, src)] = {
                "samples": n, "wins": wins, "losses": losses or 0,
                "win_rate": (wins + PRIOR_WIN * PRIOR_WEIGHT) / (n + PRIOR_WEIGHT),
                "revenue_usd": round(rev, 2), "profit_usd": round(profit, 2),
                "avg_hours": hours / wins if wins and hours else PRIOR_HOURS.get(cat, 3.0),
                "profit_per_hour": round(profit / hours, 2) if hours else None,
                "avoid": n >= AVOID_MIN_SAMPLES and (wins == 0 or profit <= 0),
            }
        return out


def score(lead: dict, stats: dict) -> tuple[float, str]:
    """Expected profit per hour of effort, in USD. Returns (score, explanation)."""
    s = stats.get((lead["category"], lead["source"]))
    if s and s["avoid"]:
        return -1.0, f"avoid: {s['samples']} outcomes, {s['wins']} wins, profit ${s['profit_usd']}"
    win = s["win_rate"] if s else PRIOR_WIN
    competition = lead.get("competition") or 0
    win_adj = win / (1 + competition / 15)            # more bidders -> lower chance
    budget = lead.get("budget_usd") or 0.0
    hours = max(s["avg_hours"] if s else PRIOR_HOURS.get(lead["category"], 3.0), budget / MARKET_USD_PER_HOUR)
    value = budget * win_adj / hours
    why = f"budget ${budget:.0f} x win {win_adj:.2f} / {hours:.1f}h ({competition} bids{', learned' if s else ', prior'})"
    return round(value, 2), why
