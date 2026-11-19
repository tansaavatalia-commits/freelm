// Anthropic Messages / OpenAI Responses translation (protocols.ts) and the
// `freelm serve` routes built on it. Mirrors tests/test_protocols.py.
import { request } from "node:http";
import type { Server } from "node:http";
import { afterEach, expect, it, vi } from "vitest";
import { FreeLLM, OpenRouter } from "../src/index.js";
import { AnthropicMessages, estimateTokens, MAX_OUTPUT_TOKENS, OpenAIResponses, ProtocolStream, SSEEvent } from "../src/protocols.js";
import { createServer } from "../src/server.js";
import { mockFetch, OK } from "./helpers.js";

const WEATHER = { name: "get_weather", description: "Weather", input_schema: { type: "object", properties: {} } };

const chunk = (delta: any, finish: string | null = null, extra: any = {}) => ({
  model: "m1", choices: [{ index: 0, delta, finish_reason: finish }], ...extra,
});

function toolDelta(index: number | null, id?: string | null, name?: string | null, args?: string) {
  const tc: any = { function: {} };
  if (index !== null) tc.index = index;
  if (id) tc.id = id;
  if (name) tc.function.name = name;
  if (args !== undefined) tc.function.arguments = args;
  return { tool_calls: [tc] };
}

function run(enc: ProtocolStream, chunks: any[]): SSEEvent[] {
  const events: SSEEvent[] = [];
  for (const c of chunks) events.push(...enc.feed(c));
  return [...events, ...enc.finish()];
}

// -- Anthropic ------------------------------------------------------------------

it("turns an Anthropic request into chat messages", () => {
  const [messages, params] = AnthropicMessages.toChat({
    model: "claude-sonnet-4-5", max_tokens: 64000, temperature: 0.2, stop_sequences: ["END"],
    system: [{ type: "text", text: "You are terse." }, { type: "text", text: "Be kind." }],
    tools: [WEATHER, { type: "web_search_20250305", name: "web_search" }],
    tool_choice: { type: "any" },
    messages: [
      { role: "user", content: "weather in Rome?" },
      { role: "assistant", content: [
        { type: "thinking", thinking: "hmm", signature: "s" },
        { type: "text", text: "Checking." },
        { type: "tool_use", id: "t1", name: "get_weather", input: { city: "Rome" } }] },
      { role: "user", content: [
        { type: "text", text: "and Milan" },
        { type: "tool_result", tool_use_id: "t1", content: [{ type: "text", text: "sunny" }] },
        { type: "tool_result", tool_use_id: "t2", content: "boom", is_error: true }] },
      { role: "user", content: [
        { type: "text", text: "look" },
        { type: "image", source: { type: "base64", media_type: "image/jpeg", data: "QUJD" } }] },
    ],
  });
  expect(messages).toEqual([
    { role: "system", content: "You are terse.\nBe kind." },
    { role: "user", content: "weather in Rome?" },
    { role: "assistant", content: "Checking.", tool_calls: [
      { id: "t1", type: "function", function: { name: "get_weather", arguments: '{"city":"Rome"}' } }] },
    // tool results first: they answer the assistant turn before the new user text
    { role: "tool", tool_call_id: "t1", content: "sunny" },
    { role: "tool", tool_call_id: "t2", content: "Error: boom" },
    { role: "user", content: "and Milan" },
    { role: "user", content: [{ type: "text", text: "look" }, { type: "image_url", image_url: { url: "data:image/jpeg;base64,QUJD" } }] },
  ]);
  expect(params.max_tokens).toBe(MAX_OUTPUT_TOKENS);
  expect(params.temperature).toBe(0.2);
  expect(params.stop).toEqual(["END"]);
  expect(params.tools.map((t: any) => t.function.name)).toEqual(["get_weather"]); // the server tool is dropped
  expect(params.tool_choice).toBe("required");
});

