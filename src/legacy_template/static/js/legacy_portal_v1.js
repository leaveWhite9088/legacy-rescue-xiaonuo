/**
 * [DEPRECATED 2024 v1 遗留脚本] 仅供 /legacy-portal 归档兼容页面挂载！
 * 注意：主站 / 与 /admin 均已于 2025 Q1 迁移至 ESModule 版 portal.js / admin.js 及 views/* 组件！
 */
(function (global) {
  function v1FormatYuan(cents) {
    var n = parseInt(cents || 0, 10);
    return "RMB " + (n / 100).toFixed(2);
  }

  function v1LoadLegacyInvoices() {
    var tokInput = document.getElementById("v1TokenInput");
    var outBody = document.getElementById("v1InvoiceTableBody");
    if (!tokInput || !outBody) return;
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/invoices", true);
    xhr.setRequestHeader("X-Legacy-Api-Token", tokInput.value.trim());
    xhr.setRequestHeader("X-V1-Client-Build", "2024.08.19");
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      if (xhr.status !== 200) {
        outBody.innerHTML = "<tr><td colspan='5'>加载失败 HTTP " + xhr.status + "</td></tr>";
        return;
      }
      var data = JSON.parse(xhr.responseText || "{}");
      var list = data.invoices || [];
      var html = "";
      for (var i = 0; i < list.length; i++) {
        var row = list[i];
        html +=
          "<tr>" +
          "<td>" + row.id + "</td>" +
          "<td>" + row.period_key + "</td>" +
          "<td>" + v1FormatYuan(row.effective_total_cents) + "</td>" +
          "<td>" + row.status + "</td>" +
          "<td>" + (row.dispute_reason || "") + "</td>" +
          "</tr>";
      }
      outBody.innerHTML = html;
    };
    xhr.send(null);
  }

  global.YunCeLegacyPortalV1 = {
    formatYuan: v1FormatYuan,
    loadInvoices: v1LoadLegacyInvoices,
  };
})(window);
