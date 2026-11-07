#!/usr/bin/env python3
"""Discover public blog article permalinks by checking public RSS/Atom feeds.
This intentionally does not fabricate URLs or bypass rate limits.
"""
import json
import re
from urllib import request, error
from xml.etree import ElementTree as ET
from datetime import datetime, timezone

FEEDS = {
  "blogger_atom": "https://ahairmj.blogspot.com/feeds/posts/default?max-results=25",
  "blogger_rss": "https://ahairmj.blogspot.com/feeds/posts/default?alt=rss&max-results=25",
  "naver_rss": "https://rss.blog.naver.com/a-hair_mj.xml",
  "naver_rss_alt": "https://blog.rss.naver.com/a-hair_mj.xml",
}
def get(feed,url):
    result={"feed":feed,"url":url,"status":"unknown","entries":[]}
    try:
        req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; MinjaeHairBlogDiscovery/1.0)", "Accept":"application/atom+xml,application/rss+xml,application/xml,text/xml"})
        with request.urlopen(req,timeout=17) as resp:
            result["http_status"]=resp.status
            payload=resp.read(1200000)
        root=ET.fromstring(payload)
        typ=root.tag.split("}")[-1]
        if typ=="feed":
            ns="{http://www.w3.org/2005/Atom}"
            for entry in root.findall(ns+"entry"):
                title=(entry.findtext(ns+"title") or "").strip()
                link=next((x.attrib.get("href","") for x in entry.findall(ns+"link") if x.attrib.get("rel")=="alternate"),"")
                if title and link:result["entries"].append({"title":title,"url":link})
        elif typ=="rss":
            for entry in root.findall("./channel/item"):
                title=(entry.findtext("title") or "").strip()
                link=(entry.findtext("link") or "").strip()
                if title and link:result["entries"].append({"title":title,"url":link})
        else:
            result["error"]="Unsupported RSS format "+typ
        result["status"]="ok"
    except error.HTTPError as exc:
        result.update(status="http_error",http_status=exc.code)
    except Exception as exc:
        result.update(status="network_or_parse_error",error=str(exc)[:300])
    return result

results=[get(name,url) for name,url in FEEDS.items()]
for r in results:
    print("FEED_RESULT",json.dumps(r,ensure_ascii=False))
print("BLOG_LINKS",json.dumps({
    "created_at":datetime.now(timezone.utc).isoformat(),
    "discovered":sum(len(r["entries"]) for r in results),
    "results":results,
},ensure_ascii=False))
