#!/usr/bin/env python3
"""sovereign-agent CLI.

Agent commands : status | run | loop | scout | memory | payout | wallet-init | simulate | check-controls
Owner commands : outcome (record real results) | wallet-new | owner-seal
"""
import argparse
import json
import logging
import os
import re
import sys
import time

from control import free_models, guard, integrity, kill_switch, network, spend_limit, whitelist
from control.paths import LOGS_DIR, ROOT, STATE_DIR
from agent import keystore, scout, signer, soul
from agent import replicate as replicate_mod
from agent.memory import Memory
from agent.config import eth_to_wei, load_config, load_env, wei_to_eth
from agent.core import run_job
from agent.ledger import Ledger
from agent.states import policy_for, state_for_balance
from agent.wallet import MockWallet, make_wallet, new_keypair


def setup_logging():
    LOGS_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOGS_DIR / "agent.log", encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


log = logging.getLogger("sovereign")


def cmd_status(args, cfg):
    integrity_problems = integrity.problems()
    wallet = make_wallet(cfg, args.wallet)
    bal = wallet.balance()
    state = state_for_balance(bal, cfg)
    pol = policy_for(state, cfg)
    ledger = Ledger.for_wallet(wallet)
    info = {
        "chain": f"{cfg['chain']['name']} (chain_id {cfg['chain']['chain_id']})",
        "real_money": cfg["chain"]["chain_id"] in network.MAINNET_CHAIN_IDS and wallet.name != "mock",
        "wallet_backend": wallet.name,
        "address": wallet.address,
        "balance_eth": wei_to_eth(bal),
        "state": state,
        "policy": pol.__dict__,
        "kill_switch": kill_switch.is_engaged(),
        "spent_today_eth": wei_to_eth(ledger.spent_today()),
        "daily_limit_eth": wei_to_eth(spend_limit.DAILY_LIMIT_WEI),
        "integrity": "OK" if not integrity_problems else integrity_problems,
    }
    if wallet.name != "mock":
        info["onchain_balance_eth"] = wei_to_eth(wallet.onchain_balance())
        info["virtual_debits_eth"] = wei_to_eth(wallet.virtual_debits())
        info["agent_owned_wallet"] = bool(keystore.address())
        try:
            usd, _, price = signer.balance_usd(wallet)
            info.update(balance_usd=round(usd, 2), eth_usd=price)
        except Exception as exc:
            info["balance_usd"] = f"n/a ({exc})"
        from control import payout as payout_rules
        try:
            owner = payout_rules.owner_address(cfg)
        except payout_rules.PayoutRefused:
            owner = "NOT SET (payouts disabled)"
        info["payout_rule"] = f">= ${payout_rules.PAYOUT_TRIGGER_USD} -> send ${payout_rules.PAYOUT_AMOUNT_USD} to {owner}"
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def cmd_run(args, cfg):
    with open(args.job, encoding="utf-8") as fh:
        job = json.load(fh)
    if args.payment_tx:
        job["payment_tx"] = args.payment_tx
    result = run_job(job, cfg, make_wallet(cfg, args.wallet), offline=args.offline)
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
    return 0 if result.status in ("done", "refused") else 2


