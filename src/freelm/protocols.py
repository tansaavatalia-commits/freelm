"""Wire-protocol translation for ``freelm serve``: Anthropic Messages
(``/v1/messages`` — what Claude Code and the Anthropic SDKs speak) and OpenAI
Responses (``/v1/responses`` — what Codex CLI speaks), both mapped onto the
chat-completions shape the router works in.

Pure functions and small state machines, no I/O: a request body becomes
``(messages, params)`` for ``chat()``; a ``chat.completion`` dict or a stream of
``chat.completion.chunk`` dicts becomes the protocol's response / SSE events.

Not translated (dropped, never an error): Anthropic server tools and thinking
blocks, Responses built-in / custom tools and reasoning items.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Coding agents ask for far more output than free tiers allow (Claude Code:
# 32K+), and an oversized max_tokens is a 400 on most of them.
MAX_OUTPUT_TOKENS = 8192

SSEEvent = Tuple[str, Dict[str, Any]]


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _text_of(content: Any) -> str:
    """Plain text of a content value (a string, or a list of text-ish parts)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    out: List[str] = []
    for p in content:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            if isinstance(p.get("text"), str):
                out.append(p["text"])
            elif p.get("type") in ("image", "input_image", "image_url"):
                out.append("[image]")
    return "\n".join(s for s in out if s)


def _user_content(parts: List[Dict[str, Any]]) -> Any:
    """Chat content for a user turn: a plain string unless an image needs parts
    (several free providers reject list content)."""
    if all(p.get("type") == "text" for p in parts):
        return "\n\n".join(p["text"] for p in parts)
    return parts


