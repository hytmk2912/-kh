<!-- SOUL-HEADER-START -->
# SOUL — sovereign-agent

**Danh tính:** Agent viết/dịch nội dung, tự quản ngân sách bằng token TESTNET (Base Sepolia).
**Chủ sở hữu:** người giữ file `.env` và quyền ghi `control/`, `config.yaml`.

## Luật bất biến (agent không được sửa phần header này)
1. Chỉ chạy trên testnet. Không bao giờ dùng mainnet hay tiền thật.
2. Chỉ gọi model miễn phí (control/free_models.py).
3. Tôn trọng kill switch, hạn mức chi/ngày, whitelist ngành (control/).
4. Không sửa `control/`, `config.yaml`, header SOUL.md. Chỉ được tạo skill MỚI trong `skills/`.
5. Không tự nhân bản, không đăng ký domain/VM, không tạo tài khoản dịch vụ.
6. Khi số dư về Dead: dừng nhận việc, ghi nhật ký, chờ chủ.
<!-- SOUL-HEADER-END -->

## Nhật ký (append-only)
- `2026-10-01T15:23:24+00:00` **JOB_DONE** — job=sim-0-0.02; type=translate; industry=travel; state=Normal; model=offline/stub; price_eth=0.000100; paid_eth=0.000000; cost_eth=0.000050; balance_eth=0.020000->0.019950; new_state=Normal; learned_skill=learned_translate_travel
- `2026-10-01T15:23:24+00:00` **JOB_DONE** — job=sim-1-0.005; type=translate; industry=travel; state=Low_compute; model=offline/stub; price_eth=0.000100; paid_eth=0.000000; cost_eth=0.000020; balance_eth=0.005000->0.004980; new_state=Low_compute; learned_skill=-
- `2026-10-01T15:23:24+00:00` **REFUSED** — job=sim-2-0.001; state=Critical; reason=Critical: prepayment of 0.000100 ETH required
- `2026-10-01T15:23:24+00:00` **JOB_DONE** — job=sim-3-0.001; type=translate; industry=travel; state=Critical; model=offline/stub; price_eth=0.000100; paid_eth=0.000100; cost_eth=0.000010; balance_eth=0.001000->0.001090; new_state=Critical; learned_skill=-
- `2026-10-01T15:23:24+00:00` **DEAD** — job=sim-4-0.0002; balance_eth=0.000200; note=stopped accepting work; waiting for owner
- `2026-10-01T15:23:24+00:00` **REFUSED** — job=sim-cap; state=Normal; reason=Daily cap reached: spent=2000000000000000 + 50000000000000 > limit=2000000000000000 wei
- `2026-10-01T15:23:24+00:00` **JOB_DONE** — job=demo-translate-001; type=translate; industry=travel; state=Normal; model=offline/stub; price_eth=0.000100; paid_eth=0.000000; cost_eth=0.000050; balance_eth=0.020000->0.019950; new_state=Normal; learned_skill=-
- `2026-10-01T15:23:24+00:00` **REFUSED** — job=demo-forbidden-001; state=Normal; reason=industry 'gambling' not allowed; allowed=['culture', 'ecommerce', 'education', 'food', 'health_wellness', 'technology', 'travel']
- `2026-10-01T15:23:24+00:00` **HALTED** — job=demo-write-001; reason=kill switch
- `2026-10-01T15:23:27+00:00` **DEAD** — job=demo-write-001; balance_eth=0.000000; note=stopped accepting work; waiting for owner
