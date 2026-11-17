"""Anthropic Messages / OpenAI Responses translation (`protocols.py`) and the
`freelm serve` routes built on it."""
import json
import threading
import urllib.error
import urllib.request

import httpx
import pytest
import respx

from conftest import ok_payload
from freelm import AsyncFreeLLM, OpenRouter
from freelm.protocols import MAX_OUTPUT_TOKENS, AnthropicMessages, OpenAIResponses, estimate_tokens
from freelm.server import make_server

OR_URL = "https://openrouter.ai/api/v1/chat/completions"
WEATHER = {"name": "get_weather", "description": "Weather", "input_schema": {"type": "object", "properties": {}}}


def chunk(delta, finish=None, **extra):
    return {"model": "m1", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **extra}


def tool_delta(index=None, id=None, name=None, args=None):
    tc = {"function": {}}
    if index is not None:
        tc["index"] = index
    if id:
        tc["id"] = id
    if name:
        tc["function"]["name"] = name
    if args is not None:
        tc["function"]["arguments"] = args
    return {"tool_calls": [tc]}


def run(enc, chunks):
    events = []
    for c in chunks:
        events += enc.feed(c)
    return events + enc.finish()


# -- Anthropic ------------------------------------------------------------------

def test_anthropic_request_becomes_chat_messages():
    messages, params = AnthropicMessages.to_chat({
        "model": "claude-sonnet-4-5", "max_tokens": 64000, "temperature": 0.2, "stop_sequences": ["END"],
        "system": [{"type": "text", "text": "You are terse."}, {"type": "text", "text": "Be kind."}],
        "tools": [WEATHER, {"type": "web_search_20250305", "name": "web_search"}],
        "tool_choice": {"type": "any"},
        "messages": [
            {"role": "user", "content": "weather in Rome?"},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "hmm", "signature": "s"},
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "t1", "name": "get_weather", "input": {"city": "Rome"}}]},
            {"role": "user", "content": [
                {"type": "text", "text": "and Milan"},
                {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "sunny"}]},
                {"type": "tool_result", "tool_use_id": "t2", "content": "boom", "is_error": True}]},
            {"role": "user", "content": [
                {"type": "text", "text": "look"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}}]},
        ],
    })
    assert messages == [
        {"role": "system", "content": "You are terse.\nBe kind."},
        {"role": "user", "content": "weather in Rome?"},
        {"role": "assistant", "content": "Checking.", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city": "Rome"}'}}]},
        # tool results first: they answer the assistant turn before the new user text
        {"role": "tool", "tool_call_id": "t1", "content": "sunny"},
        {"role": "tool", "tool_call_id": "t2", "content": "Error: boom"},
        {"role": "user", "content": "and Milan"},
        {"role": "user", "content": [{"type": "text", "text": "look"},
                                     {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}]},
    ]
    assert params["max_tokens"] == MAX_OUTPUT_TOKENS and params["temperature"] == 0.2 and params["stop"] == ["END"]
    assert [t["function"]["name"] for t in params["tools"]] == ["get_weather"]  # the server tool is dropped
    assert params["tool_choice"] == "required"


def test_anthropic_response_from_completion():
    completion = {"model": "m1", "usage": {"prompt_tokens": 7, "completion_tokens": 3}, "choices": [{
        "finish_reason": "stop",  # some providers end a tool turn with "stop"
        "message": {"role": "assistant", "content": "Let me check.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city":"Rome"}'}},
            {"id": "c2", "type": "function", "function": {"name": "get_weather", "arguments": "{not json"}}]}}]}
    out = AnthropicMessages.from_completion(completion, {"model": "claude-x"})
    assert out["type"] == "message" and out["role"] == "assistant" and out["model"] == "m1"
    assert out["content"] == [
        {"type": "text", "text": "Let me check."},
        {"type": "tool_use", "id": "c1", "name": "get_weather", "input": {"city": "Rome"}},
        {"type": "tool_use", "id": "c2", "name": "get_weather", "input": {}}]
    assert out["stop_reason"] == "tool_use" and out["usage"] == {"input_tokens": 7, "output_tokens": 3}
    cut = AnthropicMessages.from_completion(ok_payload("hi") | {"choices": [
        {"message": {"content": "hi"}, "finish_reason": "length"}]}, {})
    assert cut["stop_reason"] == "max_tokens"


