# Bot de trading 24/7 (papel por defecto). Se construye desde la raíz del repo:
#   docker build -f examples/trading_agents/deploy/Dockerfile -t trading-bot .
# Funciona en amd64 y arm64 (Oracle Cloud Always Free Ampere).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY examples/trading_agents ./bot
RUN pip install --no-cache-dir . ccxt \
 && useradd --system --uid 10001 --create-home bot \
 && mkdir -p /data && chown bot /data

USER bot
ENV FREELM_TRADING_DIR=/data PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["python", "/app/bot/bot.py"]
# papel + mejora automática diaria + analista IA (si hay claves gratuitas en el entorno)
CMD ["live", "--exchange", "papel", "--auto-optimize", "--llm"]
