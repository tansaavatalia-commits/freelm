import { useCallback, useEffect, useRef, useState } from "react";

// The core injects the installation token into the page it serves; `npm run dev` uses VITE_GENESIS_TOKEN.
const pageToken = document.querySelector<HTMLMetaElement>('meta[name="genesis-token"]')?.content ?? "";
const TOKEN = pageToken.startsWith("%") ? (import.meta.env.VITE_GENESIS_TOKEN ?? "") : pageToken;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly approvalId?: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, options: { method?: "GET" | "POST"; body?: unknown } = {}): Promise<T> {
  const hasBody = options.body !== undefined;
  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method ?? (hasBody ? "POST" : "GET"),
      headers: { "X-Genesis-Token": TOKEN, ...(hasBody ? { "Content-Type": "application/json" } : {}) },
      body: hasBody ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "GÉNESIS non risponde: la finestra di 'genesis serve' è ancora aperta?");
  }
  const data = (await response.json().catch(() => ({}))) as { error?: string; approval_id?: string };
  if (!response.ok) {
    throw new ApiError(response.status, data.error ?? `errore ${response.status}`, data.approval_id);
  }
  return data as T;
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Loads data now and again every `intervalMs` while the page is visible (0 = once). */
export function usePolling<T>(load: () => Promise<T>, intervalMs: number, deps: readonly unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const refresh = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (!intervalMs) return undefined;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [refresh, intervalMs, ...deps]);

  return { data, error, refresh };
}

/** Polls a queued task until it finishes; returns its result or throws its error. */
export async function waitForTask<T>(id: string, timeoutMs = 60000): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const task = await api<{ status: string; result: T; error: string | null }>(`/api/tasks/${id}`);
    if (task.status === "succeeded") return task.result;
    if (task.status === "failed" || task.status === "cancelled") throw new ApiError(400, task.error ?? task.status);
    await new Promise((r) => window.setTimeout(r, 400));
  }
  throw new ApiError(408, "il compito sta impiegando troppo tempo: controlla la pagina Compiti");
}
