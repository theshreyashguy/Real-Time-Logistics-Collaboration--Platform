// Raw XMLHttpRequest client (mandated by the assignment).
// Wraps XHR in a Promise and exposes the full request lifecycle:
// progress, timeout, abort, and error events — none of which fetch/axios
// surface as cleanly.

export interface XhrOptions {
  method?: string;
  body?: unknown;
  token?: string | null;
  timeout?: number;
  onProgress?: (fraction: number) => void;
  signal?: { aborted: boolean; onabort?: () => void };
}

export class HttpError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function xhrRequest<T = unknown>(
  path: string,
  opts: XhrOptions = {}
): Promise<T> {
  const {
    method = "GET",
    body,
    token,
    timeout = 8000,
    onProgress,
    signal,
  } = opts;

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const url = path.startsWith("http") ? path : API + path;
    xhr.open(method, url, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.timeout = timeout;

    // upload progress (useful for large bodies / attachments)
    if (onProgress && xhr.upload) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
    }

    xhr.ontimeout = () => reject(new HttpError(0, "Request timed out"));
    xhr.onerror = () => reject(new HttpError(0, "Network error"));
    xhr.onabort = () => reject(new HttpError(0, "Request aborted"));

    xhr.onload = () => {
      let parsed: unknown = null;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        parsed = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parsed as T);
      } else {
        const detail =
          parsed && typeof parsed === "object" && "detail" in parsed
            ? (parsed as { detail: unknown }).detail
            : parsed;
        reject(new HttpError(xhr.status, detail));
      }
    };

    // wire external abort
    if (signal) {
      signal.onabort = () => xhr.abort();
      if (signal.aborted) xhr.abort();
    }

    xhr.send(body != null ? JSON.stringify(body) : null);
  });
}
