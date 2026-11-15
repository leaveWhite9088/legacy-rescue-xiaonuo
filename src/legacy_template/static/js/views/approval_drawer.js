import { fmtYuan, fmtShortTime } from "../fmt.js";

export function renderApprovalTicketRows(tickets) {
  if (!tickets || tickets.length === 0) {
    return `<tr><td colspan="9" class="muted">当前暂无待处理的财务双签审批工单</td></tr>`;
  }
  return tickets
    .map(
      (tk) => `
      <tr>
        <td><code>${tk.id}</code></td>
        <td>${tk.ticket_type}</td>
        <td><code>${tk.tenant_id}</code></td>
        <td>${fmtYuan(tk.amount_cents)}</td>
        <td>${tk.requested_by}</td>
        <td class="approval-reason-cell">${tk.reason || "-"}</td>
        <td>${tk.first_approver || "-"} / ${tk.second_approver || "-"} (需${tk.required_approvals}签)</td>
        <td><span class="badge ${tk.status}">${tk.status}</span> <span class="muted">${fmtShortTime(tk.created_at)}</span></td>
        <td>
          ${
            tk.status === "PENDING"
              ? `<button class="small" data-approve-ticket="${tk.id}">会签通过</button>`
              : "-"
          }
        </td>
      </tr>`
    )
    .join("");
}
