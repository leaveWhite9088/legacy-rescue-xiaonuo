# -*- coding: utf-8 -*-
"""集团财务共享中心 SFTP 对账文件落盘控制单（Control File `.ctl`）格式化器。"""
import hashlib
from typing import Dict


def build_sftp_control_descriptor(data_filename: str, payload_text: str, period_key: str) -> Dict[str, str]:
    encoded = (payload_text or "").encode("utf-8")
    row_cnt = max(0, len((payload_text or "").strip().splitlines()) - 1)
    md5_hex = hashlib.md5(encoded).hexdigest()
    ctl_content = f"FILENAME={data_filename}\nPERIOD={period_key}\nDATA_ROWS={row_cnt}\nBYTE_SIZE={len(encoded)}\nMD5={md5_hex}\n"
    return {
        "ctl_filename": f"{data_filename}.ctl",
        "ctl_body": ctl_content,
        "md5": md5_hex,
    }
