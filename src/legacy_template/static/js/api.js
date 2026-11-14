/**
 * 统一 HTTP JSON 请求封装（附带 X-Request-Id 追踪与业务异常解包）
 */
export async function apiFetch(url, options = {}) {
  const reqId = `fe_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
  const mergedHeaders = {
    "X-Request-Id": reqId,
    ...(options.headers || {}),
  };
  const resp = await fetch(url, {
    ...options,
    headers: mergedHeaders,
  });
  const contentType = resp.headers.get("content-type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    payload = await resp.json();
  } else {
    payload = await resp.text();
  }
  if (!resp.ok) {
    const errMsg =
      (payload && typeof payload === "object" && payload.error) ||
      `HTTP ${resp.status} 请求失败`;
    const err = new Error(errMsg);
    err.status = resp.status;
    err.payload = payload;
    throw err;
  }
  return payload;
}
