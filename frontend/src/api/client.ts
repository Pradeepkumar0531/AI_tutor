import axios, { AxiosError, type AxiosInstance, type AxiosRequestConfig } from "axios";

import type { ApiErrorEnvelope } from "@/types";
import { clearStoredToken, getStoredToken, setStoredToken } from "./tokenStorage";

export { TOKEN_KEY } from "./tokenStorage";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string;
  details: unknown;

  constructor(
    message: string,
    opts: { code: string; status: number; requestId: string; details: unknown },
  ) {
    super(message);
    this.code = opts.code;
    this.status = opts.status;
    this.requestId = opts.requestId;
    this.details = opts.details;
  }
}

/** Backwards-compatible accessors; new code uses tokenStorage directly. */
export function getAccessToken(): string | null {
  return getStoredToken();
}

export function setAccessToken(token: string | null): void {
  if (token) setStoredToken(token);
  else clearStoredToken();
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/**
 * Single subscriber slot for session death. The auth store registers here so
 * the client never imports store code (no import cycle).
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

function notifyUnauthorized(): void {
  try {
    unauthorizedHandler?.();
  } catch {
    // A broken subscriber must never break API error propagation.
  }
}

export function toApiError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const err = error as AxiosError<ApiErrorEnvelope>;
    const status = err.response?.status ?? 0;
    // Frontend timeout / aborted navigation: classify explicitly so the UI
    // can show a retry-oriented message instead of a generic failure.
    if (!err.response && (err.code === "ECONNABORTED" || err.code === "ETIMEDOUT")) {
      return new ApiError("The request timed out. The server may still be working — try again.", {
        code: "REQUEST_TIMEOUT",
        status: 0,
        requestId: "",
        details: null,
      });
    }
    if (!err.response && err.code === "ERR_CANCELED") {
      return new ApiError("The request was cancelled.", {
        code: "REQUEST_CANCELLED",
        status: 0,
        requestId: "",
        details: null,
      });
    }
    if (!err.response) {
      return new ApiError("Could not reach the server. Check your connection and try again.", {
        code: "NETWORK_ERROR",
        status: 0,
        requestId: "",
        details: null,
      });
    }
    const payload = err.response?.data?.error;
    return new ApiError(payload?.message ?? err.message ?? "Request failed", {
      code: payload?.code ?? "REQUEST_FAILED",
      status,
      requestId: payload?.request_id ?? (err.response?.headers?.["x-request-id"] as string) ?? "",
      details: payload?.details ?? null,
    });
  }
  return new ApiError(error instanceof Error ? error.message : "Unknown error", {
    code: "UNKNOWN",
    status: 0,
    requestId: "",
    details: null,
  });
}

export function createApiClient(config?: AxiosRequestConfig): AxiosInstance {
  const client = axios.create({
    baseURL: API_BASE_URL,
    timeout: 15000,
    headers: { "Content-Type": "application/json" },
    ...config,
  });

  client.interceptors.request.use((req) => {
    const token = getStoredToken();
    if (token) req.headers.set("Authorization", `Bearer ${token}`);
    return req;
  });

  client.interceptors.response.use(
    (res) => res,
    (error: unknown) => {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        // Never fight the auth endpoints themselves (login failures are 401
        // by design); anything else means the session is dead.
        const url = error.config?.url ?? "";
        if (!url.includes("/auth/login") && !url.includes("/auth/register")) {
          clearStoredToken();
          notifyUnauthorized();
        }
      }
      return Promise.reject(error);
    },
  );

  return client;
}

/** Shared singleton; feature modules import this, never `axios.create` directly. */
export const apiClient = createApiClient();
