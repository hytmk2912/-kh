"""Extra Done checks that need a negative expectation: python3 scripts/extra_checks.py <name>"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(args, cwd=ROOT, env=None):
    return subprocess.run([PY, *args], cwd=cwd, env=env, capture_output=True, text=True)


def kill():
    env = dict(os.environ, SOVEREIGN_KILL="1")
    p = run(["main.py", "run", "--job", "examples/job_write.json", "--wallet", "mock", "--offline"], env=env)
    print("\n".join(l for l in p.stdout.splitlines() if " INFO " not in l))
    assert '"status": "halted"' in p.stdout, "kill switch did not halt the agent"
    print("kill switch halted the job (PASS)")


def replicate():
    sys.path.insert(0, str(ROOT))
    from agent.replicate import replicate as rep
    try:
        rep()
    except NotImplementedError as exc:
        print("NotImplementedError:", exc, "(PASS)")
        return
    raise AssertionError("replicate() did not raise")


def loop():
    inbox = ROOT / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "examples/job_translate.json", inbox / "loop-ok.json")
    shutil.copy(ROOT / "examples/job_forbidden.json", inbox / "loop-bad.json")
    p = run(["main.py", "loop", "--wallet", "mock", "--offline", "--once", "--no-scout"])
    print("\n".join(l for l in p.stdout.splitlines() if "loop" in l or "->" in l))
    assert (ROOT / "state/done/loop-ok.json").exists() and (ROOT / "state/refused/loop-bad.json").exists()
    assert not list(inbox.glob("loop-*.json"))
    print("loop consumed inbox: ok -> state/done, forbidden -> state/refused (PASS)")


def tamper():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("control", "agent", "skills", "examples"):
            shutil.copytree(ROOT / name, Path(tmp) / name, ignore=shutil.ignore_patterns("__pycache__", "learned_*"))
        for name in ("config.yaml", "SOUL.md", "main.py"):
            shutil.copy(ROOT / name, tmp)
        with open(Path(tmp) / "control/spend_limit.py", "a") as fh:
            fh.write("\nDAILY_LIMIT_WEI = 10**30  # tampered\n")
        print("tampered copy: appended `DAILY_LIMIT_WEI = 10**30` to control/spend_limit.py")
        p = run(["main.py", "run", "--job", "examples/job_translate.json", "--wallet", "mock", "--offline"], cwd=tmp)
        last = (p.stderr.strip().splitlines() or [""])[-1]
        print(last)
        assert p.returncode != 0 and "IntegrityError" in last, "tampering not detected"
        print("agent refused to run on tampered control layer (PASS)")


def secrets():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert ".env" not in tracked, ".env is tracked!"
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0, ".env not ignored"
    key_re = re.compile(r"0x[0-9a-fA-F]{64}")
    for f in tracked:
        p = ROOT / f
        if p.is_file() and not f.startswith("logs/") and key_re.search(p.read_text(errors="ignore")):
            raise AssertionError(f"key-like 64-hex string in tracked file {f}")
    print(f".env gitignored & untracked; no private-key-like strings in {len(tracked)} tracked files (PASS)")


if __name__ == "__main__":
    {"kill": kill, "loop": loop, "replicate": replicate, "tamper": tamper, "secrets": secrets}[sys.argv[1]]()