it("builds an Anthropic message from a completion", () => {
  const completion = { model: "m1", usage: { prompt_tokens: 7, completion_tokens: 3 }, choices: [{
    finish_reason: "stop", // some providers end a tool turn with "stop"
    message: { role: "assistant", content: "Let me check.", tool_calls: [
      { id: "c1", type: "function", function: { name: "get_weather", arguments: '{"city":"Rome"}' } },
      { id: "c2", type: "function", function: { name: "get_weather", arguments: "{not json" } }] } }] };
  const out = AnthropicMessages.fromCompletion(completion, { model: "claude-x" });
  expect([out.type, out.role, out.model]).toEqual(["message", "assistant", "m1"]);
  expect(out.content).toEqual([
    { type: "text", text: "Let me check." },
    { type: "tool_use", id: "c1", name: "get_weather", input: { city: "Rome" } },
    { type: "tool_use", id: "c2", name: "get_weather", input: {} }]);
  expect(out.stop_reason).toBe("tool_use");
  expect(out.usage).toEqual({ input_tokens: 7, output_tokens: 3 });
  const cut = AnthropicMessages.fromCompletion({ choices: [{ message: { content: "hi" }, finish_reason: "length" }] }, {});
  expect(cut.stop_reason).toBe("max_tokens");
});

it("streams text then a tool call as Anthropic events", () => {
  const events = run(AnthropicMessages.stream({ model: "claude-x", messages: [] }), [
    chunk({ role: "assistant" }),
    chunk({ content: "Let me " }),
    chunk({ content: "check." }),
    chunk(toolDelta(0, "c1", "get_weather", "")),
    chunk(toolDelta(0, null, null, '{"city":')),
    chunk(toolDelta(0, null, null, '"Rome"}'), "tool_calls"),
    { choices: [], usage: { prompt_tokens: 11, completion_tokens: 5 } },
  ]);
  expect(events.map((e) => e[0])).toEqual([
    "message_start", "ping", "content_block_start", "content_block_delta", "content_block_delta",
    "content_block_stop", "content_block_start", "content_block_delta", "content_block_delta",
    "content_block_stop", "message_delta", "message_stop"]);
  expect(events.every((e) => e[1].type === e[0])).toBe(true);
  expect(events[0][1].message.model).toBe("m1");
  expect(events[2][1]).toEqual({ type: "content_block_start", index: 0, content_block: { type: "text", text: "" } });
  expect(events[6][1].content_block).toEqual({ type: "tool_use", id: "c1", name: "get_weather", input: {} });
  const args = events.filter((e) => e[1].delta?.type === "input_json_delta").map((e) => e[1].delta.partial_json).join("");
  expect(JSON.parse(args)).toEqual({ city: "Rome" });
  expect(events[events.length - 2][1].delta.stop_reason).toBe("tool_use");
  expect(events[events.length - 2][1].usage).toEqual({ output_tokens: 5, input_tokens: 11 });
});

it("tells tool calls apart without a usable index", () => {
  // Gemini reuses index 0 for every call; others omit the index; a name can arrive late
  const events = run(AnthropicMessages.stream({}), [
    chunk(toolDelta(0, "a", "one", '{"x":1}')),
    chunk(toolDelta(0, "b", "two", '{"y":2}')),
    chunk(toolDelta(null, "c", null, '{"z"')),
    chunk(toolDelta(null, null, "three", ":3}"), "stop"),
  ]);
  const starts = events.filter((e) => e[0] === "content_block_start").map((e) => e[1].content_block);
  expect(starts.map((b) => [b.id, b.name])).toEqual([["a", "one"], ["b", "two"], ["c", "three"]]);
  const byBlock: Record<number, string> = {};
  for (const e of events) if (e[0] === "content_block_delta") byBlock[e[1].index] = (byBlock[e[1].index] ?? "") + e[1].delta.partial_json;
  expect(Object.keys(byBlock).sort().map((k) => JSON.parse(byBlock[Number(k)]))).toEqual([{ x: 1 }, { y: 2 }, { z: 3 }]);
  expect(events.filter((e) => e[0] === "content_block_stop").length).toBe(3);
});

it("keeps an empty stream a valid message", () => {
  const events = run(AnthropicMessages.stream({ model: "claude-x" }), []);
  expect(events.map((e) => e[0])).toEqual(["message_start", "ping", "message_delta", "message_stop"]);
  expect(events[2][1].delta.stop_reason).toBe("end_turn");
});

