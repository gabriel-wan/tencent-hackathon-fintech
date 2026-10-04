// Errors the API clients throw, so pages can tell "signed out" from "server down"
// from "the backend said no".

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/** 401: no valid session. Pages send the user to /login. */
export class NotSignedInError extends ApiError {
  constructor() {
    super(401, "Not signed in");
    this.name = "NotSignedInError";
  }
}

/** The backend could not be reached (network failure, or the /api proxy's 502/504). */
export class BackendUnreachableError extends Error {
  constructor(readonly reason = "backend unreachable") {
    super(reason);
    this.name = "BackendUnreachableError";
  }
}

// FastAPI sends {"detail": "..."} or, for validation errors, {"detail": [{msg, ...}]}.
function detailOf(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((d) => (d as { msg?: unknown })?.msg).filter((m) => typeof m === "string");
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}

/** Turns a fetch Response into data, or throws one of the errors above. */
export async function readResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) throw new NotSignedInError();
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null; // not JSON, e.g. an HTML error page
  }
  if (res.status === 502 || res.status === 504) {
    throw new BackendUnreachableError(detailOf(body, "backend unreachable"));
  }
  if (!res.ok) throw new ApiError(res.status, detailOf(body, res.statusText || "request failed"));
  return body as T;
}
