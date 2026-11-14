// 大额数电专票超限额（单张 10 万元上限）拆票预览组件
import { escapeHtml, formatCentsToYuan } from "../fmt.js";

const SINGLE_SHEET_LIMIT_CENTS = 10000000;

export function previewFapiaoSplitsClientSide(grossCents) {
  const total = Math.max(0, Math.floor(Number(grossCents) || 0));
  if (total === 0) return [];
  const count = Math.ceil(total / SINGLE_SHEET_LIMIT_CENTS);
  const sheets = [];
  let rem = total;
  for (let i = 1; i <= count; i++) {
    const shGross = i < count ? Math.min(SINGLE_SHEET_LIMIT_CENTS, rem) : rem;
    rem -= shGross;
    sheets.push({ seq: i, grossCents: shGross });
  }
  return sheets;
}

export function renderFapiaoSplitNotice(containerEl, grossCents) {
  if (!containerEl) return;
  const sheets = previewFapiaoSplitsClientSide(grossCents);
  if (sheets.length <= 1) {
    containerEl.innerHTML = '<span class="muted">单张限额内，无需拆票</span>';
    return;
  }
  const pills = sheets.map((s) => `<span class="badge">第 ${escapeHtml(String(s.seq))} 张：${formatCentsToYuan(s.grossCents)}</span>`).join(" ");
  containerEl.innerHTML = `<div class="split-preview">超单张限额自动拆分为 ${sheets.length} 张：${pills}</div>`;
}