it("shapes Anthropic errors and estimates tokens", () => {
  expect(AnthropicMessages.error(503, "x")).toEqual([529, { type: "error", error: { type: "overloaded_error", message: "x" } }]);
  expect(AnthropicMessages.error(400, "x")[1].error.type).toBe("invalid_request_error");
  expect(AnthropicMessages.error(502, "x")[1].error.type).toBe("api_error");
  expect(estimateTokens("a".repeat(400))).toBe(100);
  const image = { type: "image", source: { type: "base64", data: "A".repeat(100000) } };
  expect(estimateTokens([{ role: "user", content: [image] }])).toBeLessThan(1100); // base64 is not counted as text
  expect(AnthropicMessages.countTokens({ messages: [{ role: "user", content: "a".repeat(36) }] })).toEqual({ input_tokens: 10 });
  expect(() => AnthropicMessages.toChat({ messages: "nope" })).toThrow();
});

// -- Responses ------------------------------------------------------------------

it("turns a Responses request into chat messages", () => {
  const [messages, params] = OpenAIResponses.toChat({
    model: "gpt-5-codex", instructions: "Be terse.", max_output_tokens: 500,
    tools: [{ type: "function", name: "shell", description: "Run", parameters: { type: "object" } }, { type: "web_search" }],
    tool_choice: { type: "function", name: "shell" },
    text: { format: { type: "json_schema", name: "out", schema: { type: "object" }, strict: true } },
    input: [
      { type: "message", role: "developer", content: [{ type: "input_text", text: "rules" }] },
      { role: "user", content: [{ type: "input_text", text: "list files" }, { type: "input_image", image_url: "https://x/y.png" }] },
      { type: "reasoning", summary: [] },
      { type: "message", role: "assistant", content: [{ type: "output_text", text: "Running." }] },
      { type: "function_call", call_id: "c1", name: "shell", arguments: '{"cmd":"ls"}' },
      { type: "function_call", call_id: "c2", name: "shell", arguments: '{"cmd":"pwd"}' },
      { type: "function_call_output", call_id: "c1", output: "a.txt" },
      { type: "function_call_output", call_id: "c2", output: [{ type: "input_text", text: "/tmp" }] },
    ],
  });
  expect(messages).toEqual([
    { role: "system", content: "Be terse." },
    { role: "system", content: "rules" },
    { role: "user", content: [{ type: "text", text: "list files" }, { type: "image_url", image_url: { url: "https://x/y.png" } }] },
    { role: "assistant", content: "Running.", tool_calls: [
      { id: "c1", type: "function", function: { name: "shell", arguments: '{"cmd":"ls"}' } },
      { id: "c2", type: "function", function: { name: "shell", arguments: '{"cmd":"pwd"}' } }] },
    { role: "tool", tool_call_id: "c1", content: "a.txt" },
    { role: "tool", tool_call_id: "c2", content: "/tmp" },
  ]);
  expect(params.max_tokens).toBe(500);
  expect(params.tools.map((t: any) => t.function.name)).toEqual(["shell"]);
  expect(params.tool_choice).toEqual({ type: "function", function: { name: "shell" } });
  expect(params.response_format).toEqual({ type: "json_schema", json_schema: { name: "out", schema: { type: "object" }, strict: true } });
  expect(OpenAIResponses.toChat({ input: "hi" })[0]).toEqual([{ role: "user", content: "hi" }]);
  expect(() => OpenAIResponses.toChat({ input: "hi", previous_response_id: "resp_1" })).toThrow(/previous_response_id/);
  expect(() => OpenAIResponses.toChat({})).toThrow();
});

