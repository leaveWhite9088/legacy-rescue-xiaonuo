// 月末封账前置预检与三栏对账摘要弹窗渲染组件
import { escapeHtml, formatCentsToYuan } from "../fmt.js";

export function renderMonthEndPrecheckSummary(targetEl, precheckPayload) {
  if (!targetEl || !precheckPayload) return;
  const canClose = Boolean(precheckPayload.can_close);
  const statusBadge = canClose
    ? '<span class="badge badge-paid">满足关账条件</span>'
    : '<span class="badge badge-disputed">存在关账阻断项</span>';

  const blockers = Array.isArray(precheckPayload.blockers) ? precheckPayload.blockers : [];
  const blockerHtml = blockers.length === 0
    ? '<p class="ok-hint">未检测到草稿残留、挂起结算单或待审高优工单。</p>'
    : `<ul class="blocker-list">${blockers.map((b) => `<li>${escapeHtml(b)}</li>`).join("")}</ul>`;

  targetEl.innerHTML = `
    <div class="precheck-panel">
      <div class="precheck-head">
        <strong>目标账期：${escapeHtml(precheckPayload.target_period || "-")}</strong>
        ${statusBadge}
      </div>
      ${blockerHtml}
    </div>
  `;
}

export function renderTreasuryForecastSummary(targetEl, forecast) {
  if (!targetEl || !forecast) return;
  const trough = formatCentsToYuan(forecast.minimum_liquidity_trough_cents || 0);
  const endCash = formatCentsToYuan(forecast.ending_week13_cash_cents || 0);
  targetEl.innerHTML = `
    <div class="kpi-mini-row">
      <span>13 周末预计头寸：<strong>${endCash}</strong></span>
      <span>期间最低流动性水位：<strong>${trough}</strong></span>
    </div>
  `;
}
