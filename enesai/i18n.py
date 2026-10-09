"""SQ/EN switch (C-22). Albanian is the source language and the default; the Albanian
string itself is the lookup key. English strings live in i18n_en.py and are a DRAFT
translation that the client must approve before launch."""
from flask import g, has_request_context, request

LANGS = ("sq", "en")


def lang():
    if has_request_context():
        return getattr(g, "lang", "sq")
    return "sq"


def detect():
    v = request.args.get("lang")
    if v in LANGS:
        return v, True
    c = request.cookies.get("ea_lang")
    return (c if c in LANGS else "sq"), False


def gettext(__text, **kw):
    s = __text
    if lang() == "en":
        from .i18n_en import EN
        s = EN.get(s, s)
    return s % kw if kw else s


_ = gettext
