#!/usr/bin/env python3
"""Independent HTTP/XML sitemap diagnostics. Public, unauthenticated only."""
import json
import urllib.request
import urllib.error
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path

base="https://minjae38987.github.io"
sitemap=base+"/minjae-hair-site/sitemap.xml"
targets=[
("sitemap",sitemap),("project_robots",base+"/minjae-hair-site/robots.txt"),
("host_root_robots",base+"/robots.txt"),("homepage",base+"/minjae-hair-site/")
]
agents={"standard":"Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/122.0 Mobile Safari/537.36",
"googlebot_token":"Googlebot/2.1 (+http://www.google.com/bot.html)"}
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None
opener=urllib.request.build_opener(NoRedirect)
def probe(url,agent):
    r={"url":url,"agent":agent}
    req=urllib.request.Request(url,headers={"User-Agent":agents[agent],"Accept":"application/xml,text/xml,text/html,*/*"})
    try:
        with opener.open(req,timeout=20) as x:
            body=x.read(1200000)
            r.update(status=x.status,content_type=x.headers.get("Content-Type"),location=x.headers.get("Location"),
              content_length=len(body),body_start=body[:90].decode("utf-8","replace"))
            if url==sitemap:
                try:
                    root=ET.fromstring(body)
                    loc=[e.text for e in root.iter() if e.tag.endswith("loc")]
                    r["xml_valid"]=root.tag=="{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
                    r["loc_count"]=len(loc)
                    r["loc_urls"]=loc
                except Exception as e:r["xml_error"]=str(e)
    except urllib.error.HTTPError as e:
        r.update(status=e.code,content_type=e.headers.get("Content-Type"),location=e.headers.get("Location"),error=str(e))
    except Exception as e:r["error"]=str(e)
    return r
def main():
    report={"time_utc":datetime.now(timezone.utc).isoformat(),"limits":[
        "A spoofed Googlebot user-agent does not demonstrate access from Google's verified crawler IPs.",
        "Google Search Console's past fetch error, Googlebot live inspection, and manual actions cannot be read here.",
        "HTTP 200 and valid XML do not imply Google successfully processed the sitemap."
    ],"tests":[probe(url,agent) for label,url in targets for agent in agents]}
    out=Path("sitemap-diagnostics");out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    for x in report["tests"]:
        print("SITEMAP_PROBE",json.dumps(x,ensure_ascii=False))
    broken=[x for x in report["tests"] if x["url"]==sitemap and
          (x.get("status")!=200 or x.get("xml_valid")!=True or x.get("loc_count")!=4)]
    print("SITEMAP_DIAG_RESULT",json.dumps({"all_sitemap_probes_pass":len(broken)==0,"broken":broken},ensure_ascii=False))
if __name__=="__main__":main()
