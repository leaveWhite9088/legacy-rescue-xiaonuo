# -*- coding: utf-8 -*-
"""[2023 ARCHIVE] 早期纯文本催款通知邮件合并工具。"""
from typing import Dict, List


def render_2023_plaintext_dunning_emails(overdue_list: List[Dict[str, object]]) -> List[str]:
    mails: List[str] = []
    for item in overdue_list:
        mails.append(
            f"致 {item.get('company', '贵司')} 财务部：\n"
            f"贵司 {item.get('month', '2023-12')} 期技术服务费 {item.get('yuan', '0.00')} 元尚未到账，请核实汇款。谢谢！"
        )
    return mails
