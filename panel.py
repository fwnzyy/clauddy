"""The little Spotify panel the pet holds up above its head."""
import io
import time
import tkinter as tk
import tkinter.font as tkfont

from i18n import t

PW, PH = 300, 104
KEY = "#010203"
BG, EDGE = "#1c1b1a", "#3a3836"
TEXT, DIM = "#f0eee6", "#9a968e"
ACCENT, TRACK = "#1ed760", "#3a3836"
HEART_ON, HEART_OFF = "#ff4f6d", "#6b6862"
HEART = [".X.X.", "XXXXX", "XXXXX", ".XXX.", "..X.."]


def fmt(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


class MusicPanel:
    def __init__(self, root, media, on_heart, on_surprise=None, is_radio=lambda: False):
        self.media, self.on_heart, self.on_surprise, self.is_radio = media, on_heart, on_surprise, is_radio
        self.missing_since = None              # when Spotify stopped reporting a track
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-transparentcolor", KEY)
        self.top.config(bg=KEY)
        self.cv = tk.Canvas(self.top, width=PW, height=PH, bg=KEY, highlightthickness=0)
        self.cv.pack()
        self.top.withdraw()
        self.f_title = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_artist = tkfont.Font(family="Segoe UI", size=9)
        self.f_time = tkfont.Font(family="Segoe UI", size=8)
        self.visible = self.pinned = self.hover = False
        self.until = 0.0
        self.cover_key, self.cover_img = None, None
        self.liked = None                      # True / False / None (unknown)
        self.cv.bind("<Enter>", lambda e: setattr(self, "hover", True))
        self.cv.bind("<Leave>", lambda e: setattr(self, "hover", False))
        # timeline: click or drag to seek
        self.seek_frac = None                  # where the knob is while dragging
        self.bar_hover = False
        self.end = 0.0
        self.cv.bind("<ButtonPress-1>", self.on_bar_press, add="+")
        self.cv.bind("<B1-Motion>", self.on_bar_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_bar_release)
        self.cv.bind("<Motion>", self.on_move)
        for tag, cmd in (("prev", lambda: media.control("prev")), ("toggle", lambda: media.control("toggle")),
                         ("next", lambda: media.control("next")), ("heart", lambda: self.on_heart()),
                         ("shuffle", lambda: None if self.is_radio() else self._then_redraw(media.toggle_shuffle)),
                         ("repeat", lambda: self._then_redraw(media.cycle_repeat)),
                         ("surprise", lambda: self.on_surprise and self.on_surprise()),
                         ("close", self.hide)):
            self.cv.tag_bind(tag, "<Button-1>", lambda e, c=cmd: c())
            self.cv.tag_bind(tag, "<Enter>", lambda e: self.cv.config(cursor="hand2"))
            self.cv.tag_bind(tag, "<Leave>", lambda e: self.cv.config(cursor=""))

    # -- timeline
    BAR_X0, BAR_X1, BAR_Y = 104, PW - 14, 82

    def _on_bar(self, x, y):
        return self.BAR_X0 - 6 <= x <= self.BAR_X1 + 6 and self.BAR_Y - 8 <= y <= self.BAR_Y + 10

    def _frac(self, x):
        return min(1.0, max(0.0, (x - self.BAR_X0) / (self.BAR_X1 - self.BAR_X0)))

    def on_move(self, e):
        over = self._on_bar(e.x, e.y)
        if over != self.bar_hover:
            self.bar_hover = over
            self.cv.config(cursor="hand2" if over else "")

    def on_bar_press(self, e):
        if self._on_bar(e.x, e.y) and self.end > 0:
            self.seek_frac = self._frac(e.x)
            self.redraw()

    def on_bar_drag(self, e):
        if self.seek_frac is not None:
            self.seek_frac = self._frac(e.x)
            self.redraw()

    def on_bar_release(self, e):
        if self.seek_frac is not None:
            self.media.seek(self.seek_frac * self.end)
            self.seek_frac = None
            self.redraw()

    def _then_redraw(self, fn):
        fn()
        self.redraw()

    def redraw(self):
        st = self.media.now()
        if st:
            self.draw(st)

    # -- showing
    def show(self, pinned, seconds=9):
        self.pinned = pinned
        self.until = time.monotonic() + seconds
        if not self.visible:
            self.visible = True
            self.top.deiconify()
            self.top.attributes("-topmost", True)

    def hide(self):
        self.visible = self.pinned = False
        self.top.withdraw()

    def should_close(self, st):
        now = time.monotonic()
        if st is None:                          # a track change blinks for a moment: only a real
            if self.missing_since is None:      # silence of a few seconds closes the player
                self.missing_since = now
            return now - self.missing_since > 4
        self.missing_since = None
        return not self.pinned and not self.hover and now > self.until

    def place(self, pet_x, pet_y, pet_w, area):
        l, t, r, b = area
        x = int(min(max(pet_x + pet_w / 2 - PW / 2, l), r - PW))
        y = int(max(pet_y - PH + 18, t))        # just over his raised hands
        self.top.geometry(f"{PW}x{PH}+{x}+{y}")

    # -- drawing
    def _cover(self, st):
        if st["key"] == self.cover_key:
            return self.cover_img
        self.cover_key, self.cover_img = st["key"], None
        if st.get("thumb"):
            try:
                from PIL import Image, ImageTk
                im = Image.open(io.BytesIO(st["thumb"])).convert("RGB").resize((80, 80), Image.LANCZOS)
                self.cover_img = ImageTk.PhotoImage(im, master=self.top)
            except Exception:
                pass
        return self.cover_img

    def _fit(self, text, font, width):
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def draw(self, st):
        cv = self.cv
        cv.delete("all")
        # pixel-cornered card
        cv.create_rectangle(0, 0, PW, PH, fill=EDGE, outline="")
        cv.create_rectangle(2, 2, PW - 2, PH - 2, fill=BG, outline="")
        for cx, cy in ((0, 0), (PW - 4, 0), (0, PH - 4), (PW - 4, PH - 4)):
            cv.create_rectangle(cx, cy, cx + 4, cy + 4, fill=KEY, outline="")
        # cover
        img = self._cover(st)
        if img:
            cv.create_image(12, 12, image=img, anchor="nw")
        else:
            cv.create_rectangle(12, 12, 92, 92, fill="#2a2927", outline="")
            cv.create_text(52, 52, text="♪", fill=DIM, font=("Segoe UI", 22))
        x0, x1 = 104, PW - 14
        # close and "surprise me" (a radio based on this track) in the top right corner
        cv.create_text(PW - 12, 10, text="✕", fill=DIM, font=self.f_time, tags="close")
        radio = self.is_radio()
        label = "■ " + t("radio_stop") if radio else "✦ " + t("surprise")
        lw = self.f_time.measure(label) + 12
        sx1 = PW - 24
        sx0 = sx1 - lw
        cv.create_rectangle(sx0, 4, sx1, 18, fill="#2a2927", outline="", tags="surprise")
        cv.create_text((sx0 + sx1) / 2, 11, text=label, fill=TEXT, font=self.f_time, tags="surprise")
        cv.create_text(x0, 19, anchor="nw", fill=TEXT, font=self.f_title,
                       text=self._fit(st["title"], self.f_title, x1 - x0))
        cv.create_text(x0, 37, anchor="nw", fill=DIM, font=self.f_artist,
                       text=self._fit(st["artist"], self.f_artist, x1 - x0))
        # buttons: mix, prev, play/pause, next, repeat ... heart
        by = 62
        self._shuffle(x0, by, st.get("shuffle"), disabled=radio)
        self._prev(x0 + 30, by)
        self._toggle(x0 + 58, by, st["playing"])
        self._next(x0 + 88, by)
        self._repeat(x0 + 116, by, st.get("repeat", "off"))
        self._heart(x1 - 15, by - 6)
        # timeline
        self.end = st["end"]
        frac = st["pos"] / st["end"] if st["end"] > 0 else 0
        if self.seek_frac is not None:
            frac = self.seek_frac
        frac = min(1.0, frac)
        by = self.BAR_Y
        cv.create_rectangle(x0, by, x1, by + 3, fill=TRACK, outline="")
        cv.create_rectangle(x0, by, x0 + (x1 - x0) * frac, by + 3, fill=ACCENT, outline="")
        if self.bar_hover or self.seek_frac is not None:   # square pixel knob
            kx = x0 + (x1 - x0) * frac
            cv.create_rectangle(kx - 4, by - 3, kx + 4, by + 6, fill=TEXT, outline="")
        cv.create_text(x0, 89, anchor="nw", fill=DIM, font=self.f_time, text=fmt(frac * st["end"]))
        cv.create_text(x1, 89, anchor="ne", fill=DIM, font=self.f_time, text=fmt(st["end"]))

    def _hit(self, x, y, tag):                 # a generous invisible click area
        self.cv.create_rectangle(x - 6, y - 8, x + 20, y + 8, fill=BG, outline="", tags=tag)

    def _prev(self, x, y):
        self._hit(x, y, "prev")
        self.cv.create_rectangle(x, y - 6, x + 2, y + 6, fill=TEXT, outline="", tags="prev")
        self.cv.create_polygon(x + 12, y - 6, x + 12, y + 6, x + 3, y, fill=TEXT, outline="", tags="prev")

    def _next(self, x, y):
        self._hit(x, y, "next")
        self.cv.create_polygon(x, y - 6, x, y + 6, x + 9, y, fill=TEXT, outline="", tags="next")
        self.cv.create_rectangle(x + 10, y - 6, x + 12, y + 6, fill=TEXT, outline="", tags="next")

    def _toggle(self, x, y, playing):
        self._hit(x, y, "toggle")
        if playing:
            self.cv.create_rectangle(x + 1, y - 7, x + 5, y + 7, fill=TEXT, outline="", tags="toggle")
            self.cv.create_rectangle(x + 9, y - 7, x + 13, y + 7, fill=TEXT, outline="", tags="toggle")
        else:
            self.cv.create_polygon(x + 1, y - 8, x + 1, y + 8, x + 14, y, fill=TEXT, outline="", tags="toggle")

    def _shuffle(self, x, y, on, disabled=False):
        self._hit(x, y, "shuffle")
        c = "#4a4844" if disabled else ACCENT if on else TEXT   # a radio has no order to mix
        on = on and not disabled
        arrow = dict(fill=c, width=2, arrow="last", arrowshape=(5, 6, 3), tags="shuffle")
        self.cv.create_line(x, y - 5, x + 14, y + 5, **arrow)
        self.cv.create_line(x, y + 5, x + 14, y - 5, **arrow)
        if on:
            self.cv.create_rectangle(x + 6, y + 9, x + 8, y + 11, fill=c, outline="", tags="shuffle")

    def _repeat(self, x, y, mode):
        self._hit(x, y, "repeat")
        c = TEXT if mode == "off" else ACCENT
        arrow = dict(fill=c, width=2, arrow="last", arrowshape=(4, 5, 3), tags="repeat")
        self.cv.create_line(x, y + 2, x, y - 5, x + 13, y - 5, **arrow)
        self.cv.create_line(x + 14, y - 2, x + 14, y + 5, x + 1, y + 5, **arrow)
        if mode == "track":                  # repeat one: a pixel "1" inside the loop
            self.cv.create_rectangle(x + 7, y - 2, x + 9, y + 3, fill=c, outline="", tags="repeat")
            self.cv.create_rectangle(x + 5, y - 2, x + 7, y, fill=c, outline="", tags="repeat")
        if mode != "off":
            self.cv.create_rectangle(x + 6, y + 9, x + 8, y + 11, fill=c, outline="", tags="repeat")

    def _heart(self, x, y):
        self.cv.create_rectangle(x - 4, y - 4, x + 19, y + 19, fill=BG, outline="", tags="heart")
        c = HEART_ON if self.liked else HEART_OFF
        for yy, line in enumerate(HEART):
            for xx, ch in enumerate(line):
                if ch == "X":
                    self.cv.create_rectangle(x + xx * 3, y + yy * 3, x + xx * 3 + 3, y + yy * 3 + 3,
                                             fill=c, outline="", tags="heart")
