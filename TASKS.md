# TASKS — sovereign-agent

v1: chỉ testnet. v2 (chủ duyệt): Base mainnet, vòng lặp nhận việc. v3: ví agent tự tạo, tự rút lợi nhuận, tự tìm việc, bộ nhớ lợi nhuận.

Trạng thái: ✅ xong · ⏸ tạm tắt có chủ đích · ⬜ việc của chủ (owner)

## Lõi
- ✅ Nhận 1 job viết/dịch (`examples/*.json`), dựng prompt từ skill, gọi LLM free, ghi `output/<id>.md`
- ✅ Báo giá theo ký tự, tính bằng ETH testnet Base Sepolia (`pricing` trong config.yaml), xuất hoá đơn `output/<id>.invoice.json`
- ✅ Xác minh thanh toán on-chain (tx tới ví agent, status=1, value ≥ giá, chống dùng lại tx)
- ✅ Ghi sổ chi/thu `state/ledger_<backend>.jsonl`
- ✅ Nhật ký vào `SOUL.md` (append-only, header được niêm phong)

## Model miễn phí
- ✅ Gemini / Groq / OpenRouter `:free` qua `.env`; chạy thật KHÔNG BAO GIỜ dùng stub (lỗi hết → giữ job thử lại). Stub chỉ khi `--offline`
- ✅ Đã chạy thật với key Gemini của chủ: `gemini-flash-latest` (hay quá tải 503) → tự chuyển `gemini-flash-lite-latest`
- ✅ `control/free_models.py` chặn mọi model ngoài allowlist (kể cả khi config.yaml bị sửa)

## Ví (v2: Base mainnet, chủ duyệt)
- ✅ `active_chain: base_mainnet` (8453) mặc định; `--chain base_sepolia` / `CHAIN=` để chạy testnet
- ✅ Ví chỉ nhận: không có code ký/gửi tx (có test quét `agent/`), không cần private key khi chạy
- ✅ Mỗi chain id chỉ đi với đúng RPC (`control.network.check_chain`) + đối chiếu `eth_chainId`
- ✅ Thanh toán mainnet cần 5 block xác nhận, đúng chain, đúng người nhận, chống dùng lại tx
- ✅ Đã xác minh thật 1 tx Base mainnet (block 52040181) bằng `verify_payment`
- ✅ Ví `mock` offline cho demo/test/iPhone
- ⬜ Chủ đặt `WALLET_ADDRESS` của ví mình giữ khoá (không dùng địa chỉ tạo trong container tạm)
- ⬜ Ví phải có ≥ 0.0005 ETH trên Base thì agent mới thoát Dead

## v3 — tự vận hành
- ✅ `wallet-init`: agent tự tạo ví, key mã hoá (keystore v3) bằng `AGENT_KEYSTORE_PASSWORD`, không bao giờ ghi đè
- ✅ `control/payout.py`: ví ≥ $1000 → gửi $500 về `owner.payout_address`, tối đa 1 lần/ngày, giá Chainlink ETH/USD (kiểm tra độ cũ + khoảng hợp lý)
- ✅ `agent/signer.py`: nơi duy nhất ký giao dịch, luôn gọi `authorize()` trước; chờ nếu còn tx pending; test giải mã tx đã ký
- ✅ `scout`: Freelancer + Remotive (chỉ đọc), lọc bất hợp pháp (bài luận hộ, review giả, spam, cờ bạc, người lớn, KYC/tài khoản) và việc không giao được
- ✅ Xếp hạng theo lợi nhuận kỳ vọng/giờ (ngân sách × xác suất thắng điều chỉnh theo số bid ÷ giờ công)
- ✅ `memory.db`: lead, đề xuất, kết quả; tự học tỉ lệ thắng, lợi nhuận/giờ; tự tránh nhóm việc lỗ
- ✅ Đề xuất tự viết cho top 5 lead mỗi lượt (`output/proposals/`)
- ✅ `loop` gộp: kill switch → rút lợi nhuận → tìm việc (mỗi 30 vòng) → xử lý inbox
- ⬜ Chủ đặt `owner.payout_address` trong config.yaml + `owner-seal` (chưa đặt = không rút)
- ⬜ Chủ gửi đề xuất bằng tài khoản của mình và ghi `outcome` (agent không tự đăng ký/nộp/nhắn khách — xem README)
- ⏸ Chi tiêu tự do tới địa chỉ khác: không làm (rủi ro prompt injection rút sạch ví)

## v4 — vốn 0
- ✅ Critical/Dead = chế độ không vốn: vẫn nhận việc, chi phí compute = 0, không bao giờ chi ETH
- ✅ `accept --lead ID --text-file F`: thắng việc → agent làm bài ngay (đã chạy thật: ví mainnet 0 ETH, Gemini, chi phí 0)
- ✅ Loại việc `proofread` (skill `skills/proofread.md`)
- ⬜ Chủ: chạy trên máy luôn bật, gửi đề xuất, giao bài, ghi `outcome`

## Vòng lặp kiếm tiền
- ✅ `python3 main.py loop`: xử lý `state/inbox/*.json` → `state/done|refused/`, dừng khi kill switch, chờ khi Dead
- ⬜ Kênh nhận job từ khách (form/email/chợ việc) — chủ tự kết nối; agent không tự tạo tài khoản
- ⬜ API key model free trong `.env` (chưa có → output chỉ là stub)

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
- ✅ Allowlist mạng: chỉ endpoint LLM free + RPC Base mainnet/Sepolia (không registrar / cloud VM / chain khác)

## Tạm tắt
- ⏸ `agent/replicate.py: replicate()` → `NotImplementedError` ("cần chủ duyệt tay")

## Done (chạy `bash scripts/done_check.sh`, log: `logs/done_evidence.log`)
- ✅ 1 `python3 -m pytest -q`
- ✅ 2 `python3 main.py check-controls` (33 luật)
- ✅ 3 `python3 main.py simulate` (đi qua đủ 4 trạng thái + chặn hạn mức ngày)
- ✅ 4 `python3 main.py run --job examples/job_translate.json --wallet mock --offline`
- ✅ 5 job ngành cấm bị từ chối
- ✅ 6 kill switch dừng agent
- ✅ 7 `replicate()` raise NotImplementedError
- ✅ 8 `status --wallet onchain` trên Base mainnet và Sepolia (số dư on-chain thật)
- ✅ 9 job trên ví Base mainnet (số dư 0 → Dead → từ chối, đúng thiết kế)
- ✅ 9b `loop --once`: job hợp lệ → done, ngành cấm → refused
- ✅ 10 sửa control/ trong bản sao → IntegrityError, agent không chạy
- ✅ 11 `.env` không bị commit, không có private key trong repo
- ✅ 12 `scout` trên job board thật · 13 `memory` · 14 `payout --dry-run` trên mainnet

## Ghi chú / giới hạn
- Phần "Done" của brief không kèm danh sách lệnh, nên bộ 11 kiểm tra trên là định nghĩa của repo này.
- Chưa có API key free trong môi trường build → log bằng chứng dùng provider `offline`. Thêm key vào `.env` rồi bỏ `--offline` là gọi model thật.
- Chi phí compute là "chi phí ảo" (model free) → trừ thật trên ví mock, trừ ảo (`state/virtual_debits.json`) trên Base Sepolia.
- Bảo vệ trong-tiến-trình chống *agent/LLM* sửa luật; để chống *con người/tiến trình khác* thì cần quyền OS (xem README).
