#!/usr/bin/env python3
"""Social channel/short-video URL structure audit. Independent implementation.
Does NOT claim access to creator-only analytics or bypass login walls.
Run: python scripts/seo_video_channel_audit.py --youtube URL --tiktok URL
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
VIDEO_URLS = [
  "https://www.instagram.com/reel/De0pawTTsgR/",
  "https://www.instagram.com/reel/DeOGo84zGyW/",
  "https://www.instagram.com/reel/DeQ7ENoTCK4/",
  "https://www.instagram.com/reel/DeTkvUETxsg/",
  "https://www.instagram.com/reel/DeWUFRnTw_o/",
  "https://www.instagram.com/reel/De8zXQSTFSm/",
  "https://www.instagram.com/reel/DeghPUlTxFS/",
  "https://www.instagram.com/reel/DelepHbzary/",
  "https://www.instagram.com/reel/DfHICmOT7IV/",
  "https://www.instagram.com/reel/DfPL0yLTWi5/"
]
CHANNELS = {
    "instagram": "https://www.instagram.com/a.hair_minjae/",
    "youtube": None,
    "tiktok": None,
}
KNOWN_DOMAINS = {
    "instagram": {"instagram.com", "www.instagram.com"},
    "youtube": {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"},
    "tiktok": {"tiktok.com", "www.tiktok.com", "m.tiktok.com"},
}

def inspect_url(url, channel):
    if not url:
        return {"status": "address_not_configured", "url": None}
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in KNOWN_DOMAINS[channel]:
        return {"status": "invalid_channel_url", "url": url}
    return {"status": "url_structure_valid", "url": url,
            "note": "URL syntax only; accessibility, ownership, SEO ranking and performance are not established"}

def analyze(youtube_url=None, tiktok_url=None):
    channels = dict(CHANNELS)
    channels["youtube"] = youtube_url
    channels["tiktok"] = tiktok_url
    reel_urls = [x for x in VIDEO_URLS if re.match(r"https://www\\.instagram\\.com/reel/[A-Za-z0-9_-]+/$", x)]
    return {
        "scope": "URL registry and static structure; NO creator analytics measured",
        "channels": {k: inspect_url(v, k) for k,v in channels.items()},
        "instagram_reels_on_homepage": len(reel_urls),
        "instagram_reels": reel_urls,
        "data_access": {
            "instagram": "Creator-side insights require authorized Meta professional-account access",
            "youtube": "YouTube Analytics requires owner OAuth / connected authorized channel",
            "tiktok": "Display API video.list requires app approval and authorized video.list scope",
        },
        "priority_checks": [
            "profile -> Naver reservation path visibility",
            "per-video title/caption and local-intent keywords",
            "first two seconds and message clarity: video-content manual review",
            "retention and audience source only if authorized actual metrics",
            "UTM/tagged links if platforms allow, to attribute click-to-booking",
        ],
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--youtube", help="Confirmed public channel URL", default=None)
    parser.add_argument("--tiktok", help="Confirmed public account URL", default=None)
    parser.add_argument("--output", default="seo-video-channel-report.json")
    opts = parser.parse_args()
    result = analyze(opts.youtube, opts.tiktok)
    Path(opts.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"instagram_reels": result["instagram_reels_on_homepage"], "channels": result["channels"]}, ensure_ascii=False, indent=2))
    print("REPORT:", opts.output)
