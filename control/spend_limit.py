"""Daily spend cap (control layer 2).

The cap is a hard-coded constant here, NOT in config.yaml, so the agent's
configuration cannot raise it. Amounts are in wei of the testnet token.
"""
from control._frozen import freeze

WEI_PER_ETH = 10**18
# 0.002 testnet ETH per UTC day.
DAILY_LIMIT_WEI = 2 * 10**15


class SpendLimitExceeded(RuntimeError):
    pass


def remaining(spent_today_wei: int) -> int:
    return max(0, DAILY_LIMIT_WEI - int(spent_today_wei))


def check(spent_today_wei: int, amount_wei: int) -> None:
    if amount_wei < 0:
        raise ValueError("amount must be >= 0")
    if int(spent_today_wei) + int(amount_wei) > DAILY_LIMIT_WEI:
        raise SpendLimitExceeded(
            f"Daily cap reached: spent={spent_today_wei} + {amount_wei} > limit={DAILY_LIMIT_WEI} wei"
        )


freeze(__name__)
