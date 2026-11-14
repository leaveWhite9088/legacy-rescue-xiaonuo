/**
 * [DEPRECATED 2024 通用表格拼接器] 2025 重构后已停用，保留防旧私有化书签 404。
 */
(function (global) {
  function buildOldAdminTableHtml(tenants) {
    var buf = [];
    for (var i = 0; i < (tenants || []).length; i++) {
      var t = tenants[i];
      buf.push(
        "<tr><td>" + t.id + "</td><td>" + t.company_name + "</td><td>" + t.status + "</td></tr>"
      );
    }
    return buf.join("");
  }
  global.YunCeOldTableRenderer = { buildOldAdminTableHtml: buildOldAdminTableHtml };
})(window);
