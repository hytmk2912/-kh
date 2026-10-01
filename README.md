# sovereign-agent

AI agent viết/dịch nội dung, **tự quản ngân sách bằng ETH trên Base**, Python.
Nhận job → báo giá bằng ETH → chọn mức tính toán theo số dư ví → gọi **model miễn phí** →
ghi kết quả, hoá đơn và nhật ký vào `SOUL.md`.

- Mặc định: **Base mainnet (chain 8453, ETH THẬT)**, theo quyết định của chủ. Chạy testnet: `--chain base_sepolia` hoặc `CHAIN=base_sepolia`.
- Ví do **agent tự tạo**. Khoản chi duy nhất được phép: rút $500 về ví chủ khi ví đạt $1000 (`control/payout.py`).

> ⚠️ Không dùng API trả phí, không tự đăng ký domain/VM/tài khoản. Trên mainnet, chỉ dùng địa chỉ ví bạn tự giữ khoá.

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
| `python3 main.py [--chain base_mainnet\|base_sepolia] <lệnh>` | — | chọn chain (mặc định theo `active_chain`) |
| `python3 main.py status [--wallet mock\|onchain]` | agent | số dư, trạng thái, chính sách, hạn mức, integrity |
| `python3 main.py run --job F.json [--wallet ..] [--payment-tx 0x..] [--offline]` | agent | làm 1 job |
| `python3 main.py loop [--interval 60] [--max-jobs 5] [--once] [--no-scout]` | agent | vòng lặp tự vận hành: rút lợi nhuận, tìm việc, xử lý `state/inbox/` |
| `python3 main.py wallet-init` | agent | agent tự tạo ví của nó (cần `AGENT_KEYSTORE_PASSWORD`) |
| `python3 main.py scout [--offline]` | agent | tìm việc trên Freelancer/Remotive, xếp hạng, viết đề xuất |
| `python3 main.py memory` | agent | thống kê lợi nhuận đã học + lead tốt nhất |
| `python3 main.py payout [--dry-run]` | agent | kiểm tra/thực hiện rút $500 khi ví ≥ $1000 |
| `python3 main.py outcome --lead ID --won/--lost [--revenue-usd N --hours H]` | **chủ** | ghi kết quả thật để agent học |
| `python3 main.py simulate` | agent | ví mock đi qua Normal → Low_compute → Critical → Dead + chặn hạn mức |
| `python3 main.py check-controls` | agent | thử phá 33 luật, tất cả phải bị chặn |
| `python3 main.py wallet-new --write-env` | **chủ** | tạo địa chỉ EVM, key ghi vào `.env` (cần `pip install eth-account`). Mainnet: nên dùng ví riêng của bạn |
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

## Ví & thanh toán (Base mainnet)

1. Lấy địa chỉ từ ví bạn tự giữ khoá (MetaMask / Coinbase Wallet, mạng Base) → ghi `WALLET_ADDRESS=0x...` vào `.env`. **Không cần private key.**
   (Có thể dùng `wallet-new --write-env`, nhưng phải tự sao lưu key; mất máy = mất tiền.)
2. `python3 main.py status` đọc số dư thật qua `https://mainnet.base.org` (`"real_money": true`).
3. Số dư quyết định trạng thái. Ví 0 ETH → Dead → agent không nhận việc. Muốn agent làm việc
   thì ví phải có ≥ 0.0005 ETH (Critical, chỉ nhận việc trả trước) hoặc ≥ 0.01 ETH (Normal).
4. Khách trả tiền: gửi ETH trên Base tới `pay_to` trong `output/<job>.invoice.json`, rồi thêm
   `"payment_tx": "0x<hash>"` vào job (hoặc `run --payment-tx`). Agent kiểm tra on-chain: đúng chain,
   gửi tới ví agent, status=1, value ≥ giá, **đủ 5 block xác nhận**, mỗi tx chỉ dùng 1 lần.

Chi phí compute là trừ ảo (`state/virtual_debits_<chain>.json`) vì model free; agent không bao giờ chuyển tiền đi.

## Chế độ tự vận hành (v3)

```bash
pip install -r requirements.txt               # cần eth-account cho ví agent
echo "AGENT_KEYSTORE_PASSWORD=<mật khẩu dài>" >> .env
python3 main.py wallet-init                    # agent TỰ tạo ví của nó (chỉ 1 lần)
# chủ: đặt owner.payout_address trong config.yaml rồi `python3 main.py owner-seal`
python3 main.py loop --interval 60             # chạy mãi: rút lợi nhuận + tìm việc + làm job
```

