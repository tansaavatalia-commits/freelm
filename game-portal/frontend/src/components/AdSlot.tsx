import { useEffect, useRef, useState } from "react";
import { fetchAdSlot, sendImpression, type AdSlotResponse } from "../lib/api";

/**
 * Spazio pubblicitario. Senza campagne collassa del tutto (nessuno spazio vuoto).
 * "network" (D-015) non carica ancora nulla: servono account della rete e CMP (FASE 11).
 * Impression conteggiata una sola volta, quando lo slot è visibile >= 50% per >= 1 s.
 */
export function AdSlot({ placement, category }: { placement: string; category?: string }) {
  const [ad, setAd] = useState<AdSlotResponse | null>(null);
  const ref = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchAdSlot(placement, category, ctrl.signal).then(setAd, () => {});
    return () => ctrl.abort();
  }, [placement, category]);

  const direct = ad && (ad.source === "direct" || ad.source === "sponsor") && ad.creativeId !== undefined;

  useEffect(() => {
    const el = ref.current;
    if (!direct || !el || typeof IntersectionObserver === "undefined") return;
    let timer: number | undefined;
    let counted = false;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (counted) return;
        if (entry && entry.intersectionRatio >= 0.5) {
          timer = window.setTimeout(() => {
            counted = true;
            sendImpression(ad.creativeId as number, placement);
            io.disconnect();
          }, 1000);
        } else window.clearTimeout(timer);
      },
      { threshold: [0, 0.5, 1] },
    );
    io.observe(el);
    return () => {
      window.clearTimeout(timer);
      io.disconnect();
    };
  }, [direct, ad, placement]);

  if (!direct) return null;
  return (
    <aside className="ad" aria-label={ad.source === "sponsor" ? "Sponsored" : "Advertisement"}>
      <span className="ad-label">{ad.source === "sponsor" ? "Sponsored" : "Ad"}</span>
      <a ref={ref} href={ad.href} rel="sponsored noopener" target="_blank">
        <img src={ad.image} alt={ad.alt} width={ad.width} height={ad.height} loading="lazy" decoding="async" />
      </a>
    </aside>
  );
}
