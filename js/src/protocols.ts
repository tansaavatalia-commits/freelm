/** Wire-protocol translation for `freelm serve`: Anthropic Messages
 * (`/v1/messages` — what Claude Code and the Anthropic SDKs speak) and OpenAI
 * Responses (`/v1/responses` — what Codex CLI speaks), both mapped onto the
 * chat-completions shape the router works in.
 *
 * Pure functions and small state machines, no I/O: a request body becomes
 * `[messages, params]` for `chat()`; a `chat.completion` object or a stream of
 * `chat.completion.chunk` objects becomes the protocol's response / SSE events.
 *
 * Not translated (dropped, never an error): Anthropic server tools and thinking
 * blocks, Responses built-in / custom tools and reasoning items. */

type Obj = Record<string, any>;
export type SSEEvent = [string, Obj];

/** Coding agents ask for far more output than free tiers allow (Claude Code:
 * 32K+), and an oversized max_tokens is a 400 on most of them. */
export const MAX_OUTPUT_TOKENS = 8192;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function newId(prefix: string): string {
  let hex = "";
  for (let i = 0; i < 24; i++) hex += Math.floor(Math.random() * 16).toString(16);
  return `${prefix}_${hex}`;
}

/** Plain text of a content value (a string, or a list of text-ish parts). */
function textOf(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return content === null || content === undefined ? "" : String(content);
  const out: string[] = [];
  for (const p of content) {
    if (typeof p === "string") out.push(p);
    else if (isObj(p)) {
      if (typeof p.text === "string") out.push(p.text);
      else if (["image", "input_image", "image_url"].includes(p.type)) out.push("[image]");
    }
  }
  return out.filter(Boolean).join("\n");
}

/** Chat content for a user turn: a plain string unless an image needs parts
 * (several free providers reject list content). */
function userContent(parts: Obj[]): string | Obj[] {
  return parts.every((p) => p.type === "text") ? parts.map((p) => p.text).join("\n\n") : parts;
}

function clampTokens(value: unknown): number | null {
  return isNum(value) && value > 0 ? Math.floor(Math.min(value, MAX_OUTPUT_TOKENS)) : null;
}

const argumentsOf = (value: unknown): string => (typeof value === "string" ? value : JSON.stringify(value ?? {}));

function parseArguments(raw: unknown): Obj {
  if (isObj(raw)) return raw;
  try {
    const v = typeof raw === "string" && raw.trim() ? JSON.parse(raw) : {};
    return isObj(v) ? v : {};
  } catch {
    return {};
  }
}

export function hasImages(messages: Obj[]): boolean {
  return messages.some((m) => Array.isArray(m.content) && m.content.some((p: unknown) => isObj(p) && p.type === "image_url"));
}

/** Rough token count (~4 characters each); base64 payloads count as a flat
 * cost per image. Good enough for an agent's context meter. */
export function estimateTokens(value: unknown): number {
  let chars = 0;
  let images = 0;
  const stack: unknown[] = [value];
  while (stack.length) {
    const v = stack.pop();
    if (typeof v === "string") chars += v.length;
    else if (Array.isArray(v)) stack.push(...v);
    else if (isObj(v)) {
      if (["image", "input_image", "image_url"].includes(v.type)) {
        images++;
        continue;
      }
      for (const [k, x] of Object.entries(v)) {
        if (typeof x === "object" && x !== null) chars += k.length;
        stack.push(x);
      }
    } else if (v !== null && v !== undefined) chars += String(v).length;
  }
  return Math.max(1, Math.floor(chars / 4) + images * 1000);
}

function firstChoice(completion: Obj): [Obj, string | null] {
  const c = isObj(completion.choices?.[0]) ? completion.choices[0] : {};
  return [isObj(c.message) ? c.message : {}, c.finish_reason ?? null];
}

function usageOf(usage: unknown, textChars = 0): [number, number] {
  const u = isObj(usage) ? usage : {};
  return [Math.floor(Number(u.prompt_tokens) || 0), Math.floor(Number(u.completion_tokens) || 0) || Math.floor(textChars / 4)];
}

type Delta = ["text", string] | ["tool", number, string, string] | ["args", number, string];
interface ToolState {
  id: string;
  name: string;
  arguments: string;
  started: boolean;
  held: string;
}

/** `chat.completion.chunk` objects -> a flat event list:
 * `["text", s]` | `["tool", n, id, name]` | `["args", n, s]`.
 *
 * Tool calls are keyed by `index`; providers that omit it or reuse index 0 for
 * every call (Gemini) are told apart by `id`. A call whose name arrives late
 * is held back until it is known. */
