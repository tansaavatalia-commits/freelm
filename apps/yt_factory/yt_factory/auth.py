"""Autorizzazione OAuth una tantum per canale: apre il browser, riceve il codice su localhost, stampa il refresh token.

Uso:  python -m yt_factory auth --channel fatti
Accedi con l'account Google e SCEGLI IL CANALE giusto (brand account) nella schermata di consenso.
"""
from __future__ import annotations

import http.server
import secrets
import urllib.parse
import webbrowser

import httpx

from .config import Channel
from .youtube import AUTH_URL, SCOPES, TOKEN_URL

PORT = 8765


def authorize(ch: Channel) -> str:
    cid, secret = ch.env("YT_CLIENT_ID"), ch.env("YT_CLIENT_SECRET")
    if not cid or not secret:
        raise SystemExit("Imposta prima YT_CLIENT_ID e YT_CLIENT_SECRET (README, passo 3).")
    state = secrets.token_urlsafe(16)
    redirect = f"http://127.0.0.1:{PORT}/"
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if q.get("state") == state:
                got.update(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Fatto. Puoi chiudere questa pagina e tornare al terminale.</h2>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES,
        "access_type": "offline", "prompt": "consent", "state": state})
    print(f"\nCanale: {ch.name}\nApri questo link (se il browser non si apre da solo):\n{url}\n")
    webbrowser.open(url)
    srv.timeout = 300
    while "code" not in got and "error" not in got:
        srv.handle_request()
    srv.server_close()
    if "error" in got:
        raise SystemExit(f"Autorizzazione negata: {got['error']}")
    r = httpx.post(TOKEN_URL, data={"code": got["code"], "client_id": cid, "client_secret": secret,
                                    "redirect_uri": redirect, "grant_type": "authorization_code"})
    r.raise_for_status()
    token = r.json().get("refresh_token")
    if not token:
        raise SystemExit("Google non ha restituito un refresh token: revoca l'accesso dell'app e riprova.")
    var = f"YT_REFRESH_TOKEN_{ch.id.upper()}"
    print(f"OK! Salva questo segreto (es. GitHub > Settings > Secrets > Actions):\n\n{var}={token}\n")
    return token
