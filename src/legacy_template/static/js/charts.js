/**
 * 轻量无依赖配额进度条与 SVG 柱状趋势图渲染组件
 */
export function renderQuotaMeter(usedQty, includedQty) {
  const inc = Math.max(1, Number(includedQty || 1));
  const used = Math.max(0, Number(usedQty || 0));
  const ratio = Math.min(100, Math.round((used / inc) * 100));
  let cls = "meter-fill";
  if (used > inc) {
    cls += " over";
  } else if (ratio >= 80) {
    cls += " warn";
  }
  return `
    <div class="meter-track" title="配额使用率 ${ratio}%">
      <div class="${cls}" style="width: ${ratio}%"></div>
    </div>
  `;
}

export function renderMiniBarSvg(items, labelKey, valueKey) {
  if (!items || items.length === 0) {
    return `<div class="muted">暂无可视化序列数据</div>`;
  }
  const maxVal = Math.max(1, ...items.map((x) => Math.abs(Number(x[valueKey] || 0))));
  const barW = 46;
  const gap = 18;
  const height = 110;
  const width = items.length * (barW + gap) + 20;

  const bars = items
    .map((item, idx) => {
      const raw = Number(item[valueKey] || 0);
      const barH = Math.max(4, Math.round((Math.abs(raw) / maxVal) * 76));
      const x = 12 + idx * (barW + gap);
      const y = height - 22 - barH;
      const lbl = String(item[labelKey] || "").slice(0, 8);
      return `
        <g>
          <rect x="${x}" y="${y}" width="${barW}" height="${barH}" rx="4" fill="#2563eb" opacity="0.86"></rect>
          <text x="${x + barW / 2}" y="${height - 6}" text-anchor="middle" font-size="10" fill="#64748b">${lbl}</text>
        </g>
      `;
    })
    .join("");

  return `<svg width="${width}" height="${height}" role="img">${bars}</svg>`;
}