it("builds a Responses object from a completion", () => {
  const completion = { model: "m1", usage: { prompt_tokens: 7, completion_tokens: 3 }, choices: [{
    finish_reason: "tool_calls", message: { content: "ok", tool_calls: [
      { id: "c1", type: "function", function: { name: "shell", arguments: '{"cmd":"ls"}' } }] } }] };
  const out = OpenAIResponses.fromCompletion(completion, { model: "gpt-x", instructions: "i" });
  expect([out.object, out.status, out.model]).toEqual(["response", "completed", "m1"]);
  expect(out.output[0].content).toEqual([{ type: "output_text", text: "ok", annotations: [] }]);
  const call = out.output[1];
  expect([call.type, call.call_id, call.name, call.arguments]).toEqual(["function_call", "c1", "shell", '{"cmd":"ls"}']);
  expect(out.usage).toEqual({ input_tokens: 7, output_tokens: 3, total_tokens: 10 });
  const cut = OpenAIResponses.fromCompletion({ choices: [{ message: { content: "x" }, finish_reason: "length" }] }, {});
  expect(cut.status).toBe("incomplete");
  expect(cut.incomplete_details).toEqual({ reason: "max_output_tokens" });
});

it("streams Responses events in order", () => {
  const events = run(OpenAIResponses.stream({ model: "gpt-x" }), [
    chunk({ content: "Run" }),
    chunk({ content: "ning." }),
    chunk(toolDelta(0, "c1", "shell", '{"cmd":')),
    chunk(toolDelta(0, null, null, '"ls"}'), "tool_calls"),
  ]);
  expect(events.map((e) => e[0])).toEqual([
    "response.created", "response.in_progress", "response.output_item.added", "response.content_part.added",
    "response.output_text.delta", "response.output_text.delta", "response.output_text.done",
    "response.content_part.done", "response.output_item.done", "response.output_item.added",
    "response.function_call_arguments.delta", "response.function_call_arguments.delta",
    "response.function_call_arguments.done", "response.output_item.done", "response.completed"]);
  expect(events.map((e) => e[1].sequence_number)).toEqual(events.map((_, i) => i));
  expect(events.every((e) => e[1].type === e[0])).toBe(true);
  const final = events[events.length - 1][1].response;
  expect(final.status).toBe("completed");
  expect(final.id).toBe(events[0][1].response.id);
  expect(final.output[0].content[0].text).toBe("Running.");
  expect([final.output[1].call_id, final.output[1].arguments]).toEqual(["c1", '{"cmd":"ls"}']);
  expect(events[6][1].text).toBe("Running.");
  expect(events[12][1].arguments).toBe('{"cmd":"ls"}');
  const failed = OpenAIResponses.stream({}).error(502, "upstream died");
  expect(failed[0][0]).toBe("response.failed");
  expect(failed[0][1].response.error.message).toBe("upstream died");
});

// -- served over HTTP -----------------------------------------------------------

const servers: Server[] = [];
afterEach(async () => {
  vi.unstubAllGlobals();
  await Promise.all(servers.splice(0).map((s) => new Promise((r) => s.close(r))));
});

async function start(llm: FreeLLM): Promise<number> {
  const s = createServer(llm);
  servers.push(s);
  await new Promise<void>((r) => s.listen(0, "127.0.0.1", () => r()));
  return (s.address() as any).port;
}

function post(port: number, path: string, body: any) {
  return new Promise<{ status: number; headers: any; text: string }>((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = request(
      { host: "127.0.0.1", port, method: "POST", path, headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } },
      (res) => {
        let text = "";
        res.on("data", (c) => (text += c));
        res.on("end", () => resolve({ status: res.statusCode!, headers: res.headers, text }));
      },
    );
    req.on("error", reject);
    req.end(data);
  });
}

const parseSSE = (text: string): SSEEvent[] =>
  text.trim().split("\n\n").map((b) => [b.split("\n")[0].slice(7), JSON.parse(b.split("\n")[1].slice(6))]);
const hi = [{ role: "user", content: "hi" }];

it("routes agent model ids on /v1/messages to tool-capable models", async () => {
  const calls = mockFetch(() => new Response(OK("ciao", "free-m"), { status: 200 }));
  const provider = new OpenRouter("k", { discover: false });
  const port = await start(new FreeLLM([provider]));
  const r = await post(port, "/v1/messages?beta=true", { model: "claude-sonnet-4-5", max_tokens: 32000, tools: [WEATHER], messages: hi });
  const out = JSON.parse(r.text);
  expect(r.status).toBe(200);
  expect(out.type).toBe("message");
  expect(out.content).toEqual([{ type: "text", text: "ciao" }]);
  expect(r.headers["x-freellm-provider"]).toBe("openrouter");
  const sent = calls[calls.length - 1].body;
  // the agent's model id never goes upstream: a tool-capable free model serves it
  expect(provider.resolveModels("tools")).toContain(sent.model);
  expect(sent.max_tokens).toBe(MAX_OUTPUT_TOKENS);
  expect(sent.tools[0].function.name).toBe("get_weather");

  const c = await post(port, "/v1/messages/count_tokens", { messages: [{ role: "user", content: "a".repeat(76) }] });
  expect(c.status).toBe(200);
  expect(JSON.parse(c.text)).toEqual({ input_tokens: 20 });
});

