import pytest

from agent.config import load_config
from agent.wallet import OnchainWallet, WalletError

ADDR = "0x" + "ab" * 20
TX = "0x" + "12" * 32


@pytest.fixture
def wallet(monkeypatch, tmp_path):
    from agent import keystore
    monkeypatch.setattr(keystore, "KEYSTORE", tmp_path / "none.json")  # no agent wallet -> use WALLET_ADDRESS
    monkeypatch.setenv("WALLET_ADDRESS", ADDR)
    w = OnchainWallet(load_config("base_mainnet"))
    for p in (w.seen_path, w.debits_path):
        p.unlink(missing_ok=True)
    yield w
    for p in (w.seen_path, w.debits_path):
        p.unlink(missing_ok=True)


def fake_rpc(wallet, monkeypatch, *, to=ADDR, value=10**15, status="0x1", tx_block=100, head=110, chain="0x2105"):
    answers = {
        "eth_chainId": chain,
        "eth_getTransactionByHash": {"to": to, "value": hex(value), "chainId": chain},
        "eth_getTransactionReceipt": {"status": status, "blockNumber": hex(tx_block)},
        "eth_blockNumber": hex(head),
        "eth_getBalance": hex(5 * 10**16),
    }
    monkeypatch.setattr(wallet, "_rpc", lambda method, params: answers[method])


def test_mainnet_config(wallet):
    assert wallet.chain_id == 8453 and wallet.mainnet and wallet.min_confirmations == 5


def test_valid_payment_once(wallet, monkeypatch):
    fake_rpc(wallet, monkeypatch)
    assert wallet.verify_payment(TX, 10**14) == 10**15
    with pytest.raises(WalletError, match="already used"):
        wallet.verify_payment(TX.upper().replace("0X", "0x"), 10**14)


@pytest.mark.parametrize("kw,msg", [
    ({"to": "0x" + "cd" * 20}, "not sent to agent"),
    ({"status": "0x0"}, "failed"),
    ({"value": 10}, "< price"),
    ({"head": 102}, "confirmations"),
    ({"chain": "0x1"}, "RPC reports chain"),
])
def test_bad_payments(wallet, monkeypatch, kw, msg):
    fake_rpc(wallet, monkeypatch, **kw)
    with pytest.raises(WalletError, match=msg):
        wallet.verify_payment(TX, 10**14)


def test_bad_tx_hash(wallet):
    with pytest.raises(WalletError, match="64 hex"):
        wallet.verify_payment("0x1234", 1)


def test_balance_minus_virtual_debits(wallet, monkeypatch):
    fake_rpc(wallet, monkeypatch)
    wallet.debit(10**15, "test")
    assert wallet.balance() == 5 * 10**16 - 10**15


def test_bad_address(monkeypatch, tmp_path):
    from agent import keystore
    monkeypatch.setattr(keystore, "KEYSTORE", tmp_path / "none.json")
    monkeypatch.setenv("WALLET_ADDRESS", "0x123")
    with pytest.raises(WalletError):
        OnchainWallet(load_config("base_mainnet"))
