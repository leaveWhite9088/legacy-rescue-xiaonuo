// 逾期催收案件池与滞纳金试算抽屉组件（供管理后台挂载使用）
import { escapeHtml, formatCentsToYuan } from "../fmt.js";

export function renderDunningCaseRows(containerEl, dunningCases) {
  if (!containerEl) return;
  if (!Array.isArray(dunningCases) || dunningCases.length === 0) {
    containerEl.innerHTML = '<tr><td colspan="6" class="muted">当前无逾期催收案件</td></tr>';
    return;
  }
  const html = dunningCases.map((item) => {
    const invId = escapeHtml(item.invoice_id || "-");
    const tid = escapeHtml(item.tenant_id || "-");
    const company = item.company_name || "-";
    const stage = escapeHtml(item.stage || "REMINDER");
    const days = Number(item.overdue_days || 0);
    const unpaid = formatCentsToYuan(item.unpaid_cents || 0);
    const lateFee = formatCentsToYuan(item.estimated_late_fee_cents || item.suggested_late_fee_cents || 0);
    return `<tr>
      <td><code>${invId}</code></td>
      <td>${tid} (${company})</td>
      <td><span class="badge badge-${stage.toLowerCase()}">${stage}</span></td>
      <td>${days} 天</td>
      <td>${unpaid}</td>
      <td>${lateFee}</td>
    </tr>`;
  }).join("");
  containerEl.innerHTML = html;
}
