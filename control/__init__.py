"""Read-only control layer. Agent code may import it but cannot override it.

Owner-side protections (recommended in addition, see README):
  chmod -R a-w control config.yaml   # or mount read-only / run agent as another user
"""
from control import (  # noqa: F401
    free_models,
    guard,
    integrity,
    kill_switch,
    network,
    paths,
    payout,
    spend_limit,
    whitelist,
)
from control._frozen import ControlTamperError, freeze

freeze(__name__)
