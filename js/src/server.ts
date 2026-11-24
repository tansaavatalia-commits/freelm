/** `freelm serve` — the router as a local OpenAI-compatible HTTP endpoint.
 *
 * Point any OpenAI-compatible tool at it (Cursor, Cline, Continue, Open WebUI,
 * n8n, LangChain, the Vercel AI SDK, the OpenAI SDKs, ...):
 *
 *   npx freelm serve                     # http://127.0.0.1:4000/v1
 *
 * Endpoints: POST /v1/chat/completions (JSON, or SSE with stream: true),
 * POST /v1/messages (+ /count_tokens; the Anthropic Messages API, for Claude
 * Code and the Anthropic SDKs), POST /v1/responses (the OpenAI Responses API,
 * for Codex CLI), GET /v1/models (virtual aliases + discovered models),
 * GET /health. The last two protocols are translated to chat completions in
 * protocols.ts, so they share the same failover.
 * Zero dependencies: node:http is loaded at runtime (process.getBuiltinModule),
 * so importing this module never breaks edge/browser bundles. */
import type { IncomingMessage, Server, ServerResponse } from "node:http";
import { FreeLLM, FreeLLMOptions } from "./client.js";
import { providersFromEnv } from "./config.js";
import { BadRequest, ConfigError, FreeLLMError, NoProvidersAvailable, ProviderError } from "./errors.js";
import { Provider } from "./providers/base.js";
import { AnthropicMessages, COUNT_TOKENS_PATHS, hasImages, Protocol, PROTOCOLS } from "./protocols.js";
import { isVirtual, virtualAliases } from "./registry.js";
import { builtin } from "./runtime.js";
import { chunkStamper, completionBody } from "./types.js";
import { VERSION } from "./version.js";

const MAX_BODY = 20 * 1024 * 1024; // generous for base64 images, bounded against abuse
// An oversized body is read and discarded up to this much, so the 413 reaches a
// client that is still uploading; beyond it the connection is just dropped.
const DRAIN_LIMIT = 4 * MAX_BODY;
const CHAT_PATHS = new Set(["/v1/chat/completions", "/chat/completions"]);
const MODEL_PATHS = new Set(["/v1/models", "/models"]);
const HEALTH_PATHS = new Set(["/health", "/v1/health", "/healthz"]);
export const ENDPOINTS = ["/v1/chat/completions", "/v1/messages", "/v1/responses", "/v1/models", "/health"];
const LOOPBACK = new Set(["127.0.0.1", "localhost", "::1"]);
const DEFAULT_CORS_HEADERS = "Authorization, Content-Type, X-Api-Key";

/** Host header -> bare hostname ("[::1]:4000" -> "::1"). */
function hostOnly(h: string): string {
  const v = h.trim().toLowerCase();
  if (v.startsWith("[")) return v.includes("]") ? v.slice(1, v.indexOf("]")) : v;
  return v.split(":").length === 2 ? v.split(":")[0] : v;
}

/** `http://host:port/v1`, IPv6 hosts bracketed. */
export function urlFor(host: string, port: number): string {
  return `http://${host.includes(":") && !host.startsWith("[") ? `[${host}]` : host}:${port}/v1`;
}

/** Health rows with snake_case fields — the HTTP API is identical across the
 * Python and TS servers. */
function snakeHealth(rows: Record<string, any>[]): Record<string, any>[] {
  return rows.map((r) => ({
    provider: r.provider, key: r.key, tier: r.tier, ready: r.ready, disabled: r.disabled, breaker: r.breaker,
    rpd_used: r.rpdUsed, rpd: r.rpd, last_error: r.lastError, ewma_latency_ms: r.ewmaLatencyMs,
  }));
}

export interface ServeOptions {
  host?: string;
  port?: number;
  /** Require `Authorization: Bearer <apiKey>` (or `x-api-key`) from clients. */
  apiKey?: string | null;
  /** Allow browser apps on other origins. */
  cors?: boolean;
  /** Serve concrete ids no provider lists (e.g. a tool's default "gpt-4o") with
   * this alias as a fallback; null disables. Default "auto". */
  fallbackModel?: string | null;
  /** Per-request log sink (default: none). */
  log?: (line: string) => void;
}

