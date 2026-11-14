/**
 * 2024包干总账核销大表 (v1.4-2024Q3)
 * 历史前端视图组件：挂载于旧版财务/销管工作台，保留原 DOM 拼装逻辑供存量内网书签访问。
 * 注意：当前主门户 (portal.html) 与新运维后台 (admin.html) 已迁移至 static/js/views/ 目录。
 */
(function (global) {
  "use strict";

  var MODULE_CODE = "LegacyLedgerGrid2024";
  var ERA_VERSION = "v1.4-2024Q3";
  var DEFAULT_PAGE_LIMIT = 50;
  var MAGIC_YUAN_DIVISOR = 100.0;
  var COLUMN_HEADERS = ["账期", "套餐档位", "基础月费", "超额费用", "价税合计", "已实收"];
  var METRIC_FIELDS = ["period_key", "plan_code", "base_fee_cents", "overage_fee_cents", "total_cents", "paid_cents"];

  var internalState = {
    loadedAt: null,
    activePeriod: "2026-11",
    selectedRegion: "ALL",
    sortField: "id",
    sortAsc: true,
    rawRows: [],
    filteredRows: [],
    selectionMap: {},
    summaryTotals: {
      grossCents: 0,
      paidCents: 0,
      deltaCents: 0,
      flaggedCount: 0
    }
  };

  function escapeLegacyText(val) {
    if (val === null || val === undefined) {
      return "";
    }
    return String(val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatLegacyMoney(rawVal, currencyUnit) {
    if (currencyUnit === "YUAN_STR") {
      var parsed = parseFloat(String(rawVal || "0"));
      if (isNaN(parsed)) {
        return "¥0.00 (旧版元)";
      }
      return "¥" + parsed.toFixed(2) + " [2024包干]";
    }
    var cents = parseInt(rawVal || 0, 10);
    if (isNaN(cents)) {
      cents = 0;
    }
    var sign = cents < 0 ? "-" : "";
    var absVal = Math.abs(cents) / MAGIC_YUAN_DIVISOR;
    return sign + "¥" + absVal.toFixed(2);
  }

  function classifyRowRiskBadge(row) {
    var status = String(row.status || "OPEN").toUpperCase();
    var gross = parseInt(row.total_cents || row.gross_cents || 0, 10) || 0;
    var paid = parseInt(row.paid_cents || 0, 10) || 0;
    var unpaid = Math.max(0, gross - paid);

    if (status === "VOID" || status === "REFUNDED") {
      return { label: "已作废/退费", css: "badge-muted", level: 0 };
    }
    if (status === "PENDING_SETTLE") {
      return { label: "批处理锁定中", css: "badge-amber", level: 2 };
    }
    if (status === "DISPUTED" || (row.dispute_reason && String(row.dispute_reason).length > 0)) {
      return { label: "争议挂起核查", css: "badge-purple", level: 3 };
    }
    if (unpaid >= 200000) {
      return { label: "大额待收重点关注", css: "badge-red", level: 3 };
    }
    if (unpaid > 0) {
      return { label: "待结清账单", css: "badge-blue", level: 1 };
    }
    return { label: "已核销平账", css: "badge-green", level: 0 };
  }

  function recomputeSummary(rows) {
    var gross = 0;
    var paid = 0;
    var delta = 0;
    var flagged = 0;

    for (var i = 0; i < rows.length; i++) {
      var r = rows[i] || {};
      var g = r.currency_unit === "YUAN_STR"
        ? Math.round((parseFloat(r.total_cents || "0") || 0) * 100)
        : (parseInt(r.total_cents || r.gross_cents || 0, 10) || 0);
      var p = parseInt(r.paid_cents || 0, 10) || 0;
      var d = parseInt(r.delta_cents || r.tax_cents || 0, 10) || 0;
      gross += g;
      paid += p;
      delta += d;
      var badge = classifyRowRiskBadge(r);
      if (badge.level >= 2) {
        flagged += 1;
      }
    }

    internalState.summaryTotals = {
      grossCents: gross,
      paidCents: paid,
      deltaCents: delta,
      flaggedCount: flagged
    };
    return internalState.summaryTotals;
  }

  function applyClientFilters(rows, filterSpec) {
    var spec = filterSpec || {};
    var kw = String(spec.keyword || "").trim().toLowerCase();
    var statusFilter = String(spec.status || "ALL").toUpperCase();
    var minCents = parseInt(spec.minCents || 0, 10) || 0;
    var out = [];

    for (var i = 0; i < rows.length; i++) {
      var item = rows[i];
      if (!item) continue;
      if (statusFilter !== "ALL" && String(item.status || "").toUpperCase() !== statusFilter) {
        continue;
      }
      var itemCents = item.currency_unit === "YUAN_STR"
        ? Math.round((parseFloat(item.total_cents || "0") || 0) * 100)
        : (parseInt(item.total_cents || item.gross_cents || 0, 10) || 0);
      if (minCents > 0 && itemCents < minCents) {
        continue;
      }
      if (kw.length > 0) {
        var hay = [
          item.id,
          item.tenant_id,
          item.company_name,
          item.plan_code,
          item.period_key,
          item.dispute_reason
        ].join(" ").toLowerCase();
        if (hay.indexOf(kw) === -1) {
          continue;
        }
      }
      out.push(item);
    }

    out.sort(function (a, b) {
      var fa = a[internalState.sortField];
      var fb = b[internalState.sortField];
      if (fa === fb) return 0;
      var cmp = String(fa || "") < String(fb || "") ? -1 : 1;
      return internalState.sortAsc ? cmp : -cmp;
    });

    internalState.filteredRows = out;
    recomputeSummary(out);
    return out;
  }

  function buildSummaryBannerHtml() {
    var s = internalState.summaryTotals;
    var outstanding = Math.max(0, s.grossCents - s.paidCents);
    return [
      '<div class="legacy-kpi-strip" data-module="' + MODULE_CODE + '">',
      '  <div class="kpi-card"><span class="kpi-label">模块版本</span><strong>' + escapeLegacyText(ERA_VERSION) + '</strong></div>',
      '  <div class="kpi-card"><span class="kpi-label">账期范围</span><strong>' + escapeLegacyText(internalState.activePeriod) + '</strong></div>',
      '  <div class="kpi-card"><span class="kpi-label">应收汇总</span><strong>' + formatLegacyMoney(s.grossCents, "CENTS") + '</strong></div>',
      '  <div class="kpi-card"><span class="kpi-label">实收汇总</span><strong>' + formatLegacyMoney(s.paidCents, "CENTS") + '</strong></div>',
      '  <div class="kpi-card"><span class="kpi-label">待收敞口</span><strong>' + formatLegacyMoney(outstanding, "CENTS") + '</strong></div>',
      '  <div class="kpi-card"><span class="kpi-label">异常标记数</span><strong>' + String(s.flaggedCount) + ' 笔</strong></div>',
      '</div>'
    ].join("\n");
  }

  function buildTableHtml(rows) {
    var list = (rows || []).slice(0, DEFAULT_PAGE_LIMIT);
    var thead = COLUMN_HEADERS.map(function (h) {
      return "<th>" + escapeLegacyText(h) + "</th>";
    }).join("");

    var tbodyParts = [];
    for (var i = 0; i < list.length; i++) {
      var row = list[i];
      var badge = classifyRowRiskBadge(row);
      var rowId = escapeLegacyText(row.id || ("ROW_" + i));
      var checked = internalState.selectionMap[rowId] ? "checked" : "";
      var metricCells = METRIC_FIELDS.map(function (mk) {
        var raw = row[mk];
        if (mk.indexOf("_cents") !== -1) {
          return '<td class="num-col">' + formatLegacyMoney(raw, row.currency_unit) + "</td>";
        }
        return "<td>" + escapeLegacyText(raw === undefined ? "-" : raw) + "</td>";
      }).join("");

      tbodyParts.push(
        '<tr data-row-id="' + rowId + '">' +
        '<td><input type="checkbox" class="legacy-row-check" data-id="' + rowId + '" ' + checked + ' /></td>' +
        "<td><code>" + rowId + "</code></td>" +
        "<td>" + escapeLegacyText(row.tenant_id || "-") + "</td>" +
        metricCells +
        '<td><span class="legacy-badge ' + badge.css + '">' + escapeLegacyText(badge.label) + "</span></td>" +
        "</tr>"
      );
    }

    if (tbodyParts.length === 0) {
      tbodyParts.push(
        '<tr><td colspan="' + (COLUMN_HEADERS.length + 3) + '" class="empty-hint">暂无匹配的历史台账记录</td></tr>'
      );
    }

    return [
      '<table class="legacy-grid-table">',
      "  <thead><tr><th>选择</th><th>单据号</th><th>租户ID</th>" + thead + "<th>风控状态</th></tr></thead>",
      "  <tbody>" + tbodyParts.join("\n") + "</tbody>",
      "</table>"
    ].join("\n");
  }

  function mountToContainer(containerId, rows, filterSpec) {
    internalState.rawRows = Array.isArray(rows) ? rows.slice() : [];
    internalState.loadedAt = new Date().toISOString();
    var filtered = applyClientFilters(internalState.rawRows, filterSpec || {});
    if (typeof document === "undefined") {
      return { count: filtered.length, summary: internalState.summaryTotals };
    }
    var el = document.getElementById(containerId);
    if (!el) {
      return { count: filtered.length, summary: internalState.summaryTotals };
    }
    el.innerHTML = buildSummaryBannerHtml() + buildTableHtml(filtered);
    return { count: filtered.length, summary: internalState.summaryTotals };
  }

  function exportCsvText() {
    var rows = internalState.filteredRows || [];
    var header = ["id", "tenant_id"].concat(METRIC_FIELDS).concat(["status"]);
    var lines = [header.join(",")];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i] || {};
      var vals = header.map(function (k) {
        var v = r[k] === undefined || r[k] === null ? "" : String(r[k]);
        return '"' + v.replace(/"/g, '""') + '"';
      });
      lines.push(vals.join(","));
    }
    return lines.join("\n");
  }

  global[MODULE_CODE] = {
    version: ERA_VERSION,
    mountToContainer: mountToContainer,
    applyClientFilters: applyClientFilters,
    recomputeSummary: recomputeSummary,
    exportCsvText: exportCsvText,
    getStateSnapshot: function () {
      return JSON.parse(JSON.stringify(internalState));
    }
  };
})(typeof window !== "undefined" ? window : globalThis);