class Deltas {
  tools: ToolState[] = [];
  private slot = new Map<number | "last", number>();
  text = "";
  finish: string | null = null;
  usage: Obj | null = null;
  model: string | null = null;

  feed(chunk: Obj): Delta[] {
    const out: Delta[] = [];
    this.model = this.model || chunk.model || null;
    if (isObj(chunk.usage)) this.usage = chunk.usage;
    for (const choice of Array.isArray(chunk.choices) ? chunk.choices : []) {
      if (!isObj(choice)) continue;
      if (choice.finish_reason) this.finish = choice.finish_reason;
      const delta = isObj(choice.delta) ? choice.delta : {};
      const content = Array.isArray(delta.content) ? textOf(delta.content) : delta.content;
      if (typeof content === "string" && content) {
        this.text += content;
        out.push(["text", content]);
      }
      for (const tc of Array.isArray(delta.tool_calls) ? delta.tool_calls : []) if (isObj(tc)) this.tool(tc, out);
    }
    return out;
  }

  private tool(tc: Obj, out: Delta[]): void {
    const fn = isObj(tc.function) ? tc.function : {};
    const tid: string = typeof tc.id === "string" ? tc.id : "";
    const key: number | "last" = Number.isInteger(tc.index) ? tc.index : "last";
    let n = this.slot.get(key);
    if (n === undefined || (tid && this.tools[n].id && tid !== this.tools[n].id)) {
      n = this.tools.length;
      this.tools.push({ id: tid, name: "", arguments: "", started: false, held: "" });
      this.slot.set(key, n);
      this.slot.set("last", n);
    }
    const t = this.tools[n];
    t.id = t.id || tid;
    t.name = t.name || (typeof fn.name === "string" ? fn.name : "");
    let args: string = isObj(fn.arguments) ? JSON.stringify(fn.arguments) : typeof fn.arguments === "string" ? fn.arguments : "";
    t.arguments += args;
    if (!t.started) {
      if (!t.name) {
        t.held += args;
        return;
      }
      t.started = true;
      t.id = t.id || newId("call");
      out.push(["tool", n, t.id, t.name]);
      args = t.held + args;
      t.held = "";
    }
    if (args) out.push(["args", n, args]);
  }

  startedTools(): ToolState[] {
    return this.tools.filter((t) => t.started);
  }
}

/** One translated protocol, as the server uses it. */
export interface Protocol {
  name: string;
  toChat(body: Obj): [Obj[], Obj];
  fromCompletion(completion: Obj, body: Obj): Obj;
  error(status: number, message: string): [number, Obj];
  stream(body: Obj): ProtocolStream;
}
export interface ProtocolStream {
  readonly model: string | null;
  feed(chunk: Obj): SSEEvent[];
  finish(): SSEEvent[];
  error(status: number, message: string): SSEEvent[];
}

// -- Anthropic Messages ---------------------------------------------------------

const ANTHROPIC_ERRORS: Record<number, string> = {
  400: "invalid_request_error", 401: "authentication_error", 403: "permission_error", 404: "not_found_error",
  413: "request_too_large", 429: "rate_limit_error", 529: "overloaded_error",
};

function stopReason(finish: string | null, tools: boolean): string {
  if (finish === "length") return "max_tokens";
  // some providers finish a tool turn with "stop": the agent still has to run it
  return tools ? "tool_use" : "end_turn";
}