it("streams Anthropic events on /v1/messages", async () => {
  const body =
    'data: {"model":"free-m","choices":[{"index":0,"delta":{"role":"assistant"}}]}\n\n' +
    'data: {"model":"free-m","choices":[{"index":0,"delta":{"content":"Hel"}}]}\n\n' +
    'data: {"model":"free-m","choices":[{"index":0,"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n' +
    "data: [DONE]\n\n";
  mockFetch(() => new Response(body, { status: 200 }));
  const port = await start(new FreeLLM([new OpenRouter("k", { discover: false })]));
  const r = await post(port, "/v1/messages", { model: "claude-haiku-4-5", max_tokens: 100, stream: true, messages: hi });
  expect(r.status).toBe(200);
  expect(r.headers["content-type"]).toBe("text/event-stream");
  const events = parseSSE(r.text);
  expect(events.slice(0, 3).map((e) => e[0])).toEqual(["message_start", "ping", "content_block_start"]);
  expect(events[events.length - 1][0]).toBe("message_stop");
  expect(r.text).not.toContain("[DONE]");
  expect(events.filter((e) => e[0] === "content_block_delta").map((e) => e[1].delta.text).join("")).toBe("Hello");
  expect(events[0][1].message.model).toBe("free-m");
});

it("reports errors in each protocol's own shape", async () => {
  mockFetch(() => new Response("slow down", { status: 429 }));
  const port = await start(new FreeLLM([new OpenRouter("k", { discover: false })]));
  let r = await post(port, "/v1/messages", { model: "claude-x", messages: hi });
  expect(r.status).toBe(529);
  expect(JSON.parse(r.text).error.type).toBe("overloaded_error");
  r = await post(port, "/v1/messages", { model: "claude-x" });
  expect(r.status).toBe(400);
  expect(JSON.parse(r.text).type).toBe("error");
  r = await post(port, "/v1/responses", { model: "gpt-x", input: "hi" });
  expect(r.status).toBe(503);
  expect(JSON.parse(r.text).error.type).toBe("server_error");
  r = await post(port, "/v1/responses", { model: "gpt-x", input: "hi", previous_response_id: "r" });
  expect(r.status).toBe(400);
  expect(JSON.parse(r.text).error.message).toContain("previous_response_id");
});

it("serves /v1/responses as JSON and as a stream", async () => {
  const body = 'data: {"model":"free-m","choices":[{"index":0,"delta":{"content":"4"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n';
  let n = 0;
  const calls = mockFetch(() => (n++ === 0 ? new Response(OK("4", "free-m"), { status: 200 }) : new Response(body, { status: 200 })));
  const port = await start(new FreeLLM([new OpenRouter("k", { discover: false })]));
  let r = await post(port, "/v1/responses", { model: "gpt-5-codex", instructions: "terse", input: "2+2?" });
  const out = JSON.parse(r.text);
  expect(r.status).toBe(200);
  expect(out.object).toBe("response");
  expect(out.output[0].content[0].text).toBe("4");
  expect(calls[calls.length - 1].body.messages).toEqual([{ role: "system", content: "terse" }, { role: "user", content: "2+2?" }]);
  r = await post(port, "/v1/responses", { model: "gpt-5-codex", input: "2+2?", stream: true });
  const events = parseSSE(r.text);
  expect(r.status).toBe(200);
  expect(events[0][0]).toBe("response.created");
  expect(events[events.length - 1][0]).toBe("response.completed");
  expect(events[events.length - 1][1].response.output[0].content[0].text).toBe("4");
});