def test_anthropic_stream_text_then_tool_call():
    events = run(AnthropicMessages.stream({"model": "claude-x", "messages": []}), [
        chunk({"role": "assistant"}),
        chunk({"content": "Let me "}),
        chunk({"content": "check."}),
        chunk(tool_delta(0, "c1", "get_weather", "")),
        chunk(tool_delta(0, args='{"city":')),
        chunk(tool_delta(0, args='"Rome"}'), finish="tool_calls"),
        {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 5}},
    ])
    assert [e[0] for e in events] == [
        "message_start", "ping", "content_block_start", "content_block_delta", "content_block_delta",
        "content_block_stop", "content_block_start", "content_block_delta", "content_block_delta",
        "content_block_stop", "message_delta", "message_stop"]
    assert all(e[1]["type"] == e[0] for e in events)
    assert events[0][1]["message"]["model"] == "m1"
    assert events[2][1] == {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
    assert events[6][1]["content_block"] == {"type": "tool_use", "id": "c1", "name": "get_weather", "input": {}}
    args = "".join(e[1]["delta"]["partial_json"] for e in events if e[1].get("delta", {}).get("type") == "input_json_delta")
    assert json.loads(args) == {"city": "Rome"}
    assert events[-2][1]["delta"]["stop_reason"] == "tool_use"
    assert events[-2][1]["usage"] == {"output_tokens": 5, "input_tokens": 11}


def test_stream_tells_tool_calls_apart_without_a_usable_index():
    # Gemini reuses index 0 for every call; others omit the index; a name can arrive late
    events = run(AnthropicMessages.stream({}), [
        chunk(tool_delta(0, "a", "one", '{"x":1}')),
        chunk(tool_delta(0, "b", "two", '{"y":2}')),
        chunk(tool_delta(None, "c", None, '{"z"')),
        chunk(tool_delta(None, None, "three", ":3}"), finish="stop"),
    ])
    starts = [e[1]["content_block"] for e in events if e[0] == "content_block_start"]
    assert [(b["id"], b["name"]) for b in starts] == [("a", "one"), ("b", "two"), ("c", "three")]
    by_block = {}
    for e in events:
        if e[0] == "content_block_delta":
            by_block[e[1]["index"]] = by_block.get(e[1]["index"], "") + e[1]["delta"]["partial_json"]
    assert [json.loads(v) for _, v in sorted(by_block.items())] == [{"x": 1}, {"y": 2}, {"z": 3}]
    assert sum(e[0] == "content_block_stop" for e in events) == 3


def test_empty_stream_is_still_a_valid_message():
    events = run(AnthropicMessages.stream({"model": "claude-x"}), [])
    assert [e[0] for e in events] == ["message_start", "ping", "message_delta", "message_stop"]
    assert events[2][1]["delta"]["stop_reason"] == "end_turn"


def test_anthropic_errors_and_token_estimate():
    assert AnthropicMessages.error(503, "x") == (529, {"type": "error", "error": {"type": "overloaded_error", "message": "x"}})
    assert AnthropicMessages.error(400, "x")[1]["error"]["type"] == "invalid_request_error"
    assert AnthropicMessages.error(502, "x")[1]["error"]["type"] == "api_error"
    assert estimate_tokens("a" * 400) == 100
    image = {"type": "image", "source": {"type": "base64", "data": "A" * 100000}}
    assert estimate_tokens([{"role": "user", "content": [image]}]) < 1100  # base64 is not counted as text
    assert AnthropicMessages.count_tokens({"messages": [{"role": "user", "content": "a" * 36}]}) == {"input_tokens": 10}
    with pytest.raises(ValueError):
        AnthropicMessages.to_chat({"messages": "nope"})


# -- Responses ------------------------------------------------------------------

def test_responses_request_becomes_chat_messages():
    messages, params = OpenAIResponses.to_chat({
        "model": "gpt-5-codex", "instructions": "Be terse.", "max_output_tokens": 500,
        "tools": [{"type": "function", "name": "shell", "description": "Run", "parameters": {"type": "object"}},
                  {"type": "web_search"}],
        "tool_choice": {"type": "function", "name": "shell"},
        "text": {"format": {"type": "json_schema", "name": "out", "schema": {"type": "object"}, "strict": True}},
        "input": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "rules"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "list files"},
                                         {"type": "input_image", "image_url": "https://x/y.png"}]},
            {"type": "reasoning", "summary": []},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Running."}]},
            {"type": "function_call", "call_id": "c1", "name": "shell", "arguments": '{"cmd":"ls"}'},
            {"type": "function_call", "call_id": "c2", "name": "shell", "arguments": '{"cmd":"pwd"}'},
            {"type": "function_call_output", "call_id": "c1", "output": "a.txt"},
            {"type": "function_call_output", "call_id": "c2", "output": [{"type": "input_text", "text": "/tmp"}]},
        ],
    })
    assert messages == [
        {"role": "system", "content": "Be terse."},
        {"role": "system", "content": "rules"},
        {"role": "user", "content": [{"type": "text", "text": "list files"},
                                     {"type": "image_url", "image_url": {"url": "https://x/y.png"}}]},
        {"role": "assistant", "content": "Running.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "shell", "arguments": '{"cmd":"ls"}'}},
            {"id": "c2", "type": "function", "function": {"name": "shell", "arguments": '{"cmd":"pwd"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "a.txt"},
        {"role": "tool", "tool_call_id": "c2", "content": "/tmp"},
    ]
    assert params["max_tokens"] == 500
    assert [t["function"]["name"] for t in params["tools"]] == ["shell"]
    assert params["tool_choice"] == {"type": "function", "function": {"name": "shell"}}
    assert params["response_format"] == {"type": "json_schema", "json_schema": {
        "name": "out", "schema": {"type": "object"}, "strict": True}}
    assert OpenAIResponses.to_chat({"input": "hi"})[0] == [{"role": "user", "content": "hi"}]
    with pytest.raises(ValueError, match="previous_response_id"):
        OpenAIResponses.to_chat({"input": "hi", "previous_response_id": "resp_1"})
    with pytest.raises(ValueError):
        OpenAIResponses.to_chat({})


def test_responses_object_from_completion():
    completion = {"model": "m1", "usage": {"prompt_tokens": 7, "completion_tokens": 3}, "choices": [{
        "finish_reason": "tool_calls", "message": {"content": "ok", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "shell", "arguments": '{"cmd":"ls"}'}}]}}]}
    out = OpenAIResponses.from_completion(completion, {"model": "gpt-x", "instructions": "i"})
    assert out["object"] == "response" and out["status"] == "completed" and out["model"] == "m1"
    assert out["output"][0]["content"] == [{"type": "output_text", "text": "ok", "annotations": []}]
    call = out["output"][1]
    assert (call["type"], call["call_id"], call["name"], call["arguments"]) == ("function_call", "c1", "shell", '{"cmd":"ls"}')
    assert out["usage"] == {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
    cut = OpenAIResponses.from_completion({"choices": [{"message": {"content": "x"}, "finish_reason": "length"}]}, {})
    assert cut["status"] == "incomplete" and cut["incomplete_details"] == {"reason": "max_output_tokens"}


def test_responses_stream_events():
    enc = OpenAIResponses.stream({"model": "gpt-x"})
    events = run(enc, [
        chunk({"content": "Run"}),
        chunk({"content": "ning."}),
        chunk(tool_delta(0, "c1", "shell", '{"cmd":')),
        chunk(tool_delta(0, args='"ls"}'), finish="tool_calls"),
    ])
    assert [e[0] for e in events] == [
        "response.created", "response.in_progress", "response.output_item.added", "response.content_part.added",
        "response.output_text.delta", "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.output_item.added",
        "response.function_call_arguments.delta", "response.function_call_arguments.delta",
        "response.function_call_arguments.done", "response.output_item.done", "response.completed"]
    assert [e[1]["sequence_number"] for e in events] == list(range(len(events)))
    assert all(e[1]["type"] == e[0] for e in events)
    final = events[-1][1]["response"]
    assert final["status"] == "completed" and final["id"] == events[0][1]["response"]["id"]
    assert final["output"][0]["content"][0]["text"] == "Running."
    assert (final["output"][1]["call_id"], final["output"][1]["arguments"]) == ("c1", '{"cmd":"ls"}')
    assert events[6][1]["text"] == "Running." and events[12][1]["arguments"] == '{"cmd":"ls"}'
    failed = OpenAIResponses.stream({}).error(502, "upstream died")
    assert failed[0][0] == "response.failed" and failed[0][1]["response"]["error"]["message"] == "upstream died"


# -- served over HTTP -----------------------------------------------------------

@pytest.fixture
def server():
    started = []

    def start(providers, **kw):
        srv = make_server(AsyncFreeLLM(providers), port=0, **kw)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    yield start
    for srv in started:
        srv.shutdown()
        srv.server_close()


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def _sse(text):
    return [(block.split("\n")[0][7:], json.loads(block.split("\n")[1][6:])) for block in text.strip().split("\n\n")]


@respx.mock
def test_messages_endpoint_routes_agent_models_to_tool_capable_ones(server):
    route = respx.post(OR_URL).mock(return_value=httpx.Response(200, json=ok_payload("ciao", model="free-m")))
    provider = OpenRouter("k", discover=False)
    base = server([provider])
    status, headers, text = _post(base + "/v1/messages?beta=true", {
        "model": "claude-sonnet-4-5", "max_tokens": 32000, "tools": [WEATHER],
        "messages": [{"role": "user", "content": "hi"}]})
    out = json.loads(text)
    assert status == 200 and out["type"] == "message" and out["content"] == [{"type": "text", "text": "ciao"}]
    assert headers["X-FreeLLM-Provider"] == "openrouter"
    sent = json.loads(route.calls.last.request.content)
    # the agent's model id never goes upstream: a tool-capable free model serves it
    assert sent["model"] in provider.resolve_models("tools") and sent["model"] != "claude-sonnet-4-5"
    assert sent["max_tokens"] == MAX_OUTPUT_TOKENS and sent["tools"][0]["function"]["name"] == "get_weather"

    status, _, text = _post(base + "/v1/messages/count_tokens", {"messages": [{"role": "user", "content": "a" * 76}]})
    assert status == 200 and json.loads(text) == {"input_tokens": 20}


@respx.mock
def test_messages_endpoint_streams_anthropic_events(server):
    sse = (
        'data: {"model":"free-m","choices":[{"index":0,"delta":{"role":"assistant"}}]}\n\n'
        'data: {"model":"free-m","choices":[{"index":0,"delta":{"content":"Hel"}}]}\n\n'
        'data: {"model":"free-m","choices":[{"index":0,"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(OR_URL).mock(return_value=httpx.Response(200, text=sse))
    base = server([OpenRouter("k", discover=False)])
    status, headers, text = _post(base + "/v1/messages", {
        "model": "claude-haiku-4-5", "max_tokens": 100, "stream": True, "messages": [{"role": "user", "content": "hi"}]})
    assert status == 200 and headers["Content-Type"] == "text/event-stream"
    events = _sse(text)
    assert [e[0] for e in events][:3] == ["message_start", "ping", "content_block_start"]
    assert events[-1][0] == "message_stop" and "[DONE]" not in text
    assert "".join(e[1]["delta"]["text"] for e in events if e[0] == "content_block_delta") == "Hello"
    assert events[0][1]["message"]["model"] == "free-m"


@respx.mock
def test_translated_endpoints_report_errors_in_their_own_shape(server):
    respx.post(OR_URL).mock(return_value=httpx.Response(429, text="slow down"))
    base = server([OpenRouter("k", discover=False)])
    status, _, text = _post(base + "/v1/messages", {"model": "claude-x", "messages": [{"role": "user", "content": "hi"}]})
    assert status == 529 and json.loads(text)["error"]["type"] == "overloaded_error"
    status, _, text = _post(base + "/v1/messages", {"model": "claude-x"})
    assert status == 400 and json.loads(text)["type"] == "error"
    status, _, text = _post(base + "/v1/responses", {"model": "gpt-x", "input": "hi"})
    assert status == 503 and json.loads(text)["error"]["type"] == "server_error"
    status, _, text = _post(base + "/v1/responses", {"model": "gpt-x", "input": "hi", "previous_response_id": "r"})
    assert status == 400 and "previous_response_id" in json.loads(text)["error"]["message"]


@respx.mock
def test_responses_endpoint_json_and_stream(server):
    sse = (
        'data: {"model":"free-m","choices":[{"index":0,"delta":{"content":"4"},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    route = respx.post(OR_URL).mock(side_effect=[
        httpx.Response(200, json=ok_payload("4", model="free-m")), httpx.Response(200, text=sse)])
    base = server([OpenRouter("k", discover=False)])
    status, _, text = _post(base + "/v1/responses", {"model": "gpt-5-codex", "instructions": "terse", "input": "2+2?"})
    out = json.loads(text)
    assert status == 200 and out["object"] == "response" and out["output"][0]["content"][0]["text"] == "4"
    assert json.loads(route.calls.last.request.content)["messages"] == [
        {"role": "system", "content": "terse"}, {"role": "user", "content": "2+2?"}]
    status, _, text = _post(base + "/v1/responses", {"model": "gpt-5-codex", "input": "2+2?", "stream": True})
    events = _sse(text)
    assert status == 200 and events[0][0] == "response.created" and events[-1][0] == "response.completed"
    assert events[-1][1]["response"]["output"][0]["content"][0]["text"] == "4"
