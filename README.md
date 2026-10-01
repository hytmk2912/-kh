# sovereign-agent

AI agent viết/dịch nội dung, **tự quản ngân sách bằng token TESTNET** (Base Sepolia), Python.
Nhận 1 job → báo giá bằng ETH testnet → chọn mức tính toán theo số dư ví → gọi **model miễn phí** →
ghi kết quả, hoá đơn và nhật ký vào `SOUL.md`.

> ⚠️ Chỉ testnet. Không dùng mainnet, không dùng API trả phí, không tự đăng ký domain/VM/tài khoản.

## Chạy nhanh (máy bất kỳ, 1 phút)

```bash
pip install -r requirements.txt           # requests, PyYAML
cp .env.example .env                      # điền key free nếu có (không bắt buộc)
python3 main.py simulate                  # demo 4 trạng thái bằng ví mock, offline
python3 main.py run --job examples/job_translate.json --wallet mock --offline
bash scripts/done_check.sh                # toàn bộ kiểm tra Done -> logs/done_evidence.log
```

## Lệnh

| Lệnh | Ai dùng | Việc |
|---|---|---|
| `python3 main.py status [--wallet mock\|base_sepolia]` | agent | số dư, trạng thái, chính sách, hạn mức, integrity |
| `python3 main.py run --job F.json [--wallet ..] [--payment-tx 0x..] [--offline]` | agent | làm 1 job |
| `python3 main.py simulate` | agent | ví mock đi qua Normal → Low_compute → Critical → Dead + chặn hạn mức |
| `python3 main.py check-controls` | agent | thử phá 25 luật, tất cả phải bị chặn |
| `python3 main.py wallet-new --write-env` | **chủ** | tạo ví Base Sepolia, key ghi vào `.env` (cần `pip install eth-account`) |
| `python3 main.py owner-seal` | **chủ** | niêm phong lại sau khi chủ sửa `control/`, `config.yaml`, header SOUL |

Job mẫu: `examples/job_translate.json`, `examples/job_write.json`, `examples/job_forbidden.json` (ngành cấm).

## Model miễn phí (`.env`)

| Provider | Biến | Model được phép |
|---|---|---|
| Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash(-lite)`, `gemini-2.0-flash(-lite)` — dùng key của project **không bật billing** |
| Groq | `GROQ_API_KEY` | `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `gemma2-9b-it` |
| OpenRouter | `OPENROUTER_API_KEY` | chỉ id kết thúc bằng `:free` |
| offline | — | stub cục bộ khi không có key |

Thứ tự thử: `llm.provider_order` trong `config.yaml`. Provider không có key bị bỏ qua.
Mọi model đều qua `control/free_models.check()` — sửa config sang model trả phí sẽ bị chặn.

## Ví testnet & thanh toán

1. Chủ chạy `python3 main.py wallet-new --write-env` → `WALLET_ADDRESS`, `WALLET_PRIVATE_KEY` vào `.env` (gitignored, chmod 600).
2. Chủ tự nạp ETH Base Sepolia từ faucet (agent không làm việc này).
3. `python3 main.py status` đọc số dư thật qua `https://sepolia.base.org`.
4. Khách trả tiền: gửi ETH testnet tới `pay_to` trong `output/<job>.invoice.json`, rồi
   `python3 main.py run --job F.json --payment-tx 0x<hash>` — agent kiểm tra tx on-chain.

Private key chỉ để sẵn cho chủ; agent hiện **không ký giao dịch nào** (chi phí compute là trừ ảo vì model free).

## 4 trạng thái (`config.yaml → thresholds_eth`, `policies`)

| Trạng thái | Số dư | Model | Token tối đa | Nhận việc | Viết skill |
|---|---|---|---|---|---|
| Normal | ≥ 0.01 | strong | 2048 | có | có |
| Low_compute | ≥ 0.003 | light | 1024 | có | không |
| Critical | ≥ 0.0005 | light | 512 | chỉ khi trả trước | không |
| Dead | < 0.0005 | — | 0 | không, ghi SOUL & chờ chủ | không |

## 3 lớp kiểm soát — `control/` (agent import được, không ghi đè được)

