// 数电专票超限额分联试算工具组件
export function calculateSplitSheetsPreview(invoiceTotalCents, rateBps = 600, maxSheetCents = 10000000) {
  const gross = Math.max(0, Number(invoiceTotalCents || 0));
  const net = Math.floor((gross * 10000) / (10000 + rateBps));
  const tax = Math.floor((net * rateBps) / 10000);
  const count = gross > 0 ? Math.ceil(gross / maxSheetCents) : 0;
  return { totalGrossCents: gross, netCents: net, taxCents: tax, sheetCount: count };
}
