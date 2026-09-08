#!/usr/bin/env bash
# Points your Telegram bot at the deployed app. Run this once after deploying
# (and again any time the bot token, webhook secret, or Cloud Run URL change).
#
# Usage:
#   TELEGRAM_BOT_TOKEN=123:abc \
#   TELEGRAM_WEBHOOK_SECRET=some-random-string \
#   CLOUD_RUN_URL=https://zb-hub-xxxxx-uc.a.run.app \
#     ./scripts/set_telegram_webhook.sh
#
# TELEGRAM_WEBHOOK_SECRET can be any random string - generate one with:
#   openssl rand -hex 24
# It just has to match the TELEGRAM_WEBHOOK_SECRET the app itself is
# deployed with, so Telegram and the app agree on it.
set -euo pipefail

: "${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN (from @BotFather)}"
: "${TELEGRAM_WEBHOOK_SECRET:?Set TELEGRAM_WEBHOOK_SECRET - a random string, must match the app's deployed value}"
: "${CLOUD_RUN_URL:?Set CLOUD_RUN_URL to your deployed app's URL, e.g. https://zb-hub-xxxxx-uc.a.run.app}"

WEBHOOK_URL="${CLOUD_RUN_URL%/}/telegram/webhook"

echo "==> Registering Telegram webhook: $WEBHOOK_URL"
RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${WEBHOOK_URL}" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}")

echo "$RESPONSE"

if echo "$RESPONSE" | grep -q '"ok":true'; then
  echo "==> Done. Message your bot /start on Telegram to try it."
else
  echo "==> Telegram rejected that - check the response above (common cause:"
  echo "    CLOUD_RUN_URL isn't reachable yet, or the bot token is wrong)."
  exit 1
fi
