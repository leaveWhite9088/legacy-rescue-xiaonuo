import { apiFetch } from "./api.js";
import { renderQuotaMeter } from "./charts.js";
import { fmtNumber, fmtYuan } from "./fmt.js";
import { renderFapiaoHistoryRows } from "./views/fapiao_drawer.js";
import { renderInvoiceRows, renderWalletLedgerRows } from "./views/invoice_table.js";

const tokenEl = document.getElementById("tokenInput");
const periodEl = document.getElementById("periodInput");
const planBox = document.getElementById("planBox");
const walletBox = document.getElementById("walletBox");
const creditBox = document.getElementById("creditBox");
const invoiceBody = document.getElementById("invoiceBody");
const ledgerBody = document.getElementById("ledgerBody");
const fapiaoBody = document.getElementById("fapiaoBody");
const portalToast = document.getElementById("portalToast");

function showToast(msg, kind = "info") {
  if (!portalToast) return;
  portalToast.className = `toast-banner ${kind}`;
  portalToast.textContent = msg;
}

function clearToast() {
  if (!portalToast) return;
  portalToast.className = "toast-banner";
  portalToast.textContent = "";
}

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Tenant-Token": tokenEl.value.trim(),
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

async function loadAll() {
  clearToast();
  const h = headers();
  if (!h["X-Tenant-Token"]) {
    showToast("请先输入租户 X-Tenant-Token（例如 tok_cust_008 或 tok_leg_001）", "error");
    return;
  }
  try {
    const pk = encodeURIComponent(periodEl.value.trim() || "2026-11");
    const [bundleRes, walRes, invRes, fpRes] = await Promise.all([
      apiFetch(`/api/subscriptions/dashboard-bundle?period_key=${pk}`, { headers: h }),
      apiFetch("/api/wallet", { headers: h }),
      apiFetch("/api/invoices", { headers: h }),
      apiFetch("/api/fapiao", { headers: h }),
    ]);

    const q = bundleRes.quota;
    planBox.innerHTML = `
      <div class="stat">${q.plan_name} (${q.plan_code})</div>
      <div>当期已用：<strong>${fmtNumber(q.used_quantity)}</strong> / ${fmtNumber(q.included_quota)}（剩余 ${fmtNumber(q.remaining_quota)}，超额 ${fmtNumber(q.overage_quantity)}）</div>
      <div class="muted">订阅状态：${q.subscription_status} ｜ 突发限流：${q.burst_limit_per_min}/min</div>
      ${renderQuotaMeter(q.used_quantity, q.included_quota)}
    `;

    const w = walRes.wallet;
    const totalBal = Number(w.cash_balance_cents) + Number(w.promo_balance_cents);
    walletBox.innerHTML = `
      <div class="stat">${fmtYuan(totalBal)}</div>
      <div>可提现/可开票现金：<strong>${fmtYuan(w.cash_balance_cents)}</strong></div>
      <div>专用运营赠送金：<strong>${fmtYuan(w.promo_balance_cents)}</strong></div>
    `;

    if (creditBox && bundleRes.credit_profile) {
      const cp = bundleRes.credit_profile;
      creditBox.innerHTML = `
        <div class="stat">${cp.credit_score} 分 (${cp.risk_grade})</div>
        <div class="muted">建议授信上限：${fmtYuan(cp.recommended_credit_limit_cents)} ｜ 历史结清 ${cp.metrics.paid_count}/${cp.metrics.invoice_count} 笔</div>
      `;
    }

    invoiceBody.innerHTML = renderInvoiceRows(invRes.invoices || []);
    bindInvoiceActions();

    ledgerBody.innerHTML = renderWalletLedgerRows(walRes.recent_ledger || []);
    if (fapiaoBody) {
      fapiaoBody.innerHTML = renderFapiaoHistoryRows(fpRes.fapiaos || []);
    }
  } catch (err) {
    showToast(err.message || "加载租户账务数据失败", "error");
  }
}

function bindInvoiceActions() {
  invoiceBody.querySelectorAll("button[data-pay]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await apiFetch(`/api/invoices/${btn.dataset.pay}/pay`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ idempotency_key: `ui-${btn.dataset.pay}-${Date.now()}` }),
        });
        showToast(`账单 ${btn.dataset.pay} 支付成功`);
        await loadAll();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  invoiceBody.querySelectorAll("button[data-dispute]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const reason = window.prompt("请输入账单争议说明：");
      if (!reason) return;
      try {
        await apiFetch(`/api/invoices/${btn.dataset.dispute}/dispute`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ reason }),
        });
        showToast(`已提交对账单 ${btn.dataset.dispute} 的核查申诉`);
        await loadAll();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  invoiceBody.querySelectorAll("button[data-fapiao]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const taxId = window.prompt("请输入18位统一社会信用代码（纳税人识别号）：", "91310115MA1K38291X");
      if (!taxId) return;
      try {
        await apiFetch("/api/fapiao/apply", {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({
            invoice_id: btn.dataset.fapiao,
            buyer_tax_id: taxId,
            fapiao_type: "VAT_SPECIAL_E",
          }),
        });
        showToast(`账单 ${btn.dataset.fapiao} 数电专票开具成功`);
        await loadAll();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });
}

bindTabs();
document.getElementById("loadBtn").addEventListener("click", loadAll);

document.getElementById("topupBtn").addEventListener("click", async () => {
  const yuan = Number(document.getElementById("topupYuan").value || 0);
  try {
    await apiFetch("/api/wallet/topup", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ amount_cents: Math.round(yuan * 100) }),
    });
    showToast("现金充值已实时入账");
    await loadAll();
  } catch (err) {
    showToast(err.message, "error");
  }
});

document.getElementById("changePlanBtn").addEventListener("click", async () => {
  const plan = document.getElementById("planSelect").value;
  try {
    await apiFetch("/api/subscriptions/change-plan", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ plan_code: plan }),
    });
    showToast(`订阅已切换至 ${plan}`);
    await loadAll();
  } catch (err) {
    showToast(err.message, "error");
  }
});

document.getElementById("renewBtn").addEventListener("click", async () => {
  try {
    await apiFetch("/api/subscriptions/renew", { method: "POST", headers: headers() });
    showToast("手动续期出账成功");
    await loadAll();
  } catch (err) {
    showToast(err.message, "error");
  }
});

document.getElementById("cancelBtn").addEventListener("click", async () => {
  try {
    const res = await apiFetch("/api/subscriptions/cancel", { method: "POST", headers: headers() });
    showToast(res.note || "已设置周期末停止续订（当期月费不退还）");
    await loadAll();
  } catch (err) {
    showToast(err.message, "error");
  }
});

const usageSendBtn = document.getElementById("usageSendBtn");
if (usageSendBtn) {
  usageSendBtn.addEventListener("click", async () => {
    const qty = Number(document.getElementById("usageQtyInput").value || 0);
    try {
      await apiFetch("/api/usage/events", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ quantity: qty, period_key: periodEl.value.trim() || "2026-11" }),
      });
      showToast(`已上报计量事件：${qty} 次调用`);
      await loadAll();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}
