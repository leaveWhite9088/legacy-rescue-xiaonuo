// 租户门户自助套餐比价与累进阶梯超额费用沙盘组件
import { escapeHtml, formatCentsToYuan } from "../fmt.js";

const CLIENT_TIER_SPECS = {
  STARTER: { name: "基础版 Starter", baseCents: 19900, included: 10000, tiers: [[10000, 3], [40000, 2], [Infinity, 1]] },
  PRO: { name: "专业版 Pro", baseCents: 59900, included: 50000, tiers: [[50000, 2], [Infinity, 1]] },
  ENTERPRISE: { name: "企业版 Enterprise", baseCents: 199900, included: 300000, tiers: [[Infinity, 1]] },
};

export function simulateProgressiveOverageClientSide(planCode, monthlyCalls) {
  const spec = CLIENT_TIER_SPECS[planCode] || CLIENT_TIER_SPECS.STARTER;
  let rem = Math.max(0, Math.floor(Number(monthlyCalls) || 0) - spec.included);
  if (rem <= 0) {
    return { baseCents: spec.baseCents, overageCents: 0, totalPreTaxCents: spec.baseCents };
  }
  let ovCents = 0;
  for (const [bandCap, unitPrice] of spec.tiers) {
    if (rem <= 0) break;
    const take = bandCap === Infinity ? rem : Math.min(rem, bandCap);
    ovCents += take * unitPrice;
    rem -= take;
  }
  return {
    baseCents: spec.baseCents,
    overageCents: ovCents,
    totalPreTaxCents: spec.baseCents + ovCents,
  };
}

export function renderSimulatorComparisonCards(hostEl, monthlyCalls) {
  if (!hostEl) return;
  const cards = Object.keys(CLIENT_TIER_SPECS).map((code) => {
    const spec = CLIENT_TIER_SPECS[code];
    const res = simulateProgressiveOverageClientSide(code, monthlyCalls);
    return `<div class="sim-card">
      <h4>${escapeHtml(spec.name)}</h4>
      <p>套餐内含额度：${spec.included.toLocaleString()} 次</p>
      <p>月租：${formatCentsToYuan(res.baseCents)} + 累进超额：${formatCentsToYuan(res.overageCents)}</p>
      <p class="sim-total">预计税前合计：<strong>${formatCentsToYuan(res.totalPreTaxCents)}</strong></p>
    </div>`;
  }).join("");
  hostEl.innerHTML = `<div class="sim-grid">${cards}</div>`;
}