const errorBody = (message: string, type: string, code: string | null = null) => ({
  error: { message, type, param: null, code },
});

function statusFor(e: unknown): [number, Record<string, any>] {
  if (e instanceof ConfigError) return [400, errorBody(e.message, "invalid_request_error", "config_error")];
  if (e instanceof BadRequest) {
    return [e.status >= 400 && e.status < 500 ? e.status : 400, errorBody(e.message, "invalid_request_error", "rejected_by_providers")];
  }
  if (e instanceof NoProvidersAvailable) return [503, errorBody(e.message, "service_unavailable", "no_providers_available")];
  if (e instanceof ProviderError) return [502, errorBody(e.message, "upstream_error", "provider_error")];
  if (e instanceof FreeLLMError) return [500, errorBody(e.message, "server_error")];
  return [500, errorBody(`internal error: ${(e as any)?.name ?? "Error"}`, "server_error")];
}

function timingSafeEqual(a: string, b: string): boolean {
  const crypto = builtin("node:crypto");
  const ab = new TextEncoder().encode(a);
  const bb = new TextEncoder().encode(b);
  if (ab.length !== bb.length) return false;
  if (crypto?.timingSafeEqual) return crypto.timingSafeEqual(ab, bb);
  let diff = 0;
  for (let i = 0; i < ab.length; i++) diff |= ab[i] ^ bb[i];
  return diff === 0;
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const parts: Buffer[] = [];
    let size = 0;
    let tooBig = false;
    const tooLarge = () => Object.assign(new Error(`request body larger than ${MAX_BODY / (1024 * 1024)} MB`), { status: 413 });
    req.on("data", (c: Buffer) => {
      size += c.length;
      if (size > DRAIN_LIMIT) {
        req.destroy(); // a client that won't stop sending: drop it
        return;
      }
      if (size > MAX_BODY) {
        tooBig = true;
        parts.length = 0; // keep draining (discarding) until the upload ends
      } else if (!tooBig) parts.push(c);
    });
    req.on("close", () => {
      if (tooBig) reject(tooLarge()); // no-op if already settled
    });
    req.on("end", () => {
      // answer only once the whole upload is consumed, or the client (still
      // writing) sees a connection reset instead of the 413
      if (tooBig) return reject(tooLarge());
      const text = Buffer.concat(parts).toString("utf-8");
      if (!text) reject(Object.assign(new Error("a JSON request body is required"), { status: 400 }));
      else resolve(text);
    });
    req.on("error", reject);
  });
}

