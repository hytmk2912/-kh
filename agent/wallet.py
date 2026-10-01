"""Wallets.

OnchainWallet: reads the real balance of WALLET_ADDRESS on the active Base
chain (mainnet 8453 or Sepolia 84532) via the public JSON-RPC and verifies
incoming payments. RECEIVE-ONLY: there is no signing/sending code, so the
private key is never needed at runtime. Compute costs are virtual debits in
state/ (models are free). Chain/RPC pairs outside control.network are refused.

MockWallet: offline JSON wallet, used for demos, tests and iPhone runs.
"""
import json
import os
import re

from control import guard, network
from control.paths import STATE_DIR
from agent.config import eth_to_wei


ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")
TX_RE = re.compile(r"0x[0-9a-fA-F]{64}")


class WalletError(RuntimeError):
    pass


class MockWallet:
    name = "mock"

    def __init__(self, cfg: dict, path=None, start_balance_wei=None):
        self.path = path or (STATE_DIR / "mock_wallet.json")
        self.address = "0xMOCK000000000000000000000000000000000000"
        if not self.path.exists():
            start = start_balance_wei if start_balance_wei is not None else eth_to_wei(cfg["wallet"]["mock_start_balance_eth"])
            self._save({"balance_wei": start, "seen_tx": []})

    def _load(self):
        return json.loads(self.path.read_text())

    def _save(self, data):
        guard.write_text(self.path, json.dumps(data, indent=2))

    def balance(self) -> int:
        return int(self._load()["balance_wei"])

    def set_balance(self, wei: int) -> None:
        data = self._load()
        data["balance_wei"] = int(wei)
        self._save(data)

    def debit(self, amount_wei: int, memo: str) -> None:
        data = self._load()
        data["balance_wei"] = int(data["balance_wei"]) - int(amount_wei)
        self._save(data)

    def verify_payment(self, tx_hash: str, min_wei: int) -> int:
        """Mock tx format: 0xmock<anything>; credits exactly min_wei once."""
        data = self._load()
        if not tx_hash.startswith("0xmock"):
            raise WalletError("mock wallet only accepts 0xmock... payment ids")
        if tx_hash in data["seen_tx"]:
            raise WalletError("payment already used")
        data["seen_tx"].append(tx_hash)
        data["balance_wei"] = int(data["balance_wei"]) + int(min_wei)
        self._save(data)
        return int(min_wei)


class OnchainWallet:
    def __init__(self, cfg: dict):
        chain = cfg["chain"]
        self.chain_id = int(chain["chain_id"])
        self.rpc = chain["rpc_url"]
        network.check_chain(self.chain_id, self.rpc)
        self.name = chain["name"]
        self.mainnet = self.chain_id in network.MAINNET_CHAIN_IDS
        self.min_confirmations = int(chain.get("min_confirmations", 1))
        self.address = os.environ.get("WALLET_ADDRESS", "").strip()
        if not ADDRESS_RE.fullmatch(self.address):
            raise WalletError("WALLET_ADDRESS missing/invalid in .env (0x + 40 hex chars)")
        self.debits_path = STATE_DIR / f"virtual_debits_{self.name}.json"
        self.seen_path = STATE_DIR / f"seen_payments_{self.name}.json"
        self._checked_chain = False

    def _rpc(self, method, params):
        out = network.post_json(self.rpc, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=20)
        if "error" in out:
            raise WalletError(f"RPC error: {out['error']}")
        return out["result"]

    def _ensure_chain(self):
        if not self._checked_chain:
            reported = int(self._rpc("eth_chainId", []), 16)
            if reported != self.chain_id:
                raise WalletError(f"RPC reports chain {reported}, expected {self.chain_id}")
            self._checked_chain = True

    def _json(self, path, default):
        return json.loads(path.read_text()) if path.exists() else default

    def onchain_balance(self) -> int:
        self._ensure_chain()
        return int(self._rpc("eth_getBalance", [self.address, "latest"]), 16)

    def virtual_debits(self) -> int:
        return int(self._json(self.debits_path, {"wei": 0})["wei"])

    def balance(self) -> int:
        return self.onchain_balance() - self.virtual_debits()

    def debit(self, amount_wei: int, memo: str) -> None:
        guard.write_text(self.debits_path, json.dumps({"wei": self.virtual_debits() + int(amount_wei)}))

    def verify_payment(self, tx_hash: str, min_wei: int) -> int:
        if not TX_RE.fullmatch(tx_hash or ""):
            raise WalletError("payment tx hash must be 0x + 64 hex chars")
        tx_hash = tx_hash.lower()
        self._ensure_chain()
        seen = self._json(self.seen_path, [])
        if tx_hash in seen:
            raise WalletError("payment already used")
        tx = self._rpc("eth_getTransactionByHash", [tx_hash])
        receipt = self._rpc("eth_getTransactionReceipt", [tx_hash])
        if not tx or not receipt:
            raise WalletError(f"transaction not found / not mined on {self.name}")
        if tx.get("chainId") and int(tx["chainId"], 16) != self.chain_id:
            raise WalletError("transaction belongs to another chain")
        depth = int(self._rpc("eth_blockNumber", []), 16) - int(receipt["blockNumber"], 16) + 1
        if depth < self.min_confirmations:
            raise WalletError(f"only {depth}/{self.min_confirmations} confirmations; retry later")
        if (tx.get("to") or "").lower() != self.address.lower():
            raise WalletError("payment not sent to agent wallet")
        if int(receipt.get("status", "0x0"), 16) != 1:
            raise WalletError("payment transaction failed")
        value = int(tx["value"], 16)
        if value < min_wei:
            raise WalletError(f"payment {value} wei < price {min_wei} wei")
        guard.write_text(self.seen_path, json.dumps(seen + [tx_hash]))
        return value


def make_wallet(cfg: dict, backend: str | None = None):
    backend = backend or os.environ.get("WALLET_BACKEND") or cfg["wallet"]["backend"]
    if backend == "mock":
        return MockWallet(cfg)
    if backend == "onchain":
        return OnchainWallet(cfg)
    raise WalletError(f"unknown wallet backend {backend!r}")


def new_keypair() -> tuple[str, str]:
    """Generate a fresh EVM keypair (needs eth-account). Same address on every EVM chain."""
    try:
        from eth_account import Account
    except ImportError as exc:  # pragma: no cover
        raise WalletError("pip install eth-account to generate a key") from exc
    acct = Account.create()
    return acct.address, acct.key.hex()
