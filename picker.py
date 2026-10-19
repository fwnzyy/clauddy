"""Liked Songs list the pet holds up: search, scroll, click a track to play it."""
import time
import tkinter as tk
import tkinter.font as tkfont

from i18n import t
from panel import BG, DIM, EDGE, HEART, HEART_ON, KEY, TEXT, ACCENT

PW, PH = 300, 340
HEAD, ROW = 70, 34                    # header height, row height
LIST_H = PH - HEAD - 8
HOVER = "#2a2927"


class LikedPicker:
    def __init__(self, root, on_pick, now_title):
        self.on_pick, self.now_title = on_pick, now_title
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-transparentcolor", KEY)
        self.top.config(bg=KEY)
        self.cv = tk.Canvas(self.top, width=PW, height=PH, bg=KEY, highlightthickness=0)
        self.cv.pack()
        self.f_head = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_title = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.f_small = tkfont.Font(family="Segoe UI", size=8)
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: self._filter())
        self.entry = tk.Entry(self.top, textvariable=self.query, bg="#2a2927", fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=self.f_small, highlightthickness=0, bd=0)
        self.entry.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<Return>", lambda e: self._pick_first())
        self.cv.bind("<MouseWheel>", self._wheel)
        self.entry.bind("<MouseWheel>", self._wheel)
        self.cv.bind("<Motion>", self._move)
        self.cv.bind("<Leave>", lambda e: self._set_hover(None))
        self.cv.bind("<Button-1>", self._click)
        self.top.withdraw()
        self.visible = False
        self.tracks, self.shown = [], []
        self.tracks_at = 0.0
        self.scroll = 0
        self.hover_row = None
        self.status = ""

    # -- data
    def needs_refresh(self):
        return not self.tracks or time.monotonic() - self.tracks_at > 300

    def loading(self):
        self.status = t("picker_loading") if not self.tracks else ""
        self.draw()

    def set_tracks(self, tracks):
        self.tracks, self.tracks_at, self.status = tracks, time.monotonic(), ""
        self._filter()

    def error(self, msg):
        self.status = t("picker_error")
        self.draw()

    def _filter(self):
        q = self.query.get().strip().lower()
        self.shown = [x for x in self.tracks if q in x["title"].lower() or q in x["artist"].lower()] if q \
            else list(self.tracks)
        self.scroll = 0
        self.draw()

    # -- showing
    def show(self):
        self.visible = True
        self.query.set("")
        self.top.deiconify()
        self.top.attributes("-topmost", True)
        self.entry.place(x=14, y=40, width=PW - 28, height=20)
        self.top.after(50, self.entry.focus_force)
        self.draw()

    def hide(self):
        self.visible = False
        self.top.withdraw()

    def place(self, pet_x, pet_y, pet_w, area):
        l, t, r, b = area
        x = int(min(max(pet_x + pet_w / 2 - PW / 2, l), r - PW))
        y = int(max(pet_y - PH + 18, t))
        self.top.geometry(f"{PW}x{PH}+{x}+{y}")

    # -- mouse
    def _wheel(self, e):
        top = max(0, len(self.shown) * ROW - LIST_H)
        self.scroll = min(max(0, self.scroll - e.delta // 120 * ROW * 2), top)
        self.draw()

    def _row_at(self, y):
        if y < HEAD or y > PH - 8:
            return None
        i = (y - HEAD + self.scroll) // ROW
        return i if 0 <= i < len(self.shown) else None

    def _set_hover(self, i):
        if i != self.hover_row:
            self.hover_row = i
            self.cv.config(cursor="hand2" if i is not None else "")
            self.draw()

    def _move(self, e):
        self._set_hover(self._row_at(e.y))

    def _click(self, e):
        if e.x > PW - 24 and e.y < 24:
            self.hide()
            return
        i = self._row_at(e.y)
        if i is not None:
            self.on_pick(self.shown[i])

    def _pick_first(self):
        if self.shown:
            self.on_pick(self.shown[0])

    # -- drawing
    def _fit(self, text, font, width):
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def draw(self):
        cv = self.cv
        cv.delete("all")
        cv.create_rectangle(0, 0, PW, PH, fill=EDGE, outline="")
        cv.create_rectangle(2, 2, PW - 2, PH - 2, fill=BG, outline="")
        for cx, cy in ((0, 0), (PW - 4, 0), (0, PH - 4), (PW - 4, PH - 4)):
            cv.create_rectangle(cx, cy, cx + 4, cy + 4, fill=KEY, outline="")
        # list
        if self.status:
            cv.create_text(PW / 2, HEAD + 40, text=self.status, fill=DIM, font=self.f_small)
        elif not self.shown:
            cv.create_text(PW / 2, HEAD + 40, text=t("picker_empty"), fill=DIM, font=self.f_small)
        now = self.now_title()
        first = self.scroll // ROW
        for i in range(first, min(len(self.shown), first + LIST_H // ROW + 2)):
            track = self.shown[i]
            y = HEAD + i * ROW - self.scroll
            if y + ROW < HEAD or y > PH - 8:
                continue
            if i == self.hover_row:
                cv.create_rectangle(8, y, PW - 8, y + ROW - 2, fill=HOVER, outline="")
            playing = now and track["title"] == now
            cv.create_text(16, y + 9, anchor="w", fill=ACCENT if playing else TEXT, font=self.f_title,
                           text=self._fit(track["title"], self.f_title, PW - 40))
            cv.create_text(16, y + 24, anchor="w", fill=DIM, font=self.f_small,
                           text=self._fit(track["artist"], self.f_small, PW - 40))
        # header on top of rows that slid under it: pixel heart, title, count, close
        cv.create_rectangle(2, 2, PW - 2, HEAD - 2, fill=BG, outline="")
        for yy, line in enumerate(HEART):
            for xx, ch in enumerate(line):
                if ch == "X":
                    cv.create_rectangle(14 + xx * 2, 13 + yy * 2, 16 + xx * 2, 15 + yy * 2, fill=HEART_ON, outline="")
        cv.create_text(30, 18, anchor="w", text=t("picker_title"), fill=TEXT, font=self.f_head)
        if self.tracks:
            cv.create_text(PW - 30, 18, anchor="e", text=str(len(self.shown)), fill=DIM, font=self.f_small)
        cv.create_text(PW - 14, 12, text="✕", fill=DIM, font=self.f_small)
        cv.create_rectangle(2, PH - 8, PW - 2, PH - 2, fill=BG, outline="")
        for cx, cy in ((0, PH - 4), (PW - 4, PH - 4)):
            cv.create_rectangle(cx, cy, cx + 4, cy + 4, fill=KEY, outline="")
        # scrollbar
        total = len(self.shown) * ROW
        if total > LIST_H:
            h = max(20, LIST_H * LIST_H / total)
            y = HEAD + (LIST_H - h) * self.scroll / (total - LIST_H)
            cv.create_rectangle(PW - 7, y, PW - 4, y + h, fill=EDGE, outline="")
