"""The calendar icon, drawn once for the tray, windows, Dock and release bundles."""
from PIL import Image, ImageDraw


def icon_image(size=64, stale=False, padded=False):
    """Draw supersampled on a 1024 grid, then scale down for smooth edges.

    padded follows Apple's app-icon grid: an 824-pixel rounded square centred
    on the 1024 canvas, holding a white calendar, so the Dock shows it at the
    same size and shape as other apps. Otherwise the calendar fills the canvas.
    """
    scale = 4 if size <= 256 else 1
    canvas = size * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    colour = "#d97706" if stale else "#2563eb"
    if padded:
        tile = [round(c * canvas / 1024) for c in (100, 100, 924, 924)]
        d.rounded_rectangle(tile, radius=round(185 * canvas / 1024), fill=colour)
        inset, body, paper, ink = 262, 500, "white", colour
    else:
        inset, body, paper, ink = 0, 1024, colour, "white"

    def box(*coords):
        return [round((inset + c * body / 1024) * canvas / 1024) for c in coords]

    def width(w):
        return max(1, round(w * body / 1024 * canvas / 1024))

    d.rounded_rectangle(box(64, 128, 960, 960), radius=width(180), fill=paper)
    d.rectangle(box(64, 320, 960, 384), fill=ink)
    for x in (320, 704):
        d.rounded_rectangle(box(x - 40, 64, x + 40, 256), radius=width(40), fill="white")
    d.line(box(512, 496, 512, 688, 688, 688), fill=ink, width=width(64), joint="curve")
    return img.resize((size, size), Image.Resampling.LANCZOS) if scale > 1 else img
