"""Image uploads with Pillow: type sniffed from content (not the filename), size and pixel
limits, EXIF orientation applied, metadata stripped, re-encoded to JPEG/PNG with a random
file name, stored under instance/uploads (served read-only by /media/)."""
import secrets
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
ALLOWED = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageError(Exception):
    pass


def _open(fileobj):
    data = fileobj.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ImageError("Foto është më e madhe se 10 MB.")
    if not data:
        raise ImageError("Skedari është bosh.")
    import io
    try:
        im = Image.open(io.BytesIO(data))
        fmt = im.format
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("Skedari nuk është foto e vlefshme (JPG, PNG ose WebP).")
    if fmt not in ALLOWED:
        raise ImageError("Lejohen vetëm JPG, PNG ose WebP.")
    if im.width * im.height > MAX_PIXELS:
        raise ImageError("Foto ka shumë piksel.")
    return ImageOps.exif_transpose(im)


def _target(sub):
    d = Path(current_app.config["UPLOAD_DIR"]) / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(im, sub, max_side, keep_alpha=False, quality=86):
    im = im.copy()
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    name = secrets.token_hex(12)
    if keep_alpha and im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        path = _target(sub) / (name + ".png")
        im.save(path, "PNG", optimize=True)
    else:
        if im.mode != "RGB":
            bg = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        path = _target(sub) / (name + ".jpg")
        im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    return "%s/%s" % (sub, path.name)


def save_product_image(fileobj):
    """Main image ≤ 1200 px (cards use it at 1:1 well with contain)."""
    return _save(_open(fileobj), "products", 1200)


def save_category_image(fileobj):
    im = _open(fileobj)
    if im.width < 400 or im.height < 300:
        raise ImageError("Foto e kategorisë duhet të jetë të paktën 800×600 (4:3).")
    return _save(im, "categories", 1200)


def save_announcement_image(fileobj):
    return _save(_open(fileobj), "announcements", 1600)


def save_logo(fileobj, kind):
    """Logos: PNG/JPEG/WebP only. SVG uploads are refused (script/XSS risk)."""
    if (fileobj.filename or "").lower().endswith(".svg"):
        raise ImageError("SVG nuk pranohet për ngarkim (rrezik sigurie). Përdorni PNG transparent.")
    return _save(_open(fileobj), "logos", 1400, keep_alpha=True)


def delete(rel):
    if not rel or rel.startswith("/"):
        return  # bundled static assets are never deleted
    p = (Path(current_app.config["UPLOAD_DIR"]) / rel).resolve()
    root = Path(current_app.config["UPLOAD_DIR"]).resolve()
    if root in p.parents and p.is_file():
        p.unlink()
