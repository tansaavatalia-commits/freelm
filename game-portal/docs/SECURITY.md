# GAME PORTAL — Sicurezza (piano FASE 0)

| Minaccia | Contromisura |
|---|---|
| SQL injection | Solo query parametrizzate (D1 `prepare().bind()`), lint che vieta la concatenazione di stringhe SQL, validazione Zod di ogni input |
| XSS | React escaping, nessun `dangerouslySetInnerHTML` su dati utente, CSP con nonce, `Trusted Types` dove supportato |
| CSRF | Cookie `SameSite=Lax`/`Strict`, token CSRF sulle mutazioni, controllo `Origin` |
| Accessi non autorizzati | Deny-by-default, ruoli admin, MFA/passkey, sessioni brevi, admin su origin separato |
| Abuso API | Rate limiting per IP/sessione (Workers Rate Limiting o contatori), limiti di dimensione del payload, Turnstile gratuito sui form pubblici (da autorizzare) |
| Upload malevoli | Nessun upload pubblico. Upload admin solo per immagini: verifica del magic number, ricodifica, limite di dimensione, SVG vietati. I bundle dei giochi entrano solo via Git e revisione |
| Giochi malevoli | iframe sandbox su origin senza cookie, CSP `frame-ancestors`, `Permissions-Policy` restrittiva, kill switch |
| Credential leakage / segreti | Segreti solo in `wrangler secret`/GitHub Secrets, `.dev.vars` in `.gitignore`, secret scanning e push protection di GitHub, nessun segreto nel bundle client |
| Abuso pubblicitario | Impression contate solo se visibili, deduplica per sessione, filtro dei bot noti, soglie anomale ⇒ segnalazione, creatività solo statiche e revisionate |
| Supply chain | Lockfile, Dependabot, `pnpm audit`, numero minimo di dipendenze |

Header standard: `Content-Security-Policy`, `Strict-Transport-Security`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`.

Riferimento di verifica: OWASP ASVS 5.0 livello 1 (livello 2 per l'admin).
