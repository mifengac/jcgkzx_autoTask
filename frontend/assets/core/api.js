export async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 401 && window.location.pathname !== "/login") {
    window.location.href = "/login";
    throw new Error("登录已失效，请重新登录。");
  }
  if (response.status === 204) {
    return null;
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (error) {
      if (!response.ok) {
        throw new Error(text);
      }
      data = text;
    }
  }

  if (!response.ok) {
    throw new Error(data && data.detail ? data.detail : `请求失败: ${response.status}`);
  }
  return data;
}

export function jsonRequest(method, payload) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

export function parseJson(value, fallback) {
  const text = String(value ?? "").trim();
  if (!text) {
    return fallback;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`JSON 解析失败: ${error.message}`);
  }
}

export function splitLines(value) {
  return String(value ?? "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
