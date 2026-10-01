"""Kill switch (control layer 1).

The OWNER engages it by either:
  * creating a file named `KILL` in the project root, or
  * setting env var SOVEREIGN_KILL=1.
The agent cannot create/delete the KILL file (see control.guard) and must call
`check()` before every unit of work.
"""
import os

from control._frozen import freeze
from control.paths import KILL_FILE

ENV_VAR = "SOVEREIGN_KILL"


class KillSwitchEngaged(RuntimeError):
    pass


def is_engaged() -> bool:
    return KILL_FILE.exists() or os.environ.get(ENV_VAR, "").strip() in {"1", "true", "yes", "on"}


def check() -> None:
    if is_engaged():
        raise KillSwitchEngaged(
            f"Kill switch engaged (file {KILL_FILE.name} present or {ENV_VAR}=1). Agent halted."
        )


freeze(__name__)
