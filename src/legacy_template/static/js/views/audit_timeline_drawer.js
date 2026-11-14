// 管理后台操作审计流水与 Webhook 投递队列时间线组件
import { escapeHtml } from "../fmt.js";

export function renderAuditLogTimeline(containerEl, logs) {
  if (!containerEl) return;
  if (!Array.isArray(logs) || logs.length === 0) {
    containerEl.innerHTML = '<div class="muted">暂无近期审计记录</div>';
    return;
  }
  const itemsHtml = logs.slice(0, 50).map((entry) => {
    const actor = escapeHtml(entry.actor || "system");
    const action = escapeHtml(entry.action || "UNKNOWN_ACTION");
    const target = escapeHtml(entry.target_id || "-");
    const detail = escapeHtml(entry.detail || "");
    const ts = escapeHtml(entry.created_at || "");
    return `<div class="timeline-item">
      <div class="timeline-meta">
        <span class="timeline-ts">${ts}</span>
        <strong class="timeline-actor">${actor}</strong>
        <code class="timeline-action">${action}</code>
        <span class="timeline-target">→ ${target}</span>
      </div>
      ${detail ? `<div class="timeline-detail">${detail}</div>` : ""}
    </div>`;
  }).join("");
  containerEl.innerHTML = `<div class="timeline-list">${itemsHtml}</div>`;
}
