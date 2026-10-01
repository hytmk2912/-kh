"""The agent's own wallet key, created by the agent and kept encrypted in
state/agent_keystore.json (standard Ethereum keystore v3, password from
AGENT_KEYSTORE_PASSWORD in .env). Back up that file + password: if they are
lost, the funds are lost."""
import json
import os

from control import guard
from control.paths import STATE_DIR

KEYSTORE = STATE_DIR / "agent_keystore.json"
PASSWORD_ENV = "AGENT_KEYSTORE_PASSWORD"
MIN_PASSWORD_LEN = 12


class KeystoreError(RuntimeError):
    pass


def _password() -> str:
    pw = os.environ.get(PASSWORD_ENV, "")
    if len(pw) < MIN_PASSWORD_LEN:
        raise KeystoreError(f"{PASSWORD_ENV} in .env must be at least {MIN_PASSWORD_LEN} characters")
    return pw


def address() -> str:
    if not KEYSTORE.exists():
        return ""
    return "0x" + json.loads(KEYSTORE.read_text())["address"].removeprefix("0x")


def ensure() -> tuple[str, bool]:
    """Return (address, created_now). Creates the wallet once; never overwrites."""
    if KEYSTORE.exists():
        return address(), False
    from eth_account import Account

    acct = Account.create()
    keystore = Account.encrypt(acct.key, _password())
    guard.write_text(KEYSTORE, json.dumps(keystore))
    os.chmod(KEYSTORE, 0o600)
    return acct.address, True


def private_key() -> bytes:
    """Only agent/signer.py calls this."""
    if not KEYSTORE.exists():
        raise KeystoreError("agent wallet not created yet (python3 main.py wallet-init)")
    from eth_account import Account

    return Account.decrypt(json.loads(KEYSTORE.read_text()), _password())
