"""Profit payout to the owner. The ONLY module that signs transactions, and
every signature is gated by control.payout.authorize()."""
import logging

from control import payout as rules
from agent import keystore, soul
from agent.config import wei_to_eth

log = logging.getLogger("sovereign")


def eth_usd(wallet) -> tuple[float, int]:
    """Chainlink ETH/USD latestRoundData() via eth_call. Returns (price, updatedAt)."""
    import time

    feed = rules.ETH_USD_FEED.get(wallet.chain_id)
    if not feed:
        raise rules.PayoutRefused(f"no ETH/USD feed for chain {wallet.chain_id}")
    raw = wallet._rpc("eth_call", [{"to": feed, "data": "0xfeaf968c"}, "latest"])
    words = [raw[2 + 64 * i: 2 + 64 * (i + 1)] for i in range(5)]
    price, updated = int(words[1], 16) / 1e8, int(words[3], 16)
    if time.time() - updated > rules.MAX_PRICE_AGE_S:
        raise rules.PayoutRefused("ETH/USD price is stale")
    return price, updated


def balance_usd(wallet) -> tuple[float, int, float]:
    price, _ = eth_usd(wallet)
    bal = wallet.onchain_balance()
    return bal / 10**18 * price, bal, price


def maybe_payout(cfg: dict, wallet, ledger, dry_run: bool = False) -> dict:
    """Send PAYOUT_AMOUNT_USD to the owner if the wallet is worth >= trigger."""
    usd, bal, price = balance_usd(wallet)
    amount_usd = rules.due(usd)
    info = {"balance_usd": round(usd, 2), "eth_usd": price, "due_usd": amount_usd}
    if not amount_usd:
        return dict(info, action="none")
    to = rules.owner_address(cfg)  # raises if the owner has not set it yet
    value = int(amount_usd / price * 10**18)
    rules.authorize(cfg, chain_id=wallet.chain_id, to=to, value_wei=value, eth_usd=price,
                    balance_wei=bal, payouts_today=ledger.count_today("payout"))
    # No overlapping payouts: a pending tx from this wallet blocks a new one.
    latest = int(wallet._rpc("eth_getTransactionCount", [wallet.address, "latest"]), 16)
    pending = int(wallet._rpc("eth_getTransactionCount", [wallet.address, "pending"]), 16)
    if pending > latest:
        return dict(info, action="wait_pending_tx")
    gas = int(wallet._rpc("eth_estimateGas", [{"from": wallet.address, "to": to, "value": hex(value)}]), 16)
    base = int(wallet._rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
    tip = int(wallet._rpc("eth_maxPriorityFeePerGas", []), 16)
    from eth_utils import to_checksum_address

    tx = {"type": 2, "chainId": wallet.chain_id, "nonce": latest, "to": to_checksum_address(to), "value": value,
          "gas": gas, "maxFeePerGas": base * 2 + tip, "maxPriorityFeePerGas": tip, "data": b""}
    if dry_run:
        return dict(info, action="dry_run", tx={k: v for k, v in tx.items() if k != "data"})

    from eth_account import Account

    signed = Account.sign_transaction(tx, keystore.private_key())
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = wallet._rpc("eth_sendRawTransaction", ["0x" + raw.hex().removeprefix("0x")])
    ledger.record("payout", value, f"owner payout ${amount_usd} to {to} tx {tx_hash}")
    soul.log("PAYOUT", to=to, usd=amount_usd, eth=wei_to_eth(value), tx=tx_hash, balance_usd_before=round(usd, 2))
    log.info("payout sent: $%s (%s ETH) -> %s tx=%s", amount_usd, wei_to_eth(value), to, tx_hash)
    return dict(info, action="sent", tx_hash=tx_hash)
