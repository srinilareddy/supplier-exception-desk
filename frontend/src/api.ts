import { useEffect, useState } from "react";
import type { components } from "./api-schema";

type Contract = components["schemas"];
export type Session = Contract["SessionView"];
export type Overview = Contract["Overview"];
export type CasePage = Contract["CasePage"];
export type CaseSummary = Contract["CaseSummary"];
export type CaseDetail = Contract["CaseDetail"];
export type CaseChange = Contract["CaseChange"];
export type Run = Contract["RunView"];
export type User = Contract["UserView"];

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId: string | null,
    readonly payload?: unknown,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: "same-origin", ...init });
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? payload.detail
      : undefined;
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed (HTTP ${response.status}).`,
      response.status,
      response.headers.get("X-Request-ID"),
      payload,
    );
  }
  return payload as T;
}

export function writeHeaders(session: Session, type?: string) {
  return {
    "X-CSRF-Token": session.csrf_token,
    ...(type ? { "Content-Type": type } : {}),
  };
}

export function messageFor(error: unknown) {
  if (error instanceof ApiError) {
    return error.status >= 500 && error.requestId
      ? `${error.message} Request ID ${error.requestId}.`
      : error.message;
  }
  return "The connection failed. Check that the desk is running and try again.";
}

export function isRun(payload: unknown): payload is Run {
  return payload !== null && typeof payload === "object"
    && "source" in payload && "issues" in payload && Array.isArray(payload.issues);
}

export function useResource<T>(
  path: string,
  revision: number,
  onExpired: () => void,
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    api<T>(path, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 401) onExpired();
        else setError(messageFor(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, revision, onExpired]);
  return { data, setData, error, loading };
}
