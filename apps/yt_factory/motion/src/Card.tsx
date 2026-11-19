/**
 * Grafiche animate dello studio. Una "card" occupa un'intera scena: immagine della scena sfocata e in lento zoom,
 * velo scuro, e sopra l'animazione dei dati (che il pipeline ha già verificato contro il testo parlato).
 */
import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Pair = { value: string; label: string };
type Point = { year: string; label: string };

export type CardProps = {
  kind: "stat" | "compare" | "list" | "timeline" | "quote";
  fmt: "short" | "long";
  duration: number;
  palette: string[];
  background?: string; // nome file nella cartella media (publicDir)
  title?: string;
  value?: string;
  label?: string;
  sub?: string;
  a?: Pair;
  b?: Pair;
  items?: string[];
  points?: Point[];
  text?: string;
  author?: string;
};

const FONT = "Inter, 'DejaVu Sans', Arial, sans-serif";

/** "$9.4 billion" -> {pre:"$", num:9.4, dec:1, post:" billion", sep:true}; null se non c'è un numero da animare. */
function parseNumber(v: string) {
  const m = v.match(/^([^\d-]*)(-?\d{1,3}(?:[,.\s]\d{3})+|-?\d+(?:[.,]\d+)?)(.*)$/s);
  if (!m) return null;
  const raw = m[2];
  const thousands = /\d[,.\s]\d{3}(\D|$)/.test(raw) && !/^\d+[.,]\d{1,2}$/.test(raw);
  const clean = thousands ? raw.replace(/[,.\s]/g, "") : raw.replace(",", ".");
  const num = parseFloat(clean);
  if (Number.isNaN(num)) return null;
  const dec = thousands ? 0 : (clean.split(".")[1] || "").length;
  const sepChar = thousands ? (raw.match(/[,.\s]/) || [","])[0] : "";
  return { pre: m[1], num, dec, post: m[3], sepChar };
}

function formatNumber(n: number, dec: number, sepChar: string, decChar: string) {
  let s = n.toFixed(dec);
  if (sepChar) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, sepChar);
  if (dec && decChar !== ".") s = s.replace(".", decChar);
  return s;
}

const CountUp: React.FC<{ value: string; progress: number }> = ({ value, progress }) => {
  const p = parseNumber(value);
  if (!p) return <>{value}</>;
  const decChar = /\d,\d{1,2}(\D|$)/.test(value) && !p.sepChar ? "," : ".";
  return (
    <>
      {p.pre}
      {formatNumber(p.num * progress, p.dec, p.sepChar, decChar)}
      {p.post}
    </>
  );
};

