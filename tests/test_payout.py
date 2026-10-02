import json

import pytest

from control import payout as rules
from agent.config import load_config

OWNER = "0x" + "0f" * 20
AGENT_PW = "correct horse battery staple"


@pytest.fixture
def cfg():
    c = load_config("base_mainnet")
    c["owner"] = {"payout_address": OWNER}
    return c


def test_constants_match_owner_rule():
    assert (rules.PAYOUT_TRIGGER_USD, rules.PAYOUT_AMOUNT_USD) == (1000, 500)
    with pytest.raises(PermissionError):
        rules.PAYOUT_AMOUNT_USD = 10**6


@pytest.mark.parametrize("usd,due", [(999.99, 0), (1000, 500), (5000, 500), (0, 0)])
def test_due(usd, due):
    assert rules.due(usd) == due


def test_owner_address_required():
    c = dict(load_config("base_mainnet"), owner={"payout_address": ""})
    with pytest.raises(rules.PayoutRefused, match="not set"):
        rules.owner_address(c)


def _auth(cfg, **kw):
    args = dict(chain_id=8453, to=OWNER, value_wei=int(500 / 2500 * 10**18), eth_usd=2500,
                balance_wei=int(1200 / 2500 * 10**18), payouts_today=0)
    args.update(kw)
    rules.authorize(cfg, **args)


def test_authorize_ok(cfg):
    _auth(cfg)


@pytest.mark.parametrize("kw,msg", [
    ({"to": "0x" + "ee" * 20}, "not the owner"),
    ({"value_wei": int(600 / 2500 * 10**18)}, "exceeds"),
    ({"balance_wei": int(900 / 2500 * 10**18)}, "trigger"),
    ({"payouts_today": 1}, "already"),
    ({"eth_usd": 5}, "sane"),
    ({"chain_id": 84532}, "price feed"),
])
def test_authorize_refuses(cfg, kw, msg):
    with pytest.raises(rules.PayoutRefused, match=msg):
        _auth(cfg, **kw)


class FakeRPC:
    def __init__(self, eth_usd=2500.0, balance_usd=1200.0, pending_extra=0):
        import time
        self.sent = []
        price = int(eth_usd * 1e8)
        words = [0, price, 0, int(time.time()), 0]
        self.answers = {
            "eth_call": "0x" + "".join(f"{w:064x}" for w in words),
            "eth_getBalance": hex(int(balance_usd / eth_usd * 10**18)),
            "eth_estimateGas": hex(21000),
            "eth_getBlockByNumber": {"baseFeePerGas": hex(10**7)},
            "eth_maxPriorityFeePerGas": hex(10**6),
            "eth_chainId": hex(8453),
        }
        self.pending_extra = pending_extra

    def __call__(self, method, params):
        if method == "eth_getTransactionCount":
            return hex(7 + (self.pending_extra if params[1] == "pending" else 0))
        if method == "eth_sendRawTransaction":
            self.sent.append(params[0])
            return "0x" + "ab" * 32
        return self.answers[method]


@pytest.fixture
def agent_wallet(monkeypatch, tmp_path, journal):
    from agent import keystore
    from agent.wallet import OnchainWallet
    from control.paths import STATE_DIR
    ks = STATE_DIR / "test" / "keystore.json"
    ks.parent.mkdir(parents=True, exist_ok=True)
    ks.unlink(missing_ok=True)
    monkeypatch.setattr(keystore, "KEYSTORE", ks)
    monkeypatch.setenv(keystore.PASSWORD_ENV, AGENT_PW)
    address, created = keystore.ensure()
    assert created and keystore.ensure() == (address, False)  # never overwritten
    w = OnchainWallet(load_config("base_mainnet"))
    assert w.address.lower() == address.lower()
    return w


def ledger_tmp():
    from agent.ledger import Ledger
    from control.paths import STATE_DIR
    p = STATE_DIR / "test" / "payout_ledger.jsonl"
    p.unlink(missing_ok=True)
    return Ledger(p)


def test_payout_sends_exactly_500_to_owner(cfg, agent_wallet, monkeypatch):
    from eth_account import Account
    from agent import signer
    rpc = FakeRPC()
    monkeypatch.setattr(agent_wallet, "_rpc", rpc)
    ledger = ledger_tmp()
    res = signer.maybe_payout(cfg, agent_wallet, ledger)
    assert res["action"] == "sent" and len(rpc.sent) == 1
    from eth_account.typed_transactions import TypedTransaction
    from hexbytes import HexBytes
    tx = TypedTransaction.from_bytes(HexBytes(rpc.sent[0])).as_dict()
    to = tx["to"] if isinstance(tx["to"], str) else "0x" + bytes(tx["to"]).hex()
    assert to.lower() == OWNER.lower()
    assert abs(tx["value"] / 10**18 * 2500 - 500) < 0.01
    assert tx["chainId"] == 8453 and tx["nonce"] == 7
    assert Account.recover_transaction(rpc.sent[0]).lower() == agent_wallet.address.lower()
    # second payout the same day is refused
    with pytest.raises(rules.PayoutRefused, match="already"):
        signer.maybe_payout(cfg, agent_wallet, ledger)


def test_no_payout_below_trigger(cfg, agent_wallet, monkeypatch):
    from agent import signer
    rpc = FakeRPC(balance_usd=999)
    monkeypatch.setattr(agent_wallet, "_rpc", rpc)
    assert signer.maybe_payout(cfg, agent_wallet, ledger_tmp())["action"] == "none" and not rpc.sent


def test_payout_waits_for_pending_tx(cfg, agent_wallet, monkeypatch):
    from agent import signer
    rpc = FakeRPC(pending_extra=1)
    monkeypatch.setattr(agent_wallet, "_rpc", rpc)
    assert signer.maybe_payout(cfg, agent_wallet, ledger_tmp())["action"] == "wait_pending_tx" and not rpc.sent


def test_payout_without_owner_address_refused(agent_wallet, monkeypatch):
    from agent import signer
    rpc = FakeRPC()
    monkeypatch.setattr(agent_wallet, "_rpc", rpc)
    with pytest.raises(rules.PayoutRefused, match="not set"):
        signer.maybe_payout(dict(load_config("base_mainnet"), owner={"payout_address": ""}), agent_wallet, ledger_tmp())
    assert not rpc.sent


def test_keystore_is_encrypted(agent_wallet):
    from agent import keystore
    data = json.loads(keystore.KEYSTORE.read_text())
    assert "crypto" in data and "private" not in json.dumps(data).lower()


def test_configured_owner_is_valid():
    assert rules.owner_address(load_config("base_mainnet")).lower() == "0xf39d3725b8be130e090b5ab5fd96368319a13b1f"