/** Build (but don't start) a server for `llm`; call `.listen()` on it. */
export function createServer(llm: FreeLLM, opts: ServeOptions = {}): Server {
  const http = builtin("node:http");
  if (!http) throw new ConfigError("freelm serve needs Node.js (node:http) — >= 20.16 / 22.3, or Bun");
  const fallback = opts.fallbackModel === undefined ? "auto" : opts.fallbackModel;
  const warned = new Set<string>();
  const log = opts.log;

  const modelChain = (requested: unknown): string | string[] => {
    if (typeof requested !== "string" || !requested.trim()) return fallback ?? "auto";
    if (isVirtual(requested) || !fallback) return requested;
    if (llm.providers.some((p: Provider) => p.knowsModel(requested))) return requested;
    if (!warned.has(requested) && log) {
      warned.add(requested);
      log(`note: no free provider lists model '${requested}'; trying it, then '${fallback}'`);
    }
    return [requested, fallback];
  };

  /** Model chain for the translated protocols. Agents name models no free tier
   * has ("claude-sonnet-4-5", "gpt-5-codex"): those are never sent upstream —
   * the request goes to models that can serve it (vision for images, tool
   * calling for tools, a fast one for a small-model id), then `fallbackModel`. */
  const agentChain = (requested: unknown, messages: Record<string, any>[], params: Record<string, any>): string | string[] => {
    if (!fallback) return modelChain(requested);
    if (typeof requested === "string" && requested.trim() &&
        (isVirtual(requested) || llm.providers.some((p: Provider) => p.knowsModel(requested)))) return requested;
    const name = typeof requested === "string" ? requested.toLowerCase() : "";
    let first: string;
    if (hasImages(messages)) first = "vision";
    else if (params.tools) first = "tools";
    else if (["haiku", "mini", "nano", "flash"].some((s) => name.includes(s))) first = "fast";
    else return fallback;
    return first !== fallback ? [first, fallback] : first;
  };

  let loopbackOnly = false; // set from the bound address once listening
  const cors = (res: ServerResponse, req?: IncomingMessage) => {
    if (!opts.cors) return;
    res.setHeader("Access-Control-Allow-Origin", "*");
    // reflect what the browser asks for (openai-node sends x-stainless-* headers)
    const asked = req?.headers["access-control-request-headers"];
    res.setHeader("Access-Control-Allow-Headers", typeof asked === "string" && asked ? asked : DEFAULT_CORS_HEADERS);
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  };

  const sendJson = (res: ServerResponse, status: number, obj: unknown, headers: Record<string, string> = {}) => {
    const data = JSON.stringify(obj);
    cors(res);
    res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data), ...headers });
    res.end(data);
  };

  const authorized = (req: IncomingMessage, res: ServerResponse): boolean => {
    if (loopbackOnly && !LOOPBACK.has(hostOnly(String(req.headers.host ?? "")))) {
      // DNS rebinding: a page on evil.example resolving to 127.0.0.1
      sendJson(res, 403, errorBody("this freelm server only answers requests addressed to localhost", "invalid_request_error", "forbidden_host"));
      return false;
    }
    if (!opts.apiKey) return true;
    const auth = String(req.headers.authorization ?? "");
    const given = auth.toLowerCase().startsWith("bearer ") ? auth.slice(7).trim() : String(req.headers["x-api-key"] ?? "");
    if (given && timingSafeEqual(given, opts.apiKey)) return true;
    sendJson(res, 401, errorBody("missing or invalid API key for this freelm server", "invalid_request_error", "invalid_api_key"));
    return false;
  };

  const models = async () => {
    await (llm as any).ensureDiscovered?.().catch?.(() => {});
    const created = Math.floor(Date.now() / 1000);
    const data = virtualAliases().map((id) => ({ id, object: "model", created, owned_by: "freelm" }));
    const seen = new Set(data.map((d) => d.id));
    for (const p of llm.providers)
      for (const m of p.models)
        if (!seen.has(m.id)) {
          seen.add(m.id);
          data.push({ id: m.id, object: "model", created, owned_by: p.name });
        }
    return { object: "list", data };
  };

  const chat = async (req: IncomingMessage, res: ServerResponse, body: Record<string, any>) => {
    const t0 = performance.now();
    const { stream, stream_options: _so, messages, model: requested, ...rest } = body;
    const params: Record<string, any> = {};
    for (const [k, v] of Object.entries(rest)) if (v !== null && v !== undefined) params[k] = v;
    const model = modelChain(requested);
    const ac = new AbortController();
    res.on("close", () => {
      if (!res.writableFinished) ac.abort(); // the client went away: stop pulling tokens upstream
    });
    const done = (status: number, what: string) =>
      log?.(`${req.method} ${req.url?.split("?")[0]} ${status} ${what} ${Math.round(performance.now() - t0)}ms`);

    if (!stream) {
      try {
        const r = await llm.chat(messages, { ...params, model, signal: ac.signal });
        sendJson(res, 200, completionBody(r), { "X-FreeLLM-Provider": r.provider ?? "", "X-FreeLLM-Model": r.model ?? "" });
        done(200, `${r.provider}/${r.model}`);
      } catch (e) {
        if (ac.signal.aborted) return;
        const [status, err] = statusFor(e);
        sendJson(res, status, err);
        done(status, (e as any)?.name ?? "error");
      }
      return;
    }

    const it = llm.streamChunks(messages, { ...params, model, signal: ac.signal })[Symbol.asyncIterator]();
    let first: IteratorResult<Record<string, any>>;
    try {
      first = await it.next(); // failover settles before we commit to a 200
    } catch (e) {
      if (ac.signal.aborted) return;
      const [status, err] = statusFor(e);
      sendJson(res, status, err);
      done(status, (e as any)?.name ?? "error");
      return;
    }
    const stamp = chunkStamper();
    cors(res);
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
    let served: string | null = null;
    const write = (c: Record<string, any>) => {
      served ??= c.model ?? null;
      res.write(`data: ${JSON.stringify(stamp(c))}\n\n`);
    };
    try {
      if (!first.done) write(first.value);
      for (let r = first; !r.done; ) {
        r = await it.next();
        if (!r.done) write(r.value);
      }
    } catch (e) {
      if (!ac.signal.aborted) res.write(`data: ${JSON.stringify(statusFor(e)[1])}\n\n`);
    }
    if (!ac.signal.aborted) {
      res.end("data: [DONE]\n\n");
      done(200, `stream/${served}`);
    }
  };

  /** Serve an Anthropic Messages / OpenAI Responses request through chat(). */
  const translated = async (
    req: IncomingMessage, res: ServerResponse, proto: Protocol, body: Record<string, any>,
    messages: Record<string, any>[], params: Record<string, any>,
  ) => {
    const t0 = performance.now();
    const model = agentChain(body.model, messages, params);
    const ac = new AbortController();
    res.on("close", () => {
      if (!res.writableFinished) ac.abort(); // the client went away: stop pulling tokens upstream
    });
    const done = (status: number, what: string) =>
      log?.(`${req.method} ${req.url?.split("?")[0]} ${status} ${what} ${Math.round(performance.now() - t0)}ms`);
    const fail = (e: unknown) => {
      if (ac.signal.aborted) return;
      const [s, err] = statusFor(e);
      const [status, out] = proto.error(s, err.error.message);
      sendJson(res, status, out);
      done(status, (e as any)?.name ?? "error");
    };

    if (!body.stream) {
      try {
        const r = await llm.chat(messages, { ...params, model, signal: ac.signal });
        sendJson(res, 200, proto.fromCompletion(completionBody(r), body), {
          "X-FreeLLM-Provider": r.provider ?? "", "X-FreeLLM-Model": r.model ?? "",
        });
        done(200, `${r.provider}/${r.model}`);
      } catch (e) {
        fail(e);
      }
      return;
    }

    const it = llm.streamChunks(messages, { ...params, model, signal: ac.signal })[Symbol.asyncIterator]();
    let r: IteratorResult<Record<string, any>>;
    try {
      r = await it.next(); // failover settles before we commit to a 200
    } catch (e) {
      fail(e);
      return;
    }
    const enc = proto.stream(body);
    const emit = (events: [string, Record<string, any>][]) => {
      if (events.length) res.write(events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""));
    };
    cors(res);
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
    try {
      while (!r.done) {
        emit(enc.feed(r.value));
        r = await it.next();
      }
      emit(enc.finish());
    } catch (e) {
      if (!ac.signal.aborted) {
        const [status, err] = statusFor(e);
        emit(enc.error(status, err.error.message));
      }
    }
    if (!ac.signal.aborted) {
      res.end();
      done(200, `stream/${enc.model}`);
    }
  };

  const server: Server = http.createServer(async (req: IncomingMessage, res: ServerResponse) => {
    const path = (req.url ?? "/").split("?")[0].replace(/\/+$/, "") || "/";
    try {
      if (req.method === "OPTIONS") {
        cors(res, req);
        res.writeHead(204, { "Content-Length": "0" });
        res.end();
        return;
      }
      if (req.method === "GET" && HEALTH_PATHS.has(path)) {
        sendJson(res, 200, { status: "ok", version: VERSION, keys: snakeHealth(llm.health()) });
        return;
      }
      if (!authorized(req, res)) return;
      if (req.method === "GET" && MODEL_PATHS.has(path)) {
        sendJson(res, 200, await models());
        return;
      }
      if (req.method === "GET" && (path === "/" || path === "/v1")) {
        sendJson(res, 200, { name: "freelm", version: VERSION, endpoints: ENDPOINTS });
        return;
      }
      const proto = PROTOCOLS[path];
      const counting = COUNT_TOKENS_PATHS.has(path);
      if (req.method !== "POST" || (!CHAT_PATHS.has(path) && !proto && !counting)) {
        sendJson(res, 404, errorBody(`no route for ${req.method} ${path}`, "invalid_request_error", "not_found"));
        return;
      }
      const fail = (status: number, message: string) => {
        if (proto || counting) {
          const [s, err] = (proto ?? AnthropicMessages).error(status, message);
          sendJson(res, s, err);
        } else sendJson(res, status, errorBody(message, "invalid_request_error"));
      };
      if (!String(req.headers["content-type"] ?? "").toLowerCase().includes("application/json")) {
        // also what keeps arbitrary web pages out: a cross-origin JSON POST
        // needs a CORS preflight, which is refused unless --cors
        res.setHeader("Connection", "close");
        fail(415, "Content-Type must be application/json");
        return;
      }
      let body: any;
      let chatArgs: [Record<string, any>[], Record<string, any>] | null = null;
      try {
        body = JSON.parse(await readBody(req));
        if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("body must be a JSON object");
        if (counting) {
          sendJson(res, 200, AnthropicMessages.countTokens(body));
          return;
        }
        if (proto) chatArgs = proto.toChat(body);
        else if (!Array.isArray(body.messages)) throw new Error("body must be an object with a 'messages' list");
      } catch (e: any) {
        if (e?.status) {
          res.setHeader("Connection", "close");
          fail(e.status, String(e.message));
        } else fail(400, `invalid JSON body: ${e?.message ?? e}`);
        return;
      }
      if (proto && chatArgs) await translated(req, res, proto, body, chatArgs[0], chatArgs[1]);
      else await chat(req, res, body);
    } catch (e) {
      if (!res.headersSent) {
        const [status, err] = statusFor(e);
        sendJson(res, status, err);
      } else res.end();
    }
  });
  server.on("listening", () => {
    const addr: any = server.address();
    loopbackOnly = !!addr && typeof addr === "object" && (addr.address === "127.0.0.1" || addr.address === "::1");
  });
  return server;
}

