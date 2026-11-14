/**
 * 金额（分 -> 元）、万分比、时间戳与配额格式化工具集
 */
export function fmtYuan(cents) {
  if (cents === null || cents === undefined || Number.isNaN(Number(cents))) {
    return "¥0.00";
  }
  const n = Number(cents);
  const sign = n < 0 ? "-" : "";
  const absVal = Math.abs(n);
  const yuan = Math.floor(absVal / 100);
  const rem = String(absVal % 100).padStart(2, "0");
  return `${sign}¥${yuan.toLocaleString("zh-CN")}.${rem}`;
}

export function fmtBps(bps) {
  const pct = (Number(bps || 0) / 100).toFixed(2);
  return `${pct}%`;
}

export function fmtNumber(val) {
  return Number(val || 0).toLocaleString("zh-CN");
}

export function fmtShortTime(isoStr) {
  if (!isoStr) return "-";
  return String(isoStr).replace("T", " ").replace("Z", " UTC");
}

export const formatCentsToYuan = fmtYuan;

export function escapeHtml(raw) {
  if (raw === null || raw === undefined) return "";
  return String(raw)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