/** `POST /v1/messages` <-> chat completions. */
export const AnthropicMessages = {
  name: "anthropic",

  toChat(body: Obj): [Obj[], Obj] {
    if (!Array.isArray(body.messages)) throw new Error("body must be an object with a 'messages' list");
    const messages: Obj[] = [];
    const system = textOf(body.system);
    if (system) messages.push({ role: "system", content: system });
    for (const m of body.messages) {
      if (!isObj(m)) throw new Error("every message must be an object");
      const role = m.role === "assistant" ? "assistant" : "user";
      const blocks = typeof m.content === "string" ? [{ type: "text", text: m.content }] : m.content;
      if (!Array.isArray(blocks)) throw new Error("message content must be a string or a list of blocks");
      const parts: Obj[] = [];
      const calls: Obj[] = [];
      for (const b of blocks) {
        if (!isObj(b)) continue;
        if (b.type === "text" && b.text) parts.push({ type: "text", text: b.text });
        else if (b.type === "image" && isObj(b.source)) {
          const src = b.source;
          const url = src.type === "url" ? src.url : `data:${src.media_type ?? "image/png"};base64,${src.data ?? ""}`;
          parts.push({ type: "image_url", image_url: { url } });
        } else if (b.type === "tool_use") {
          calls.push({ id: b.id || newId("call"), type: "function", function: { name: b.name || "", arguments: argumentsOf(b.input) } });
        } else if (b.type === "tool_result") {
          let text = textOf(b.content);
          if (b.is_error) text = `Error: ${text}`;
          // tool results answer the previous assistant turn: they go first
          messages.push({ role: "tool", tool_call_id: b.tool_use_id || "", content: text });
        }
      }
      if (role === "assistant") {
        const msg: Obj = { role: "assistant" };
        const text = parts.filter((p) => p.type === "text").map((p) => p.text).join("\n\n");
        if (text || !calls.length) msg.content = text;
        if (calls.length) msg.tool_calls = calls;
        messages.push(msg);
      } else if (parts.length) messages.push({ role: "user", content: userContent(parts) });
    }

    const params: Obj = {};
    const mt = clampTokens(body.max_tokens);
    if (mt) params.max_tokens = mt;
    for (const k of ["temperature", "top_p"]) if (isNum(body[k])) params[k] = body[k];
    if (Array.isArray(body.stop_sequences) ? body.stop_sequences.length : body.stop_sequences) params.stop = body.stop_sequences;
    const tools = (Array.isArray(body.tools) ? body.tools : [])
      // server tools (web_search_20250305, bash_..., ...) carry a versioned type and no schema
      .filter((t: unknown) => isObj(t) && t.name && (t.type === undefined || t.type === null || t.type === "custom"))
      .map((t: Obj) => ({
        type: "function",
        function: { name: t.name, description: t.description || "", parameters: t.input_schema || { type: "object", properties: {} } },
      }));
    if (tools.length) {
      params.tools = tools;
      const tc = body.tool_choice;
      const kind = isObj(tc) ? tc.type : null;
      if (kind === "any") params.tool_choice = "required";
      else if (kind === "tool" && tc.name) params.tool_choice = { type: "function", function: { name: tc.name } };
      else if (kind === "none") params.tool_choice = "none";
    }
    return [messages, params];
  },

  fromCompletion(completion: Obj, body: Obj): Obj {
    const [msg, finish] = firstChoice(completion);
    const text = textOf(msg.content);
    const content: Obj[] = text ? [{ type: "text", text }] : [];
    const calls: Obj[] = (Array.isArray(msg.tool_calls) ? msg.tool_calls : []).filter(isObj);
    for (const c of calls) {
      const fn = isObj(c.function) ? c.function : {};
      content.push({ type: "tool_use", id: c.id || newId("call"), name: fn.name || "", input: parseArguments(fn.arguments) });
    }
    const [tin, tout] = usageOf(completion.usage, text.length);
    return {
      id: newId("msg"), type: "message", role: "assistant", model: completion.model || body.model,
      content, stop_reason: stopReason(finish, calls.length > 0), stop_sequence: null,
      usage: { input_tokens: tin, output_tokens: tout },
    };
  },

  countTokens(body: Obj): Obj {
    return { input_tokens: estimateTokens([body.system, body.messages, body.tools]) };
  },

  error(status: number, message: string): [number, Obj] {
    // 529 (overloaded) is what Anthropic clients back off and retry on
    const s = status === 503 ? 529 : status;
    return [s, { type: "error", error: { type: ANTHROPIC_ERRORS[s] ?? "api_error", message } }];
  },

  stream(body: Obj): AnthropicStream {
    return new AnthropicStream(body);
  },
};

/** Chat chunks -> Anthropic SSE events (`message_start` ... `message_stop`). */
export class AnthropicStream implements ProtocolStream {
  private d = new Deltas();
  private started = false;
  private blocks = 0;
  private textBlock: number | null = null;
  private toolBlock = new Map<number, number>();
  private open: number[] = [];

  constructor(private body: Obj) {}

  get model(): string | null {
    return this.d.model;
  }

  private start(out: SSEEvent[]): void {
    if (this.started) return;
    this.started = true;
    out.push(["message_start", {
      type: "message_start",
      message: {
        id: newId("msg"), type: "message", role: "assistant", model: this.d.model || this.body.model, content: [],
        stop_reason: null, stop_sequence: null,
        usage: { input_tokens: AnthropicMessages.countTokens(this.body).input_tokens, output_tokens: 0 },
      },
    }]);
    out.push(["ping", { type: "ping" }]);
  }

