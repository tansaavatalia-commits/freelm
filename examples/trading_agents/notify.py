"""Avisos al móvil por Telegram (gratis y opcionales).

Configuración (2 minutos):
1. En Telegram, habla con @BotFather, envía /newbot y copia el token.
2. Escribe cualquier cosa a tu bot nuevo y abre
   https://api.telegram.org/bot<TOKEN>/getUpdates para ver tu ``chat.id``.
3. Define ``TELEGRAM_BOT_TOKEN`` y ``TELEGRAM_CHAT_ID`` en el entorno (o como
   secrets de GitHub Actions / en ``deploy/bot.env``).

Sin esas variables, no se envía nada. Un fallo al enviar nunca detiene el bot.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import httpx


class Notifier:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None, http: object = None) -> None:
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")
        self.http = http
        self.sent = 0

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            post = self.http.post if self.http is not None else httpx.post  # type: ignore[attr-defined]
            r = post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                     json={"chat_id": self.chat_id, "text": text[:4000], "disable_web_page_preview": True},
                     timeout=10)
            ok = getattr(r, "status_code", 200) < 400
            self.sent += int(ok)
            return ok
        except Exception as e:  # noqa: BLE001 - avisar es opcional
            print(f"[telegram] no enviado: {type(e).__name__}", file=sys.stderr)
            return False
