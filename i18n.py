"""Every piece of text the app shows, in Russian and English (lowercase except Spotify and Claude Code).

The choice is kept in %APPDATA%\\Clauddy\\config.json; the first run follows the Windows language."""
import ctypes
import json
import os

CONFIG = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Clauddy", "config.json")

STRINGS = {
    "player":          {"ru": "плеер Spotify", "en": "Spotify player"},
    "liked":           {"ru": "любимые треки", "en": "liked songs"},
    "freeze":          {"ru": "заморозить клода", "en": "freeze claude"},
    "clone":           {"ru": "добавить ещё клода", "en": "add another claude"},
    "unclone":         {"ru": "убрать копии клода", "en": "remove extra claudes"},
    "unclone_one":     {"ru": "убрать этого клода", "en": "remove this claude"},
    "connect":         {"ru": "подключить к Claude Code", "en": "connect to Claude Code"},
    "disconnect":      {"ru": "отключить от Claude Code", "en": "disconnect from Claude Code"},
    "api_on":          {"ru": "Spotify web api (для премиума)…", "en": "Spotify web api (premium)…"},
    "api_off":         {"ru": "отключить Spotify web api", "en": "disconnect Spotify web api"},
    "autostart":       {"ru": "запускать вместе с windows", "en": "start with windows"},
    # the switch is written in the language it switches to, so it's readable either way
    "language":        {"ru": "switch to english", "en": "переключить на русский"},
    "hide":            {"ru": "спрятать в трей", "en": "hide to tray"},
    "tray_hide":       {"ru": "спрятать клода", "en": "hide claude"},
    "tray_show":       {"ru": "показать клода", "en": "show claude"},
    "quit":            {"ru": "выход", "en": "quit"},

    "connected":       {"ru": "готово, перезапусти Claude Code и я начну реагировать на его работу.\n"
                              "копия старых настроек: settings.json.clauddy-backup",
                        "en": "done. restart Claude Code and i'll start reacting to it.\n"
                              "your old settings are saved as settings.json.clauddy-backup"},
    "disconnected":    {"ru": "хуки clauddy убраны из настроек Claude Code",
                        "en": "clauddy hooks removed from Claude Code settings"},
    "settings_error":  {"ru": "не получилось изменить {path}:\n{err}", "en": "couldn't change {path}:\n{err}"},
    "no_spotify":      {"ru": "не нашёл окно Spotify. сердечко работает с приложением Spotify для windows, "
                              "когда оно открыто (можно свёрнутым)",
                        "en": "couldn't find the Spotify window. the heart works with the Spotify desktop app "
                              "while it's open (minimized is fine)"},
    "spotify_ready":   {"ru": "Spotify подключён, теперь сердечко в плеере добавляет трек в любимые",
                        "en": "Spotify connected. the heart in the player now saves tracks to liked songs"},
    "client_id":       {"ru": "чтобы сердечко работало через web api, нужен твой client id Spotify:\n\n"
                              "1. на открывшейся странице войди и нажми \"Create app\"\n"
                              "2. в redirect uris вставь http://127.0.0.1:47613/callback\n"
                              "3. отметь \"Web API\" и сохрани\n"
                              "4. скопируй client id сюда\n\n"
                              "потом Spotify попросит разрешить доступ в браузере",
                        "en": "to use the web api for the heart, paste your Spotify client id:\n\n"
                              "1. sign in on the page that just opened and click \"Create app\"\n"
                              "2. add this redirect uri: http://127.0.0.1:47613/callback\n"
                              "3. tick \"Web API\" and save\n"
                              "4. copy the client id here\n\n"
                              "Spotify will then ask you to allow access in the browser"},

    "surprise":        {"ru": "удиви меня", "en": "surprise me"},
    "radio_stop":      {"ru": "стоп", "en": "stop"},
    "radio_failed":    {"ru": "не получилось включить волну, Spotify открыт?",
                        "en": "couldn't start a radio. is Spotify open?"},
    "picker_title":    {"ru": "любимые треки", "en": "liked songs"},
    "picker_loading":  {"ru": "загружаю любимые треки…", "en": "loading liked songs…"},
    "picker_empty":    {"ru": "ничего не нашлось", "en": "nothing found"},
    "picker_error":    {"ru": "Spotify не ответил, он открыт?", "en": "Spotify didn't answer. is it open?"},

    "oauth_stale":     {"ru": "этот вход устарел, запусти подключение Spotify ещё раз из меню clauddy",
                        "en": "this sign-in has expired. start the Spotify connection again from the clauddy menu"},
    "oauth_denied":    {"ru": "Spotify не дал доступ: {err}", "en": "Spotify denied access: {err}"},
    "oauth_failed":    {"ru": "не получилось войти: {err}", "en": "couldn't sign in: {err}"},
    "oauth_ok":        {"ru": "Spotify подключён, вкладку можно закрыть", "en": "Spotify connected. you can close this tab"},
}


def _system_lang():
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return "ru" if primary in (0x19, 0x22, 0x23) else "en"     # Russian, Ukrainian, Belarusian
    except Exception:
        return "en"


def _load():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            lang = json.load(f).get("lang")
        if lang in ("ru", "en"):
            return lang
    except (OSError, ValueError):
        pass
    return _system_lang()


LANG = _load()


def set_lang(lang):
    global LANG
    LANG = lang
    data = {}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["lang"] = lang
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def t(key, **kw):
    s = STRINGS[key][LANG]
    return s.format(**kw) if kw else s
