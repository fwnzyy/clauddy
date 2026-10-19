"""Clauddy: a tiny pixel Claude that walks on your desktop and reacts to Claude Code.

Runs a local HTTP server on 127.0.0.1 only; Claude Code "http" hooks post events to it.
Nothing ever leaves your computer.

  clauddy.py                 run the pet
  clauddy.py --preview f.png save a sprite sheet of every animation
  clauddy.py --icon f.ico    write the app icon
"""
import ctypes
import json
import math
import os
import queue
import random
import struct
import sys
import threading
import time
import zlib
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import i18n
from i18n import t

APP = "clauddy"
PORT = 47613
HOOK_URL = f"http://127.0.0.1:{PORT}/hook"
SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
HOOK_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
               "Stop", "Notification", "SessionEnd"]
SLEEP_AFTER = 120        # seconds of nobody around before he naps

S = 4                    # screen pixels per sprite pixel
COLS, ROWS = 24, 18
W, H = COLS * S, ROWS * S
KEY = "#010203"          # transparent color key
TICK = 50                # ms per frame
SPEED = 2                # screen px per tick while walking

COL = {
    "body": "#d97757", "eye": "#1b1b1b",
    "screen": "#3b3b3b", "base": "#9c9c9c", "logo": "#e8e8e8",
    "bulb": "#ffd84a", "bulboff": "#5e5a45", "socket": "#8a8a8a", "ray": "#fff1a0",
    "bang": "#ff5a4a", "spark": "#ffd84a",
    "blushbody": "#e2665a", "cheek": "#ff8fa3", "heart": "#ff4f6d",
    "zzz": "#cfd3dc", "sweat": "#7cc4ff",
    "cover": "#8a5a3c", "page": "#f2ede0", "mug": "#f2f2f2", "coffee": "#6b4226", "steam": "#b9b9b9",
    "wing": "#8ecbff", "wing2": "#c9a6ff", "bug": "#2b2b2b",
}
HEART = [".X.X.", "XXXXX", ".XXX.", "..X.."]
ZED = ["XXX", "..X", ".X.", "XXX"]
NOTE = [".XX", ".X.", "XX.", "XX."]
CODE_COLORS = ["#7ec699", "#6fb3f2", "#e6c07b", "#c678dd"]


# ---------------------------------------------------------------- sprites

