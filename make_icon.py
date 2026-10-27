"""Draw Quiet Player's icon into quiet_player.ico.

A deep blue rounded square with a plain white play triangle, nothing else.
Each size is drawn separately (4x supersampled, then shrunk) so the small
ones stay crisp instead of being scaled down from 256.

    python make_icon.py
"""

import os

from PIL import Image, ImageDraw

BLUE = (0x1F, 0x3A, 0x5F, 255)
WHITE = (255, 255, 255, 255)
SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 4                       # supersampling factor
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quiet_player.ico")


def draw(size):
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Small transparent margin; at 16 px a 1 px margin is all there is room for.
    margin = max(1, round(size * 0.04)) * SS
    side = big - 2 * margin
    d.rounded_rectangle((margin, margin, margin + side - 1, margin + side - 1),
                        radius=round(side * 0.19), fill=BLUE)

    # Large triangle, equilateral-ish, nudged right so it *looks* centred
    # (its visual centre is its centroid, not its bounding box centre).
    h = side * 0.50
    w = h * 0.88
    cx = big / 2 + w * 0.10
    cy = big / 2
    # Snap the vertical edge to whole output pixels so it stays sharp at 16 px.
    left = round((cx - w / 2) / SS) * SS
    d.polygon([(left, cy - h / 2), (left, cy + h / 2), (left + w, cy)], fill=WHITE)

    return img.resize((size, size), Image.LANCZOS)


def main():
    images = [draw(s) for s in SIZES]
    # Pillow writes one entry per size in `sizes`, taking the matching image
    # from append_images when there is one.
    images[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES],
                    append_images=images[:-1])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
