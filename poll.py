"""Receive Telegram updates by long polling instead of a webhook.

Telegram's webhook calls can't reach the server, but the server can still
reach Telegram, so the bot asks for updates itself.
"""
from src.telegram_api import TelegramApi
from src.telegram_app import TelegramApp

import os
import time
import traceback

ERROR_DELAY = 5


def log_error(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    print(message.replace(token, "<TOKEN>"), flush=True)


def main():
    telegram_api = TelegramApi()
    telegram_app = TelegramApp()

    # getUpdates is refused while a webhook is set.
    while True:
        try:
            telegram_api.delete_webhook()
            break
        except Exception:
            log_error("deleteWebhook failed:\n" + traceback.format_exc())
            time.sleep(ERROR_DELAY)
    print("webhook deleted, polling for updates", flush=True)

    offset = None
    while True:
        try:
            updates = telegram_api.get_updates(offset)
        except Exception:
            log_error("getUpdates failed:\n" + traceback.format_exc())
            time.sleep(ERROR_DELAY)
            continue

        for data in updates:
            # Confirm the update even if handling fails, so one bad update
            # can't block all the ones after it.
            offset = data["update_id"] + 1
            try:
                telegram_app.update(data)
            except Exception:
                log_error("update {} failed:\n{}".format(
                    data["update_id"], traceback.format_exc()))


if __name__ == "__main__":
    main()