  private openBlock(out: SSEEvent[], block: Obj): number {
    const i = this.blocks++;
    this.open.push(i);
    out.push(["content_block_start", { type: "content_block_start", index: i, content_block: block }]);
    return i;
  }

  private closeBlock(out: SSEEvent[], i: number): void {
    this.open = this.open.filter((x) => x !== i);
    out.push(["content_block_stop", { type: "content_block_stop", index: i }]);
  }

  feed(chunk: Obj): SSEEvent[] {
    const out: SSEEvent[] = [];
    const events = this.d.feed(chunk);
    this.start(out);
    for (const ev of events) {
      if (ev[0] === "text") {
        if (this.textBlock === null) this.textBlock = this.openBlock(out, { type: "text", text: "" });
        out.push(["content_block_delta", { type: "content_block_delta", index: this.textBlock, delta: { type: "text_delta", text: ev[1] } }]);
      } else if (ev[0] === "tool") {
        if (this.textBlock !== null) {
          // text before a tool call is complete
          this.closeBlock(out, this.textBlock);
          this.textBlock = null;
        }
        this.toolBlock.set(ev[1], this.openBlock(out, { type: "tool_use", id: ev[2], name: ev[3], input: {} }));
      } else {
        out.push(["content_block_delta", {
          type: "content_block_delta", index: this.toolBlock.get(ev[1]), delta: { type: "input_json_delta", partial_json: ev[2] },
        }]);
      }
    }
    return out;
  }

  finish(): SSEEvent[] {
    const out: SSEEvent[] = [];
    this.start(out);
    for (const i of [...this.open]) this.closeBlock(out, i);
    const [tin, tout] = usageOf(this.d.usage, this.d.text.length);
    const usage: Obj = { output_tokens: tout };
    if (tin) usage.input_tokens = tin;
    out.push(["message_delta", {
      type: "message_delta",
      delta: { stop_reason: stopReason(this.d.finish, this.d.startedTools().length > 0), stop_sequence: null },
      usage,
    }]);
    out.push(["message_stop", { type: "message_stop" }]);
    return out;
  }

  error(status: number, message: string): SSEEvent[] {
    return [["error", AnthropicMessages.error(status, message)[1]]];
  }
}

// -- OpenAI Responses -----------------------------------------------------------

function responseMessage(item: Obj): Obj | null {
  const r = item.role || "user";
  const role = r === "system" || r === "developer" ? "system" : r === "assistant" ? "assistant" : "user";
  const content = item.content;
  if (typeof content === "string") return content ? { role, content } : null;
  const parts: Obj[] = [];
  for (const p of Array.isArray(content) ? content : []) {
    if (!isObj(p)) continue;
    if (typeof p.text === "string" && p.text) parts.push({ type: "text", text: p.text });
    else if (p.type === "input_image") {
      const url = isObj(p.image_url) ? p.image_url.url : p.image_url;
      if (url) parts.push({ type: "image_url", image_url: { url } });
    }
  }
  if (!parts.length) return null;
  if (role !== "user") return { role, content: parts.filter((p) => p.type === "text").map((p) => p.text).join("\n\n") };
  return { role, content: userContent(parts) };
}

function envelope(
  body: Obj, id: string, created: number, model: unknown, status: string, output: Obj[],
  usage: Obj | null = null, incomplete: string | null = null,
): Obj {
  return {
    id, object: "response", created_at: created, status, error: null,
    incomplete_details: incomplete ? { reason: incomplete } : null,
    instructions: body.instructions ?? null, model, output,
    parallel_tool_calls: true, tool_choice: body.tool_choice || "auto",
    tools: body.tools || [], metadata: body.metadata || {}, usage,
  };
}

const textItem = (id: string, text: string, status = "completed"): Obj => ({
  type: "message", id, status, role: "assistant",
  content: status === "completed" ? [{ type: "output_text", text, annotations: [] }] : [],
});

const callItem = (id: string, callId: string, name: string, args: string, status = "completed"): Obj => ({
  type: "function_call", id, call_id: callId, name, arguments: args, status,
});

function usageObj(usage: unknown, textChars: number): Obj {
  const [tin, tout] = usageOf(usage, textChars);
  return { input_tokens: tin, output_tokens: tout, total_tokens: tin + tout };
}

