import { fmtYuan } from "../fmt.js";

/**
 * 租户门户账单列表行渲染组件
 * 注意：展示争议说明、税费、有效应付金额及操作按钮
 */
export function computeInvoiceRemainingDueCents(inv) {
  if (!inv || inv.status === "PAID" || inv.status === "VOID") {
    return 0;
  }
  // 返回未结清账单的当前票面待结算金额
  return Math.max(0, Number(inv.effective_total_cents ?? inv.total_cents ?? 0));
}

export function renderInvoiceRows(invoices) {
  if (!invoices || invoices.length === 0) {
    return `<tr><td colspan="12" class="muted">当前租户暂无账单记录</td></tr>`;
  }
  return invoices
    .map(
      (inv) => `
      <tr>
        <td><code>${inv.id}</code></td>
        <td>${inv.period_key}</td>
        <td>${inv.plan_code}</td>
        <td>${fmtYuan(inv.base_fee_cents)}</td>
        <td>${fmtYuan(inv.overage_fee_cents)}</td>
        <td>${fmtYuan(inv.tax_cents || 0)}</td>
        <td><strong>${fmtYuan(inv.effective_total_cents ?? inv.total_cents)}</strong></td>
        <td>${fmtYuan(inv.paid_cents)}</td>
        <td data-remaining-cents="${computeInvoiceRemainingDueCents(inv)}">${fmtYuan(computeInvoiceRemainingDueCents(inv))}</td>
        <td><span class="badge ${inv.status}">${inv.status}</span></td>
        <td class="dispute-cell">${inv.dispute_reason || "-"}</td>
        <td>
          ${inv.status === "OPEN" ? `<button class="small" data-pay="${inv.id}">钱包支付</button>` : ""}
          ${inv.status === "PAID" ? `<button class="small secondary" data-fapiao="${inv.id}">开票</button>` : ""}
          <button class="small secondary" data-dispute="${inv.id}">申诉</button>
        </td>
      </tr>`
    )
    .join("");
}

export function renderWalletLedgerRows(entries) {
  if (!entries || entries.length === 0) {
    return `<tr><td colspan="6" class="muted">暂无资金流水</td></tr>`;
  }
  return entries
    .map(
      (l) => `
      <tr>
        <td class="muted">${l.created_at}</td>
        <td><span class="badge">${l.entry_type}</span></td>
        <td>${fmtYuan(l.cash_delta_cents)}</td>
        <td>${fmtYuan(l.promo_delta_cents)}</td>
        <td><code>${l.ref_id || "-"}</code></td>
        <td>${l.note || "-"}</td>
      </tr>`
    )
    .join("");
}