1. **Kill switch** — chủ tạo file `KILL` ở thư mục gốc hoặc đặt `SOVEREIGN_KILL=1`. Agent kiểm tra trước mỗi job.
2. **Hạn mức chi/ngày** — `control/spend_limit.py: DAILY_LIMIT_WEI` (0.002 ETH testnet/ngày UTC), hằng số trong code, không ở config.
3. **Whitelist ngành** — `control/whitelist.py` (education, technology, travel, ecommerce, food, culture, health_wellness; loại việc write/translate).

Cơ chế bảo vệ:
- Module `control.*` bị đóng băng: `control.spend_limit.DAILY_LIMIT_WEI = ...` → `ControlTamperError`; hằng số là `frozenset`/`MappingProxyType`.
- `control/guard.py` là đường ghi file duy nhất của agent: chỉ `skills/*.md` **mới** (không ghi đè/xoá), `state/`, `logs/`, `output/`, và append `SOUL.md` sau khi xác minh header. Cấm `control/`, `config.yaml`, `.env`, `KILL`, mọi file khác; chặn path traversal.
- `control/MANIFEST.sha256` niêm phong `control/*.py`, `config.yaml`, header `SOUL.md`; sai lệch → agent từ chối chạy.
- `control/network.py`: chỉ cho HTTPS tới Gemini/Groq/OpenRouter và RPC Base Sepolia. Không registrar, không cloud VM, không mainnet.
- Output của LLM **không bao giờ được thực thi**; skill chỉ là template Markdown.

Khuyến nghị thêm (lớp OS, mạnh nhất): `chmod -R a-w control config.yaml`, hoặc chạy agent bằng user khác / mount read-only.

**Nhân bản:** `agent/replicate.py: replicate()` raise `NotImplementedError` — cần chủ duyệt tay.

## Chạy trên iPhone

**a-Shell** (miễn phí, App Store) — có Python 3 + pip, chỉ cài được gói thuần Python:
```sh
pip install requests pyyaml
# đưa repo vào: tải ZIP từ GitHub rồi giải nén vào thư mục a-Shell (Files app), hoặc `lg2 clone <url>`
cd sovereign-agent
python3 main.py simulate
python3 main.py run --job examples/job_translate.json --wallet mock --offline
```
- `eth-account` (C extension) không cài được trên a-Shell → tạo ví trên máy khác/Codespaces, chỉ copy `WALLET_ADDRESS` vào `.env` trên iPhone. Đọc số dư & xác minh thanh toán chỉ cần địa chỉ, không cần private key.
- Có API key free → bỏ `--offline`. Không có → dùng stub offline.
- Thay thế: **iSH** (Alpine Linux): `apk add python3 py3-pip git` rồi làm như Linux (chậm hơn).
- Kill switch trên iPhone: tạo file trống `KILL` trong thư mục repo bằng app Files.

## Chạy trên máy free tier

- **GitHub Codespaces** (giờ miễn phí hàng tháng của tài khoản GitHub sẵn có): mở repo → Code → Codespaces → terminal → các lệnh "Chạy nhanh". Lưu key vào Codespaces Secrets thay vì commit.
- **Google Cloud Shell** / bất kỳ VM free nào chủ đã có: `git clone`, `pip install -r requirements.txt eth-account`, chạy như trên.
- Chạy định kỳ: `crontab -e` → `*/30 * * * * cd ~/sovereign-agent && python3 main.py status >> logs/cron.log 2>&1`.

Agent **không** tự tạo các tài khoản/máy này; chủ dùng cái đã có.

## Cấu trúc

```
control/        lớp kiểm soát chỉ-đọc (kill switch, spend_limit, whitelist, free_models, network, guard, integrity)
agent/          runtime: core, wallet, llm, states, ledger, skills, soul, replicate (stub)
skills/         prompt template; agent được thêm file .md mới
examples/       job mẫu
scripts/        done_check.sh, extra_checks.py
logs/           agent.log, done_evidence.log (bằng chứng)
state/, output/ dữ liệu chạy (gitignored)
SOUL.md         header niêm phong + nhật ký append-only
config.yaml     ngưỡng, giá, model (chủ sửa rồi `owner-seal`)
TASKS.md        tiến độ
```
