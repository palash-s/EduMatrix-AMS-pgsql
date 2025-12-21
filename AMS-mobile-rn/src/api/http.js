export async function httpJson(url, { method = 'GET', token, body, timeoutMs = 12000 } = {}) {
  const headers = {
    Accept: 'application/json',
  };

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    if (e && (e.name === 'AbortError' || String(e.message || '').toLowerCase().includes('aborted'))) {
      throw new Error(`Request timed out (${timeoutMs}ms). Check API_BASE_URL: ${url}`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  const json = text ? safeJson(text) : null;

  if (!res.ok) {
    const msg = (json && (json.error || json.message)) || text || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  return json;
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