def cmd_loop(args, cfg):
    """Autonomous loop. Each round:
      1. kill switch -> stop
      2. owner payout check ($1000 -> send $500 to owner), on-chain wallets only
      3. scout the job boards every `scout.every_rounds` rounds
      4. process jobs in state/inbox/ -> state/done/ | state/refused/
         (errors stay in the inbox and are retried). With 0 capital the
         state policy allows zero-cost work only, so the loop keeps working.
    """
    inbox, done, refused = (STATE_DIR / d for d in ("inbox", "done", "refused"))
    for d in (inbox, done, refused):
        d.mkdir(parents=True, exist_ok=True)
    wallet = make_wallet(cfg, args.wallet)
    log.info("loop start | chain=%s wallet=%s address=%s inbox=%s", cfg["chain"]["name"], wallet.name, wallet.address, inbox)
    rounds = 0
    while True:
        rounds += 1
        if kill_switch.is_engaged():
            log.warning("kill switch engaged -> loop stops")
            return 0
        if wallet.name != "mock" and keystore.address():
            try:
                log.info("payout check: %s", signer.maybe_payout(cfg, wallet, Ledger.for_wallet(wallet)))
            except Exception as exc:
                log.warning("payout check skipped: %s: %s", type(exc).__name__, exc)
        if not args.no_scout and (rounds - 1) % cfg["scout"]["every_rounds"] == 0:
            try:
                summary = scout.run(cfg, offline=args.offline)
                log.info("scout: %d new leads, %d proposals drafted", summary["new_leads"], len(summary["drafted"]))
            except Exception as exc:
                log.warning("scout failed: %s: %s", type(exc).__name__, exc)
        try:
            state = state_for_balance(wallet.balance(), cfg)
        except Exception as exc:
            log.error("balance check failed: %s", exc)
            state = None
        jobs = sorted(inbox.glob("*.json"))
        if state:
            for path in jobs[: args.max_jobs]:
                try:
                    job = json.loads(path.read_text(encoding="utf-8"))
                    result = run_job(job, cfg, wallet, offline=args.offline)
                except Exception as exc:  # keep job for retry
                    log.error("job %s failed, will retry: %s: %s", path.name, type(exc).__name__, exc)
                    continue
                target = done if result.status == "done" else refused
                guard.move(path, target / path.name)
                guard.write_text(target / f"{path.stem}.result.json", json.dumps(result.__dict__, indent=2, ensure_ascii=False))
                log.info("job %s -> %s (%s)", path.name, result.status, result.reason or result.model)
                if result.status == "halted":
                    return 0
        if args.once or (args.rounds and rounds >= args.rounds):
            return 0
        time.sleep(args.interval)


def cmd_wallet_init(args, cfg):
    """The agent creates its OWN wallet (once). Needs AGENT_KEYSTORE_PASSWORD in .env."""
    address, created = keystore.ensure()
    print(json.dumps({"agent_address": address, "created_now": created, "keystore": str(keystore.KEYSTORE),
                      "chain": cfg["chain"]["name"]}, indent=2))
    if created:
        soul.log("WALLET_CREATED", address=address, chain=cfg["chain"]["name"])
        print("BACK UP state/agent_keystore.json AND the password now. Lose them = lose the funds.")
    return 0


def cmd_payout(args, cfg):
    wallet = make_wallet(cfg, "onchain")
    print(json.dumps(signer.maybe_payout(cfg, wallet, Ledger.for_wallet(wallet), dry_run=args.dry_run), indent=2))
    return 0


def cmd_scout(args, cfg):
    summary = scout.run(cfg, offline=args.offline)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_memory(args, cfg):
    mem = Memory()
    stats = {f"{c}/{s}": v for (c, s), v in mem.stats().items()}
    top = [{k: l[k] for k in ("id", "status", "category", "score", "budget_usd", "title", "url")} for l in mem.leads(limit=args.top)]
    print(json.dumps({"learned_stats": stats or "no outcomes recorded yet", "top_leads": top}, indent=2, ensure_ascii=False))
    return 0


def cmd_accept(args, cfg):
    """You won a lead: give the client's material, the agent does the work now."""
    mem = Memory()
    lead = mem.lead(args.lead)
    if not lead:
        print(f"unknown lead {args.lead} (see `python3 main.py memory`)")
        return 1
    material = open(args.text_file, encoding="utf-8").read()
    jtype = lead["category"] if lead["category"] in ("write", "translate", "proofread") else "write"
    job = {"id": lead["id"].replace(":", "_"), "type": jtype, "industry": "general",
           "target_lang": args.target_lang, "brief": args.brief or lead["title"]}
    if jtype == "write":
        job["brief"] = f"{job['brief']}\n\nClient instructions:\n{material}"
    else:
        job["source_text"] = material
    result = run_job(job, cfg, make_wallet(cfg, args.wallet))
    if result.status == "done":
        mem.set_lead(lead["id"], status="in_progress")
        print(f"Deliverable: {result.output_path}\nReview it, deliver from your account, then run:\n"
              f"  python3 main.py outcome --lead {lead['id']} --won --revenue-usd <paid> --hours <your review time>")
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
    return 0 if result.status == "done" else 1


def cmd_outcome(args, cfg):
    """Record what really happened with a lead (feeds the profit memory)."""
    mem = Memory()
    lead = mem.lead(args.lead)
    if not lead:
        print(f"unknown lead {args.lead}")
        return 1
    status = "won" if args.won else "lost"
    mem.record_outcome(args.lead, lead["category"], lead["source"], status,
                       revenue_usd=args.revenue_usd, cost_usd=args.cost_usd, hours=args.hours)
    mem.set_lead(args.lead, status=status)
    soul.log("OUTCOME", lead=args.lead, status=status, revenue_usd=args.revenue_usd, hours=args.hours)
    print(json.dumps(mem.stats().get((lead["category"], lead["source"])), indent=2))
    return 0


