// 门户账单待付摘要卡片组件
import { fmtYuan } from "../fmt.js";

export function renderBillingSummaryCard(inv) {
  if (!inv) return "";
  const due = inv.status === "PAID" || inv.status === "VOID" ? 0 : Math.max(0, Number(inv.total_cents || 0));
  return `<div class="summary-card"><h4>${inv.company_name || ""}</h4><span>${fmtYuan(due)}</span><p>${inv.dispute_reason || "-"}</p></div>`;
}
