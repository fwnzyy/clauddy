"""What Spotify is playing (via Windows media sessions) and liking tracks (via the Spotify Web API).

Track info, cover, timeline and play/pause/next/prev come from Windows itself and need no login.
Adding to Liked Songs needs the user's own Spotify app Client ID and a one-time login in the browser
(OAuth with PKCE: no secret is stored, only the user's tokens in %APPDATA%\\Clauddy\\spotify.json).
"""
import asyncio
import base64
import hashlib
import json
import os
import queue
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from i18n import t

CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Clauddy")
PLAYING = 4   # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
REPEAT_MODES = {0: "off", 1: "track", 2: "context"}   # MediaPlaybackAutoRepeatMode: none, track, list
REPEAT_NEXT = {"off": "context", "context": "track", "track": "off"}


def _repeat_value(info):
    try:
        mode = info.auto_repeat_mode
        return int(mode) if mode is not None else 0
    except Exception:
        return 0


def _quietly(fn):
    try:
        fn()
    except Exception:
        pass


def _crop_frame(png):
    """Cuts the black frame and the Spotify logo strip off a Windows media thumbnail."""
    import io
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("RGB")
        top = im.crop((0, 0, im.width, int(im.height * 0.78)))   # the logo sits in the bottom fifth
        box = top.point(lambda v: 255 if v > 24 else 0).convert("L").getbbox()
        if box:
            im = im.crop(box)
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    except Exception:
        return png


class MediaWatcher:
    """Polls the Spotify media session once a second on its own asyncio thread."""

    def __init__(self):
        self.state = None
        self.session = None
        cli = SpotifyCLI()
        self.cli = cli if cli.available() else None
        self.cover_tries = {}                # track key -> attempts at a clean cover
        self.mode_override = None            # (shuffle, repeat, wall time) right after we change them
        self.jobs = None                     # serial queue of CLI calls
        self.seek_override = None           # (position, wall time) until Spotify reports the new spot
        self.lock = threading.Lock()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._poll())

    async def _poll(self):
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
            mgr = await Manager.request_async()
        except Exception:
            return                                  # no media API here: the music features stay off
        while True:
            try:
                await self._update(mgr)
            except Exception:
                self.session = None
                self._set(None)
            await asyncio.sleep(1)

    async def _update(self, mgr):
        s = next((x for x in mgr.get_sessions()
                  if "spotify" in (x.source_app_user_model_id or "").lower()), None)
        self.session = s
        if s is None:
            self._set(None)
            return
        p = await s.try_get_media_properties_async()
        tl = s.get_timeline_properties()
        key = (p.title or "", p.artist or "")
        old = self.state
        thumb = old["thumb"] if old and old["key"] == key else None
        if thumb is None:
            thumb = await self._clean_cover(key, p.thumbnail)
        pos, updated = tl.position.total_seconds(), tl.last_updated_time.timestamp()
        ov = self.seek_override
        if ov and updated < ov[1] and time.time() - ov[1] < 3:
            pos, updated = ov                       # Spotify hasn't caught up with our seek yet
        info = s.get_playback_info()
        shuffle, repeat = bool(info.is_shuffle_active), REPEAT_MODES.get(_repeat_value(info), "off")
        mo = self.mode_override
        if mo and time.time() - mo[2] < 5:          # we just changed these: trust ourselves for a moment
            shuffle, repeat = mo[0], mo[1]
        self._set({
            "key": key, "title": key[0], "artist": key[1],
            "playing": int(info.playback_status) == PLAYING,
            "pos": pos, "end": tl.end_time.total_seconds(),
            "updated": updated, "thumb": thumb,
            "shuffle": shuffle, "repeat": repeat,
        })

    async def _clean_cover(self, key, ref):
        """The Windows thumbnail from Spotify comes framed in black with a Spotify logo, so prefer
        the real album art; after a few misses fall back to the thumbnail with the frame cut off."""
        tries = self.cover_tries.get(key, 0)
        if self.cli and tries < 3:
            self.cover_tries[key] = tries + 1
            try:
                art = await asyncio.get_running_loop().run_in_executor(None, self.cli.cover, key[0])
                if art:
                    return art
            except Exception:
                pass
            return None                              # try again on the next poll
        raw = await self._read_thumb(ref) if ref else None
        return _crop_frame(raw) if raw else None

    @staticmethod
    async def _read_thumb(ref):
        from winrt.windows.storage.streams import Buffer, InputStreamOptions
        try:
            stream = await ref.open_read_async()
            buf = Buffer(stream.size)
            await stream.read_async(buf, stream.size, InputStreamOptions.READ_AHEAD)
            return bytes(buf)
        except Exception:
            return None

    def _set(self, st):
        with self.lock:
            self.state = st

    def now(self):
        """Snapshot with the playback position moved on to the present moment."""
        with self.lock:
            st = dict(self.state) if self.state and self.state["title"] else None
        if st and st["playing"]:
            st["pos"] = min(st["end"], st["pos"] + max(0.0, time.time() - st["updated"]))
        return st

    def seek(self, seconds):
        s = self.session
        if s is None:
            return
        self.seek_override = (seconds, time.time())
        with self.lock:
            if self.state:
                self.state["pos"], self.state["updated"] = self.seek_override

        async def go():
            await s.try_change_playback_position_async(int(seconds * 10_000_000))   # 100 ns ticks

        asyncio.run_coroutine_threadsafe(go(), self.loop)

    def toggle_shuffle(self):
        st = self.now()
        if not st:
            return
        on = not st["shuffle"]
        self._remember_modes(on, st["repeat"])
        self._in_background(lambda: self.cli.run("shuffle", "on" if on else "off"),
                            lambda s: s.try_change_shuffle_active_async(on))

    def cycle_repeat(self):
        """off -> repeat the album/playlist -> repeat the track -> off."""
        st = self.now()
        if not st:
            return
        mode = REPEAT_NEXT[st["repeat"]]
        self._remember_modes(st["shuffle"], mode)

        def smtc(s):
            from winrt.windows.media import MediaPlaybackAutoRepeatMode as R
            return s.try_change_auto_repeat_mode_async(
                {"off": R.NONE, "track": R.TRACK, "context": R.LIST}[mode])

        self._in_background(lambda: self.cli.run("repeat", mode), smtc)

    def _remember_modes(self, shuffle, repeat):
        self.mode_override = (shuffle, repeat, time.time())
        with self.lock:
            if self.state:
                self.state["shuffle"], self.state["repeat"] = shuffle, repeat

    def _in_background(self, with_cli, with_smtc):
        """Spotify's CLI if we have it, otherwise the Windows media session.
        CLI calls go through one worker so quick clicks reach Spotify in the order they were made."""
        if self.cli:
            if self.jobs is None:
                self.jobs = queue.Queue()

                def worker():
                    while True:
                        _quietly(self.jobs.get())
                        time.sleep(0.7)        # back-to-back commands make Spotify drop the earlier one

                threading.Thread(target=worker, daemon=True).start()
            self.jobs.put(with_cli)
        elif self.session is not None:
            s = self.session

            async def go():
                await with_smtc(s)

            asyncio.run_coroutine_threadsafe(go(), self.loop)

    def control(self, what):
        s = self.session
        if s is None:
            return

        async def go():
            if what == "toggle":
                await s.try_toggle_play_pause_async()
            elif what == "next":
                await s.try_skip_next_async()
            elif what == "prev":
                await s.try_skip_previous_async()

        asyncio.run_coroutine_threadsafe(go(), self.loop)