def cmd_simulate(args, cfg):
    """Walk the agent through all 4 states with an offline mock wallet."""
    sim = STATE_DIR / "sim"
    for f in ("wallet.json", "ledger.jsonl", "ledger_cap.jsonl"):
        if (sim / f).exists():
            (sim / f).unlink()
    wallet = MockWallet(cfg, path=sim / "wallet.json")
    ledger = Ledger(sim / "ledger.jsonl")
    with open(ROOT / "examples/job_translate.json", encoding="utf-8") as fh:
        base_job = json.load(fh)

    rows = []
    for i, (eth, pay) in enumerate([(0.02, None), (0.005, None), (0.001, None), (0.001, "0xmock-pay-1"), (0, None)]):
        wallet.set_balance(eth_to_wei(eth))
        job = dict(base_job, id=f"sim-{i}-{eth}", payment_tx=pay) if pay else dict(base_job, id=f"sim-{i}-{eth}")
        r = run_job(job, cfg, wallet, ledger, offline=True)
        rows.append((eth, pay or "-", r.state, r.status, r.model or "-", r.reason[:70]))

    # Daily cap: pretend today's spend already hit the hard limit.
    cap_ledger = Ledger(sim / "ledger_cap.jsonl")
    cap_ledger.record("spend", spend_limit.DAILY_LIMIT_WEI, "sim: cap reached")
    wallet.set_balance(eth_to_wei(0.02))
    r = run_job(dict(base_job, id="sim-cap"), cfg, wallet, cap_ledger, offline=True)
    rows.append((0.02, "cap-hit", r.state, r.status, "-", r.reason[:70]))

    print(f"{'balance':>8} | {'payment':<13} | {'state':<11} | {'status':<7} | {'model':<12} | reason")
    for row in rows:
        print(f"{row[0]:>8} | {row[1]:<13} | {row[2]:<11} | {row[3]:<7} | {row[4]:<12} | {row[5]}")
    states_seen = {row[2] for row in rows}
    ok = {"Normal", "Low_compute", "Critical", "Dead"} <= states_seen and rows[-1][3] == "refused"
    print("SIMULATION", "PASS" if ok else "FAIL", "- states seen:", sorted(states_seen))
    return 0 if ok else 1


