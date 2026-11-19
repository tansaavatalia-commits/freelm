import { useTitle } from "./useTitle";

// ATTENZIONE: testi in BOZZA. Privacy e termini richiedono revisione legale prima
// della pubblicazione (docs/LEGAL_CHECKLIST.md, decisione D-009).

export function About() {
  useTitle("About");
  return (
    <section className="prose">
      <h1>About Tabluo</h1>
      <p>Tabluo is an independent home for classic card, puzzle and logic games. Every game here is original work or used under a verified licence.</p>
      <p>We keep things fast and respectful: no downloads, no sign-up, and no tracking cookies.</p>
    </section>
  );
}

export function Privacy() {
  useTitle("Privacy");
  return (
    <section className="prose">
      <h1>Privacy</h1>
      <p className="draft">Draft — this page is under legal review and is not yet final.</p>
      <p>Favorites and history are stored only in your browser. Gameplay statistics are counted in aggregate (game, day, duration) without any identifier, account or cookie.</p>
    </section>
  );
}

export function Terms() {
  useTitle("Terms");
  return (
    <section className="prose">
      <h1>Terms of use</h1>
      <p className="draft">Draft — this page is under legal review and is not yet final.</p>
    </section>
  );
}

export function Advertise() {
  useTitle("Advertise");
  return (
    <section className="prose">
      <h1>Advertise on Tabluo</h1>
      <p>We sell a small number of clearly labelled, non-intrusive placements directly to brands, plus sponsorships of categories and daily puzzles. No third-party tracking pixels.</p>
      <p className="draft">Media kit and contact details will be published at launch.</p>
    </section>
  );
}