/** `env` (default: this process's) with the Anthropic and OpenAI SDK variables
 * pointed at a freelm server on `port` — what `freelm run` gives the tool it
 * launches. A real ANTHROPIC_API_KEY is blanked so the tool cannot fall back
 * to a paid account. */
export function agentEnv(port: number, apiKey: string, env?: Record<string, string | undefined>): Record<string, string | undefined> {
  const out: Record<string, string | undefined> = { ...(env ?? builtin("node:process")?.env ?? {}) };
  const root = `http://127.0.0.1:${port}`;
  Object.assign(out, {
    ANTHROPIC_BASE_URL: root, ANTHROPIC_AUTH_TOKEN: apiKey, ANTHROPIC_API_KEY: "",
    OPENAI_BASE_URL: `${root}/v1`, OPENAI_API_BASE: `${root}/v1`, OPENAI_API_KEY: apiKey,
  });
  // a configured proxy must not swallow the loopback calls
  for (const v of ["NO_PROXY", "no_proxy"]) out[v] = [out[v], "127.0.0.1,localhost"].filter(Boolean).join(",");
  return out;
}

/** Run `freelm serve` in-process (providers default to the environment).
 * Resolves once listening; returns the node:http Server. */
export async function serve(
  opts: ServeOptions & FreeLLMOptions & { providers?: Provider[]; quiet?: boolean } = {},
): Promise<Server> {
  const { providers, host = "127.0.0.1", port = 4000, apiKey, cors, fallbackModel, quiet, log, ...clientOpts } = opts;
  const provs = providers ?? providersFromEnv();
  const llm = new FreeLLM(provs, clientOpts);
  const out = (line: string) => {
    if (!quiet) process.stderr.write(line + "\n");
  };
  const server = createServer(llm, { apiKey, cors, fallbackModel, log: log ?? out });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, () => resolve());
  });
  const addr: any = server.address();
  const url = urlFor(host, addr?.port ?? port);
  const names = provs.map((p) => p.name + (p.keys.length > 1 ? ` (${p.keys.length} keys)` : "")).join(", ");
  process.stderr.write(`freelm ${VERSION} — OpenAI-compatible endpoint on ${url}\n`);
  process.stderr.write(`providers: ${names} · strategy: ${llm.strategy}\n`);
  process.stderr.write(`use it:    baseURL=${url}  apiKey=${apiKey ? "<your --api-key>" : "anything"}  model=auto\n`);
  if (!LOOPBACK.has(host) && !apiKey) {
    process.stderr.write(
      "warning: listening beyond localhost without --api-key — anyone who can reach this port can spend your free quota\n",
    );
  }
  process.stderr.write("Ctrl+C to stop.\n");
  return server;
}