def cmd_check_controls(args, cfg):
    checks = []

    def expect(name, fn, exc_types):
        try:
            fn()
        except exc_types as exc:
            checks.append((True, name, f"blocked: {type(exc).__name__}: {str(exc)[:90]}"))
            return
        except Exception as exc:  # wrong exception type
            checks.append((False, name, f"unexpected {type(exc).__name__}: {exc}"))
            return
        checks.append((False, name, "NOT blocked"))

    def allowed(name, fn):
        try:
            res = fn()
            checks.append((True, name, f"allowed: {res}"))
        except Exception as exc:
            checks.append((False, name, f"failed: {type(exc).__name__}: {exc}"))

    import control

    checks.append((not integrity.problems(), "integrity manifest matches", integrity.problems() or "OK"))
    expect("override control.spend_limit.DAILY_LIMIT_WEI", lambda: setattr(spend_limit, "DAILY_LIMIT_WEI", 10**30), PermissionError)
    expect("replace control.kill_switch.check", lambda: setattr(kill_switch, "check", lambda: None), PermissionError)
    expect("delete control.whitelist", lambda: delattr(control, "whitelist"), PermissionError)
    expect("mutate whitelist set", lambda: whitelist.ALLOWED_INDUSTRIES.add("gambling"), AttributeError)
    expect("agent writes control/kill_switch.py", lambda: guard.write_text(ROOT / "control/kill_switch.py", "x"), PermissionError)
    expect("agent writes config.yaml", lambda: guard.write_text(ROOT / "config.yaml", "x"), PermissionError)
    expect("agent writes .env", lambda: guard.write_text(ROOT / ".env", "x"), PermissionError)
    expect("agent deletes KILL / writes KILL", lambda: guard.write_text(ROOT / "KILL", ""), PermissionError)
    expect("agent overwrites SOUL.md", lambda: guard.write_text(ROOT / "SOUL.md", "pwned"), PermissionError)
    expect("agent injects SOUL header marker", lambda: guard.append_soul(integrity.SOUL_HEADER_START), PermissionError)
    expect("path traversal skills/../config.yaml", lambda: guard.write_text(ROOT / "skills/../config.yaml", "x"), PermissionError)
    expect("agent overwrites existing skill", lambda: guard.write_text(ROOT / "skills/translate.md", "x"), PermissionError)
    expect("agent writes executable skill .py", lambda: guard.write_text(ROOT / "skills/evil.py", "x"), PermissionError)
    probe = ROOT / "skills" / "zz_check_probe.md"
    if probe.exists():
        probe.unlink()
    allowed("agent creates NEW skill skills/zz_check_probe.md", lambda: guard.write_text(probe, "# probe\n").name)
    probe.unlink(missing_ok=True)
    expect("paid model openai/gpt-4o", lambda: free_models.check("openrouter", "openai/gpt-4o"), PermissionError)
    expect("paid model gemini-2.5-pro", lambda: free_models.check("gemini", "gemini-2.5-pro"), PermissionError)
    allowed("free model groq/llama-3.1-8b-instant", lambda: free_models.check("groq", "llama-3.1-8b-instant") or "ok")
    expect("network to domain registrar", lambda: network.check_url("https://api.namecheap.com/xml.response"), PermissionError)
    expect("network to cloud VM API", lambda: network.check_url("https://compute.googleapis.com/compute/v1"), PermissionError)
    expect("network to Ethereum L1 RPC", lambda: network.check_url("https://eth.llamarpc.com"), PermissionError)
    expect("chain id paired with wrong RPC", lambda: network.check_chain(8453, "https://sepolia.base.org"), PermissionError)
    expect("unknown chain id", lambda: network.check_chain(1, "https://mainnet.base.org"), PermissionError)
    from control import payout as payout_rules
    owner_cfg = dict(cfg, owner={"payout_address": "0x" + "0f" * 20})
    big = dict(chain_id=8453, eth_usd=2500.0, balance_wei=10**18, payouts_today=0)
    expect("payout to a stranger address", lambda: payout_rules.authorize(
        owner_cfg, to="0x" + "ee" * 20, value_wei=2 * 10**17, **big), PermissionError)
    expect("payout above $500", lambda: payout_rules.authorize(
        owner_cfg, to="0x" + "0f" * 20, value_wei=3 * 10**17, **big), PermissionError)
    expect("payout below $1000 balance", lambda: payout_rules.authorize(
        owner_cfg, to="0x" + "0f" * 20, value_wei=10**16, **dict(big, balance_wei=10**17)), PermissionError)
    expect("payout with no owner address set", lambda: payout_rules.owner_address({"owner": {"payout_address": ""}}), PermissionError)
    expect("override payout amount", lambda: setattr(payout_rules, "PAYOUT_AMOUNT_USD", 10**9), PermissionError)
    expect("POST to job board (auto-apply/sign-up)", lambda: network.post_json("https://www.freelancer.com/api/x", {}), PermissionError)
    expect("whitelist: gambling", lambda: whitelist.check("write", "gambling"), PermissionError)
    expect("spend over daily cap", lambda: spend_limit.check(spend_limit.DAILY_LIMIT_WEI, 1), RuntimeError)
    expect("replicate()", replicate_mod.replicate, NotImplementedError)

    def kill_test():
        os.environ[kill_switch.ENV_VAR] = "1"
        try:
            kill_switch.check()
        finally:
            os.environ.pop(kill_switch.ENV_VAR, None)
    expect("kill switch engaged (SOVEREIGN_KILL=1)", kill_test, RuntimeError)

    failed = 0
    for ok, name, detail in checks:
        failed += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"CONTROLS {'PASS' if not failed else 'FAIL'} ({len(checks) - failed}/{len(checks)})")
    return 0 if not failed else 1


