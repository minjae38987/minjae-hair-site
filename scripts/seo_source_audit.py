#!/usr/bin/env python3
"""Lightweight, standard-library-only static SEO audit for the hair portfolio.
Inspired by openly documented technical SEO checks; no Claude installation required.
This is an independent implementation, not the Claude SEO plugin itself.
"""
from html.parser import HTMLParser
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = {}
        self.meta = {}
        self.links = []
        self.jsonld = []
        self.in_title = False
        self.title = ""
        self.in_h1 = False
        self.h1_text = []
        self.in_jsonld = False
        self._json = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.in_h1 = True
        if tag == "meta" and d.get("name"):
            self.meta[d["name"].lower()] = d.get("content", "")
        if tag == "link":
            self.links.append(d)
        if tag == "a":
            self.links.append(d)
        if tag == "script" and d.get("type") == "application/ld+json":
            self.in_jsonld = True
            self._json = ""

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_h1:
            self.h1_text.append(data)
        if self.in_jsonld:
            self._json += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "h1":
            self.in_h1 = False
        if tag == "script" and self.in_jsonld:
            self.in_jsonld = False
            self.jsonld.append(self._json)

def audit():
    page = Inspector()
    page.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    sitemap = ET.fromstring((ROOT / "sitemap.xml").read_text(encoding="utf-8"))
    canonical = [l.get("href") for l in page.links if l.get("rel") == "canonical"]
    bookings = [l.get("href") for l in page.links if "booking.naver.com" in (l.get("href") or "")]
    blogs = [l.get("href") for l in page.links if any(x in (l.get("href") or "") for x in ("blogspot.com", "blogger.com"))]
    errors = []
    for i, item in enumerate(page.jsonld, 1):
        try:
            json.loads(item)
        except json.JSONDecodeError as exc:
            errors.append(f"JSON-LD block {i}: {exc}")
    summary = {
        "title": page.title.strip(),
        "description": page.meta.get("description", ""),
        "robots_meta": page.meta.get("robots", ""),
        "canonical": canonical,
        "h1_count": page.tags.get("h1", 0),
        "h1_text": " ".join(page.h1_text).strip(),
        "image_count": page.tags.get("img", 0),
        "iframe_count": page.tags.get("iframe", 0),
        "booking_link_count": len(bookings),
        "blogger_link_count": len(blogs),
        "jsonld_blocks": len(page.jsonld),
        "jsonld_parse_errors": errors,
        "robots_txt_has_sitemap": "sitemap:" in robots.lower(),
        "sitemap_url_count": len(sitemap.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")),
        "not_measured": ["live Google indexing", "actual ranking", "PageSpeed", "Core Web Vitals", "Blogger post URLs"],
    }
    return summary

if __name__ == "__main__":
    data = audit()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if not data["title"] or not data["description"] or data["h1_count"] != 1 or data["jsonld_parse_errors"]:
        sys.exit(1)
