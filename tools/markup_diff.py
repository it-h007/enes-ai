"""Compare element structure (tag + class list) of a rendered page with the prototype page.
Usage: python tools/markup_diff.py ours.html prototype.html [selector-class]
Prints a unified diff of the tag/class sequence (text and attribute values ignored)."""
import difflib
import sys
from html.parser import HTMLParser

SKIP = {"script", "svg", "path", "circle", "line", "rect", "polyline", "g", "text", "defs", "linearGradient", "stop", "head", "meta", "link", "title"}


class P(HTMLParser):
    def __init__(self, root=None):
        super().__init__()
        self.out, self.depth, self.root, self.inside, self.rootdepth, self.svg = [], 0, root, root is None, None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = " ".join(sorted((a.get("class") or "").split()))
        if tag in ("svg",):
            self.svg += 1
        if not self.inside and self.root and self.root in (a.get("class") or "").split():
            self.inside, self.rootdepth = True, self.depth
        if self.inside and tag not in SKIP and not self.svg and "ea-protonav" not in cls:
            extra = "".join(" %s" % k for k in sorted(a) if k.startswith("data-ea") or k in ("role",))
            self.out.append("  " * min(self.depth, 30) + tag + ("." + cls.replace(" ", ".") if cls else "") + extra)
        if tag not in ("img", "input", "br", "hr", "meta", "link", "source", "col", "wbr", "path", "circle", "line", "rect", "polyline", "stop"):
            self.depth += 1

    def handle_endtag(self, tag):
        if tag not in ("img", "input", "br", "hr", "meta", "link", "source", "col", "wbr", "path", "circle", "line", "rect", "polyline", "stop"):
            self.depth -= 1
        if tag == "svg":
            self.svg -= 1
        if self.inside and self.root and self.depth == self.rootdepth:
            self.inside = False


def seq(path, root):
    p = P(root)
    p.feed(open(path, encoding="utf-8").read())
    return [l.strip() for l in p.out]


if __name__ == "__main__":
    a, b = seq(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else None), seq(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    d = list(difflib.unified_diff(b, a, "prototype", "flask", lineterm="", n=1))
    print("\n".join(d) if d else "IDENTICAL structure (%d elements)" % len(a))
