#!/usr/bin/env python3
"""Public-page SEO and reservation-path audit.
Uses Python standard library only. No login, bypass, or private analytics.
Run: python scripts/seo_channel_audit.py [--blogger URL] [--naver-blog URL] [--output PATH]
"""
import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DEFAULT = {
    "portfolio": "https://minjae38987.github.io/minjae-hair-site/",
    "naver_place": "https://map.naver.com/p/entry/place/2074303770",
    "naver_booking": "https://m.booking.naver.com/booking/13/bizes/1512690/items/8096768",
}
ALLOWED_HOSTS = {
    "minjae38987.github.io", "map.naver.com", "m.place.naver.com",
    "place.naver.com", "m.booking.naver.com", "booking.naver.com",
    "blog.naver.com", "m.blog.naver.com", "blogger.com", "www.blogger.com",
    "blogspot.com",
}
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = {}
        self.meta = {}
        self.links = []
        self.img = []
        self.headings = []
        self._collect = None
        self._buf = []
        self.title = ""
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta[key.lower()] = a.get("content", "")
        if tag in ("link", "a"):
            self.links.append({"tag": tag, **a})
        if tag == "img":
            self.img.append({"src": a.get("src", ""), "alt": a.get("alt", "")})
        if tag in ("title", "h1", "h2"):
            self._collect = tag
            self._buf = []
    def handle_data(self, data):
        if self._collect:
            self._buf.append(data)
    def handle_endtag(self, tag):
        if tag == self._collect:
            t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if tag == "title":
                self.title = t
            elif t:
                self.headings.append({"level": tag, "text": t[:200]})
            self._collect = None
            self._buf = []

def allowed(url):
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and (host in ALLOWED_HOSTS or host.endswith(".blogspot.com"))
class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise ValueError("Redirect host not allowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)
OPENER = urllib.request.build_opener(RestrictedRedirect)

def check(label, url):
    result = {"channel": label, "requested_url": url, "status": "unknown", "limitations": []}
    if not allowed(url):
        result.update(status="not_checked", error="URL not in approved public target domains")
        return result
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"HairSEOAudit/1.0 (public pages; no login)", "Accept":"text/html"})
        with OPENER.open(req, timeout=13) as res:
            final = res.url
            if not allowed(final):
                raise ValueError("Host changed outside allowlist")
            raw = res.read(2_000_000)
            ctype = res.headers.get("Content-Type", "")
            result.update(http_status=res.status, final_url=final, content_type=ctype, bytes_read=len(raw))
        if "html" not in ctype.lower():
            result.update(status="not_html", limitations=["Not HTML; cannot assess on-page SEO"])
            return result
        html = raw.decode("utf-8", errors="replace")
        p = Page()
        p.feed(html)
        can = [i.get("href") for i in p.links if i.get("rel") == "canonical"]
        calls = [i.get("href") for i in p.links if "booking.naver.com" in i.get("href", "")]
        result.update(status="fetched", title=p.title, description=p.meta.get("description", ""),
            robots=p.meta.get("robots", ""), canonical=can, heading_count=len(p.headings),
            headings=p.headings[:15], img_count=len(p.img), img_alt_missing=sum(not i["alt"] for i in p.img),
            booking_links=calls[:10], jsonld_script_count=len(re.findall(r'<script[^>]+application/ld\\+json', html, re.I)),
            rendered_js_not_inspected=True)
        if label in ("naver_place", "naver_booking"):
            result["limitations"].append("JavaScript-rendered booking interface, dates, prices, and reservations are not confirmed by HTML fetch")
    except urllib.error.HTTPError as e:
        result.update(status="blocked_or_http_error", http_status=e.code, error=str(e))
    except Exception as e:
        result.update(status="fetch_failed", error=str(e))
    return result

def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--blogger", help="Actual public post or blog URL")
    arg.add_argument("--naver-blog", help="Actual public blog or post URL")
    arg.add_argument("--output", default="seo-channel-report.json")
    options = arg.parse_args()
    targets = dict(DEFAULT)
    if options.blogger:
        targets["blogger"] = options.blogger
    if options.naver_blog:
        targets["naver_blog"] = options.naver_blog
    result = {
        "audited_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": "unauthenticated public HTML only; no automatic booking interactions",
        "channels": [check(k,v) for k,v in targets.items()],
        "not_configured": [c for c in ("blogger", "naver_blog") if c not in targets],
        "manual_checks": {
            "naver_booking":["name/photo/pricing/service list", "booking step friction", "availability by real user session", "mobile screenshots"],
            "naver_place":["stylist profile visibility", "service/review presentation", "booking CTA", "mobile appearance"],
            "blogger":["published canonical URL", "search visibility", "photo rendering", "booking CTA"],
            "naver_blog":["real post URL", "post layout", "image rendering after save", "booking CTA"]
        }
    }
    Path(options.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in result["channels"]:
        print(item["channel"], item["status"], item.get("http_status",""), item.get("title","")[:70])
    print("NOT_CONFIGURED:", ", ".join(result["not_configured"]) or "none")
    print("REPORT:", options.output)

if __name__ == "__main__":
    main()