def compose(mode, t, facing=0, sleepy=False):
    """Return the frame as a list of (x, y, w, h, color) in sprite pixels."""
    out = []

    def r(x, y, w, h, c):
        out.append((x, y, w, h, COL.get(c, c)))

    bx, by = 7, 11       # body top-left; legs end on the bottom row
    dy = 0
    legs = "stand"
    eye_x = facing
    eye_h = 2
    arm_l = arm_r = 2    # arm row relative to body top
    blink = t % 64 in (0, 1)

    if mode == "squash":                     # flattened for a moment after a hard landing
        r(bx - 1, by + 2, 12, 4, "body")
        r(bx + 2, by + 3, 2, 1, "eye")
        r(bx + 6, by + 3, 2, 1, "eye")
        for lx in (1, 3, 6, 8):
            r(bx + lx, by + 6, 1, 1, "body")
        return out

    if sleepy and mode in ("idle", "walk", "coffee"):
        eye_h = 1                            # late at night: heavy eyelids
    if mode == "walk":
        legs = "a" if (t // 3) % 2 == 0 else "b"
    elif mode == "run":
        legs = "a" if (t // 2) % 2 == 0 else "b"
    elif mode == "read":
        dy, legs, eye_x = 2, "none", 0       # eyes peek over the book
        arm_l = arm_r = 2
    elif mode == "coffee":
        eye_x = 0
        sip = t % 70 >= 55
        arm_r = 0 if sip else 2
        if sip:
            eye_h = 1
    elif mode == "exercise":
        eye_x = 0
        if (t // 48) % 2 == 0:               # squats
            down = (t // 6) % 2 == 1
            dy = 1 if down else 0
            arm_l = arm_r = 2 if down else 0
        else:                                # jumping jacks
            up = (t // 5) % 2 == 0
            dy = -2 if up else 0
            arm_l = arm_r = -1 if up else 2
    elif mode == "listen":
        eye_x = 0
        dy = 1 if (t // 6) % 2 else 0        # bobbing to the beat
        eye_h = 1 if (t // 24) % 2 else 2
    elif mode == "present":                  # holding the music panel up
        eye_x = 0
        arm_l = arm_r = -1
    elif mode == "held":
        legs = "dangle"
        arm_l = arm_r = 0
        eye_x = 0
    elif mode == "done":
        hop = [0, 1, 2, 3, 3, 2, 1, 0, 0, 0][t % 10]
        dy = -hop
        if hop:
            arm_l = arm_r = 0
        eye_x = 0
    elif mode == "type":
        eye_h = 1
        eye_x = 0
    elif mode == "think":
        eye_x = 0
        eye_h = 1 if (t // 20) % 3 == 2 else 2
    elif mode == "alert":
        eye_x = 0
        arm_r = -1 if (t // 4) % 2 == 0 else 1
    elif mode == "love":
        eye_x = 0
        arm_l = arm_r = 0 if (t // 4) % 2 == 0 else 1
    elif mode == "hello":
        eye_x = 0
        arm_r = -2 if (t // 3) % 2 == 0 else 0
    elif mode == "oops":
        eye_x = 0
        arm_l = arm_r = 3
    elif mode == "sleep":
        dy = 2                               # sitting, legs tucked under
        arm_l = arm_r = 3
        legs = "none"

    y0 = by + dy
    body = "blushbody" if mode == "love" else "body"
    # body
    r(bx, y0, 10, 5, body)
    # eyes
    if mode == "love":                       # happy ^ ^ eyes and pink cheeks
        for ex in (bx + 2, bx + 7):
            r(ex - 1, y0 + 2, 1, 1, "eye")
            r(ex, y0 + 1, 1, 1, "eye")
            r(ex + 1, y0 + 2, 1, 1, "eye")
        r(bx + 1, y0 + 3, 2, 1, "cheek")
        r(bx + 7, y0 + 3, 2, 1, "cheek")
    elif mode == "sleep":                    # closed eyes
        r(bx + 2, y0 + 2, 2, 1, "eye")
        r(bx + 6, y0 + 2, 2, 1, "eye")
    elif mode == "oops":                     # x x eyes
        for ex in (bx + 2, bx + 7):
            for ddx, ddy in ((-1, 1), (1, 1), (0, 2), (-1, 3), (1, 3)):
                r(ex + ddx, y0 + ddy, 1, 1, "eye")
    elif blink and mode not in ("held", "type"):
        r(bx + 2 + eye_x, y0 + 2, 1, 1, "eye")
        r(bx + 7 + eye_x, y0 + 2, 1, 1, "eye")
    else:
        top = y0 + 1 if eye_h == 2 else y0 + 2
        r(bx + 2 + eye_x, top, 1, eye_h, "eye")
        r(bx + 7 + eye_x, top, 1, eye_h, "eye")
    # arms
    if mode == "type":
        a = (t // 2) % 2
        r(bx - 1, y0 + 2 + a, 1, 2, body)
        r(bx + 10, y0 + 3 - a, 1, 2, body)
    else:
        r(bx - 1, y0 + arm_l, 1, 2, body)
        r(bx + 10, y0 + arm_r, 1, 2, body)
    # legs
    for i, lx in enumerate((1, 3, 6, 8)):
        if legs == "none":
            break
        if legs == "a":
            tall = 2 if i % 2 == 0 else 1
        elif legs == "b":
            tall = 1 if i % 2 == 0 else 2
        else:
            tall = 2
        r(bx + lx, y0 + 5, 1, tall, body)

    if mode == "type":
        off = max(0, 5 - t)                  # laptop slides up from below
        r(8, 14 + off, 8, 3, "screen")
        r(11, 15 + off, 2, 1, "logo")
        r(6, 17 + off, 12, 1, "base")
        if t > 5:                            # little lines of code floating up
            for k in range(3):
                age = (t + k * 5) % 15
                gen = (t + k * 5) // 15
                x = 18 + (gen * 7 + k * 3) % 4
                y = 10 - age // 3
                w = 1 + (gen + k) % 3
                r(x, y, w, 1, CODE_COLORS[(gen + k) % 4])
    elif mode == "think":
        on = (t // 8) % 2 == 0
        c = "bulb" if on else "bulboff"
        r(11, 4, 2, 1, c)
        r(10, 5, 4, 2, c)
        r(11, 7, 2, 1, c)
        r(11, 8, 2, 1, "socket")
        if on:
            for x, y in ((8, 5), (15, 5), (9, 3), (14, 3)):
                r(x, y, 1, 1, "ray")
    elif mode == "alert":
        if (t // 4) % 2 == 0:
            r(11, 4, 2, 4, "bang")
            r(11, 9, 2, 1, "bang")
    elif mode == "love":                     # a heart bobbing above the head
        hy = 5 - (t // 5) % 2
        for yy, line in enumerate(HEART):
            for xx, ch in enumerate(line):
                if ch == "X":
                    r(10 + xx, hy + yy, 1, 1, "heart")
    elif mode == "sleep":                    # z's drifting up and to the right
        for k in range(2):
            age = (t + k * 20) % 40
            zx, zy = 17 + age // 10, 10 - age // 6
            for yy, line in enumerate(ZED):
                for xx, ch in enumerate(line):
                    if ch == "X":
                        r(zx + xx, zy + yy, 1, 1, "zzz")
    elif mode == "oops":                     # a drop of sweat
        if (t // 6) % 2 == 0:
            r(bx + 11, by - 2 + (t // 2) % 3, 1, 2, "sweat")
    elif mode == "read":                     # an open book, a page turning now and then
        r(7, 15, 10, 3, "cover")
        r(8, 15, 4, 2, "page")
        r(12, 15, 4, 2, "page")
        flip = t % 60
        if flip < 8:                         # page lifting from right to left
            r(14 - flip // 2, 14, 2, 1, "page")
    elif mode == "coffee":
        sip = t % 70 >= 55
        mx, my = (bx + 8, y0 + 1) if sip else (bx + 11, y0 + 2)
        r(mx, my, 2, 2, "mug")
        r(mx, my, 2, 1, "coffee")
        r(mx + 2, my, 1, 1, "mug")
        if not sip:
            for k in range(2):
                sy = my - 1 - ((t // 4 + k * 2) % 4)
                r(mx + ((t // 6 + k) % 2), sy, 1, 1, "steam")
    elif mode == "exercise" and (t // 48) % 2 == 0 and t > 150:
        r(bx + 11, by - 1, 1, 2, "sweat")
    elif mode == "listen":                   # notes floating up
        for k in range(2):
            age = (t + k * 18) % 36
            nx, ny = (3 if k else 18) + (age // 12), 9 - age // 5
            for yy, line in enumerate(NOTE):
                for xx, ch in enumerate(line):
                    if ch == "X":
                        r(nx + xx, ny + yy, 1, 1, CODE_COLORS[((t + k * 18) // 36 + k) % 4])
    elif mode == "done" and dy < 0:
        spots = [(3, 7), (20, 6), (5, 3), (18, 2), (12, 3), (2, 10), (21, 10)]
        for k in range(3):
            x, y = spots[(t // 2 + k * 3) % len(spots)]
            r(x, y, 1, 1, "spark")
    return out


def rasterize(rects, scale):
    px = [[(0, 0, 0, 0)] * (COLS * scale) for _ in range(ROWS * scale)]
    for x, y, w, h, c in rects:
        rgb = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
        for yy in range(max(0, y * scale), min(ROWS * scale, (y + h) * scale)):
            for xx in range(max(0, x * scale), min(COLS * scale, (x + w) * scale)):
                px[yy][xx] = rgb
    return px


def png_bytes(pixels):
    h, w = len(pixels), len(pixels[0])
    raw = b"".join(b"\x00" + bytes(c for p in row for c in p) for row in pixels)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def write_preview(path):
    rows = [("idle", 0, 0), ("walk", 0, 1), ("walk", 3, 1), ("walk", 3, -1), ("held", 0, 0),
            ("done", 3, 0), ("type", 0, 0), ("type", 3, 0), ("type", 12, 0), ("type", 19, 0),
            ("think", 0, 0), ("think", 8, 0), ("alert", 0, 0), ("love", 0, 0), ("love", 5, 0),
            ("sleep", 0, 0), ("sleep", 25, 0), ("squash", 0, 0), ("oops", 0, 0), ("hello", 0, 0),
            ("idle", 5, -1), ("idle", 5, 1),
            ("read", 10, 0), ("read", 2, 0), ("coffee", 8, 0), ("coffee", 60, 0), ("exercise", 6, 0),
            ("exercise", 48, 0), ("listen", 4, 0), ("present", 0, 0), ("run", 2, 1)]
    frames = [rasterize(compose(m, t, f), 3) for m, t, f in rows]
    fw, fh = len(frames[0][0]), len(frames[0])
    bg = (40, 40, 40, 255)
    sheet = [[bg] * ((fw + 6) * len(frames)) for _ in range(fh)]
    for i, fr in enumerate(frames):
        for y in range(fh):
            for x in range(fw):
                if fr[y][x][3]:
                    sheet[y][i * (fw + 6) + x] = fr[y][x]
    with open(path, "wb") as f:
        f.write(png_bytes(sheet))


def write_icon(path):
    rects = compose("idle", 5, 0)
    # crop to the character (cols 6..17, rows 11..17) and centre it in 64x64
    px = [[(0, 0, 0, 0)] * 64 for _ in range(64)]
    s = 5
    for x, y, w, h, c in rects:
        rgb = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
        for yy in range((y - 11) * s, (y - 11 + h) * s):
            for xx in range((x - 6) * s, (x - 6 + w) * s):
                X, Y = xx + 2, yy + 14
                if 0 <= X < 64 and 0 <= Y < 64:
                    px[Y][X] = rgb
    data = png_bytes(px)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, 1))
        f.write(struct.pack("<BBBBHHII", 64, 64, 0, 0, 1, 32, len(data), 22))
        f.write(data)


# ---------------------------------------------------------------- windows helpers

user32 = ctypes.windll.user32 if sys.platform == "win32" else None


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


def setup_dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]


def work_area(x, y):
    """Work area (excluding taskbar) of the monitor nearest to the point."""
    mon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    w = mi.rcWork
    return w.left, w.top, w.right, w.bottom


def window_rect(hwnd):
    """Visible frame of a top-level window, or None if it is gone, hidden, minimized or maximized."""
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) \
            or user32.IsZoomed(hwnd):
        return None
    rc = RECT()
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rc), ctypes.sizeof(rc)):
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rc))   # 9 = DWMWA_EXTENDED_FRAME_BOUNDS
    return rc.left, rc.top, rc.right, rc.bottom


def climbable_window():
    """The foreground window if it is a normal app window worth standing on."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    if pid.value == os.getpid():
        return None
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(wintypes.HWND(hwnd), cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return None
    rc = window_rect(hwnd)
    if not rc or rc[2] - rc[0] < W * 2:
        return None
    l, t, r, b = work_area((rc[0] + rc[2]) // 2, rc[1] + 5)
    if rc[1] < t + 10 or rc[1] > b - 160:     # top edge must be on screen and well above the taskbar
        return None
    return hwnd


# ---------------------------------------------------------------- claude code settings

def _load_settings():
    if not os.path.exists(SETTINGS):
        return {}
    with open(SETTINGS, encoding="utf-8") as f:
        text = f.read().strip()
    return json.loads(text) if text else {}


def _save_settings(data):
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    tmp = SETTINGS + ".clauddy-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def _ours(h):
    return isinstance(h, dict) and h.get("type") == "http" and h.get("url") == HOOK_URL


def is_connected():
    try:
        hooks = _load_settings().get("hooks", {})
    except Exception:
        return False
    return any(_ours(h) for groups in hooks.values() if isinstance(groups, list)
               for g in groups if isinstance(g, dict) for h in g.get("hooks", []))


def connect():
    data = _load_settings()
    backup = SETTINGS + ".clauddy-backup"
    if os.path.exists(SETTINGS) and not os.path.exists(backup) \
            and not os.path.exists(SETTINGS + ".claudepet-backup"):   # made under the old name
        with open(SETTINGS, "rb") as src, open(backup, "wb") as dst:
            dst.write(src.read())
    hooks = data.setdefault("hooks", {})
    for ev in HOOK_EVENTS:
        groups = hooks.setdefault(ev, [])
        if any(_ours(h) for g in groups for h in g.get("hooks", [])):
            continue
        group = {"hooks": [{"type": "http", "url": HOOK_URL, "timeout": 2}]}
        if ev in ("PreToolUse", "PostToolUse"):
            group = {"matcher": "*", **group}
        groups.append(group)
    _save_settings(data)


def disconnect():
    data = _load_settings()
    hooks = data.get("hooks", {})
    for ev in list(hooks):
        groups = hooks[ev]
        if not isinstance(groups, list):
            continue
        for g in groups:
            if isinstance(g, dict) and "hooks" in g:
                g["hooks"] = [h for h in g["hooks"] if not _ours(h)]
        hooks[ev] = [g for g in groups if not (isinstance(g, dict) and g.get("hooks") == [])]
        if not hooks[ev]:
            del hooks[ev]
    if not hooks:
        data.pop("hooks", None)
    _save_settings(data)


# ---------------------------------------------------------------- autostart

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'"{sys.executable}"')
        else:
            try:
                winreg.DeleteValue(k, APP)
            except OSError:
                pass


# ---------------------------------------------------------------- event server

events = queue.Queue()
SPOTIFY = None          # media.SpotifyLikes, set in main()


class HookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
        if isinstance(data, dict):
            events.put(data)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_GET(self):                           # the Spotify login comes back here
        path, _, query = self.path.partition("?")
        if path != "/callback" or SPOTIFY is None:
            self.send_response(404)
            self.end_headers()
            return
        ok, msg = SPOTIFY.handle_callback(query)
        if ok:
            events.put({"hook_event_name": "_spotify_connected"})
        page = (f"<!doctype html><meta charset=utf-8><title>clauddy</title>"
                f"<body style='font:16px Segoe UI;background:#1c1b1a;color:#f0eee6;text-align:center;"
                f"padding-top:80px'>{msg}</body>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args):
        pass


def start_server():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), HookHandler)  # raises if already running
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------------------------------------------------------------- the pet

ERROR_LOG = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Clauddy", "error.log")


def log_error(*exc):
    """Appends the current (or given) exception to %APPDATA%\\Clauddy\\error.log."""
    import traceback
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") +
                    "".join(traceback.format_exception(*exc) if exc else traceback.format_exc()) + "\n")
    except OSError:
        pass


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    """How long since the user last touched the keyboard or mouse anywhere."""
    li = LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    if not user32.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0


def is_night():
    h = time.localtime().tm_hour
    return h >= 22 or h < 6


BUTTERFLY = [["XY.YX", "XXBXX", ".XBX.", "..B.."],
             [".Y.Y.", ".XBX.", "..B..", "..B.."]]
BUTTERFLY_COLORS = {"X": COL["wing"], "Y": COL["wing2"], "B": COL["bug"]}


class Butterfly:
    """A tiny butterfly in its own see-through window. He chases it; it never lets him win."""

    def __init__(self, tk, root, x, y, direction):
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-transparentcolor", KEY)
        self.top.config(bg=KEY)
        self.w, self.h = 5 * S, 4 * S
        self.cv = tk.Canvas(self.top, width=self.w, height=self.h, bg=KEY, highlightthickness=0)
        self.cv.pack()
        self.x, self.y, self.dir = float(x), float(y), direction
        self.t0 = time.monotonic()
        self.flee = False
        self.frame = None

    def step(self, area, pet_x, pet_airborne):
        l, t, r, b = area
        age = time.monotonic() - self.t0
        if self.flee:
            self.x += self.dir * 3
            self.y -= 6
        else:
            self.x += self.dir * 2.2 + math.sin(age * 2.3) * 1.5
            self.y = b - 70 + math.sin(age * 1.7) * 35 + math.sin(age * 4.1) * 8
            if pet_airborne and abs(self.x - (pet_x + W / 2)) < 50:
                self.y -= 30                                # dodges at the last moment
            if self.x < l + 20:
                self.dir = 1
            elif self.x > r - 40:
                self.dir = -1
        frame = int(age * 8) % 2
        if frame != self.frame:
            self.frame = frame
            self.cv.delete("all")
            for yy, line in enumerate(BUTTERFLY[frame]):
                for xx, ch in enumerate(line):
                    if ch != ".":
                        self.cv.create_rectangle(xx * S, yy * S, xx * S + S, yy * S + S,
                                                 fill=BUTTERFLY_COLORS[ch], outline="")
        self.top.geometry(f"{self.w}x{self.h}+{int(self.x)}+{int(self.y)}")

    def gone(self, area):
        return self.flee and self.y < area[1] - 40

    def destroy(self):
        self.top.destroy()


class Pet:
    ACT_TIME = {"read": (8, 15), "coffee": (6, 10), "exercise": (5, 8), "listen": (8, 14),
                "chase": (10, 16), "climb": (8, 15)}

    MAX_CLONES = 8

    def __init__(self, media=None, likes=None, leader=None):
        """The first pet is the leader: it owns the tray, the music panels and the event queue.
        Extra pets (clones) get their own little window and copy whatever the leader decides to do."""
        import tkinter as tk
        self.tk = tk
        self.leader = leader
        self.lead = leader or self
        self.clones = []
        if leader is None:
            self.root = tk.Tk()
            self.root.report_callback_exception = log_error   # clicks and menus: log, don't die
            self.win = self.root
        else:
            self.root = leader.root
            self.win = tk.Toplevel(self.root)
        self.win.title(APP)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", KEY)
        self.win.config(bg=KEY)
        self.cv = tk.Canvas(self.win, width=W, height=H, bg=KEY, highlightthickness=0, cursor="hand2")
        self.cv.pack()
        self.media, self.likes = media, likes
        self.panel = self.picker = self.cli = None
        self.frozen = False
        if media and leader is None:
            from panel import MusicPanel
            self.panel = MusicPanel(self.root, media, self.on_heart, self.on_surprise,
                                    is_radio=lambda: self.radio_on)
            from media import SpotifyCLI
            cli = SpotifyCLI()
            if cli.available():
                from picker import LikedPicker
                self.cli = cli
                self.picker = LikedPicker(self.root, self.play_track,
                                          lambda: (self.media.now() or {}).get("title"))

        if leader is None:
            l, t, r, b = work_area(0, 0)    # primary monitor
            self.x, self.y = (l + r) // 2 - W // 2, b - H
        else:                               # clones drop in next to the leader
            self.x, self.y = leader.x + random.choice((-1, 1)) * random.randint(W, 3 * W), leader.y - 250
        now = time.monotonic()
        # physics
        self.vy = None                      # falling speed, None when standing
        self.air_vx = 0.0
        self.arc = None                     # a planned jump: (x0, y0, x1, y1, start, duration, on_land)
        self.surface = self.surface_rc = None   # the window he is standing on
        self.squash_until = 0.0
        # what he is doing
        self.mode, self.t, self.facing = "idle", 0, 0
        self.wander, self.wander_until = "idle", now + 2
        self.agent, self.agent_until, self.pending = None, 0.0, None
        self.act, self.act_until, self.act_end = None, 0.0, now
        self.bfly = None
        self.present_until = 0.0
        self.last_track = None
        self.local_likes = {}
        self.radio_on = False               # "surprise me" radio is playing
        # mouse
        self.drag, self.moved = None, 0
        self.hover_until = 0.0
        self.strokes = []
        self.stroke_x = self.stroke_dir = None
        self.stroke_run = 0
        self.last_ptr = None
        self.pet_block_until = 0.0
        # app
        self.cmds = leader.cmds if leader else queue.Queue()   # actions from the tray and worker threads
        self.hidden = self.closed = False
        self.last_geo = None
        if leader:
            self.vy = 0.0                   # falls into place

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Double-Button-1>", lambda e: self.lead.toggle_panel())
        self.cv.bind("<ButtonPress-3>", lambda e: self.lead.on_menu(e, clicked=self))
        self.cv.bind("<Motion>", self.on_hover)
        self.cv.bind("<Enter>", self.on_enter)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.root.after(TICK, self.tick)
        self.root.after(3000, self.keep_on_top)

    # ------------------------------------------------------------ mouse
    def airborne(self):
        return self.vy is not None or self.arc is not None

    def on_press(self, e):
        self.drag = (e.x_root - self.x, e.y_root - self.y)
        self.moved = 0
        self.vy, self.arc = None, None
        self.surface = None
        self.strokes = []
        self.end_act(jump_down=False, mirror=False)

    def on_motion(self, e):
        if not self.drag:
            return
        nx, ny = e.x_root - self.drag[0], e.y_root - self.drag[1]
        self.moved += abs(nx - self.x) + abs(ny - self.y)
        self.x, self.y = nx, ny
        self.last_ptr = (e.x_root, e.y_root)

    def on_release(self, e):
        self.drag = None
        self.strokes, self.stroke_x = [], None
        self.last_ptr = (e.x_root, e.y_root)
        self.pet_block_until = time.monotonic() + 1.0   # no petting from the drop itself
        if self.moved < 4:                  # a click: little happy hop
            self.set_agent("done", 1.0)
        elif not self.lead.frozen:          # frozen: he stays exactly where he was put
            self.vy, self.air_vx = 0.0, 0.0

    def petting_blocked(self):
        return self.drag is not None or self.airborne() or time.monotonic() < self.pet_block_until

    def pointer_moved(self, x, y):
        """True only if the cursor itself moved (not the pet moving under a still cursor)."""
        moved = self.last_ptr != (x, y)
        self.last_ptr = (x, y)
        return moved

    def on_hover(self, e):
        """Back-and-forth movement over the pet counts as strokes."""
        if self.petting_blocked():
            self.last_ptr, self.stroke_x = (e.x_root, e.y_root), None
            return
        if not self.pointer_moved(e.x_root, e.y_root):
            return
        if self.stroke_x is not None:
            dx = e.x_root - self.stroke_x
            d = (dx > 0) - (dx < 0)
            if d and d != self.stroke_dir:
                if self.stroke_run >= 6:
                    self.stroke()
                self.stroke_dir, self.stroke_run = d, 0
            self.stroke_run += abs(dx)
        self.stroke_x = e.x_root

    def on_enter(self, e):
        x, y = self.root.winfo_pointerxy()
        if self.petting_blocked():
            self.last_ptr = (x, y)
            return
        if self.pointer_moved(x, y):
            self.stroke()

    def stroke(self):
        now = time.monotonic()
        if self.strokes and now - self.strokes[-1] < 0.2:
            return                          # same stroke crossing a gap between legs
        self.strokes = [s for s in self.strokes if now - s < 2.5] + [now]
        if len(self.strokes) >= 3 or now < self.hover_until:
            self.hover_until = now + 2.5    # petted: smile, and keep smiling while petting goes on

    # ------------------------------------------------------------ menus
    def menu_items(self):
        """(label, command, is-checked callable or None) for both the tray and the right-click menu."""
        do = self.cmds.put
        items = []
        if self.panel and self.media.now():
            items.append((t("player"), lambda: do("panel"), None))
        if self.picker:
            items.append((t("liked"), lambda: do("picker"), None))
        items.append((t("freeze"), lambda: do("freeze"), lambda: self.frozen))
        if len(self.clones) < self.MAX_CLONES:
            items.append((t("clone"), lambda: do("clone"), None))
        if self.clones:
            items.append((t("unclone"), lambda: do("unclone"), None))
        if is_connected():
            items.append((t("disconnect"), lambda: do("disconnect"), None))
        else:
            items.append((t("connect"), lambda: do("connect"), None))
        if self.likes and not self.cli:
            if self.likes.connected():
                items.append((t("api_off"), lambda: do("spotify_off"), None))
            else:
                items.append((t("api_on"), lambda: do("spotify_on"), None))
        if getattr(sys, "frozen", False):
            items.append((t("autostart"), lambda: do("autostart"), autostart_enabled))
        items.append((t("language"), lambda: do("language"), None))
        return items

    def on_menu(self, e, clicked=None):
        m = self.menu
        m.delete(0, "end")
        for label, cmd, checked in self.menu_items():
            if checked is None:
                m.add_command(label=label, command=cmd)
            else:
                self._menu_var = self.tk.BooleanVar(master=self.root, value=checked())
                m.add_checkbutton(label=label, command=cmd, variable=self._menu_var)
        if clicked is not None and clicked is not self:
            m.add_command(label=t("unclone_one"), command=lambda: self.cmds.put(("unclone_one", clicked)))
        m.add_separator()
        m.add_command(label=t("hide"), command=lambda: self.cmds.put("toggle"))
        m.add_command(label=t("quit"), command=lambda: self.cmds.put("quit"))
        m.tk_popup(e.x_root, e.y_root)

    def start_tray(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return
        px = rasterize(compose("idle", 5), 1)
        img = Image.new("RGBA", (COLS, ROWS))
        img.putdata([p for row in px for p in row])
        img = img.crop((6, 10, 18, 18)).resize((48, 32), Image.NEAREST)
        icon_img = Image.new("RGBA", (48, 48))
        icon_img.paste(img, (0, 8))
        do = self.cmds.put

        def dynamic():
            yield pystray.MenuItem(lambda i: t("tray_show") if self.hidden else t("tray_hide"),
                                   lambda: do("toggle"), default=True)
            for label, cmd, checked in self.menu_items():
                if checked is None:
                    yield pystray.MenuItem(label, cmd)
                else:
                    yield pystray.MenuItem(label, cmd, checked=lambda i, c=checked: c())
            yield pystray.Menu.SEPARATOR
            yield pystray.MenuItem(lambda i: t("quit"), lambda: do("quit"))

        self.tray = pystray.Icon(APP, icon_img, APP, pystray.Menu(dynamic))
        self.tray.run_detached()

    def run_cmd(self, c):
        from tkinter import messagebox
        if isinstance(c, tuple) and c[0] == "liked":
            _, key, liked = c
            self.local_likes[key] = liked
            if self.panel and key == self.last_track:
                self.panel.liked = liked
            return
        if isinstance(c, tuple) and c[0] == "tracks":
            self.picker.set_tracks(c[1])
            return
        if isinstance(c, tuple) and c[0] == "tracks_failed":
            self.picker.error(c[1])
            return
        if isinstance(c, tuple) and c[0] == "unclone_one":
            if c[1] in self.clones:
                self.clones.remove(c[1])
                c[1].destroy()
            return
        if c == "radio_failed":
            messagebox.showinfo(APP, t("radio_failed"))
            return
        if c == "no_spotify_window":
            messagebox.showinfo(APP, t("no_spotify"))
            return
        if c == "toggle":
            self.hidden = not self.hidden
            for p in [self] + self.clones:
                if self.hidden:
                    p.win.withdraw()
                else:
                    p.win.deiconify()
                    p.win.attributes("-topmost", True)
            if self.hidden:
                if self.panel:
                    self.panel.hide()
                if self.picker:
                    self.picker.hide()
        elif c == "freeze":
            self.frozen = not self.frozen
            for p in [self] + self.clones:
                if self.frozen:
                    p.end_act(jump_down=False, mirror=False)
                    p.vy = p.arc = None         # stop mid-air too
                elif not p.surface:
                    p.vy = 0.0                  # thawed: gravity is back
        elif c == "clone":
            if len(self.clones) < self.MAX_CLONES:
                self.clones.append(Pet(self.media, self.likes, leader=self))
        elif c == "unclone":
            for p in self.clones:
                p.destroy()
            self.clones = []
        elif c == "language":
            i18n.set_lang("en" if i18n.LANG == "ru" else "ru")
            for ui in (self.picker, self.panel):
                if ui and ui.visible:
                    ui.redraw() if ui is self.panel else ui.draw()
            if getattr(self, "tray", None):
                self.tray.update_menu()
        elif c == "picker":
            if self.picker.visible:
                self.picker.hide()
            else:
                self.open_picker()
        elif c == "connect":
            self.do_connect()
        elif c == "disconnect":
            self.do_disconnect()
        elif c == "autostart":
            set_autostart(not autostart_enabled())
        elif c == "panel":
            self.toggle_panel()
        elif c == "panel_open":
            self.open_panel(pinned=True)
        elif c == "spotify_on":
            self.connect_spotify()
        elif c == "spotify_off":
            self.likes.disconnect()
            if self.panel:
                self.panel.liked = None
        elif c == "spotify_ready":
            messagebox.showinfo(APP, t("spotify_ready"))
            self.refresh_like()
        elif c == "quit":
            self.quit()

    def quit(self):
        self.closed = True
        if getattr(self, "tray", None):
            self.tray.stop()
        self.root.destroy()

    def destroy(self):
        """Removes a clone (the leader quits instead)."""
        self.closed = True
        if self.bfly and self.leader is None:
            self.bfly.destroy()
        self.win.destroy()

    def do_connect(self):
        from tkinter import messagebox
        try:
            connect()
            messagebox.showinfo(APP, t("connected"))
        except Exception as ex:
            messagebox.showerror(APP, t("settings_error", path=SETTINGS, err=ex))

    def do_disconnect(self):
        from tkinter import messagebox
        try:
            disconnect()
            messagebox.showinfo(APP, t("disconnected"))
        except Exception as ex:
            messagebox.showerror(APP, t("settings_error", path=SETTINGS, err=ex))

    def keep_on_top(self):
        if self.closed:
            return
        self.win.attributes("-topmost", True)
        self.root.after(3000, self.keep_on_top)

    # ------------------------------------------------------------ spotify
    def toggle_panel(self):
        if not self.panel:
            return
        if self.panel.visible:
            self.panel.hide()
        else:
            self.open_panel(pinned=True)

    def open_panel(self, pinned):
        st = self.media.now()
        if not st or self.hidden:
            return
        self.end_act()
        self.panel.show(pinned)
        self.present_until = time.monotonic() + 1.0
        self.panel.draw(st)
        if self.panel.liked is None:
            self.refresh_like()

    def open_picker(self):
        """Our own Liked Songs list above his head; picking a track plays it."""
        if not self.picker:
            return
        if self.panel:
            self.panel.hide()
        self.end_act()
        self.picker.show()
        self.present_until = time.monotonic() + 1.0
        self.picker.place(self.x, self.y, W, work_area(self.x + W // 2, self.y + H // 2))
        if self.picker.needs_refresh():
            self.picker.loading()

            def work():
                try:
                    self.cmds.put(("tracks", self.cli.liked_tracks()))
                except Exception as ex:
                    self.cmds.put(("tracks_failed", str(ex)))

            threading.Thread(target=work, daemon=True).start()

    def play_track(self, track):
        """Plays a track picked from the list inside Liked Songs, so skipping and shuffle keep working."""
        self.picker.hide()
        self.set_agent("type", 3)                   # he "types" the request into Spotify
        self.radio_on = False

        def work():
            try:
                self.cli.play_liked(track["uri"])
                time.sleep(1.0)                     # let the media session catch up
                self.cmds.put("panel_open")
            except Exception as ex:
                self.cmds.put(("tracks_failed", str(ex)))

        threading.Thread(target=work, daemon=True).start()

    def on_surprise(self):
        """'Surprise me' starts a radio from the track playing right now; the same button then stops it."""
        if not self.cli:
            self.cmds.put("radio_failed")
            return
        stopping = self.radio_on
        self.set_agent("think", 6)                  # the bulb while he picks something

        def work():
            try:
                if stopping:                        # back to Liked Songs, shuffle stays as it was
                    self.cli.play_liked()
                    self.radio_on, ok = False, True
                else:
                    ok = self.cli.radio()
                    self.radio_on = ok
            except Exception:
                ok = False
            self.agent = None
            if ok and not stopping:
                self.hover_until = time.monotonic() + 1.5   # pleased with himself
            if not ok:
                self.cmds.put("radio_failed")

        threading.Thread(target=work, daemon=True).start()

    def check_radio(self):
        """After a track change: if Spotify is playing a named context again (Liked Songs, a playlist),
        the radio was left some other way and the button should say 'surprise me' again."""
        if not (self.cli and self.radio_on):
            return

        def work():
            try:
                time.sleep(1.5)
                cp = self.cli.run("now-playing").get("currently_playing") or {}
                if cp.get("context_description"):
                    self.radio_on = False
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def refresh_like(self, delay=0.0):
        key = self.last_track
        if not key:
            return
        if self.cli:
            def check():
                uri = self.cli.now_uri()
                return uri and self.cli.is_liked(uri)
        elif self.likes and self.likes.connected():
            def check():
                tid = self.likes.current_track()
                return tid and self.likes.is_liked(tid)
        else:
            return

        def work():
            time.sleep(delay)
            try:
                liked = check()
                if liked is not None:
                    self.cmds.put(("liked", key, bool(liked)))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def on_heart(self):
        use_api = self.likes and self.likes.connected()
        if self.panel.liked and not (self.cli or use_api):
            return                                  # Alt+Shift+B can only add; removing is done in Spotify
        key, new = self.last_track, not self.panel.liked
        self.panel.liked = new                      # feels instant; corrected if Spotify says no
        if new:
            self.hover_until = time.monotonic() + 2.0
        if self.picker:
            self.picker.tracks_at = 0.0             # the list changed: reload it next time

        def work():
            ok = False
            try:
                if self.cli:                        # Spotify's own CLI: works with free accounts
                    uri = self.cli.now_uri()
                    if uri:
                        self.cli.set_liked(uri, new)
                        ok = True
                elif use_api:                       # Premium + Web API
                    tid = self.likes.current_track()
                    ok = bool(tid) and self.likes.set_liked(tid, new)
                else:                               # last resort: Spotify's Alt+Shift+B
                    from media import like_via_shortcut
                    ok = like_via_shortcut()
                    if not ok:
                        self.cmds.put("no_spotify_window")
            except Exception:
                ok = False
            self.cmds.put(("liked", key, new if ok else not new))

        threading.Thread(target=work, daemon=True).start()

    def connect_spotify(self):
        from tkinter import simpledialog
        import webbrowser
        webbrowser.open("https://developer.spotify.com/dashboard")
        cid = simpledialog.askstring(
            APP,
            t("client_id"),
            initialvalue=self.likes.client_id, parent=self.root)
        if cid and cid.strip():
            self.likes.start_login(cid)

    # ------------------------------------------------------------ claude code events
    def set_agent(self, state, seconds):
        self.agent = state
        self.agent_until = time.monotonic() + seconds
        self.pending = None

    def on_event(self, d):
        ev = d.get("hook_event_name", "")
        if ev == "_spotify_connected":
            self.cmds.put("spotify_ready")
            return
        if ev not in ("Stop", "SessionEnd"):
            self.end_act()                          # work comes first: drop whatever he was doing
        if ev == "SessionStart":
            self.set_agent("hello", 2.5)
        elif ev == "PostToolUseFailure":            # a tool failed: x x, sweat, then back to thinking
            self.set_agent("oops", 2)
            self.pending = ("think", time.monotonic() + 2)
        elif ev == "UserPromptSubmit":
            self.set_agent("think", 120)
        elif ev == "PreToolUse":                    # any tool means work: laptop out
            self.set_agent("type", 120)
        elif ev == "PostToolUse":
            # keep typing through quick tool chains; only a real pause between tools,
            # while the model reasons about the next step, turns the bulb on
            self.set_agent("type", 120)
            self.pending = ("think", time.monotonic() + 4)
        elif ev == "Notification":
            self.set_agent("alert", 120)
        elif ev == "Stop":
            self.set_agent("done", 3)
        elif ev == "SessionEnd":
            self.agent = None
        for c in self.clones:                       # the whole gang reacts together
            c.on_event(d)

    # ------------------------------------------------------------ activities
    def choose_next(self, now, music):
        night = is_night()
        if now - self.act_end > 20 and random.random() < 0.4:
            w = {"read": 4 if night else 3, "coffee": 6 if 6 <= time.localtime().tm_hour < 12 else 2,
                 "exercise": 0 if night else 2, "chase": 2, "climb": 2, "splat": 1}
            if music:
                w["listen"], w["panel"] = 4, 2
            names = [k for k in w if w[k]]
            name = random.choices(names, weights=[w[k] for k in names])[0]
            self.start_act(name, now)
            if self.act or self.airborne() or (self.panel and self.panel.visible):
                for c in self.clones:               # clones copy the leader
                    if name != "panel" and c.on_ground():
                        c.start_act(name, now)
                        c.act_until = self.act_until
                return
        if self.wander == "idle" or random.random() < 0.3:
            self.wander, self.facing = "walk", random.choice((-1, 1))
            self.wander_until = now + random.uniform(2, 6)
        else:
            self.wander = "idle"
            self.wander_until = now + random.uniform(2, 5)
        for c in self.clones:
            c.wander, c.facing, c.wander_until = self.wander, self.facing, self.wander_until

    def on_ground(self):
        return not (self.drag or self.airborne() or self.act)

    def start_act(self, name, now):
        if name == "splat":                         # a big jump straight up, then splat
            self.vy, self.air_vx = -26.0, 0.0
            self.act_end = now
            return
        if name == "panel":
            self.open_panel(pinned=False)
            self.act_end = now
            return
        if name == "climb":
            hwnd = climbable_window()
            if not hwnd:
                return
            rc = window_rect(hwnd)
            tx = min(max(self.x, rc[0]), rc[2] - W)
            self.jump_to(tx, rc[1] - H, lambda: self.land_on(hwnd))
        if name == "chase":
            if self.leader:                         # everyone chases the leader's butterfly
                self.bfly = self.leader.bfly
                if not self.bfly:
                    return
            else:
                l, t, r, b = work_area(self.x + W // 2, self.y + H // 2)
                side = random.choice((-1, 1))
                bx = min(max(self.x + side * 300, l + 30), r - 50)
                self.bfly = Butterfly(self.tk, self.root, bx, b - 90, side)
        lo, hi = self.ACT_TIME[name]
        self.act, self.act_until = name, now + random.uniform(lo, hi)

    def end_act(self, jump_down=True, mirror=True):
        if self.bfly:
            if self.leader is None:                 # only the leader owns the butterfly
                self.bfly.destroy()
            self.bfly = None
        if self.act == "climb" and self.surface and jump_down:
            self.surface = None
            self.vy, self.air_vx = -10.0, self.facing * 2.0
        if self.act:
            self.act_end = time.monotonic()
        self.act = None
        if mirror:
            for c in self.clones:
                c.end_act(jump_down, mirror=False)

    def jump_to(self, x1, y1, on_land):
        dist = math.hypot(x1 - self.x, y1 - self.y)
        self.arc = (self.x, self.y, x1, y1, time.monotonic(), 0.35 + dist / 1800, on_land)

    def land_on(self, hwnd):
        rc = window_rect(hwnd)
        if rc:
            self.surface, self.surface_rc = hwnd, rc
        else:
            self.vy = 0.0

    def step_act(self, now, lo, hi):
        """One tick of the current activity. Returns the animation to show."""
        act = self.act
        if act == "chase":
            b = self.bfly
            if now > self.act_until and not b.flee:
                b.flee = True
            if b.gone(work_area(b.x, max(b.y, 0))):
                self.end_act()
                return "idle"
            dx = (b.x + b.w / 2) - (self.x + W / 2)
            if abs(dx) < 8 or b.flee:
                return "idle"
            self.facing = 1 if dx > 0 else -1
            self.x += self.facing * SPEED * 2
            ground = work_area(self.x + W // 2, self.y + H // 2)[3]
            if abs(dx) < 40 and b.y > ground - 100 and random.random() < 0.08:
                self.vy, self.air_vx = -14.0, self.facing * 2.0   # leap for it
            return "run"
        if act == "climb":
            if now > self.act_until:
                self.end_act()
                return "held"
            self.x += self.facing * SPEED
            if self.x <= lo:
                self.x, self.facing = lo, 1
            elif self.x >= hi:
                self.x, self.facing = hi, -1
            return "walk"
        if now > self.act_until:
            self.end_act()
            return "idle"
        return act

    # ------------------------------------------------------------ main loop
    def tick(self):
        """One frame. A bug in any part of it is logged and the pet keeps going."""
        if self.closed:
            return
        try:
            self.step()
        except Exception:
            log_error()
        if not self.closed:
            self.root.after(TICK, self.tick)

    def step(self):
        now = time.monotonic()
        st = None
        if self.leader is None:                     # shared work happens once, in the leader
            while not self.cmds.empty():
                self.run_cmd(self.cmds.get_nowait())
                if self.closed:
                    return
            while not events.empty():
                self.on_event(events.get_nowait())
            st = self.media.now() if self.media else None
            self.track_music(st)
            if self.bfly:
                self.bfly.step(work_area(self.bfly.x, self.bfly.y), self.x, self.airborne())
        if self.pending and now >= self.pending[1]:
            self.set_agent(self.pending[0], 60)
        if self.agent and now > self.agent_until:
            self.agent = None

        if self.drag:
            mode = "held"
        elif self.arc:
            x0, y0, x1, y1, t0, dur, on_land = self.arc
            f = min(1.0, (now - t0) / dur)
            self.x = x0 + (x1 - x0) * f
            self.y = y0 + (y1 - y0) * f - 120 * 4 * f * (1 - f)
            if f >= 1:
                self.arc = None
                on_land()
            mode = "held"
        elif self.vy is not None:
            l, t, r, b = work_area(self.x + W // 2, self.y + H // 2)
            self.vy = min(self.vy + 2.5, 40)
            self.y += self.vy
            self.x = min(max(self.x + self.air_vx, l), r - W)
            if self.y >= b - H:
                if self.vy >= 25:                   # dropped from high up: splat
                    self.squash_until = now + 0.4
                self.y, self.vy = b - H, None
            mode = "held"
        else:
            mode = self.ground_tick(now, st)

        if mode != self.mode:
            self.mode, self.t = mode, 0
        else:
            self.t += 1
        area = work_area(self.x + W // 2, self.y + H // 2)
        if self.panel and self.panel.visible:
            if self.panel.should_close(st):
                self.panel.hide()
            else:
                if self.t % 3 == 0 and st:          # between tracks Spotify briefly reports nothing
                    self.panel.draw(st)
                self.panel.place(self.x, self.y, W, area)
        if self.picker and self.picker.visible:
            self.picker.place(self.x, self.y, W, area)
            if self.t % 10 == 0:
                self.picker.draw()                  # keeps the playing track highlighted
        self.draw()

    def track_music(self, st):
        if not self.panel:
            return
        key = st["key"] if st else None
        if key == self.last_track:
            return
        changed = self.last_track is not None and key is not None
        self.last_track = key
        self.panel.liked = self.local_likes.get(key)   # what we know from earlier clicks on this track
        if key:
            self.refresh_like(delay=1.5)            # give Spotify a moment to agree on the new track
            self.check_radio()
        if changed and st["playing"] and not self.agent and not self.airborne() and random.random() < 0.5:
            self.open_panel(pinned=False)

    def ground_tick(self, now, st):
        frozen = self.lead.frozen
        if frozen:                                  # stays exactly where it was put
            ground, lo, hi = self.y, self.x, self.x
        elif self.surface:
            rc = window_rect(self.surface)
            if not rc:                              # the window went away under him: fall
                self.surface = None
                self.end_act(jump_down=False)
                self.vy, self.air_vx = 0.0, 0.0
                return "held"
            self.x += rc[0] - self.surface_rc[0]   # ride along if the window moves
            self.surface_rc = rc
            ground, lo, hi = rc[1] - H, rc[0], rc[2] - W
        else:
            l, t, r, b = work_area(self.x + W // 2, self.y + H // 2)
            ground, lo, hi = b - H, l, r - W
        self.y = ground

        lp = self.lead
        music_ui = (lp.panel and lp.panel.visible) or (lp.picker and lp.picker.visible)
        if now < self.squash_until:
            mode = "squash"
        elif now < self.hover_until and self.agent != "done":
            mode = "love"
        elif self.agent:
            mode = self.agent
        elif music_ui:
            mode = "present" if now < lp.present_until else "listen"
        elif idle_seconds() > (60 if is_night() else SLEEP_AFTER):
            self.end_act(mirror=False)
            mode = "sleep"
        elif frozen:
            mode = "idle"
        elif self.act:
            mode = self.step_act(now, lo, hi)
        else:
            if self.leader is None and now > self.wander_until:
                self.choose_next(now, bool(st and st["playing"]))
            mode = self.wander
            if self.act:
                mode = "idle"
            elif mode == "walk":
                self.x += self.facing * SPEED
                if self.x <= lo:
                    self.x, self.facing = lo, 1
                elif self.x >= hi:
                    self.x, self.facing = hi, -1
        if not self.airborne():
            self.x = min(max(self.x, lo), hi)
        return mode

    def draw(self):
        geo = f"{W}x{H}+{int(self.x)}+{int(self.y)}"
        if geo != self.last_geo:
            self.win.geometry(geo)
            self.last_geo = geo
        self.cv.delete("all")
        facing = 0
        if self.mode in ("walk", "run"):
            facing = self.facing
        elif self.mode == "idle":               # eyes follow the cursor
            dx = self.root.winfo_pointerx() - (self.x + W / 2)
            facing = 1 if dx > 60 else -1 if dx < -60 else 0
        for x, y, w, h, c in compose(self.mode, self.t, facing, sleepy=is_night()):
            self.cv.create_rectangle(x * S, y * S, (x + w) * S, (y + h) * S, fill=c, outline="")

    def run(self):
        self.start_tray()
        self.root.mainloop()


def main():
    global SPOTIFY
    if len(sys.argv) == 3 and sys.argv[1] == "--preview":
        write_preview(sys.argv[2])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--icon":
        write_icon(sys.argv[2])
        return
    setup_dpi()
    media = None
    try:
        from media import MediaWatcher, SpotifyLikes
        media, SPOTIFY = MediaWatcher(), SpotifyLikes()
    except Exception:
        pass
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":    # checks the bundled music support
        time.sleep(3)
        st = media.now() if media else None
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(f"media={bool(media)} track={st and st['title']!r} cover={bool(st and st['thumb'])}\n")
        return
    try:
        start_server()
    except OSError:
        return                              # already running
    Pet(media, SPOTIFY).run()


if __name__ == "__main__":
    main()