const Background: React.FC<{ background?: string; palette: string[] }> = ({ background, palette }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const scale = interpolate(frame, [0, durationInFrames], [1.08, 1.2]);
  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${palette[0]}, ${palette[1] || palette[0]})` }}>
      {background ? (
        <Img
          src={staticFile(background)}
          style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${scale})`,
                   filter: "blur(14px) brightness(0.45) saturate(1.2)" }}
        />
      ) : null}
      <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 45%, transparent 0%, ${palette[0]}cc 85%)` }} />
    </AbsoluteFill>
  );
};

export const Card: React.FC<CardProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width } = useVideoConfig();
  const accent = props.palette[props.palette.length - 1];
  const long = props.fmt === "long";
  const u = width / 1080; // unità di scala: stesse proporzioni in verticale e orizzontale
  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 120 } });
  const exit = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  const count = interpolate(frame, [4, Math.min(durationInFrames * 0.6, 45)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const appear = (i: number) => spring({ frame: frame - 6 - i * 8, fps, config: { damping: 16 } });

  const titleEl = props.title ? (
    <div style={{ fontSize: 56 * u, fontWeight: 800, letterSpacing: 4 * u, textTransform: "uppercase",
                  color: accent, marginBottom: 40 * u, opacity: enter }}>{props.title}</div>
  ) : null;

  let body: React.ReactNode = null;
  if (props.kind === "stat" && props.value) {
    body = (
      <div style={{ textAlign: "center", transform: `scale(${0.7 + 0.3 * enter})` }}>
        {titleEl}
        <div style={{ fontSize: (long ? 150 : 170) * u, fontWeight: 900, color: "white", lineHeight: 1.05,
                      textShadow: `0 0 ${40 * u}px ${accent}88` }}>
          <CountUp value={props.value} progress={count} />
        </div>
        {props.label ? <div style={{ fontSize: 58 * u, fontWeight: 700, color: "white", marginTop: 30 * u,
                                      opacity: appear(2) }}>{props.label}</div> : null}
        {props.sub ? <div style={{ fontSize: 40 * u, color: "#ffffffbb", marginTop: 18 * u, opacity: appear(4) }}>
          {props.sub}</div> : null}
      </div>
    );
  } else if (props.kind === "compare" && props.a && props.b) {
    const pa = parseNumber(props.a.value)?.num ?? 1;
    const pb = parseNumber(props.b.value)?.num ?? 1;
    const max = Math.max(Math.abs(pa), Math.abs(pb), 1e-9);
    const bar = (pair: Pair, n: number, i: number) => {
      const grow = spring({ frame: frame - 8 - i * 10, fps, config: { damping: 18 } });
      return (
        <div style={{ marginBottom: 60 * u, opacity: appear(i) }} key={i}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "white", fontSize: 62 * u,
                        fontWeight: 700, marginBottom: 16 * u }}>
            <span>{pair.label}</span>
            <span style={{ color: i === 1 ? accent : "white", fontWeight: 900 }}>
              <CountUp value={pair.value} progress={count} />
            </span>
          </div>
          <div style={{ height: 56 * u, borderRadius: 28 * u, background: "#ffffff22", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${Math.max(4, (Math.abs(n) / max) * 100 * grow)}%`,
                          borderRadius: 28 * u, background: i === 1 ? accent : "#ffffffcc" }} />
          </div>
        </div>
      );
    };
    body = (
      <div style={{ width: (long ? 1200 : 860) * u * (long ? 0.56 : 1) }}>
        {titleEl}
        {bar(props.a, pa, 0)}
        {bar(props.b, pb, 1)}
      </div>
    );
  } else if (props.kind === "list" && props.items?.length) {
    body = (
      <div style={{ width: 940 * u * (long ? 0.6 : 1) }}>
        {titleEl}
        {props.items.slice(0, 4).map((it, i) => {
          const a = appear(i);
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 28 * u, marginBottom: 44 * u,
                                  opacity: a, transform: `translateX(${(1 - a) * -80 * u}px)` }}>
              <div style={{ minWidth: 104 * u, height: 104 * u, borderRadius: 52 * u, background: accent,
                            color: props.palette[0], fontSize: 58 * u, fontWeight: 900, display: "flex",
                            alignItems: "center", justifyContent: "center" }}>{i + 1}</div>
              <div style={{ color: "white", fontSize: 70 * u, fontWeight: 800, lineHeight: 1.12 }}>{it}</div>
            </div>
          );
        })}
      </div>
    );
  } else if (props.kind === "timeline" && props.points?.length) {
    const pts = props.points.slice(0, 4);
    const line = interpolate(frame, [4, 4 + pts.length * 10], [0, 100], { extrapolateRight: "clamp" });
    body = (
      <div style={{ position: "relative", width: 860 * u * (long ? 0.6 : 1), paddingLeft: 70 * u }}>
        {titleEl}
        <div style={{ position: "absolute", left: 22 * u, top: props.title ? 110 * u : 0, width: 8 * u,
                      height: `${line}%`, background: accent, borderRadius: 4 * u }} />
        {pts.map((p, i) => {
          const a = appear(i);
          return (
            <div key={i} style={{ position: "relative", marginBottom: 64 * u, opacity: a,
                                  transform: `translateY(${(1 - a) * 30 * u}px)` }}>
              <div style={{ position: "absolute", left: -62 * u, top: 18 * u, width: 36 * u, height: 36 * u,
                            borderRadius: 18 * u, background: accent, boxShadow: `0 0 ${24 * u}px ${accent}` }} />
              <div style={{ color: accent, fontSize: 92 * u, fontWeight: 900 }}>{p.year}</div>
              <div style={{ color: "white", fontSize: 60 * u, fontWeight: 700, lineHeight: 1.15 }}>{p.label}</div>
            </div>
          );
        })}
      </div>
    );
  } else if (props.kind === "quote" && props.text) {
    const chars = Math.floor(interpolate(frame, [4, Math.min(durationInFrames * 0.7, 75)], [0, props.text.length],
                                         { extrapolateRight: "clamp" }));
    body = (
      <div style={{ width: 900 * u * (long ? 0.7 : 1), textAlign: "left" }}>
        <div style={{ fontSize: 220 * u, color: accent, lineHeight: 0.6, fontWeight: 900, opacity: enter }}>“</div>
        <div style={{ color: "white", fontSize: 64 * u, fontWeight: 700, lineHeight: 1.25 }}>
          {props.text.slice(0, chars)}
          <span style={{ opacity: frame % 20 < 10 ? 1 : 0, color: accent }}>|</span>
        </div>
        {props.author ? <div style={{ color: accent, fontSize: 44 * u, marginTop: 36 * u, fontWeight: 700,
                                       opacity: appear(6) }}>— {props.author}</div> : null}
      </div>
    );
  }

  return (
    <AbsoluteFill style={{ fontFamily: FONT }}>
      <Background background={props.background} palette={props.palette} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", opacity: exit,
                             paddingBottom: long ? 0 : 380 * u /* lascia spazio ai sottotitoli in basso */ }}>
        {body}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
