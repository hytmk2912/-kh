"""Outgoing-money rules (control layer 4). The ONLY transfer the agent may ever
sign is a profit payout to the owner's address.

Owner rule: when the agent wallet is worth >= PAYOUT_TRIGGER_USD, send
PAYOUT_AMOUNT_USD to the owner; the rest stays as working capital.

Why so narrow: the agent reads untrusted text from the internet (job posts,
client messages). If it could pay arbitrary addresses, one prompt-injected
job post could drain the wallet. So destinations are not decided by the agent
or the LLM: only `owner.payout_address` in the owner-sealed config.yaml.
"""
import re
from types import MappingProxyType

from control._frozen import freeze

PAYOUT_TRIGGER_USD = 1000
PAYOUT_AMOUNT_USD = 500
MAX_PAYOUTS_PER_DAY = 1
# Chainlink ETH/USD price feeds (read-only eth_call on the chain's own RPC).
ETH_USD_FEED = MappingProxyType({8453: "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"})
MAX_PRICE_AGE_S = 3 * 3600
MIN_SANE_ETH_USD, MAX_SANE_ETH_USD = 100, 100_000

_ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
_ZERO = "0x" + "0" * 40


class PayoutRefused(PermissionError):
    pass


def owner_address(cfg: dict) -> str:
    addr = str((cfg.get("owner") or {}).get("payout_address") or "").strip()
    if not _ADDR.fullmatch(addr) or addr.lower() == _ZERO:
        raise PayoutRefused("owner.payout_address not set in config.yaml (owner must set it and run owner-seal)")
    return addr


def due(balance_usd: float) -> float:
    """USD amount to pay out now (0 when below the trigger)."""
    return float(PAYOUT_AMOUNT_USD) if balance_usd >= PAYOUT_TRIGGER_USD else 0.0


def authorize(cfg: dict, *, chain_id: int, to: str, value_wei: int, eth_usd: float,
              balance_wei: int, payouts_today: int) -> None:
    """Raise unless this exact transfer is the owner payout. Called right before signing."""
    if chain_id not in ETH_USD_FEED:
        raise PayoutRefused(f"payouts only on chains with a price feed: {sorted(ETH_USD_FEED)}")
    if to.lower() != owner_address(cfg).lower():
        raise PayoutRefused(f"destination {to} is not the owner payout address")
    if payouts_today >= MAX_PAYOUTS_PER_DAY:
        raise PayoutRefused("payout already made today")
    if not (MIN_SANE_ETH_USD <= eth_usd <= MAX_SANE_ETH_USD):
        raise PayoutRefused(f"ETH/USD price {eth_usd} outside sane range")
    balance_usd = balance_wei / 10**18 * eth_usd
    if balance_usd < PAYOUT_TRIGGER_USD:
        raise PayoutRefused(f"balance ${balance_usd:.2f} < trigger ${PAYOUT_TRIGGER_USD}")
    value_usd = value_wei / 10**18 * eth_usd
    if value_usd > PAYOUT_AMOUNT_USD * 1.01:
        raise PayoutRefused(f"payout ${value_usd:.2f} exceeds ${PAYOUT_AMOUNT_USD}")


freeze(__name__)
