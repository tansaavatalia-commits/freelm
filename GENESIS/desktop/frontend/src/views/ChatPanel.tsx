import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { api, errorText, streamEvents, usePolling } from "../api";
import { Markdown } from "../markdown";
import type { Agent, AgentRun, ChatMessage, ChatStatus, Conversation, Task } from "../types";

export const CHAT = "genesis";
const DIRECTOR = "director";

interface AgentAsk {
  id: string;
  target: string;
  text: string;
  at: number;
}

function time(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

export function ChatPanel({
  agents,
  runs,
  target,
  setTarget,
  onActivity,
  inputRef,
}: {
  agents: Agent[];
  runs: AgentRun[];
  target: string;
  setTarget: (t: string) => void;
  onActivity: (agentId: string | null) => void; // light up the globe (null: GÉNESIS itself)
  inputRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const convs = usePolling(() => api<Conversation[]>("/api/chat?limit=50"), 0);
  const chatStatus = usePolling(() => api<ChatStatus>("/api/chat-status"), 15000);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<{ text: string; engine: string } | null>(null);
  const [asks, setAsks] = useState<AgentAsk[]>([]);
  const [text, setText] = useState("");
  const [isPrivate, setPrivate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const names = new Map(agents.map((a) => [a.id, a.name]));

  // open the most recent conversation once the list arrives
  useEffect(() => {
    if (activeId === null && convs.data && convs.data.length > 0) setActiveId(convs.data[0].id);
  }, [convs.data, activeId]);

  const load = useCallback(async (id: string) => {
    try {
      const c = await api<Conversation & { messages: ChatMessage[] }>(`/api/chat/${id}`);
      setMessages(c.messages);
      setPrivate(c.private);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    setAsks([]);
    if (activeId) void load(activeId);
    else setMessages([]);
  }, [activeId, load]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming, asks, runs]);

  async function newConversation(priv = false): Promise<string> {
    const c = await api<Conversation>("/api/chat", { body: { private: priv } });
    await convs.refresh();
    setActiveId(c.id);
    setMessages([]);
    return c.id;
  }

  async function sendChat(goal: string) {
    const id = activeId ?? (await newConversation(isPrivate));
    setStreaming({ text: "", engine: "" });
    onActivity(null);
    await streamEvents(`/api/chat/${id}/send`, { text: goal }, (e) => {
      if (e.type === "user") setMessages((m) => [...m, e.message as ChatMessage]);
      else if (e.type === "start") setStreaming({ text: "", engine: String(e.name ?? e.engine ?? "") });
      else if (e.type === "delta") {
        setStreaming((s) => ({ engine: s?.engine ?? "", text: (s?.text ?? "") + String(e.text ?? "") }));
        onActivity(null);
      } else if (e.type === "done") {
        setMessages((m) => [...m, e.message as ChatMessage]);
        setStreaming(null);
      } else if (e.type === "error") setError(String(e.error));
    });
    setStreaming(null);
    void convs.refresh();
  }

  async function sendAgent(goal: string) {
    const body = target === DIRECTOR
      ? { kind: "agents.direct", payload: { goal, private: isPrivate } }
      : { kind: "agents.run", payload: { agent: target, goal, private: isPrivate } };
    await api<Task>("/api/tasks", { body });
    setAsks((a) => [...a, { id: `${Date.now()}`, target, text: goal, at: Date.now() }]);
    onActivity(target);
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const goal = text.trim();
    if (!goal || busy) return;
    setBusy(true);
    setError(null);
    setText("");
    try {
      if (target === CHAT) await sendChat(goal);
      else await sendAgent(goal);
    } catch (e) {
      setError(errorText(e));
      setText(goal);
      setStreaming(null);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  }

  async function remove() {
    if (!activeId || !window.confirm("Nascondere questa conversazione? Resta nei backup e nelle esportazioni.")) return;
    await api(`/api/chat/${activeId}/delete`, { body: {} });
    setActiveId(null);
    await convs.refresh();
  }

  const online = chatStatus.data?.online ?? false;
  const active = convs.data?.find((c) => c.id === activeId);
  const empty = messages.length === 0 && !streaming && asks.length === 0;

  return (
    <section className="chat" aria-label="Chat con GÉNESIS">
      <header className="chat-head">
        <select value={activeId ?? ""} onChange={(e) => setActiveId(e.target.value || null)} aria-label="Conversazione">
          {!activeId && <option value="">Nuova conversazione</option>}
          {(convs.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>{c.private ? "🔒 " : ""}{c.title}</option>
          ))}
        </select>
        <button type="button" onClick={() => { setActiveId(null); setMessages([]); setAsks([]); inputRef.current?.focus(); }}
                title="Nuova conversazione">＋ Nuova</button>
        {activeId && <button type="button" onClick={remove} title="Nascondi la conversazione" aria-label="Nascondi la conversazione">🗑</button>}
      </header>

      <p className={`chat-engine ${online ? "chat-engine-on" : ""}`}>
        {online
          ? <>● Motore online: {chatStatus.data?.engine}{active?.private || isPrivate ? " · conversazione privata: resta su questo PC" : ""}</>
          : <>○ Motore online spento: rispondo a calcoli, testo e «ricorda che…». <a href="#/motori">Come accenderlo</a></>}
      </p>

      <div className="chat-log" ref={scrollRef} aria-live="polite">
        {empty && (
          <div className="chat-empty">
            <p className="chat-empty-title">Che cosa facciamo?</p>
            <p>Scrivi qui sotto. Prova: «quanto fa 12*(3+4)?», «ricorda che preferisco risposte brevi»
              {online ? ", «spiegami cos'è un buco nero»" : ""}.</p>
            <p>Puoi anche scegliere un agente dal menu o cliccare il suo nome sul globo.</p>
          </div>
        )}
        {messages.map((m) => (
          <article key={m.id} className={`msg msg-${m.role} ${m.status === "error" ? "msg-error" : ""}`}>
            <div className="msg-meta">
              {m.role === "user" ? "Tu" : "GÉNESIS"} · {time(m.created_at)}
              {m.role === "assistant" && m.engine && <> · {m.engine}{m.ms != null ? ` · ${Math.round(m.ms)} ms` : ""}</>}
            </div>
            <div className="msg-body">{m.role === "assistant" ? <Markdown text={m.content} /> : m.content}</div>
          </article>
        ))}
        {streaming && (
          <article className="msg msg-assistant msg-live">
            <div className="msg-meta">GÉNESIS · {streaming.engine || "sto pensando"}</div>
            <div className="msg-body">
              {streaming.text ? <Markdown text={streaming.text} /> : <span className="dots" aria-label="sto scrivendo"><i /><i /><i /></span>}
            </div>
          </article>
        )}
        {asks.map((a) => {
          const run = runs.find((r) => r.goal === a.text && Date.parse(r.created_at) >= a.at - 60_000);
          const who = a.target === DIRECTOR ? "Director" : names.get(a.target) ?? a.target;
          return (
            <div key={a.id}>
              <article className="msg msg-user"><div className="msg-meta">Tu → {who}</div><div className="msg-body">{a.text}</div></article>
              <article className={`msg msg-assistant ${run?.status === "failed" ? "msg-error" : ""}`}>
                <div className="msg-meta">{who} · {run ? (run.status === "running" ? "al lavoro" : run.status === "succeeded" ? "riuscita" : "fallita") : "in coda"}</div>
                <div className="msg-body">
                  {run?.output ? <Markdown text={run.output} /> : <span className="dots" aria-label="in attesa"><i /><i /><i /></span>}
                </div>
              </article>
            </div>
          );
        })}
      </div>

      {error && <p className="chat-error" role="alert">{error}</p>}
      <form className="chat-form" onSubmit={submit}>
        <div className="chat-row">
          <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Destinatario">
            <option value={CHAT}>GÉNESIS (chat)</option>
            <option value={DIRECTOR}>Director (scompone e delega)</option>
            {agents.filter((a) => a.id !== DIRECTOR).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          {!activeId && target === CHAT && (
            <label className="chat-private" title="La conversazione non esce da questo PC">
              <input type="checkbox" checked={isPrivate} onChange={(e) => setPrivate(e.target.checked)} /> privata
            </label>
          )}
        </div>
        <div className="chat-row">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            rows={2}
            maxLength={8000}
            placeholder={target === CHAT ? "Scrivi a GÉNESIS… (Invio per inviare, Maiusc+Invio per andare a capo)" : `Scrivi a ${names.get(target) ?? "Director"}…`}
            aria-label="Richiesta"
          />
          <button type="submit" disabled={busy || !text.trim()}>{busy ? "…" : "Invia"}</button>
        </div>
      </form>
    </section>
  );
}
