// DEPRECATED 2024 Q4: 早期静态管理后台脚本备份（当前 admin.html 已改用 ES Module 版 static/js/admin.js 及其 views/ 子模块）
// 保留原因：仅供比对 2024 旧版表格列宽与打印弹窗行为，生产页面未加载本文件。
(function () {
  function legacyRenderTenantList2024(rows) {
    var box = document.getElementById("legacy-2024-tenant-box");
    if (!box || !rows) return;
    var out = "";
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      out += "<div class='old-row'>" + (r.id || "") + " - " + String(r.status || "") + "</div>";
    }
    box.innerHTML = out;
  }
  window.__yunceLegacyAdmin2024 = { render: legacyRenderTenantList2024 };
})();
