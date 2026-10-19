"""Draws pet.ico (256/48/32/16) and icon_preview.png from the pet's own sprites."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clauddy import compose, png_bytes  # noqa: E402

BG_TOP, BG_BOTTOM = (48, 46, 43), (30, 29, 27)
BORDER = (217, 119, 87)
LIGHT, ORANGE = (240, 238, 230), (217, 119, 87)

FONT = {  # 5x7 pixel font, just the letters we need
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
}


def hex_rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def canvas(n):
    """Rounded square with a soft vertical gradient and a thin orange rim."""
    rad = n * 0.2
    rim = max(1, n // 64)
    px = []
    for y in range(n):
        f = y / (n - 1)
        bg = tuple(int(a + (b - a) * f) for a, b in zip(BG_TOP, BG_BOTTOM))
        row = []
        for x in range(n):
            cx = min(max(x + 0.5, rad), n - rad)
            cy = min(max(y + 0.5, rad), n - rad)
            d = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
            if d > rad:
                row.append((0, 0, 0, 0))
            elif d > rad - rim and (n >= 48):
                row.append(BORDER + (255,))
            elif n >= 48 and (x < rim or y < rim or x >= n - rim or y >= n - rim):
                row.append(BORDER + (255,))
            else:
                row.append(bg + (255,))
        px.append(row)
    return px


def blit_sprite(px, rects, crop, scale, ox, oy):
    cx0, cy0, cx1, cy1 = crop
    for x, y, w, h, c in rects:
        rgb = hex_rgb(c) + (255,)
        for sy in range(max(y, cy0), min(y + h, cy1)):
            for sx in range(max(x, cx0), min(x + w, cx1)):
                for yy in range(scale):
                    for xx in range(scale):
                        X, Y = ox + (sx - cx0) * scale + xx, oy + (sy - cy0) * scale + yy
                        if 0 <= X < len(px) and 0 <= Y < len(px):
                            px[Y][X] = rgb


def blit_text(px, text, colors, scale, oy):
    width = len(text) * 6 * scale - scale
    ox = (len(px) - width) // 2
    for i, ch in enumerate(text):
        glyph = FONT.get(ch)
        if not glyph:
            continue
        rgb = colors[i] + (255,)
        for gy, line in enumerate(glyph):
            for gx, bit in enumerate(line):
                if bit == "1":
                    for yy in range(scale):
                        for xx in range(scale):
                            px[oy + gy * scale + yy][ox + (i * 6 + gx) * scale + xx] = rgb


def big_icon():
    n = 256
    px = canvas(n)
    # the pet at its laptop, with code floating up: cols 5..23, rows 6..18
    crop = (5, 6, 23, 18)
    scale = 10
    ox = (n - (crop[2] - crop[0]) * scale) // 2
    blit_sprite(px, compose("type", 12), crop, scale, ox, 34)
    text = "CLAUDE CODE"
    colors = [LIGHT] * 6 + [LIGHT] + [ORANGE] * 4
    blit_text(px, text, colors, 3, 184)
    return px


def small_icon(n):
    px = canvas(n)
    crop = (6, 11, 18, 18)               # just the pet: 12 x 7
    scale = max(1, (n - 2) // 12)
    ox = (n - 12 * scale) // 2
    oy = (n - 7 * scale) // 2
    blit_sprite(px, compose("idle", 5), crop, scale, ox, oy)
    return px


def write_ico(path, images):
    blobs = [png_bytes(p) for p in images]
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(blobs)))
        offset = 6 + 16 * len(blobs)
        for p, b in zip(images, blobs):
            n = len(p)
            f.write(struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(b), offset))
            offset += len(b)
        for b in blobs:
            f.write(b)


if __name__ == "__main__":
    big = big_icon()
    write_ico("pet.ico", [big] + [small_icon(n) for n in (48, 32, 16)])
    with open("icon_preview.png", "wb") as f:
        f.write(png_bytes(big))