/** `POST /v1/responses` <-> chat completions. */
export const OpenAIResponses = {
  name: "responses",

  toChat(body: Obj): [Obj[], Obj] {
    if (body.previous_response_id) {
      throw new Error("previous_response_id is not supported: freelm keeps no response state, send the whole conversation in 'input'");
    }
    const inp = typeof body.input === "string" ? [{ role: "user", content: body.input }] : body.input;
    if (!Array.isArray(inp)) throw new Error("body must have an 'input' string or list");
    const messages: Obj[] = [];
    if (typeof body.instructions === "string" && body.instructions) messages.push({ role: "system", content: body.instructions });
    for (const raw of inp) {
      const item = typeof raw === "string" ? { role: "user", content: raw } : raw;
      if (!isObj(item)) continue;
      const kind = item.type || ("role" in item ? "message" : null);
      if (kind === "message") {
        const msg = responseMessage(item);
        if (msg) messages.push(msg);
      } else if (kind === "function_call") {
        const call = {
          id: item.call_id || item.id || newId("call"), type: "function",
          function: { name: item.name || "", arguments: argumentsOf(item.arguments) },
        };
        const last = messages[messages.length - 1];
        if (last && last.role === "assistant") (last.tool_calls ??= []).push(call);
        else messages.push({ role: "assistant", tool_calls: [call] });
      } else if (kind === "function_call_output") {
        messages.push({
          role: "tool", tool_call_id: item.call_id || "",
          content: typeof item.output === "string" ? item.output : textOf(item.output),
        });
      }
      // reasoning, web_search_call, local_shell_call, custom tools...: not translatable
    }

    const params: Obj = {};
    const mt = clampTokens(body.max_output_tokens);
    if (mt) params.max_tokens = mt;
    for (const k of ["temperature", "top_p"]) if (isNum(body[k])) params[k] = body[k];
    const tools = (Array.isArray(body.tools) ? body.tools : [])
      .filter((t: unknown) => isObj(t) && t.type === "function" && t.name)
      .map((t: Obj) => ({
        type: "function",
        function: { name: t.name, description: t.description || "", parameters: t.parameters || { type: "object", properties: {} } },
      }));
    if (tools.length) {
      params.tools = tools;
      const tc = body.tool_choice;
      if (tc === "none" || tc === "required") params.tool_choice = tc;
      else if (isObj(tc) && tc.type === "function" && tc.name) params.tool_choice = { type: "function", function: { name: tc.name } };
    }
    const fmt = isObj(body.text) ? body.text.format : null;
    if (isObj(fmt) && fmt.type === "json_object") params.response_format = { type: "json_object" };
    else if (isObj(fmt) && fmt.type === "json_schema") {
      const js: Obj = {};
      for (const k of ["name", "schema", "strict", "description"]) if (k in fmt) js[k] = fmt[k];
      params.response_format = { type: "json_schema", json_schema: js };
    }
    return [messages, params];
  },

  fromCompletion(completion: Obj, body: Obj): Obj {
    const [msg, finish] = firstChoice(completion);
    const text = textOf(msg.content);
    const output: Obj[] = text ? [textItem(newId("msg"), text)] : [];
    for (const c of Array.isArray(msg.tool_calls) ? msg.tool_calls : []) {
      const fn = isObj(c) && isObj(c.function) ? c.function : {};
      if (fn.name) output.push(callItem(newId("fc"), c.id || newId("call"), fn.name, argumentsOf(fn.arguments)));
    }
    const cut = finish === "length";
    return envelope(
      body, newId("resp"), Math.floor(Date.now() / 1000), completion.model || body.model,
      cut ? "incomplete" : "completed", output, usageObj(completion.usage, text.length), cut ? "max_output_tokens" : null,
    );
  },

  error(status: number, message: string): [number, Obj] {
    const type = status >= 400 && status < 500 ? "invalid_request_error" : "server_error";
    return [status, { error: { message, type, param: null, code: null } }];
  },

  stream(body: Obj): ResponsesStream {
    return new ResponsesStream(body);
  },
};

/** Chat chunks -> Responses SSE events (`response.created` ... `response.completed`). */
export class ResponsesStream implements ProtocolStream {
  private d = new Deltas();
  private id = newId("resp");
  private created = Math.floor(Date.now() / 1000);
  private seq = 0;
  private started = false;
  private output: (Obj | null)[] = []; // finished items, by output_index
  private msg: [number, string] | null = null; // [output_index, item id] of the open text item
  private msgText = "";
  private calls = new Map<number, [number, string]>(); // tool n -> [output_index, item id]