def cmd_wallet_new(args, cfg):
    """OWNER: create an EVM key (valid on Base mainnet and Sepolia). Key only goes to .env.

    For real money prefer an address from a wallet YOU hold (MetaMask, Coinbase
    Wallet...): the agent only needs WALLET_ADDRESS, never the private key.
    """
    address, key = new_keypair()
    print(f"New EVM address (works on {cfg['chain']['name']}, chain {cfg['chain']['chain_id']}): {address}")
    print("WARNING: back up the key yourself. If this machine/container is lost, funds sent here are lost.")
    if args.write_env:
        env = ROOT / ".env"
        existing = env.read_text() if env.exists() else ""
        if re.search(r"^WALLET_PRIVATE_KEY=\s*\S", existing, re.M):
            print("Refusing: .env already has WALLET_PRIVATE_KEY. Remove it first.")
            return 1
        lines = [l for l in existing.splitlines() if not l.startswith(("WALLET_ADDRESS=", "WALLET_PRIVATE_KEY="))]
        lines += [f"WALLET_ADDRESS={address}", f"WALLET_PRIVATE_KEY={key if key.startswith('0x') else '0x' + key}"]
        env.write_text("\n".join(lines) + "\n")
        os.chmod(env, 0o600)
        print("Saved to .env (gitignored, chmod 600). Private key NOT printed.")
    else:
        print("Private key not saved. Re-run with --write-env to store it in .env.")
    print("Testnet: fund from a Base Sepolia faucet. Mainnet: agent only RECEIVES payments here.")
    return 0


def cmd_owner_seal(args, cfg):
    hashes = integrity.seal()
    for name, digest in hashes.items():
        print(f"{digest[:16]}  {name}")
    print(f"Sealed {len(hashes)} entries into control/MANIFEST.sha256")
    return 0


def main(argv=None):
    load_env()
    setup_logging()
    p = argparse.ArgumentParser(prog="sovereign-agent")
    p.add_argument("--chain", choices=["base_mainnet", "base_sepolia"], help="override config active_chain")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--wallet", choices=["mock", "onchain"])
    r = sub.add_parser("run")
    r.add_argument("--job", required=True)
    r.add_argument("--wallet", choices=["mock", "onchain"])
    r.add_argument("--payment-tx")
    r.add_argument("--offline", action="store_true", help="use local stub instead of free LLM APIs")
    lp = sub.add_parser("loop")
    lp.add_argument("--wallet", choices=["mock", "onchain"])
    lp.add_argument("--interval", type=int, default=60, help="seconds between rounds")
    lp.add_argument("--max-jobs", type=int, default=5, help="jobs per round")
    lp.add_argument("--rounds", type=int, default=0, help="stop after N rounds (0 = forever)")
    lp.add_argument("--once", action="store_true")
    lp.add_argument("--offline", action="store_true")
    lp.add_argument("--no-scout", action="store_true", help="do not search job boards")
    sub.add_parser("wallet-init")
    po = sub.add_parser("payout"); po.add_argument("--dry-run", action="store_true")
    sc = sub.add_parser("scout"); sc.add_argument("--offline", action="store_true")
    me = sub.add_parser("memory"); me.add_argument("--top", type=int, default=10)
    ac = sub.add_parser("accept")
    ac.add_argument("--lead", required=True)
    ac.add_argument("--text-file", required=True, help="client's source text / instructions (UTF-8)")
    ac.add_argument("--target-lang", default="en")
    ac.add_argument("--brief", default="")
    ac.add_argument("--wallet", choices=["mock", "onchain"])
    oc = sub.add_parser("outcome")
    oc.add_argument("--lead", required=True)
    g = oc.add_mutually_exclusive_group(required=True)
    g.add_argument("--won", action="store_true"); g.add_argument("--lost", action="store_true")
    oc.add_argument("--revenue-usd", type=float, default=0.0)
    oc.add_argument("--cost-usd", type=float, default=0.0)
    oc.add_argument("--hours", type=float, default=0.0)
    sub.add_parser("simulate")
    sub.add_parser("check-controls")
    w = sub.add_parser("wallet-new"); w.add_argument("--write-env", action="store_true")
    sub.add_parser("owner-seal")
    args = p.parse_args(argv)
    cfg = load_config(args.chain)
    handler = {
        "status": cmd_status, "run": cmd_run, "simulate": cmd_simulate, "check-controls": cmd_check_controls,
        "wallet-new": cmd_wallet_new, "loop": cmd_loop,
        "wallet-init": cmd_wallet_init, "payout": cmd_payout, "scout": cmd_scout, "memory": cmd_memory,
        "outcome": cmd_outcome, "accept": cmd_accept, "owner-seal": cmd_owner_seal,
    }[args.cmd]
    return handler(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
