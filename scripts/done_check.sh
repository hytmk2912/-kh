#!/usr/bin/env bash
# Runs every "Done" check and writes evidence to logs/done_evidence.log
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=logs/done_evidence.log
mkdir -p logs
: > "$LOG"
fail=0
step() {
  local name="$1"; shift
  echo "===== [$name] \$ $* =====" | tee -a "$LOG"
  "$@" 2>&1 | grep -v ' INFO ' | tee -a "$LOG"
  local rc=${PIPESTATUS[0]}
  echo "----- [$name] exit=$rc -----" | tee -a "$LOG"
  echo | tee -a "$LOG"
  [ "$rc" -eq 0 ] || fail=1
}
echo "sovereign-agent done-check $(date -u +%FT%TZ) python=$(python3 --version 2>&1)" | tee -a "$LOG"

step "1 unit tests"            python3 -m pytest -q
step "2 control layer"         python3 main.py check-controls
step "3 four states + cap"     python3 main.py simulate
step "4 job (mock wallet)"     python3 main.py run --job examples/job_translate.json --wallet mock --offline
step "5 whitelist refusal"     python3 main.py run --job examples/job_forbidden.json --wallet mock --offline
step "6 kill switch"            python3 scripts/extra_checks.py kill
step "7 replicate disabled"     python3 scripts/extra_checks.py replicate

if grep -q '^WALLET_ADDRESS=0x' .env 2>/dev/null; then
  step "8a Base MAINNET wallet status" python3 main.py --chain base_mainnet status --wallet onchain
  step "8b Base Sepolia wallet status" python3 main.py --chain base_sepolia status --wallet onchain
  step "9 job on Base mainnet wallet"  python3 main.py --chain base_mainnet run --job examples/job_write.json --wallet onchain --offline
else
  echo "===== [8-9] skipped: no WALLET_ADDRESS in .env (run: python3 main.py wallet-new --write-env) =====" | tee -a "$LOG"
fi

step "9b earning loop (mock)"   python3 scripts/extra_checks.py loop
step "12 scout real job boards" python3 main.py scout --offline
step "13 work memory"           python3 main.py memory --top 5
if [ -f state/agent_keystore.json ]; then
  step "14 owner payout check (dry run, mainnet)" python3 main.py payout --dry-run
fi
step "10 tamper detection"     python3 scripts/extra_checks.py tamper
step "11 no secrets committed" python3 scripts/extra_checks.py secrets

if [ "$fail" -eq 0 ]; then echo "ALL DONE CHECKS PASSED" | tee -a "$LOG"; else echo "SOME CHECKS FAILED" | tee -a "$LOG"; exit 1; fi