  constructor(private body: Obj) {}

  get model(): string | null {
    return this.d.model;
  }

  private ev(out: SSEEvent[], kind: string, data: Obj): void {
    out.push([kind, { type: kind, sequence_number: this.seq++, ...data }]);
  }

  private snapshot(status: string, usage: Obj | null = null, incomplete: string | null = null): Obj {
    return envelope(
      this.body, this.id, this.created, this.d.model || this.body.model, status,
      this.output.filter((o): o is Obj => o !== null), usage, incomplete,
    );
  }

  private start(out: SSEEvent[]): void {
    if (this.started) return;
    this.started = true;
    this.ev(out, "response.created", { response: this.snapshot("in_progress") });
    this.ev(out, "response.in_progress", { response: this.snapshot("in_progress") });
  }

  private closeMessage(out: SSEEvent[]): void {
    if (!this.msg) return;
    const [idx, mid] = this.msg;
    const part = { type: "output_text", text: this.msgText, annotations: [] };
    this.ev(out, "response.output_text.done", { item_id: mid, output_index: idx, content_index: 0, text: this.msgText });
    this.ev(out, "response.content_part.done", { item_id: mid, output_index: idx, content_index: 0, part });
    const item = textItem(mid, this.msgText);
    this.output[idx] = item;
    this.ev(out, "response.output_item.done", { output_index: idx, item });
    this.msg = null;
    this.msgText = "";
  }

  feed(chunk: Obj): SSEEvent[] {
    const out: SSEEvent[] = [];
    const events = this.d.feed(chunk);
    this.start(out);
    for (const ev of events) {
      if (ev[0] === "text") {
        if (!this.msg) {
          this.msg = [this.output.length, newId("msg")];
          this.output.push(null);
          const [idx, mid] = this.msg;
          this.ev(out, "response.output_item.added", { output_index: idx, item: textItem(mid, "", "in_progress") });
          this.ev(out, "response.content_part.added", {
            item_id: mid, output_index: idx, content_index: 0, part: { type: "output_text", text: "", annotations: [] },
          });
        }
        const [idx, mid] = this.msg;
        this.msgText += ev[1];
        this.ev(out, "response.output_text.delta", { item_id: mid, output_index: idx, content_index: 0, delta: ev[1] });
      } else if (ev[0] === "tool") {
        this.closeMessage(out);
        const idx = this.output.length;
        const fid = newId("fc");
        this.output.push(null);
        this.calls.set(ev[1], [idx, fid]);
        this.ev(out, "response.output_item.added", { output_index: idx, item: callItem(fid, ev[2], ev[3], "", "in_progress") });
      } else {
        const [idx, fid] = this.calls.get(ev[1])!;
        this.ev(out, "response.function_call_arguments.delta", { item_id: fid, output_index: idx, delta: ev[2] });
      }
    }
    return out;
  }

  finish(): SSEEvent[] {
    const out: SSEEvent[] = [];
    this.start(out);
    this.closeMessage(out);
    for (const [n, [idx, fid]] of this.calls) {
      const t = this.d.tools[n];
      this.ev(out, "response.function_call_arguments.done", { item_id: fid, output_index: idx, arguments: t.arguments });
      const item = callItem(fid, t.id, t.name, t.arguments);
      this.output[idx] = item;
      this.ev(out, "response.output_item.done", { output_index: idx, item });
    }
    const cut = this.d.finish === "length";
    const usage = usageObj(this.d.usage, this.d.text.length);
    if (cut) this.ev(out, "response.incomplete", { response: this.snapshot("incomplete", usage, "max_output_tokens") });
    else this.ev(out, "response.completed", { response: this.snapshot("completed", usage) });
    return out;
  }

  error(_status: number, message: string): SSEEvent[] {
    const out: SSEEvent[] = [];
    const response = this.snapshot("failed");
    response.error = { code: "server_error", message };
    this.ev(out, "response.failed", { response });
    return out;
  }
}

export const PROTOCOLS: Record<string, Protocol> = {
  "/v1/messages": AnthropicMessages, "/messages": AnthropicMessages,
  "/v1/responses": OpenAIResponses, "/responses": OpenAIResponses,
};
export const COUNT_TOKENS_PATHS = new Set(["/v1/messages/count_tokens", "/messages/count_tokens"]);