class SpotifyCLI:
    """Spotify's own command-line tool that ships with the desktop app (signed by Spotify AB).

    Talks to the running Spotify app, so it works with free accounts: Liked Songs, likes, play by URI.
    """

    def __init__(self):
        self.path = os.path.join(os.environ.get("APPDATA", ""), "Spotify", "spotify_cli.exe")
        self.user = None

    def available(self):
        return os.path.exists(self.path)

    def run(self, *args, timeout=15):
        import subprocess
        out = subprocess.run([self.path, *args, "--format", "json"], capture_output=True, timeout=timeout,
                             encoding="utf-8", errors="replace", creationflags=0x08000000)  # CREATE_NO_WINDOW
        if out.returncode != 0:
            raise RuntimeError((out.stderr or out.stdout).strip() or "spotify_cli failed")
        text = out.stdout.strip()
        try:
            return json.loads(text) if text else {}
        except ValueError:                  # some commands ("queue add") answer in plain text
            return {"text": text}

    def liked_tracks(self):
        if not self.user:
            self.user = self.run("me")["username"]
        d = self.run("playlist", "get", f"spotify:user:{self.user}:collection", "--limit", "10000")
        return [{"uri": t["uri"], "title": t["name"], "artist": ", ".join(t.get("artists", []))}
                for t in d.get("tracks", []) if t.get("type") == "track"]

    def now_uri(self):
        cp = self.run("now-playing").get("currently_playing") or {}
        uri = cp.get("uri", "")
        return uri if uri.startswith("spotify:track:") else None

    def is_liked(self, uri):
        return bool(self.run("library", "contains", uri).get("contains", {}).get(uri))

    def set_liked(self, uri, on):
        self.run("library", "add" if on else "remove", uri)

    def play(self, uri):
        self.run("play", uri)

    def queue_add(self, uri):
        self.run("queue", "add", uri)

    def next(self):
        self.run("next")

    def liked_uri(self):
        if not self.user:
            self.user = self.run("me")["username"]
        return f"spotify:user:{self.user}:collection"

    def play_liked(self, start_uri=None):
        """Plays Liked Songs as the context, optionally starting from one of its tracks.

        The CLI can't start a context at a given track, so the track is queued and skipped to:
        afterwards Spotify carries on inside Liked Songs (shuffled if shuffle is on) instead of
        falling back to a radio, which is what happens after a lone track."""
        self.run("play", self.liked_uri())
        if start_uri:
            time.sleep(0.7)
            self.queue_add(start_uri)
            time.sleep(0.7)
            self.next()

    def unqueue(self, uris):
        """Removes the given tracks from the up-next queue (only what we put there ourselves)."""
        if not uris:
            return
        items = self.run("queue", "list").get("next_tracks", [])
        for pos in range(len(items) - 1, -1, -1):        # from the end, so positions stay valid
            it = items[pos]
            if it.get("provider") == "queue" and it.get("uri") in uris:
                self.run("queue", "remove", str(pos))

    def radio(self):
        """Starts a radio (Spotify's endless mix) based on the track that is playing right now."""
        uri = self.now_uri()
        if not uri:
            return False
        tid = uri.split(":")[-1]
        for station in (f"spotify:station:track:{tid}", f"spotify:radio:track:{tid}"):
            try:
                self.run("play", station)               # Spotify takes it and plays similar tracks
                return True
            except RuntimeError:
                continue                               # older apps know only the second form
        return False

    def cover(self, title):
        """Clean 300px album art of the playing track, or None if Spotify is on another track already."""
        uri = self.now_uri()
        if not uri:
            return None
        ent = (self.run("lookup", uri).get("entities") or [{}])[0]
        url = ent.get("image_url", "")
        if ent.get("name") != title or "i.scdn.co/image/" not in url:
            return None
        # ab67616d00004851... is the 64px size; ab67616d00001e02... is the 300px one
        url = url.replace("ab67616d00004851", "ab67616d00001e02")
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()


