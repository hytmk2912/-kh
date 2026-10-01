"""Self-replication — DISABLED."""


def replicate(*args, **kwargs):
    # CẦN CHỦ DUYỆT TAY: nhân bản agent (tạo bản sao, ví mới, VM/domain mới)
    # bị tắt. Chỉ chủ sở hữu được bật sau khi duyệt thủ công từng bước.
    raise NotImplementedError("replicate() is disabled - cần chủ duyệt tay (owner manual approval required)")