| Việc | Agent tự làm | Ghi chú |
|---|---|---|
| Tạo & giữ ví | ✅ `wallet-init`, key mã hoá trong `state/agent_keystore.json` | Sao lưu file này + mật khẩu. Mất = mất tiền |
| Rút lợi nhuận | ✅ ví ≥ $1000 (giá Chainlink ETH/USD) → gửi $500 về `owner.payout_address`, phần còn lại làm vốn | Tối đa 1 lần/ngày; chỉ gửi được tới đúng địa chỉ chủ |
| Tìm việc trên Internet | ✅ đọc Freelancer + Remotive (API công khai), lọc việc bất hợp pháp/không làm được | Chỉ đọc, không đăng ký tài khoản |
| Xếp hạng việc lời nhất | ✅ điểm = ngân sách × xác suất thắng ÷ giờ công, có tính số người đang bid | Học từ kết quả thật |
| Nhớ việc đã làm | ✅ `state/memory.db` (SQLite): lead, đề xuất, kết quả, doanh thu, giờ công | `python3 main.py memory` |
| Tránh việc lỗ | ✅ nhóm (loại việc, nguồn) có ≥ 5 kết quả mà 0 thắng hoặc lợi nhuận ≤ 0 → tự bỏ qua | |
| Viết đề xuất | ✅ `output/proposals/*.md` cho 5 lead tốt nhất mỗi lượt | Bài đăng việc được coi là dữ liệu không tin cậy |
| **Gửi đề xuất / nói chuyện với khách** | ❌ **chủ làm** bằng tài khoản của chủ | Lý do bên dưới |
| Ghi kết quả | chủ: `python3 main.py outcome --lead freelancer:123 --won --revenue-usd 80 --hours 2` (hoặc `--lost`) | Đây là dữ liệu để agent học |

### Những gì agent cố ý KHÔNG tự làm, và lý do

- **Tiêu tiền tuỳ ý / chuyển tới địa chỉ khác:** agent đọc nội dung lạ trên Internet (bài đăng việc, tin nhắn khách). Nếu nó được gửi tiền tới địa chỉ tuỳ ý, chỉ một bài đăng chứa câu lệnh độc (prompt injection) là có thể rút sạch ví. Vì vậy nơi nhận tiền duy nhất là địa chỉ chủ đặt trong `config.yaml` (được niêm phong); luật nằm trong `control/payout.py`. Agent cũng chưa có khoản chi nào cần tiền vì model đều miễn phí.
- **Tự đăng ký tài khoản, tự nộp đề xuất, tự nhắn khách lạ:** Freelancer/Upwork/Fiverr cấm tài khoản tự động và yêu cầu xác minh danh tính người thật; gửi tin hàng loạt cho người lạ là spam. Vi phạm sẽ bị khoá tài khoản (của bạn). Agent chỉ đọc API công khai; các host việc làm bị chặn POST ở `control/network.py`.
- **Tiền từ khách trên Freelancer** được trả bằng tiền pháp định vào tài khoản Freelancer của **chủ**, không vào ví ETH của agent. Ví agent chỉ nhận tiền khi khách trả bằng ETH trên Base, hoặc khi chủ nạp vốn vào ví.

## Vòng lặp nhận việc

```bash
mkdir -p state/inbox
cp examples/job_translate.json state/inbox/   # khách/chủ thả job JSON vào đây
python3 main.py loop --interval 60            # chạy mãi; Ctrl+C hoặc tạo file KILL để dừng
```
Mỗi vòng: kiểm tra kill switch → đọc số dư → nếu Dead thì chờ, không nhận việc → xử lý tối đa
`--max-jobs` job → `state/done/` hoặc `state/refused/` kèm `*.result.json`. Job lỗi (vd. model API lỗi) ở lại inbox để thử lại.
Agent **không tự đi tìm khách**: bạn phải đưa job vào inbox (tự tay, qua script đồng bộ email/form của bạn...).

## 4 trạng thái (`config.yaml → thresholds_eth`, `policies`)

| Trạng thái | Số dư | Model | Token tối đa | Nhận việc | Viết skill |
|---|---|---|---|---|---|
| Normal | ≥ 0.01 | strong | 2048 | có | có |
| Low_compute | ≥ 0.003 | light | 1024 | có | không |
| Critical | ≥ 0.0005 | light | 512 | chỉ khi trả trước | không |
| Dead | < 0.0005 | — | 0 | không, ghi SOUL & chờ chủ | không |

## 3 lớp kiểm soát — `control/` (agent import được, không ghi đè được)

1. **Kill switch** — chủ tạo file `KILL` ở thư mục gốc hoặc đặt `SOVEREIGN_KILL=1`. Agent kiểm tra trước mỗi job.
2. **Hạn mức chi/ngày** — `control/spend_limit.py: DAILY_LIMIT_WEI` (0.002 ETH/ngày UTC), hằng số trong code, không ở config.
3. **Whitelist ngành** — `control/whitelist.py` (education, technology, travel, ecommerce, food, culture, health_wellness; loại việc write/translate).

Cơ chế bảo vệ:
- Module `control.*` bị đóng băng: `control.spend_limit.DAILY_LIMIT_WEI = ...` → `ControlTamperError`; hằng số là `frozenset`/`MappingProxyType`.
- `control/guard.py` là đường ghi file duy nhất của agent: chỉ `skills/*.md` **mới** (không ghi đè/xoá), `state/`, `logs/`, `output/`, và append `SOUL.md` sau khi xác minh header. Cấm `control/`, `config.yaml`, `.env`, `KILL`, mọi file khác; chặn path traversal.
- `control/MANIFEST.sha256` niêm phong `control/*.py`, `config.yaml`, header `SOUL.md`; sai lệch → agent từ chối chạy.
- `control/network.py`: chỉ cho HTTPS tới Gemini/Groq/OpenRouter và RPC Base (mainnet / Sepolia); mỗi chain id chỉ đi với đúng RPC của nó. Không registrar, không cloud VM, không chain khác.
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
