"""Links out of an HTML page with the text and the nearest heading before each one (stdlib html.parser)."""
import html
import re
import urllib.parse
from html.parser import HTMLParser

_HEAD = {"h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "dt", "th"}
_BLOCK = {"li", "p", "tr", "div", "section", "article", "dd"}


class _P(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links = []          # {href, text, heading, block}
        self.title = ""
        self._in_title = False
        self._a = None
        self._head_depth = 0
        self._head_buf = []
        self.heading = ""
        self.block_heading = ""   # the first bold / heading text inside the current list item or paragraph
        self._block_has_head = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "a" and a.get("href"):
            self._a = {"href": urllib.parse.urljoin(self.base, html.unescape(a["href"])), "text": [],
                       "heading": self.heading, "block": self.block_heading}
        if tag in _HEAD:
            self._head_depth += 1
            self._head_buf = []
        if tag in _BLOCK:
            self.block_heading, self._block_has_head = "", False

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._a is not None:
            self._a["text"] = _clean(" ".join(self._a["text"]))
            self.links.append(self._a)
            self._a = None
        if tag in _HEAD and self._head_depth:
            self._head_depth -= 1
            t = _clean(" ".join(self._head_buf))
            if t:
                self.heading = t
                if not self._block_has_head:
                    self.block_heading, self._block_has_head = t, True

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._a is not None:
            self._a["text"].append(data)
        if self._head_depth:
            self._head_buf.append(data)


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse(text, base_url):
    """(title, [{href, text, heading, block}]) of an HTML page. Pure."""
    p = _P(base_url)
    try:
        p.feed(text or "")
        p.close()
    except Exception:          # html.parser is lenient; a truly broken page still gives what was read
        pass
    return _clean(html.unescape(p.title)), p.links


COURSE_EXT = (".gpx", ".kml", ".kmz", ".geojson")


def is_course_file(href):
    path = urllib.parse.urlsplit(href).path.lower()
    return path.endswith(COURSE_EXT)
