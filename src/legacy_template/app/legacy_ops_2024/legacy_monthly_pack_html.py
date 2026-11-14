# -*- coding: utf-8 -*-
"""2024 版月度财务结算函 HTML 静态邮件模板生成器（历史遗留，已不被 V2 门户主表直接挂载）。
注意：本模块内置了 `escape_html_v2024`，但仅作用于邮件静态归档附件，门户实时表格已迁至 `static/js/views/`。
"""
from typing import Any, Dict, List


def escape_html_v2024(raw_val: Any) -> str:
    """2024 邮件归档专用 HTML 实体转义函数。"""
    txt = "" if raw_val is None else str(raw_val)
    return (
        txt.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def format_rmb_2024(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    abs_c = abs(int(cents))
    yuan = abs_c // 100
    rem = abs_c % 100
    return f"{sign}¥{yuan:,}.{rem:02d}"


def render_2024_customer_statement_html(
    tenant_profile: Dict[str, Any],
    period_key: str,
    invoices: List[Dict[str, Any]],
    adjustments: List[Dict[str, Any]],
    wallet_snapshot: Dict[str, int],
) -> str:
    """生成 2024 款离线归档对账单 HTML（供法务存证与月结邮件抄送使用）。"""
    comp_name = escape_html_v2024(tenant_profile.get("company_name", "未知企业客户"))
    tid = escape_html_v2024(tenant_profile.get("id", "-"))
    tax_code = escape_html_v2024(tenant_profile.get("tax_profile_code", "CN_VAT_6_INCLUSIVE"))

    inv_rows_html: List[str] = []
    sum_billed = 0
    sum_paid = 0
    for inv in invoices:
        tot = int(inv.get("total_cents") or 0)
        paid = int(inv.get("paid_cents") or 0)
        sum_billed += tot
        sum_paid += paid
        reason = escape_html_v2024(inv.get("dispute_reason") or "-")
        inv_rows_html.append(
            "<tr>"
            f"<td>{escape_html_v2024(inv.get('id'))}</td>"
            f"<td>{escape_html_v2024(inv.get('plan_code'))}</td>"
            f"<td>{format_rmb_2024(int(inv.get('base_fee_cents') or 0))}</td>"
            f"<td>{format_rmb_2024(int(inv.get('overage_fee_cents') or 0))}</td>"
            f"<td>{format_rmb_2024(int(inv.get('tax_cents') or 0))}</td>"
            f"<td><strong>{format_rmb_2024(tot)}</strong></td>"
            f"<td>{escape_html_v2024(inv.get('status'))}</td>"
            f"<td>{reason}</td>"
            "</tr>"
        )

    adj_rows_html: List[str] = []
    sum_adj = 0
    for adj in adjustments:
        amt = int(adj.get("amount_cents") or 0)
        sum_adj += amt
        adj_rows_html.append(
            "<tr>"
            f"<td>{escape_html_v2024(adj.get('id'))}</td>"
            f"<td>{escape_html_v2024(adj.get('target_closed_period') or '-')}</td>"
            f"<td>{escape_html_v2024(adj.get('adjustment_type'))}</td>"
            f"<td>{format_rmb_2024(amt)}</td>"
            f"<td>{escape_html_v2024(adj.get('reason') or '')}</td>"
            "</tr>"
        )

    cash_bal = format_rmb_2024(int(wallet_snapshot.get("cash_balance_cents", 0)))
    promo_bal = format_rmb_2024(int(wallet_snapshot.get("promo_balance_cents", 0)))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>云测智算月度电子对账函 - {escape_html_v2024(period_key)}</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; color: #1f2937; margin: 24px; }}
  .hdr {{ border-bottom: 2px solid #1e40af; padding-bottom: 12px; margin-bottom: 18px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
  th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; }}
  th {{ background-color: #f3f4f6; }}
  .summary-box {{ background: #eff6ff; padding: 12px 16px; border-radius: 6px; }}
</style>
</head>
<body>
  <div class="hdr">
    <h2>云测智算 (YunCe Cloud) 客户月度账单确认函</h2>
    <p>客户名称：{comp_name}（租户号：{tid}） | 账期：{escape_html_v2024(period_key)} | 税制：{tax_code}</p>
  </div>
  <h3>一、本期账单明细</h3>
  <table>
    <thead>
      <tr><th>账单号</th><th>套餐</th><th>月租费</th><th>超额阶梯费</th><th>税额</th><th>应付总额</th><th>状态</th><th>备注/争议</th></tr>
    </thead>
    <tbody>{''.join(inv_rows_html) or '<tr><td colspan="8">本期无账单记录</td></tr>'}</tbody>
  </table>
  <h3>二、跨期红冲与账务调整单（Booking in Open Period）</h3>
  <table>
    <thead>
      <tr><th>调账单号</th><th>追溯封账期</th><th>方向</th><th>金额</th><th>调账事由</th></tr>
    </thead>
    <tbody>{''.join(adj_rows_html) or '<tr><td colspan="5">本期无跨期调账记录</td></tr>'}</tbody>
  </table>
  <div class="summary-box">
    <p>本期开票合计：{format_rmb_2024(sum_billed)} | 已核销实收：{format_rmb_2024(sum_paid)} | 本期调账净额：{format_rmb_2024(sum_adj)}</p>
    <p>期末现金账户余额：{cash_bal} | 期末赠送金余额：{promo_bal}</p>
  </div>
</body>
</html>"""
