#!/usr/bin/env bash
# Instala el bot en un servidor Ubuntu (p. ej. Oracle Cloud Always Free) y lo deja 24/7.
#   curl -fsSL <url-raw-de-este-archivo> | bash -s -- https://github.com/USUARIO/freelm.git
# o, con el repo ya clonado:  bash examples/trading_agents/deploy/oracle-setup.sh
set -euo pipefail
REPO="${1:-}"
BRANCH="${BRANCH:-claude/intelligent-multi-agent-bot-79boq0}"
DIR="${DIR:-$HOME/freelm}"

echo "==> Docker"
if ! command -v docker >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker.io docker-compose-v2 git
  sudo usermod -aG docker "$USER"
fi

echo "==> Código"
if [ ! -d "$DIR/.git" ]; then
  [ -n "$REPO" ] || { echo "indica la URL del repo: bash oracle-setup.sh https://github.com/USUARIO/freelm.git"; exit 2; }
  git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR/examples/trading_agents/deploy"

echo "==> Configuración"
if [ ! -f bot.env ]; then cp bot.env.example bot.env; fi
chmod 600 bot.env
mkdir -p data && sudo chown 10001 data

echo "==> Arranque (papel + mejora diaria)"
sudo docker compose up -d --build
echo
echo "Listo. Comandos útiles:"
echo "  sudo docker compose -f $PWD/docker-compose.yml logs -f --tail 50     # ver qué hace"
echo "  sudo docker compose -f $PWD/docker-compose.yml run --rm bot gate     # ¿listo para dinero real?"
echo "  sudo docker compose -f $PWD/docker-compose.yml run --rm bot status --source binance"
echo "  nano $PWD/bot.env && sudo docker compose -f $PWD/docker-compose.yml up -d   # añadir claves"
