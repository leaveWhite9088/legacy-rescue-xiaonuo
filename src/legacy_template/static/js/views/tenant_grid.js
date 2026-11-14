import { fmtYuan } from "../fmt.js";

/**
 * 管理后台全平台租户名录表格渲染器
 */
export function renderTenantDirectoryRows(rows) {
  if (!rows || rows.length === 0) {
    return `<tr><td colspan="7" class="muted">没有符合筛选条件的租户记录</td></tr>`;
  }
  return rows
    .map(
      (t) => `
      <tr>
        <td><code>${t.id}</code></td>
        <td class="tenant-company-cell">${t.company_name}</td>
        <td><span class="badge ${t.status}">${t.status} (v${t.schema_version})</span></td>
        <td class="muted">${t.tax_profile_code || "-"}</td>
        <td>${t.plan_code || "-"}</td>
        <td>${fmtYuan(t.cash_balance_cents)}</td>
        <td>${fmtYuan(t.promo_balance_cents)}</td>
      </tr>`
    )
    .join("");
}
