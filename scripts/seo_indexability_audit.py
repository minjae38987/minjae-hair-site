#!/usr/bin/env python3
"""Public indexability preflight for four canonical website pages.
Checks publicly observable technical conditions; does not claim Google indexing.
"""
import json
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

ROOT="https://minjae38987.github.io/minjae-hair-site/"
URLS=[
 ROOT,
 ROOT+"styles/mens-leaf-cut-before-after/",
 ROOT+"styles/mens-leaf-volume-perm/",
 ROOT+"styles/mens-down-perm-guide/",
]
UA="MinjaeHairIndexabilityAudit/1.0 (+public website preflight)"
class HTML(HTMLParser):
 def __init__(self):
  super().__init__(); self.can=[];self.meta=[];self.links=[];self.title="";self._title=False
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=="title":self._title=True
  if tag=="link" and "canonical" in a.get("rel","").lower().split():self.can.append(a.get("href",""))
  if tag=="meta" and a.get("name","").lower() in ("robots","googlebot"):self.meta.append({"name":a["name"].lower(),"content":a.get("content","")})
  if tag=="a" and a.get("href"):self.links.append(a["href"])
 def handle_endtag(self,tag):
  if tag=="title":self._title=False
 def handle_data(self,data):
  if self._title:self.title+=data
def request(url):
 try:
  req=urllib.request.Request(url,headers={"User-Agent":UA})
  with urllib.request.urlopen(req,timeout=20) as res:
   raw=res.read(2600000)
   return {"status":res.status,"url":res.url,"headers":dict(res.headers.items()),"body":raw.decode("utf-8","replace")}
 except Exception as err:return {"error":str(err)[:300]}
def main():
 output=Path("seo-indexability");output.mkdir(exist_ok=True)
 robots=request(ROOT+"robots.txt")
 sitemap=request(ROOT+"sitemap.xml")
 robots_content=robots.get("body","")
 sitemaps=[]
 if "body" in sitemap:
  try:
   doc=ET.fromstring(sitemap["body"])
   sitemaps=[e.text.strip() for e in doc.iter() if e.tag.endswith("loc") and e.text]
  except Exception as exc:sitemap["parse_error"]=str(exc)
 report={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"robots":{"status":robots.get("status"),"sitemap_line_present":("Sitemap: "+ROOT+"sitemap.xml") in robots_content,"no_global_disallow":not bool(re.search(r"(?im)^Disallow:\s*/\s*$",robots_content))},"sitemap":{"status":sitemap.get("status"),"parse_error":sitemap.get("parse_error"),"entries":sitemaps},"pages":[],"limitations":["This checks public indexability prerequisites, not Google URL Inspection/index coverage.","A page with HTTP 200 and indexable metadata may remain unindexed.","This audit does not submit sitemaps or make Google indexing requests."]}
 for url in URLS:
  r=request(url);a={"url":url,"http_status":r.get("status"),"redirected_to":r.get("url"),"error":r.get("error")}
  if "body" in r:
   p=HTML();p.feed(r["body"])
   a["title"]=p.title.strip()
   a["canonical"]=p.can
   a["robots_meta"]=p.meta
   a["x_robots_tag"]=r["headers"].get("X-Robots-Tag",r["headers"].get("x-robots-tag",""))
   a["content_type"]=r["headers"].get("Content-Type",r["headers"].get("content-type",""))
   a["listed_in_sitemap"]=url in sitemaps
   a["homepage_inbound_links"]=0
   if url==ROOT: home_links=p.links
   a["outgoing_internal_links"]=len([v for v in p.links if urljoin(url,v).startswith(ROOT)])
   a["noindex"]=bool(re.search(r"(?i)\bnoindex\b",a["x_robots_tag"])) or any(re.search(r"(?i)\bnoindex\b",v["content"]) for v in p.meta)
  report["pages"].append(a)
 # Re-fetch the home page for robust internal link verification independent of page ordering.
 home=HTML();hr=request(ROOT)
 if "body" in hr:home.feed(hr["body"])
 links={urljoin(ROOT,href).split("#")[0] for href in home.links}
 for item in report["pages"]:
  item["linked_from_homepage"]=item["url"]==ROOT or item["url"] in links
  item["preflight_pass"]=(item.get("http_status")==200 and
    item.get("canonical")==[item["url"]] and not item.get("noindex",True) and
    item.get("listed_in_sitemap",False) and item.get("linked_from_homepage",False) and
    report["robots"]["no_global_disallow"])
 failures=[x["url"] for x in report["pages"] if not x["preflight_pass"]]
 report["failed_preflights"]=failures
 (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 md=["# 4개 URL 공개 색인 가능 조건 점검","","| 페이지 | HTTP | Canonical | Sitemap | 홈 내부링크 | Noindex 없음 | 사전 점검 |","|---|---:|---|---|---|---|---|"]
 for x in report["pages"]:
  label="홈페이지" if x["url"]==ROOT else x["url"].rstrip("/").split("/")[-1]
  md.append("| "+label+" | "+str(x.get("http_status","-"))+" | "+("정상" if x.get("canonical")==[x["url"]] else "점검")+
   " | "+("예" if x.get("listed_in_sitemap") else "아니오")+" | "+("예" if x.get("linked_from_homepage") else "아니오")+
   " | "+("예" if x.get("noindex") is False else "미확인/아니오")+" | "+("통과" if x["preflight_pass"] else "확인 필요")+" |")
 md+=["","**주의:** 이 검사는 URL 색인 '완료'가 아닌 공개 기술 요건만 확인합니다.","","## 실패 항목",*([f"- {x}" for x in failures] if failures else ["- 없음"])]
 (output/"report.md").write_text("\n".join(md)+"\n",encoding="utf-8")
 print("\n".join(md))
 print("INDEXABILITY_JSON",json.dumps({"pages":report["pages"],"robots":report["robots"],"sitemap_entries":len(sitemaps)},ensure_ascii=False))
if __name__=="__main__":main()