def _spotify_window():
    """Main window of the Spotify desktop app, or None."""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    found = []

    def exe_of(hwnd):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = k.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        buf, n = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
        k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
        k.CloseHandle(h)
        return os.path.basename(buf.value).lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if u.GetWindowTextLengthW(hwnd) and u.GetParent(hwnd) == 0 and exe_of(hwnd) == "spotify.exe":
            cls = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(hwnd, cls, 64)
            if cls.value.startswith("Chrome_WidgetWin"):
                found.append(hwnd)
                return False
        return True

    u.EnumWindows(each, 0)
    return found[0] if found else None


def like_via_shortcut(press=True):
    """Adds the current track to Liked Songs with Spotify's own Alt+Shift+B, then gives focus back.

    Works with free Spotify accounts: no Web API needed. The shortcut only adds (pressing it again
    does not remove). Returns False if the app window isn't found.
    """
    import ctypes
    u = ctypes.windll.user32
    hwnd = _spotify_window()
    if not hwnd:
        return False
    before = u.GetForegroundWindow()
    above = _window_above(hwnd)                               # to put Spotify back where it was
    minimized = u.IsIconic(hwnd)
    if minimized:
        u.ShowWindow(hwnd, 4)                                 # SW_SHOWNOACTIVATE
    u.keybd_event(0x12, 0, 0, 0)                              # a tap of Alt lets us take the foreground
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.25)
    ok = u.GetForegroundWindow() == hwnd
    if ok and press:
        for vk in (0x12, 0x10, 0x42):                         # Alt, Shift, B
            u.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        for vk in (0x42, 0x10, 0x12):
            u.keybd_event(vk, 0, 2, 0)
        time.sleep(0.15)
    if minimized:
        u.ShowWindow(hwnd, 6)                                 # SW_MINIMIZE
    if before and before != hwnd:
        u.SetForegroundWindow(before)
    if above and not minimized:
        # slide Spotify back under the window that covered it (e.g. Claude on the other monitor)
        u.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(above), 0, 0, 0, 0,
                       0x0001 | 0x0002 | 0x0010)              # NOSIZE | NOMOVE | NOACTIVATE
    return ok


