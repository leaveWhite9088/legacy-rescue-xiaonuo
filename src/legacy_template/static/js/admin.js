import { apiFetch } from "./api.js";
import { fmtYuan } from "./fmt.js";
import { renderCohortChartPanel, renderMrrOverviewCard } from "./views/analytics_panel.js";
import { renderApprovalTicketRows } from "./views/approval_drawer.js";
import { renderTenantDirectoryRows } from "./views/tenant_grid.js";

const keyEl = document.getElementById("adminKeyInput");
const filterEl = document.getElementById("tenantFilterInput");
const tenantBody = document.getElementById("tenantBody");
const periodBody = document.getElementById("periodBody");
const adjBody = document.getElementById("adjBody");
const partnerBody = document.getElementById("partnerBody");
const auditBody = document.getElementById("auditBody");
const mrrContainer = document.getElementById("mrrContainer");
const cohortContainer = document.getElementById("cohortContainer");
const approvalBody = document.getElementById("approvalBody");
const subledgerBox = document.getElementById("subledgerBox");
const adminToast = document.getElementById("adminToast");

let cachedTenants = [];

function showToast(msg, kind = "info") {
  if (!adminToast) return;
  adminToast.className = `toast-banner ${kind}`;
  adminToast.textContent = msg;
}

function adminHeaders() {
  return {
    "Content-Type": "application/json",
    "X-Admin-Key": keyEl.value.trim(),
  };
}

function bindTabs() {
  const buttons = document.querySelectorAll(".tab-btn[data-tab]");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const pane = document.getElementById(btn.dataset.tab);
      if (pane) pane.classList.add("active");
    });
  });
}

function renderTenants() {
  const kw = filterEl.value.trim().toLowerCase();
  const rows = kw
    ? cachedTenants.filter(
        (t) =>
          String(t.id).toLowerCase().includes(kw) ||
          String(t.company_name).toLowerCase().includes(kw)
      )
    : cachedTenants;
  tenantBody.innerHTML = renderTenantDirectoryRows(rows);
}

async function loadAdmin() {
  const h = adminHeaders();
  try {
    const [tRes, pRes, aRes, cRes, logRes, mrrRes, cohRes, aprRes, subRes] = await Promise.all([
      apiFetch("/api/admin/tenants?limit=300", { headers: h }),
      apiFetch("/api/admin/periods", { headers: h }),
      apiFetch("/api/admin/adjustments", { headers: h }),
      apiFetch("/api/partners/commissions?period_key=2026-11", { headers: h }),
      apiFetch("/api/admin/audit-logs", { headers: h }),
      apiFetch("/api/admin/analytics/mrr", { headers: h }),
      apiFetch("/api/admin/analytics/cohorts", { headers: h }),
      apiFetch("/api/admin/approvals", { headers: h }),
      apiFetch("/api/admin/diagnostics/subledger", { headers: h }),
    ]);

    cachedTenants = tRes.tenants || [];
    renderTenants();

    if (mrrContainer) {
      mrrContainer.innerHTML = renderMrrOverviewCard(mrrRes.mrr);
    }
    if (cohortContainer) {
      cohortContainer.innerHTML = renderCohortChartPanel(cohRes.cohorts || []);
    }

    periodBody.innerHTML = (pRes.periods || [])
      .map(
        (p) => `
        <tr>
          <td><strong>${p.period_key}</strong></td>
          <td><span class="badge ${p.status}">${p.status}</span></td>
          <td>${p.archived_total_cents == null ? "-" : fmtYuan(p.archived_total_cents)}</td>
          <td>${
            p.status === "OPEN"
              ? `<button class="small" data-close="${p.period_key}">执行月结封账</button>`
              : `<span class="muted">已归档锁定 (${p.closed_by || "finance"})</span>`
          }</td>
        </tr>`
      )
      .join("");

    periodBody.querySelectorAll("button[data-close]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await apiFetch(`/api/admin/periods/${btn.dataset.close}/close`, {
            method: "POST",
            headers: adminHeaders(),
          });
          showToast(`账期 ${btn.dataset.close} 已正式封账归档`);
          await loadAdmin();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    adjBody.innerHTML = (aRes.adjustments || [])
      .map(
        (a) => `
        <tr>
          <td><code>${a.id}</code></td>
          <td><code>${a.ref_invoice_id}</code></td>
          <td>${a.target_period_key}</td>
          <td>${a.applied_period_key}</td>
          <td>${fmtYuan(a.delta_cents)}</td>
          <td><span class="badge ${a.status}">${a.status}</span></td>
        </tr>`
      )
      .join("");

    partnerBody.innerHTML = (cRes.commissions || [])
      .map(
        (c) => `
        <tr>
          <td><code>${c.partner_code}</code></td>
          <td>${c.tier}</td>
          <td>${fmtYuan(c.net_cash_collected_cents)}</td>
          <td><strong>${fmtYuan(c.commission_cents)}</strong></td>
        </tr>`
      )
      .join("");

    auditBody.innerHTML = (logRes.logs || [])
      .slice(0, 15)
      .map(
        (l) => `
        <tr>
          <td class="muted">${l.created_at}</td>
          <td>${l.actor}</td>
          <td><code>${l.action}</code></td>
          <td><code>${l.target_id}</code></td>
          <td class="muted">${l.detail || "-"}</td>
        </tr>`
      )
      .join("");

    if (approvalBody) {
      approvalBody.innerHTML = renderApprovalTicketRows(aprRes.tickets || []);
      approvalBody.querySelectorAll("button[data-approve-ticket]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const approver = window.prompt("请输入审批人账号：", "cfo_reviewer");
          if (!approver) return;
          try {
            await apiFetch(`/api/admin/approvals/${btn.dataset.approveTicket}/decide`, {
              method: "POST",
              headers: adminHeaders(),
              body: JSON.stringify({ approver, decision: "APPROVE" }),
            });
            await loadAdmin();
          } catch (err) {
            showToast(err.message, "error");
          }
        });
      });
    }

    if (subledgerBox && subRes) {
      const wa = subRes.wallets_audit || {};
      const seals = (subRes.closed_seals || [])
        .map((s) => `${s.period_key}: ${s.seal_intact ? "封账一致" : "存在篡改偏差!"}`)
        .join(" ｜ ");
      subledgerBox.innerHTML = `
        <div>钱包扫描数：${wa.checked_wallets || 0} ｜ 负余额异常户：<strong>${wa.negative_wallet_count || 0}</strong> ｜ 流水偏差户：${wa.ledger_drift_count || 0}</div>
        <div class="muted" style="margin-top:4px">历史封账校验：${seals || "-"}</div>
      `;
    }
  } catch (err) {
    showToast(err.message || "管理后台数据刷新失败", "error");
  }
}

bindTabs();
filterEl.addEventListener("input", renderTenants);
document.getElementById("loadAdminBtn").addEventListener("click", loadAdmin);
document.getElementById("runJobsBtn").addEventListener("click", async () => {
  try {
    await apiFetch("/api/admin/jobs/run", {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify({}),
    });
    showToast("全量后台定时批处理任务已执行完毕");
    await loadAdmin();
  } catch (err) {
    showToast(err.message, "error");
  }
});
