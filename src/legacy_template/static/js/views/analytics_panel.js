import { renderMiniBarSvg } from "../charts.js";
import { fmtBps, fmtYuan } from "../fmt.js";

export function renderMrrOverviewCard(mrrData) {
  if (!mrrData) {
    return `<div class="muted">尚未加载经营指标</div>`;
  }
  return `
    <div class="kpi-strip">
      <div class="kpi-box">
        <div class="kpi-label">活跃订阅合同 MRR</div>
        <div class="kpi-value">${fmtYuan(mrrData.active_contracted_mrr_cents)}</div>
        <div class="kpi-sub">折合年化 ARR：${fmtYuan(mrrData.estimated_arr_cents)}</div>
      </div>
      <div class="kpi-box">
        <div class="kpi-label">上期封账开单总额</div>
        <div class="kpi-value">${fmtYuan(mrrData.previous_period_billed_cents)}</div>
        <div class="kpi-sub">已归档锁定</div>
      </div>
      <div class="kpi-box">
        <div class="kpi-label">当期累计已出账单</div>
        <div class="kpi-value">${fmtYuan(mrrData.current_period_billed_to_date_cents)}</div>
        <div class="kpi-sub">环比进度：${fmtBps(mrrData.period_over_period_ratio_bps)}</div>
      </div>
      <div class="kpi-box">
        <div class="kpi-label">待到期退订观察户</div>
        <div class="kpi-value">${mrrData.pending_cancellation_count}</div>
        <div class="kpi-sub">当期服务保留中</div>
      </div>
    </div>
  `;
}

export function renderCohortChartPanel(cohorts) {
  if (!cohorts || cohorts.length === 0) {
    return `<div class="muted">暂无群组留存数据</div>`;
  }
  const svg = renderMiniBarSvg(cohorts, "cohort", "target_period_cents");
  const rows = cohorts
    .map(
      (c) => `
      <tr>
        <td>${c.cohort}</td>
        <td>${c.tenant_count}</td>
        <td>${fmtYuan(c.base_period_cents)}</td>
        <td>${fmtYuan(c.target_period_cents)}</td>
        <td>${fmtBps(c.nrr_bps)}</td>
      </tr>`
    )
    .join("");
  return `
    <div style="margin-bottom: 12px">${svg}</div>
    <table>
      <thead><tr><th>签约季度</th><th>租户数</th><th>基期营收</th><th>对比期营收</th><th>净留存率 NRR</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}