def _clamp_tokens(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(min(value, MAX_OUTPUT_TOKENS))


def _arguments(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {})


def _parse_arguments(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def has_images(messages: List[Dict[str, Any]]) -> bool:
    return any(
        isinstance(m.get("content"), list)
        and any(isinstance(p, dict) and p.get("type") == "image_url" for p in m["content"])
        for m in messages
    )


def estimate_tokens(value: Any) -> int:
    """Rough token count (~4 characters each); base64 payloads count as a flat
    cost per image. Good enough for an agent's context meter."""
    chars = 0
    images = 0
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            chars += len(v)
        elif isinstance(v, list):
            stack.extend(v)
        elif isinstance(v, dict):
            if v.get("type") in ("image", "input_image", "image_url"):
                images += 1
                continue
            for k, x in v.items():
                chars += len(k) if isinstance(x, (dict, list)) else 0
                stack.append(x)
        elif v is not None:
            chars += len(str(v))
    return max(1, chars // 4 + images * 1000)


def _first_choice(completion: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    choices = completion.get("choices") or []
    c = choices[0] if choices and isinstance(choices[0], dict) else {}
    msg = c.get("message") if isinstance(c.get("message"), dict) else {}
    return msg, c.get("finish_reason")


def _usage(usage: Any, text_chars: int = 0) -> Tuple[int, int]:
    u = usage if isinstance(usage, dict) else {}
    return int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0) or text_chars // 4


class _Deltas:
    """``chat.completion.chunk`` dicts -> a flat event list:
    ``("text", s)`` | ``("tool", n, id, name)`` | ``("args", n, s)``.

    Tool calls are keyed by ``index``; providers that omit it or reuse index 0
    for every call (Gemini) are told apart by ``id``. A call whose name arrives
    late is held back until it is known."""

    def __init__(self) -> None:
        self.tools: List[Dict[str, Any]] = []
        self._slot: Dict[Any, int] = {}
        self.text = ""
        self.finish: Optional[str] = None
        self.usage: Optional[Dict[str, Any]] = None
        self.model: Optional[str] = None

    def feed(self, chunk: Dict[str, Any]) -> List[Tuple[Any, ...]]:
        out: List[Tuple[Any, ...]] = []
        self.model = self.model or chunk.get("model")
        if isinstance(chunk.get("usage"), dict):
            self.usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            if choice.get("finish_reason"):
                self.finish = choice["finish_reason"]
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            content = delta.get("content")
            if isinstance(content, list):
                content = _text_of(content)
            if isinstance(content, str) and content:
                self.text += content
                out.append(("text", content))
            for tc in delta.get("tool_calls") or []:
                if isinstance(tc, dict):
                    self._tool(tc, out)
        return out

    def _tool(self, tc: Dict[str, Any], out: List[Tuple[Any, ...]]) -> None:
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        tid, idx = tc.get("id"), tc.get("index")
        key: Any = idx if isinstance(idx, int) else "last"
        n = self._slot.get(key)
        if n is None or (tid and self.tools[n]["id"] and tid != self.tools[n]["id"]):
            n = len(self.tools)
            self.tools.append({"id": tid or "", "name": "", "arguments": "", "started": False, "held": ""})
            self._slot[key] = self._slot["last"] = n
        t = self.tools[n]
        t["id"] = t["id"] or tid or ""
        t["name"] = t["name"] or fn.get("name") or ""
        args = fn.get("arguments")
        if isinstance(args, dict):
            args = json.dumps(args)
        args = args if isinstance(args, str) else ""
        t["arguments"] += args
        if not t["started"]:
            if not t["name"]:
                t["held"] += args
                return
            t["started"] = True
            t["id"] = t["id"] or _id("call")
            out.append(("tool", n, t["id"], t["name"]))
            args, t["held"] = t["held"] + args, ""
        if args:
            out.append(("args", n, args))

    def started_tools(self) -> List[Dict[str, Any]]:
        return [t for t in self.tools if t["started"]]


# -- Anthropic Messages ---------------------------------------------------------

_ANTHROPIC_ERRORS = {400: "invalid_request_error", 401: "authentication_error", 403: "permission_error",
                     404: "not_found_error", 413: "request_too_large", 429: "rate_limit_error",
                     529: "overloaded_error"}


def _stop_reason(finish: Optional[str], tools: bool) -> str:
    if finish == "length":
        return "max_tokens"
    # some providers finish a tool turn with "stop": the agent still has to run it
    return "tool_use" if tools else "end_turn"


class AnthropicMessages:
    """``POST /v1/messages`` <-> chat completions."""

    name = "anthropic"

    @staticmethod
    def to_chat(body: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not isinstance(body.get("messages"), list):
            raise ValueError("body must be an object with a 'messages' list")
        messages: List[Dict[str, Any]] = []
        system = _text_of(body.get("system"))
        if system:
            messages.append({"role": "system", "content": system})
        for m in body["messages"]:
            if not isinstance(m, dict):
                raise ValueError("every message must be an object")
            role = "assistant" if m.get("role") == "assistant" else "user"
            content = m.get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            if not isinstance(blocks, list):
                raise ValueError("message content must be a string or a list of blocks")
            parts: List[Dict[str, Any]] = []
            calls: List[Dict[str, Any]] = []
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                kind = b.get("type")
                if kind == "text" and b.get("text"):
                    parts.append({"type": "text", "text": b["text"]})
                elif kind == "image" and isinstance(b.get("source"), dict):
                    src = b["source"]
                    url = src.get("url") if src.get("type") == "url" else (
                        f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}")
                    parts.append({"type": "image_url", "image_url": {"url": url}})
                elif kind == "tool_use":
                    calls.append({"id": b.get("id") or _id("call"), "type": "function",
                                  "function": {"name": b.get("name") or "", "arguments": _arguments(b.get("input"))}})
                elif kind == "tool_result":
                    text = _text_of(b.get("content"))
                    if b.get("is_error"):
                        text = f"Error: {text}"
                    # tool results answer the previous assistant turn: they go first
                    messages.append({"role": "tool", "tool_call_id": b.get("tool_use_id") or "", "content": text})
            if role == "assistant":
                msg: Dict[str, Any] = {"role": "assistant"}
                text = "\n\n".join(p["text"] for p in parts if p["type"] == "text")
                if text or not calls:
                    msg["content"] = text
                if calls:
                    msg["tool_calls"] = calls
                messages.append(msg)
            elif parts:
                messages.append({"role": "user", "content": _user_content(parts)})

        params: Dict[str, Any] = {}
        mt = _clamp_tokens(body.get("max_tokens"))
        if mt:
            params["max_tokens"] = mt
        for k in ("temperature", "top_p"):
            if isinstance(body.get(k), (int, float)) and not isinstance(body.get(k), bool):
                params[k] = body[k]
        if body.get("stop_sequences"):
            params["stop"] = body["stop_sequences"]
        tools = [
            {"type": "function", "function": {"name": t["name"], "description": t.get("description") or "",
                                              "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}}
            for t in body.get("tools") or []
            # server tools (web_search_20250305, bash_..., ...) carry a versioned type and no schema
            if isinstance(t, dict) and t.get("name") and t.get("type") in (None, "custom")
        ]
        if tools:
            params["tools"] = tools
            tc = body.get("tool_choice")
            kind = tc.get("type") if isinstance(tc, dict) else None
            if kind == "any":
                params["tool_choice"] = "required"
            elif kind == "tool" and tc.get("name"):
                params["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}
            elif kind == "none":
                params["tool_choice"] = "none"
        return messages, params

    @staticmethod
    def from_completion(completion: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        msg, finish = _first_choice(completion)
        text = _text_of(msg.get("content"))
        content: List[Dict[str, Any]] = [{"type": "text", "text": text}] if text else []
        calls = [c for c in msg.get("tool_calls") or [] if isinstance(c, dict)]
        for c in calls:
            fn = c.get("function") if isinstance(c.get("function"), dict) else {}
            content.append({"type": "tool_use", "id": c.get("id") or _id("call"), "name": fn.get("name") or "",
                            "input": _parse_arguments(fn.get("arguments"))})
        tin, tout = _usage(completion.get("usage"), len(text))
        return {
            "id": _id("msg"), "type": "message", "role": "assistant",
            "model": completion.get("model") or body.get("model"),
            "content": content, "stop_reason": _stop_reason(finish, bool(calls)), "stop_sequence": None,
            "usage": {"input_tokens": tin, "output_tokens": tout},
        }

    @staticmethod
    def count_tokens(body: Dict[str, Any]) -> Dict[str, Any]:
        return {"input_tokens": estimate_tokens([body.get("system"), body.get("messages"), body.get("tools")])}

    @staticmethod
    def error(status: int, message: str) -> Tuple[int, Dict[str, Any]]:
        # 529 (overloaded) is what Anthropic clients back off and retry on
        status = 529 if status == 503 else status
        return status, {"type": "error", "error": {"type": _ANTHROPIC_ERRORS.get(status, "api_error"),
                                                   "message": message}}

    @staticmethod
    def stream(body: Dict[str, Any]) -> "AnthropicStream":
        return AnthropicStream(body)


class AnthropicStream:
    """Chat chunks -> Anthropic SSE events (``message_start`` ... ``message_stop``)."""

    def __init__(self, body: Dict[str, Any]) -> None:
        self.body = body
        self.d = _Deltas()
        self.started = False
        self.blocks = 0
        self.text_block: Optional[int] = None
        self.tool_block: Dict[int, int] = {}
        self.open: List[int] = []

    def _start(self, out: List[SSEEvent]) -> None:
        if self.started:
            return
        self.started = True
        tin = AnthropicMessages.count_tokens(self.body)["input_tokens"]
        out.append(("message_start", {"type": "message_start", "message": {
            "id": _id("msg"), "type": "message", "role": "assistant",
            "model": self.d.model or self.body.get("model"), "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": tin, "output_tokens": 0}}}))
        out.append(("ping", {"type": "ping"}))

    def _open(self, out: List[SSEEvent], block: Dict[str, Any]) -> int:
        i = self.blocks
        self.blocks += 1
        self.open.append(i)
        out.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": block}))
        return i

    def _close(self, out: List[SSEEvent], i: int) -> None:
        self.open.remove(i)
        out.append(("content_block_stop", {"type": "content_block_stop", "index": i}))

    def feed(self, chunk: Dict[str, Any]) -> List[SSEEvent]:
        out: List[SSEEvent] = []
        events = self.d.feed(chunk)
        self._start(out)
        for ev in events:
            if ev[0] == "text":
                if self.text_block is None:
                    self.text_block = self._open(out, {"type": "text", "text": ""})
                out.append(("content_block_delta", {"type": "content_block_delta", "index": self.text_block,
                                                    "delta": {"type": "text_delta", "text": ev[1]}}))
            elif ev[0] == "tool":
                if self.text_block is not None:  # text before a tool call is complete
                    self._close(out, self.text_block)
                    self.text_block = None
                self.tool_block[ev[1]] = self._open(out, {"type": "tool_use", "id": ev[2], "name": ev[3], "input": {}})
            else:
                out.append(("content_block_delta", {"type": "content_block_delta", "index": self.tool_block[ev[1]],
                                                    "delta": {"type": "input_json_delta", "partial_json": ev[2]}}))
        return out

    def finish(self) -> List[SSEEvent]:
        out: List[SSEEvent] = []
        self._start(out)
        for i in list(self.open):
            self._close(out, i)
        tin, tout = _usage(self.d.usage, len(self.d.text))
        usage = {"output_tokens": tout}
        if tin:
            usage["input_tokens"] = tin
        out.append(("message_delta", {"type": "message_delta", "delta": {
            "stop_reason": _stop_reason(self.d.finish, bool(self.d.started_tools())), "stop_sequence": None},
            "usage": usage}))
        out.append(("message_stop", {"type": "message_stop"}))
        return out

    def error(self, status: int, message: str) -> List[SSEEvent]:
        return [("error", AnthropicMessages.error(status, message)[1])]


# -- OpenAI Responses -----------------------------------------------------------

def _response_message(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    role = item.get("role") or "user"
    role = "system" if role in ("system", "developer") else ("assistant" if role == "assistant" else "user")
    content = item.get("content")
    if isinstance(content, str):
        return {"role": role, "content": content} if content else None
    parts: List[Dict[str, Any]] = []
    for p in content if isinstance(content, list) else []:
        if not isinstance(p, dict):
            continue
        if isinstance(p.get("text"), str) and p["text"]:
            parts.append({"type": "text", "text": p["text"]})
        elif p.get("type") == "input_image":
            url = p.get("image_url")
            url = url.get("url") if isinstance(url, dict) else url
            if url:
                parts.append({"type": "image_url", "image_url": {"url": url}})
    if not parts:
        return None
    if role != "user":
        return {"role": role, "content": "\n\n".join(p["text"] for p in parts if p["type"] == "text")}
    return {"role": role, "content": _user_content(parts)}


class OpenAIResponses:
    """``POST /v1/responses`` <-> chat completions."""

    name = "responses"

    @staticmethod
    def to_chat(body: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if body.get("previous_response_id"):
            raise ValueError("previous_response_id is not supported: freelm keeps no response state, "
                             "send the whole conversation in 'input'")
        inp = body.get("input")
        if isinstance(inp, str):
            inp = [{"role": "user", "content": inp}]
        if not isinstance(inp, list):
            raise ValueError("body must have an 'input' string or list")
        messages: List[Dict[str, Any]] = []
        if isinstance(body.get("instructions"), str) and body["instructions"]:
            messages.append({"role": "system", "content": body["instructions"]})
        for item in inp:
            if isinstance(item, str):
                item = {"role": "user", "content": item}
            if not isinstance(item, dict):
                continue
            kind = item.get("type") or ("message" if "role" in item else None)
            if kind == "message":
                msg = _response_message(item)
                if msg:
                    messages.append(msg)
            elif kind == "function_call":
                call = {"id": item.get("call_id") or item.get("id") or _id("call"), "type": "function",
                        "function": {"name": item.get("name") or "", "arguments": _arguments(item.get("arguments"))}}
                last = messages[-1] if messages else None
                if last and last["role"] == "assistant":
                    last.setdefault("tool_calls", []).append(call)
                else:
                    messages.append({"role": "assistant", "tool_calls": [call]})
            elif kind == "function_call_output":
                out = item.get("output")
                messages.append({"role": "tool", "tool_call_id": item.get("call_id") or "",
                                 "content": out if isinstance(out, str) else _text_of(out)})
            # reasoning, web_search_call, local_shell_call, custom tools...: not translatable

        params: Dict[str, Any] = {}
        mt = _clamp_tokens(body.get("max_output_tokens"))
        if mt:
            params["max_tokens"] = mt
        for k in ("temperature", "top_p"):
            if isinstance(body.get(k), (int, float)) and not isinstance(body.get(k), bool):
                params[k] = body[k]
        tools = [
            {"type": "function", "function": {"name": t["name"], "description": t.get("description") or "",
                                              "parameters": t.get("parameters") or {"type": "object", "properties": {}}}}
            for t in body.get("tools") or []
            if isinstance(t, dict) and t.get("type") == "function" and t.get("name")
        ]
        if tools:
            params["tools"] = tools
            tc = body.get("tool_choice")
            if tc in ("none", "required"):
                params["tool_choice"] = tc
            elif isinstance(tc, dict) and tc.get("type") == "function" and tc.get("name"):
                params["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}
        fmt = body.get("text", {}).get("format") if isinstance(body.get("text"), dict) else None
        if isinstance(fmt, dict) and fmt.get("type") == "json_object":
            params["response_format"] = {"type": "json_object"}
        elif isinstance(fmt, dict) and fmt.get("type") == "json_schema":
            params["response_format"] = {"type": "json_schema", "json_schema": {
                k: fmt[k] for k in ("name", "schema", "strict", "description") if k in fmt}}
        return messages, params

    @staticmethod
    def _envelope(body: Dict[str, Any], rid: str, created: int, model: Any, status: str,
                  output: List[Dict[str, Any]], usage: Optional[Dict[str, Any]] = None,
                  incomplete: Optional[str] = None) -> Dict[str, Any]:
        return {
            "id": rid, "object": "response", "created_at": created, "status": status, "error": None,
            "incomplete_details": {"reason": incomplete} if incomplete else None,
            "instructions": body.get("instructions"), "model": model, "output": output,
            "parallel_tool_calls": True, "tool_choice": body.get("tool_choice") or "auto",
            "tools": body.get("tools") or [], "metadata": body.get("metadata") or {}, "usage": usage,
        }

    @staticmethod
    def _text_item(mid: str, text: str, status: str = "completed") -> Dict[str, Any]:
        return {"type": "message", "id": mid, "status": status, "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}] if status == "completed" else []}

    @staticmethod
    def _call_item(fid: str, call_id: str, name: str, arguments: str, status: str = "completed") -> Dict[str, Any]:
        return {"type": "function_call", "id": fid, "call_id": call_id, "name": name, "arguments": arguments,
                "status": status}

    @staticmethod
    def _usage_obj(usage: Any, text_chars: int) -> Dict[str, Any]:
        tin, tout = _usage(usage, text_chars)
        return {"input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout}

    @classmethod
    def from_completion(cls, completion: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        msg, finish = _first_choice(completion)
        text = _text_of(msg.get("content"))
        output: List[Dict[str, Any]] = [cls._text_item(_id("msg"), text)] if text else []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") if isinstance(c, dict) and isinstance(c.get("function"), dict) else {}
            if fn.get("name"):
                output.append(cls._call_item(_id("fc"), c.get("id") or _id("call"), fn["name"],
                                             _arguments(fn.get("arguments"))))
        cut = finish == "length"
        return cls._envelope(body, _id("resp"), int(time.time()), completion.get("model") or body.get("model"),
                             "incomplete" if cut else "completed", output,
                             cls._usage_obj(completion.get("usage"), len(text)), "max_output_tokens" if cut else None)

    @staticmethod
    def error(status: int, message: str) -> Tuple[int, Dict[str, Any]]:
        kind = "invalid_request_error" if 400 <= status < 500 else "server_error"
        return status, {"error": {"message": message, "type": kind, "param": None, "code": None}}

    @staticmethod
    def stream(body: Dict[str, Any]) -> "ResponsesStream":
        return ResponsesStream(body)


class ResponsesStream:
    """Chat chunks -> Responses SSE events (``response.created`` ... ``response.completed``)."""

    def __init__(self, body: Dict[str, Any]) -> None:
        self.body = body
        self.d = _Deltas()
        self.id = _id("resp")
        self.created = int(time.time())
        self.seq = 0
        self.started = False
        self.output: List[Optional[Dict[str, Any]]] = []  # finished items, by output_index
        self.msg: Optional[Tuple[int, str]] = None        # (output_index, item id) of the open text item
        self.msg_text = ""
        self.calls: Dict[int, Tuple[int, str]] = {}       # tool n -> (output_index, item id)

    def _ev(self, out: List[SSEEvent], kind: str, **data: Any) -> None:
        out.append((kind, {"type": kind, "sequence_number": self.seq, **data}))
        self.seq += 1

    def _snapshot(self, status: str, usage: Optional[Dict[str, Any]] = None,
                  incomplete: Optional[str] = None) -> Dict[str, Any]:
        return OpenAIResponses._envelope(self.body, self.id, self.created, self.d.model or self.body.get("model"),
                                         status, [o for o in self.output if o], usage, incomplete)

    def _start(self, out: List[SSEEvent]) -> None:
        if self.started:
            return
        self.started = True
        self._ev(out, "response.created", response=self._snapshot("in_progress"))
        self._ev(out, "response.in_progress", response=self._snapshot("in_progress"))

    def _close_message(self, out: List[SSEEvent]) -> None:
        if self.msg is None:
            return
        idx, mid = self.msg
        part = {"type": "output_text", "text": self.msg_text, "annotations": []}
        self._ev(out, "response.output_text.done", item_id=mid, output_index=idx, content_index=0, text=self.msg_text)
        self._ev(out, "response.content_part.done", item_id=mid, output_index=idx, content_index=0, part=part)
        item = OpenAIResponses._text_item(mid, self.msg_text)
        self.output[idx] = item
        self._ev(out, "response.output_item.done", output_index=idx, item=item)
        self.msg, self.msg_text = None, ""

    def feed(self, chunk: Dict[str, Any]) -> List[SSEEvent]:
        out: List[SSEEvent] = []
        events = self.d.feed(chunk)
        self._start(out)
        for ev in events:
            if ev[0] == "text":
                if self.msg is None:
                    idx, mid = len(self.output), _id("msg")
                    self.output.append(None)
                    self.msg = (idx, mid)
                    self._ev(out, "response.output_item.added", output_index=idx,
                             item=OpenAIResponses._text_item(mid, "", "in_progress"))
                    self._ev(out, "response.content_part.added", item_id=mid, output_index=idx, content_index=0,
                             part={"type": "output_text", "text": "", "annotations": []})
                idx, mid = self.msg
                self.msg_text += ev[1]
                self._ev(out, "response.output_text.delta", item_id=mid, output_index=idx, content_index=0, delta=ev[1])
            elif ev[0] == "tool":
                self._close_message(out)
                idx, fid = len(self.output), _id("fc")
                self.output.append(None)
                self.calls[ev[1]] = (idx, fid)
                self._ev(out, "response.output_item.added", output_index=idx,
                         item=OpenAIResponses._call_item(fid, ev[2], ev[3], "", "in_progress"))
            else:
                idx, fid = self.calls[ev[1]]
                self._ev(out, "response.function_call_arguments.delta", item_id=fid, output_index=idx, delta=ev[2])
        return out

    def finish(self) -> List[SSEEvent]:
        out: List[SSEEvent] = []
        self._start(out)
        self._close_message(out)
        for n, (idx, fid) in self.calls.items():
            t = self.d.tools[n]
            self._ev(out, "response.function_call_arguments.done", item_id=fid, output_index=idx,
                     arguments=t["arguments"])
            item = OpenAIResponses._call_item(fid, t["id"], t["name"], t["arguments"])
            self.output[idx] = item
            self._ev(out, "response.output_item.done", output_index=idx, item=item)
        cut = self.d.finish == "length"
        usage = OpenAIResponses._usage_obj(self.d.usage, len(self.d.text))
        if cut:
            self._ev(out, "response.incomplete", response=self._snapshot("incomplete", usage, "max_output_tokens"))
        else:
            self._ev(out, "response.completed", response=self._snapshot("completed", usage))
        return out

    def error(self, status: int, message: str) -> List[SSEEvent]:
        out: List[SSEEvent] = []
        resp = self._snapshot("failed")
        resp["error"] = {"code": "server_error", "message": message}
        self._ev(out, "response.failed", response=resp)
        return out


PROTOCOLS = {
    "/v1/messages": AnthropicMessages, "/messages": AnthropicMessages,
    "/v1/responses": OpenAIResponses, "/responses": OpenAIResponses,
}
COUNT_TOKENS_PATHS = ("/v1/messages/count_tokens", "/messages/count_tokens")
