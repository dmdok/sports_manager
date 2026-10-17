import re
import unicodedata


def esc_format(text):
    """Escape underscores and asterisks so Telegram Markdown shows them literally.

    Same as esc_format from the markdown-strings package, which was removed from PyPI.
    """
    return str(text).replace("_", r"\_").replace("*", r"\*")


def try_parse_int(x, default=None):
    try:
        return int(x)
    except:
        return default


def is_bidirectional(text):
    return any(unicodedata.bidirectional(x) in ('R', 'AL') for x in text)


def get_full_name(player):
    full_name = " ".join(x for x in [player["first_name"], player["last_name"]] if x != None)
    if is_bidirectional(full_name):
        return "..."
    else:
        return full_name  


def get_username(player, silent):
    username = player["custom_name"]
    if not username:
        username = player["username"]
    if not username:
        username = get_full_name(player)
    if silent:
        username = esc_format(username)
    else:
        username = "[{}](tg://user?id={})".format(username, player["id"])
    return username


def is_valid_custom_name(custom_name):
    return len(custom_name) >= 4 and len(custom_name) <= 64 and re.match("^[a-zA-Zа-яА-Я0-9_() ]+$", custom_name)