def _window_above(hwnd):
    """The nearest visible, normal (not always-on-top) window above hwnd in the z-order, or None."""
    import ctypes
    u = ctypes.windll.user32
    u.GetWindow.restype = ctypes.c_void_p
    h = u.GetWindow(ctypes.c_void_p(hwnd), 3)                # GW_HWNDPREV
    while h:
        if u.IsWindowVisible(ctypes.c_void_p(h)) and not u.IsIconic(ctypes.c_void_p(h)) \
                and u.GetWindowTextLengthW(ctypes.c_void_p(h)) \
                and not (u.GetWindowLongW(ctypes.c_void_p(h), -20) & 0x8):   # GWL_EXSTYLE & WS_EX_TOPMOST
            return h
        h = u.GetWindow(ctypes.c_void_p(h), 3)
    return None


class SpotifyLikes:
    REDIRECT = "http://127.0.0.1:47613/callback"
    SCOPES = "user-library-read user-library-modify user-read-currently-playing"

    def __init__(self):
        self.path = os.path.join(CONFIG_DIR, "spotify.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self.verifier = self.oauth_state = None
        self.lock = threading.Lock()

    def _save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    @property
    def client_id(self):
        return self.data.get("client_id", "")

    def connected(self):
        return bool(self.data.get("refresh_token"))

    def disconnect(self):
        for k in ("access_token", "refresh_token", "expires_at"):
            self.data.pop(k, None)
        self._save()

    # -- login
    def start_login(self, client_id):
        self.data["client_id"] = client_id.strip()
        self._save()
        self.verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b"=").decode()
        self.oauth_state = secrets.token_urlsafe(16)
        q = urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": self.REDIRECT,
            "code_challenge_method": "S256", "code_challenge": challenge,
            "scope": self.SCOPES, "state": self.oauth_state,
        })
        webbrowser.open("https://accounts.spotify.com/authorize?" + q)

    def handle_callback(self, query):
        """Called from the local HTTP server. Returns (ok, message)."""
        p = urllib.parse.parse_qs(query)
        if not self.verifier or p.get("state", [""])[0] != self.oauth_state:
            return False, t("oauth_stale")
        if "error" in p:
            return False, t("oauth_denied", err=p["error"][0])
        try:
            tok = self._token_request({
                "grant_type": "authorization_code", "code": p.get("code", [""])[0],
                "redirect_uri": self.REDIRECT, "client_id": self.client_id, "code_verifier": self.verifier,
            })
        except Exception as ex:
            return False, t("oauth_failed", err=ex)
        self.verifier = None
        self._store(tok)
        return True, t("oauth_ok")

    def _token_request(self, form):
        req = urllib.request.Request("https://accounts.spotify.com/api/token",
                                     data=urllib.parse.urlencode(form).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def _store(self, tok):
        self.data["access_token"] = tok["access_token"]
        if tok.get("refresh_token"):
            self.data["refresh_token"] = tok["refresh_token"]
        self.data["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
        self._save()

    def _access(self):
        with self.lock:
            if time.time() >= self.data.get("expires_at", 0):
                self._store(self._token_request({
                    "grant_type": "refresh_token", "refresh_token": self.data["refresh_token"],
                    "client_id": self.client_id,
                }))
            return self.data["access_token"]

    # -- web api
    def _api(self, method, path):
        req = urllib.request.Request("https://api.spotify.com/v1" + path, method=method,
                                     headers={"Authorization": "Bearer " + self._access()})
        if method in ("PUT", "DELETE"):
            req.data = b""
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as e:
            return e.code, None

    def current_track(self):
        status, data = self._api("GET", "/me/player/currently-playing")
        item = (data or {}).get("item") or {}
        return item.get("id")

    def is_liked(self, track_id):
        status, data = self._api("GET", f"/me/tracks/contains?ids={track_id}")
        if status == 200 and isinstance(data, list):
            return bool(data[0])
        status, data = self._api("GET", f"/me/library/contains?uris=spotify:track:{track_id}")
        return status == 200 and isinstance(data, list) and bool(data[0])

    def set_liked(self, track_id, on):
        method = "PUT" if on else "DELETE"
        status, _ = self._api(method, f"/me/tracks?ids={track_id}")
        if status not in (200, 201, 204):
            status, _ = self._api(method, f"/me/library?uris=spotify:track:{track_id}")
        return status in (200, 201, 204)
