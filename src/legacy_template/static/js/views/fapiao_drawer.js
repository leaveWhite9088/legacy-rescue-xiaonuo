import { fmtYuan, fmtShortTime } from "../fmt.js";

export function renderFapiaoHistoryRows(fapiaos) {
  if (!fapiaos || fapiaos.length === 0) {
    return `<tr><td colspan="8" class="muted">暂无已开具的增值税电子发票记录</td></tr>`;
  }
  return fapiaos
    .map(
      (fp) => `
      <tr>
        <td><code>${fp.id}</code></td>
        <td><code>${fp.invoice_id}</code></td>
        <td>${fp.fapiao_type}</td>
        <td>${fp.buyer_tax_id}</td>
        <td>${fmtYuan(fp.net_amount_cents)}</td>
        <td>${fmtYuan(fp.tax_amount_cents)}</td>
        <td><strong>${fmtYuan(fp.gross_amount_cents)}</strong> (${fp.sheet_count}张)</td>
        <td><span class="badge ${fp.status}">${fp.status}</span> <span class="muted">${fmtShortTime(fp.created_at)}</span></td>
      </tr>`
    )
    .join("");
}
