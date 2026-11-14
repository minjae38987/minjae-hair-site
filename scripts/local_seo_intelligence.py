#!/usr/bin/env python3
"""Privacy-preserving local stylist SEO evidence report (standard library only).
Inspired by Claude SEO's local SEO/content cluster methodology; no upstream code executed.
No scraping, ranking assumptions, publishing, credentials, or customer-level information.
"""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

KEYWORDS = {
    '뜨는 옆머리': ['다운펌', '남자커트', '뜨는머리'],
    '직모 볼륨': ['볼륨매직', '쉐도우펌', '가르마펌'],
    '짧은 디자인': ['드롭컷', '필러스컷', '가일컷', '숏가일'],
    '자연스러운 디자인': ['시스루댄디', '리프컷', '시스루펌'],
}
OWNER_TERMS = ['다운펌', '필러스', '드롭', '가일', '시스루', '리프', '모질', '두상', '상담', '손질']

def audit(source: dict, as_of: date) -> dict:
    if not isinstance(source.get('competitors'), list):
        raise ValueError('competitors must be a list')
    records = []
    counters = Counter()
    seen_ids = set()
    for row in source['competitors']:
        identifier = row['designer_id']
        if identifier in seen_ids:
            raise ValueError(f'duplicate designer id: {identifier}')
        seen_ids.add(identifier)
        observed = date.fromisoformat(row['observed_at'])
        age = (as_of - observed).days
        if age < 0:
            raise ValueError(f'observation in future: {identifier}')
        texts = ' '.join(map(str, row.get('claims', []) + row.get('styles', [])))
        overlap = [term for term in OWNER_TERMS if term in texts]
        counters.update(overlap)
        trust = {'naver_profile_snapshot': 'B', 'official_personal_profile': 'A', 'third_party_mirror': 'D', 'third_party_listing': 'C'}.get(row.get('source_type'), 'unverified')
        records.append({
            'designer_id': identifier, 'name': row.get('name'), 'salon': row.get('salon'),
            'observed_at': observed.isoformat(), 'age_days': age,
            'source_grade': trust, 'requires_recheck': age > 30 or trust in ('D', 'unverified'),
            'overlap_terms': overlap, 'overlap_count': len(overlap),
            'source_url': row.get('source_url'),
            'review_count_observed': row.get('review_count'),
            'styling_count_observed': row.get('styling_count'),
            'caveat': '포지셔닝 문구 중복도이며 순위·매출·예약·시술 실력 아님',
        })
    records.sort(key=lambda r: (-r['overlap_count'], r['name'] or ''))
    clusters = [{'customer_problem': key, 'example_keywords': vals,
                 'intent': '정보탐색 또는 예약검토', 'serp_overlap_verified': False,
                 'next_evidence': '네이버/구글 검색 결과와 GSC 데이터 확보 후 검증'}
                for key, vals in KEYWORDS.items()]
    return {
        'schema_version': 'local_seo_intelligence_v1', 'as_of': as_of.isoformat(),
        'method': '관측된 개인 포지셔닝 문구의 문자열 중복; 실제 검색 결과 순위 분석 아님',
        'source_provenance': '사용자 기존 GitHub 자료; 실시간 재직 여부와 검색순위 미확인',
        'individuals': records, 'term_frequency': dict(counters.most_common()),
        'keyword_clusters_hypotheses': clusters,
        'differentiation_hypothesis': '고객 모류 진단 → 커트/다운펌 선택 근거 → 같은 각도 전후 비교 → 자가 손질',
        'not_measured': ['실제 검색순위', '검색량', '매장과 개인별 신규 예약', '전환율', '현재 재직', '현재 리뷰 수'],
        'safety': {'auto_publish': False, 'external_requests': False, 'credential_access': False,
                   'customer_personal_data': False, 'no_claim_of_unique_skill': True},
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, default=Path('marketing/individual_brand_evidence_20261109.json'))
    p.add_argument('--output', type=Path, default=Path('output/local-seo-intelligence.json'))
    p.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = p.parse_args()
    result = audit(json.loads(args.input.read_text(encoding='utf-8')), args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"local SEO evidence report: {len(result['individuals'])} designers; {args.output}")
if __name__ == '__main__':
    main()
