"""Evidence-first, read-only brand strategy for MINJAE's existing six roles.

Does not claim to run six autonomous models, inspect media, publish or measure
bookings. Converts grounded competitor observations into reviewable briefs.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROLES = (
    "video_analyst", "marketing_analyst", "content_planner",
    "copywriter", "editor", "quality_reviewer"
)
CHANNELS = ("naver_place", "naver_blog", "instagram", "youtube_shorts", "website")
SEGMENTS = (
    ("side_hair", "뜨는 옆머리", "옆머리가 계속 뜨는 이유를 알고 싶은 고객",
     "커트와 다운펌이 필요한 부분을 구분하는 상담"),
    ("flat_straight", "볼륨 없는 직모", "앞머리나 정수리의 볼륨이 부족한 고객",
     "커트만으로 가능한 부분과 펌이 필요한 이유 설명"),
    ("style_uncertainty", "사진과 실제 머리의 차이", "참고 사진대로 되지 않을까 걱정하는 고객",
     "현재 길이·모류·모질과 원하는 실루엣을 비교하는 상담"),
)
KEYWORDS = ("두상", "모질", "모류", "1:1", "맞춤", "다운펌", "필러스", "드롭", "가일",
            "시스루", "숏가일", "리프", "손질", "볼륨", "상담")
SOURCE_TYPES = {"official_profile", "naver_profile_snapshot", "public_post", "third_party_mirror"}
BANNED_CLAIMS = ("유일", "독보적", "100% 보장", "완벽 보장", "무조건 성공", "1위 확정",
                 "누구보다", "절대 실패하지")
RESERVATION_URL = ("https://m.booking.naver.com/booking/13/bizes/1512690/"
                   "items/8096768?theme=place&tab=details&lang=ko&area=pll")
DEFAULT_PROMISE = "뜨는 머리, 자르기 전에 이유부터 봅니다."

def _valid_url(value):
    if not isinstance(value, str) or not value.startswith("https://"):
        return False
    parsed = urlsplit(value)
    return bool(parsed.netloc and not parsed.username and not parsed.password)

def _str(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise ValueError("Missing or unsafe text: "+name)
    return value.strip()

def _date(value):
    text=_str(value,"observed_at",10)
    try: parsed=date.fromisoformat(text)
    except ValueError as exc: raise ValueError("Invalid observed_at") from exc
    if parsed.isoformat()!=text: raise ValueError("Invalid observed_at")
    return text

def validate(data):
    if not isinstance(data,dict) or data.get("schema_version")!="individual_brand_evidence_v1":
        raise ValueError("Expected individual_brand_evidence_v1")
    owner=data.get("owner")
    if not isinstance(owner,dict) or _str(owner.get("id"),"owner.id")!="minjae":
        raise ValueError("Expected minjae owner")
    if not isinstance(data.get("competitors"),list) or not data["competitors"]:
        raise ValueError("Competitor observations required")
    if len(data["competitors"])>30: raise ValueError("Too many competitors")
    seen=set()
    for entry in data["competitors"]:
        if not isinstance(entry,dict): raise ValueError("Invalid competitor")
        identity=_str(entry.get("designer_id"),"designer_id",80)
        if identity in seen or identity=="minjae": raise ValueError("Duplicate or owner designer")
        seen.add(identity)
        _str(entry.get("name"),"name",80)
        _str(entry.get("salon"),"salon",100)
        _date(entry.get("observed_at"))
        source_type=entry.get("source_type")
        if source_type not in SOURCE_TYPES: raise ValueError("Unknown source type")
        if not _valid_url(entry.get("source_url")):raise ValueError("Invalid source URL")
        for field in ("claims", "styles"):
            value=entry.get(field)
            if not isinstance(value,list) or len(value)>20 or not value:
                raise ValueError("Missing "+field)
            for item in value:_str(item,field,100)
        for metric in ("review_count","styling_count"):
            value=entry.get(metric)
            if value is not None and (type(value) is not int or value<0):
                raise ValueError("Bad count: "+metric)
    return data

def _overlaps(profile):
    owner_terms=set(profile.get("owner",{}).get("comparison_keywords",[]))
    if not owner_terms: owner_terms={"두상","모질","상담","손질","다운펌","필러스","드롭","가일","시스루","리프"}
    results=[]
    for entry in profile["competitors"]:
        corpus=" ".join(entry["claims"]+entry["styles"])
        shared=sorted(k for k in owner_terms if isinstance(k,str) and k in corpus)
        results.append({
          "designer_id":entry["designer_id"],"name":entry["name"],"salon":entry["salon"],
          "overlap_terms":shared,"overlap_term_count":len(shared),
          "observed_at":entry["observed_at"],"source_url":entry["source_url"],
          "source_type":entry["source_type"],"counts_not_customer_totals":True,
          "booking_performance":None,"skill_quality":None
        })
    return sorted(results,key=lambda r:(-r["overlap_term_count"],r["designer_id"]))

def _copy():
    p=DEFAULT_PROMISE
    ig_tags=["#서울대입구미용실","#에이점헤어_민재","#다운펌","#뜨는옆머리","#남자머리"]
    return {
      "naver_place":{
        "headline":p,
        "body":"뜨는 옆머리·볼륨 부족·손질 고민부터 확인하고, 모류·모질·두상을 바탕으로 커트와 펌의 선택 기준을 설명합니다. 결과는 실제 시술 사진으로 확인해 주세요.",
        "cta":"민재 디자이너 지정예약에서 상담 가능 여부 확인",
        "booking_url":RESERVATION_URL,
      },
      "naver_blog":{
        "headline":"서울대입구 남자머리 | 뜨는 옆머리, 커트와 다운펌 중 무엇이 필요할까?",
        "body":"옆머리가 뜨는 위치와 길이, 모류를 먼저 살펴봅니다. 실제 고객 사례에서 확인된 조건과 시술 전후 사진으로 선택 기준을 설명합니다.",
        "cta":"민재 디자이너 지정예약에서 상담 예약 확인",
        "booking_url":RESERVATION_URL,
      },
      "instagram":{
        "headline":"뜨는 옆머리, 짧게 자르는 것만이 답일까요?",
        "body":"옆머리가 뜨는 이유부터 확인합니다. 실제 모류에 따라 커트와 다운펌의 선택 기준이 달라질 수 있습니다. 상담은 프로필의 예약 링크에서 확인해 주세요.",
        "hashtags":ig_tags,
        "cta":"프로필 예약 링크 확인",
      },
      "youtube_shorts":{
        "headline":"뜨는 옆머리, 커트와 다운펌 선택 기준",
        "body":"옆머리가 뜨는 위치와 모류에 따라 시술 선택을 다르게 검토할 수 있습니다. 실제 사례를 통해 설명하겠습니다. 헤어 상담 및 예약은 채널 프로필의 네이버 예약 링크를 확인해 주세요.",
        "cta":"채널 프로필의 네이버 예약 링크 확인",
      },
      "website":{
        "headline":p,
        "body":"옆머리 부피, 앞머리 볼륨, 원하는 스타일과 현재 모발의 차이를 먼저 확인합니다. 필요한 시술과 그 한계를 설명하는 상담을 지향합니다.",
        "cta":"민재 디자이너 네이버 지정예약 확인",
        "booking_url":RESERVATION_URL,
      },
    }

def analyze(data):
    validate(data)
    overlap=_overlaps(data)
    copy=_copy()
    copy_issues=[]
    for ch,item in copy.items():
        for key in ("headline","body","cta"):
            s=item[key]
            if any(x in s for x in BANNED_CLAIMS):copy_issues.append(ch+": exaggerated "+key)
    if len(copy["instagram"]["hashtags"])!=5:copy_issues.append("instagram hashtag count")
    if len(set(copy["instagram"]["hashtags"]))!=5:copy_issues.append("instagram hashtag duplicates")
    if "프로필" not in copy["youtube_shorts"]["cta"]:copy_issues.append("youtube CTA")
    if any(x.get("booking_performance") is not None for x in overlap):copy_issues.append("fabricated competitor booking data")
    segments=[{"segment_id":sid,"problem":name,"customer_question":question,"verified_service_hypothesis":answer,
       "required_proof":["source ownership/consent","real before image","technical assessment","real after image","home styling explanation"],
       "result_proven":False, "paid_new_customers":None} for sid,name,question,answer in SEGMENTS]
    roles={
      "video_analyst":{"responsibility":"원본·시술 전후 진위와 고객 동의 확인","deliverable":"evidence_requirements_only","media_inspected":False},
      "marketing_analyst":{"responsibility":"개별 디자이너 공개 자료·중첩 분석·유료 신규 KPI","deliverable":"individual_competitor_overlap","measured_booking_attribution":False},
      "content_planner":{"responsibility":"고객 유형·검색 의도·채널별 발견→신뢰→예약 경로 설계","deliverable":"segment_channel_briefs"},
      "copywriter":{"responsibility":"실제로 증명 가능한 문구·채널별 CTA·정확히 5개 인스타 해시태그","deliverable":"platform_copy_drafts"},
      "editor":{"responsibility":"콘텐츠 아웃라인과 Windows 편집 인수인계, 실제 렌더 미수행","deliverable":"production_handoff","video_rendered":False},
      "quality_reviewer":{"responsibility":"출처·실적·시술·동의·이탈 가설을 독립 검증","deliverable":"qa_decision"}
    }
    source_caveats=["공개 문구의 겹침은 실력·예약률·성과의 순위가 아닙니다.",
        "과거 네이버 프로필 표시 건수는 월간 고객·유료 신규 건수와 같지 않습니다.",
        "제3자 미러는 원문 직접 검증 전까지 신뢰도가 낮습니다.",
        "고객 동의·실제 시술 전후·예약 완료를 현재 자료로 입증하지 못했습니다."]
    issues=list(copy_issues)
    if any(p["source_type"]=="third_party_mirror" for p in overlap):
        issues.append("mirror_based_comparisons_need_official_confirmation")
    issues+=["actual_case_proof_missing","paid_booking_attribution_missing",
             "manual_editorial_review_required"]
    return {
       "schema_version":"six_role_brand_strategy_v1","status":"strategy_draft_review_required",
       "brand":{"main_promise":DEFAULT_PROMISE,
                "service_mechanism":"모류·모질·두상 확인 → 커트/다운펌/펌 선택 기준 → 실증 결과 → 손질 안내",
                "unique_skill_proven":False,"market_advantage_proven":False},
       "roles":roles,"individual_competitors":overlap,
       "customer_segments":segments,"channel_copy":copy,
       "quality":{"pass":False,"blockers":issues,"caveats":source_caveats,
                  "publication_approved":False,"media_production_approved":False},
       "conversion":{"paid_new_customers":None,"booking_completed":None,
                     "booking_clicks_are_bookings":False},
       "human_review_required":True,"auto_publish":False
    }

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args(argv)
    data=json.loads(args.input.read_text(encoding="utf-8"))
    output=analyze(data)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("BRAND_STRATEGY",output["status"],"COMPETITORS",len(output["individual_competitors"]))
if __name__=="__main__":
    main()
