# TASKS — sovereign-agent

Trạng thái: ✅ xong · ⏸ tạm tắt có chủ đích · ⬜ việc của chủ (owner)

## Lõi
- ✅ Nhận 1 job viết/dịch (`examples/*.json`), dựng prompt từ skill, gọi LLM free, ghi `output/<id>.md`
- ✅ Báo giá theo ký tự, tính bằng ETH testnet Base Sepolia (`pricing` trong config.yaml), xuất hoá đơn `output/<id>.invoice.json`
- ✅ Xác minh thanh toán on-chain (tx tới ví agent, status=1, value ≥ giá, chống dùng lại tx)
- ✅ Ghi sổ chi/thu `state/ledger_<backend>.jsonl`
- ✅ Nhật ký vào `SOUL.md` (append-only, header được niêm phong)

## Model miễn phí
- ✅ Gemini / Groq / OpenRouter `:free` qua `.env`; fallback stub `offline` khi chưa có key
- ✅ `control/free_models.py` chặn mọi model ngoài allowlist (kể cả khi config.yaml bị sửa)

## Ví testnet
- ✅ Base Sepolia (chain 84532), `python main.py wallet-new --write-env` → key chỉ nằm trong `.env` (gitignored, chmod 600)
- ✅ Từ chối chain id không phải testnet (kiểm tra cả cấu hình lẫn `eth_chainId` từ RPC)
- ✅ Ví `mock` offline cho demo/test/iPhone
- ⬜ Nạp ETH testnet vào ví (faucet — chủ tự làm, agent không tạo tài khoản)

## 4 trạng thái (ngưỡng ở config.yaml)
- ✅ Normal: model mạnh, 2048 token, được viết skill mới
- ✅ Low_compute: model nhẹ, 1024 token, không viết skill
- ✅ Critical: model nhẹ, 512 token, chỉ nhận việc đã trả trước
- ✅ Dead: không nhận việc, ghi SOUL, chờ chủ

## 3 lớp kiểm soát (control/, chỉ-đọc)
- ✅ Kill switch: file `KILL` hoặc `SOVEREIGN_KILL=1`
- ✅ Hạn mức chi/ngày: hằng số `DAILY_LIMIT_WEI` (0.002 ETH testnet) — không nằm trong config
- ✅ Whitelist ngành + loại việc
- ✅ Module đóng băng (gán/xoá thuộc tính → `ControlTamperError`), hằng số kiểu bất biến
- ✅ `control/guard.py`: agent chỉ ghi được `skills/` (file .md MỚI), `state/`, `logs/`, `output/`, append SOUL
- ✅ Manifest SHA-256 (`control/MANIFEST.sha256`) cho control/, config.yaml, header SOUL — sai lệch → agent không chạy
- ✅ Allowlist mạng: chỉ endpoint LLM free + RPC Base Sepolia (không registrar / cloud VM / mainnet)

## Tạm tắt
- ⏸ `agent/replicate.py: replicate()` → `NotImplementedError` ("cần chủ duyệt tay")

## Done (chạy `bash scripts/done_check.sh`, log: `logs/done_evidence.log`)
- ✅ 1 `python3 -m pytest -q`
- ✅ 2 `python3 main.py check-controls`
- ✅ 3 `python3 main.py simulate` (đi qua đủ 4 trạng thái + chặn hạn mức ngày)
- ✅ 4 `python3 main.py run --job examples/job_translate.json --wallet mock --offline`
- ✅ 5 job ngành cấm bị từ chối
- ✅ 6 kill switch dừng agent
- ✅ 7 `replicate()` raise NotImplementedError
- ✅ 8 `python3 main.py status --wallet base_sepolia` (số dư on-chain thật)
- ✅ 9 job trên ví testnet thật (số dư 0 → Dead → từ chối, đúng thiết kế)
- ✅ 10 sửa control/ trong bản sao → IntegrityError, agent không chạy
- ✅ 11 `.env` không bị commit, không có private key trong repo

## Ghi chú / giới hạn
- Phần "Done" của brief không kèm danh sách lệnh, nên bộ 11 kiểm tra trên là định nghĩa của repo này.
- Chưa có API key free trong môi trường build → log bằng chứng dùng provider `offline`. Thêm key vào `.env` rồi bỏ `--offline` là gọi model thật.
- Chi phí compute là "chi phí ảo" (model free) → trừ thật trên ví mock, trừ ảo (`state/virtual_debits.json`) trên Base Sepolia.
- Bảo vệ trong-tiến-trình chống *agent/LLM* sửa luật; để chống *con người/tiến trình khác* thì cần quyền OS (xem README).
