import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { CatalogEntry } from "@tabluo/shared";
import { GAMES_ORIGIN } from "../config";
import { gameStatus, sendEvent } from "../lib/api";
import { acceptMessage, expectedOrigin, gameUrl, sandboxFor } from "../lib/player";

type State = "checking" | "suspended" | "loading" | "ready" | "error";

export function Player({ game }: { game: CatalogEntry }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<State>("checking");
  const [reason, setReason] = useState("");

  // Kill switch: lo stato viene verificato prima di caricare il gioco.
  useEffect(() => {
    const ctrl = new AbortController();
    setState("checking");
    gameStatus(game.slug, ctrl.signal).then(
      (s) => {
        setReason(s.reason);
        setState(s.playable ? "loading" : "suspended");
      },
      () => {},
    );
    return () => ctrl.abort();
  }, [game.slug]);

  useEffect(() => {
    const origin = expectedOrigin(GAMES_ORIGIN, game);
    const started = performance.now();
    let reported = false;
    const onMessage = (e: MessageEvent) => {
      const msg = acceptMessage(e, frame.current?.contentWindow, origin);
      if (!msg) return;
      if (msg.type === "ready") setState("ready");
      else if (msg.type === "complete") sendEvent({ slug: game.slug, version: game.version, seconds: msg.seconds, completed: true, won: msg.won });
      else if (msg.type === "error" && !reported) {
        reported = true;
        sendEvent({ slug: game.slug, version: game.version, seconds: (performance.now() - started) / 1000, error: true });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [game]);

  // Se il gioco non risponde entro 15 s mostriamo un errore recuperabile.
  useEffect(() => {
    if (state !== "loading") return;
    const t = window.setTimeout(() => setState((s) => (s === "loading" ? "error" : s)), 15_000);
    return () => window.clearTimeout(t);
  }, [state]);

  const [w, h] = game.aspect.split(":").map(Number) as [number, number];
  if (state === "suspended")
    return (
      <div className="player-message" role="alert">
        <strong>This game is temporarily unavailable.</strong>
        {reason ? <span> {reason}</span> : null}
      </div>
    );

  return (
    <div className="player" ref={wrap}>
      <div className="player-frame" style={{ aspectRatio: `${w} / ${h}`, "--ar": w / h } as CSSProperties}>
        {state === "checking" ? null : (
          <iframe
            ref={frame}
            title={`${game.title} game`}
            src={gameUrl(GAMES_ORIGIN, game.slug)}
            sandbox={sandboxFor(game)}
            allow="fullscreen"
            referrerPolicy="no-referrer"
            loading="eager"
          />
        )}
        {state === "checking" || state === "loading" ? <div className="player-overlay">Loading…</div> : null}
        {state === "error" ? (
          <div className="player-overlay" role="alert">
            The game did not load.{" "}
            <button type="button" onClick={() => { setState("loading"); frame.current?.setAttribute("src", gameUrl(GAMES_ORIGIN, game.slug)); }}>
              Retry
            </button>
          </div>
        ) : null}
      </div>
      <div className="player-tools">
        <button type="button" onClick={() => void wrap.current?.requestFullscreen?.().catch(() => {})}>
          ⛶ Fullscreen
        </button>
      </div>
    </div>
  );
}
