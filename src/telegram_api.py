import json
import requests
import os
import time


class TelegramApi:
    # Connection attempts to api.telegram.org occasionally hang, so retry them.
    # Only connection errors are retried: the request never reached Telegram,
    # so a retry can't produce a duplicate message.
    RETRY_DELAYS = [1, 2]

    def __init__(self):
        self.__telegram_bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.__base_url = "https://api.telegram.org/bot" + self.__telegram_bot_token

    def __request(self, http_method, api_method, timeout=5, **kwargs):
        url = self.__base_url + "/" + api_method
        for delay in self.RETRY_DELAYS + [None]:
            try:
                return requests.request(http_method, url, timeout=timeout, **kwargs)
            except requests.exceptions.ConnectionError as e:
                if delay is None:
                    raise
                print("{} failed to connect, retrying in {}s: {}".format(
                    api_method, delay, type(e).__name__), flush=True)
                time.sleep(delay)

    def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, reply_to_message_id=None):
        data = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        print("Starting sending message... ", flush=True)
        print(json.dumps(data), flush=True)
        response = self.__request("POST", "sendMessage", json=data)
        print("Message sent", flush=True)
        if response.status_code != 200:
            print(response.content, flush=True)

    def get_chat_member(self, chat_id, user_id):
        params = {"chat_id": chat_id, "user_id": user_id}
        response = self.__request("GET", "getChatMember", params=params)
        if response.status_code != 200:
            return None
        return response.json()["result"]

    def delete_webhook(self):
        # Pending updates are kept, so getUpdates delivers them.
        response = self.__request("POST", "deleteWebhook")
        response.raise_for_status()

    def get_updates(self, offset=None, timeout=30):
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        # The HTTP timeout must outlast Telegram's long-poll timeout.
        response = self.__request("GET", "getUpdates", timeout=timeout + 10, params=params)
        response.raise_for_status()
        return response.json()["result"]
