#!/usr/bin/env python3
"""External, public-page SEO HTTP audit (no authentication or scraping bypass).
Run: python scripts/seo_live_http_audit.py --out seo-live
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

SITE = "https://minjae38987.github.io/minjae-hair-site/"
PAGES = {
    "homepage": SITE,
    "leaf_cut": SITE + "styles/mens-leaf-cut-before-after/",
    "volume_perm": SITE + "styles/mens-leaf-volume-perm/",
    "down_perm": SITE + "styles/mens-down-perm-guide/",
    "robots": SITE + "robots.txt",
    "sitemap": SITE + "sitemap.xml",
    "blogger": "https://ahairmj.blogspot.com/",
    "naver_blog": "https://m.blog.naver.com/a-hair_mj",
}
IMAGES = {
    "leaf_photo": "https://raw.githubusercontent.com/minjae38987/minjae-hair-site/main/blogger-media/leaf-before-after-20261107/image4.jpg",
    "volume_photo": "https://raw.githubusercontent.com/minjae38987/minjae-hair-site/main/blogger-media/volume-leaf-20261106/image5.jpg",
}

class Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.robots = ""
        self.canonical = []
        self.headings = []
        self.images = []
        self.anchors = []
        self.jsonld = []
        self._capture = None
        self._data = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("title", "h1", "h2"):
            self._capture = tag
            self._data = []
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._capture = "jsonld"
            self._data = []
        elif tag == "meta":
            if a.get("name", "").lower() == "description":
                self.description = a.get("content", "")
            if a.get("name", "").lower() == "robots":
                self.robots = a.get("content", "")
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical.append(a.get("href", ""))
        elif tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": a.get("alt", "")})
        elif tag == "a":
            self.anchors.append(a.get("href", ""))
    def handle_data(self, data):
        if self._capture:
            self._data.append(data)
    def handle_endtag(self, tag):
        if tag == self._capture or (tag == "script" and self._capture == "jsonld"):
            val = re.sub(r"\s+", " ", "".join(self._data)).strip()
            if self._capture == "title":
                self.title = val
            elif self._capture in ("h1", "h2"):
                self.headings.append({"tag": self._capture, "text": val[:200]})
            elif self._capture == "jsonld":
                try:
                    self.jsonld.append({"valid": True, "type": json.loads("".join(self._data)).get("@type", "graph")})
                except (ValueError, TypeError) as e:
                    self.jsonld.append({"valid": False, "error": str(e)[:150]})
            self._capture = None
            self._data = []

def get(url):
    result = {"requested_url": url, "checked_at": datetime.now(timezone.utc).isoformat()}
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MinjaeHairSEOLiveAudit/1.0; public-read)",
        "Accept": "text/html,application/xhtml+xml,application/xml,image/*;q=0.8,*/*;q=0.5",
    })
    try:
        with urllib.request.urlopen(request, timeout=18) as r:
            data = r.read(2_500_000)
            result.update({
                "status": "accessible" if r.status == 200 else "http_error",
                "http_status": r.status, "final_url": r.url,
                "content_type": r.headers.get("Content-Type", ""),
                "bytes_read": len(data),
            })
    except urllib.error.HTTPError as e:
        result.update(status="http_error", http_status=e.code, error=str(e))
        return result
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        result.update(status="network_error", error=str(e))
        return result
    kind = result["content_type"].lower()
    if "html" in kind:
        p = Extract()
        p.feed(data.decode("utf-8", "replace"))
        result["seo"] = {
            "title": p.title, "description": p.description, "robots": p.robots,
            "canonical": p.canonical, "h1_count": sum(x["tag"] == "h1" for x in p.headings),
            "headings": p.headings[:14], "images": len(p.images),
            "missing_image_alt": sum(not x["alt"].strip() for x in p.images),
            "booking_link_count": sum("booking.naver.com" in x for x in p.anchors),
            "blogger_link_count": sum("ahairmj.blogspot.com" in x for x in p.anchors),
            "naver_blog_link_count": sum("blog.naver.com/a-hair_mj" in x for x in p.anchors),
            "jsonld": p.jsonld,
        }
    if "xml" in kind or url.endswith(".xml"):
        result["xml_has_urlset"] = b"<urlset" in data
        result["xml_loc_count"] = data.count(b"<loc>")
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="seo-live")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {key: get(url) for key, url in {**PAGES, **IMAGES}.items()}
    findings = []
    for key in ("homepage", "leaf_cut", "volume_perm", "down_perm"):
        item = results[key]
        if item["status"] != "accessible":
            findings.append({"level": "high" if item["status"] == "http_error" and item.get("http_status") == 404 else "investigate",
                             "subject": key, "finding": "Public fetch not confirmed; check error and retry in browser"})
            continue
        seo = item.get("seo", {})
        for field in ("title", "description"):
            if not seo.get(field):
                findings.append({"level": "high", "subject": key, "finding": "Missing " + field})
        if seo.get("h1_count") != 1:
            findings.append({"level": "medium", "subject": key, "finding": "H1 count should be 1"})
        if not seo.get("canonical"):
            findings.append({"level": "medium", "subject": key, "finding": "Canonical missing"})
        if seo.get("missing_image_alt"):
            findings.append({"level": "medium", "subject": key, "finding": "Images without alt"})
        if not seo.get("booking_link_count"):
            findings.append({"level": "medium", "subject": key, "finding": "No booking link in HTML"})
    if results["sitemap"].get("status") == "accessible" and results["sitemap"].get("xml_loc_count", 0) < 4:
        findings.append({"level": "high", "subject": "sitemap", "finding": "Fewer than 4 sitemap entries"})
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "HTTP requests from GitHub Actions runner; no browser JavaScript rendering",
        "limits": ["A 200 response does not prove search indexing or ranking",
                   "Naver/Blogger bot controls may block automated requests independently of normal browser access",
                   "JavaScript-rendered UI, booking completion and Core Web Vitals not measured"],
        "results": results, "findings": findings,
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 민재 헤어 라이브 SEO HTTP 점검", "", "GitHub Actions 외부 네트워크에서 공개 URL에 접근한 결과", "",
             "| 채널 / 경로 | HTTP 상태 | 검사 결과 |", "|---|---|---|"]
    for key, item in results.items():
        st = str(item.get("http_status", "-"))
        lines.append(f"| {key} | {st} | {item['status']} |")
    lines += ["", "## 개선 후보"]
    if findings:
        for finding in findings:
            lines.append(f"- **{finding['level']}** / {finding['subject']}: {finding['finding']}")
    else:
        lines.append("- HTTP 응답과 기초 HTML SEO 검사에서 발견된 중대 오류 없음 (색인·성능은 별도)")
    lines += ["", "## 해석 시 주의", *["- " + x for x in report["limits"]]]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\n--- Per-page metadata and conversion link checks ---")
    for key in ("homepage", "leaf_cut", "volume_perm", "down_perm"):
        item = results[key]
        meta = item.get("seo", {})
        print(json.dumps({
            "page": key, "http_status": item.get("http_status"),
            "title": meta.get("title"),
            "description_length": len(meta.get("description", "")),
            "canonical": meta.get("canonical"),
            "h1_count": meta.get("h1_count"),
            "image_count": meta.get("images"),
            "missing_image_alt": meta.get("missing_image_alt"),
            "booking_links": meta.get("booking_link_count"),
            "blogger_links": meta.get("blogger_link_count"),
            "naver_blog_links": meta.get("naver_blog_link_count"),
            "schema_valid": all(x.get("valid") for x in meta.get("jsonld", [])),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
