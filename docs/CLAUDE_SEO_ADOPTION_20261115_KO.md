# Claude SEO 선택적 도입 — 2026-11-15

## 결론
AgriciDaniel/claude-seo (MIT) 전체를 설치하지 않고 지역 SEO·경쟁 디자이너 포지셔닝·키워드 클러스터 구성 방법만 독립적인 표준 라이브러리 모듈로 적용한다. 이 코드는 원본 플러그인을 실행하거나 복제하지 않는다.

## 근거와 위험
- 검토: 원본 README, SECURITY.md, install.ps1, requirements.txt, seo-local/SKILL.md, seo-cluster/SKILL.md
- 원본 프로젝트의 설치/브라우저 샌드박스/외부 인증 의존 위험 때문에 자동 실행은 미도입
- 개인별 관측자료: marketing/individual_brand_evidence_20261109.json
- 오래된 관측과 제3자 미러는 재검증 대상으로 표시
- 개인 프로필 표현의 문자열 중복은 검색 노출·시술 수준·예약 실적을 뜻하지 않음
- 실제 SERP 상위 URL 중복, 순위, 검색량은 별도 측정 없이는 출력하지 않음

## 실행 (Python 3.11 이상)
python scripts/local_seo_intelligence.py --input marketing/individual_brand_evidence_20261109.json --output output/local-seo-intelligence.json --as-of 2026-11-15
python -m unittest discover -s tests -p 'test_local_seo_intelligence.py' -v

## 보호 규칙
- API·브라우저·고객 개인정보·GitHub Secrets 접근 없음
- 외부 요청, 자동 게시, 자동 예약 조작, 프로덕션 배포 없음
- 관측 30일 초과 또는 미러 출처는 재확인 대상으로 표시
- 미측정은 0으로 치환하지 않음
- 기존 GA4/ChatCut/GitHub Actions 파일은 변경하지 않음

## 다음 검증
1. GitHub Actions 없이 수동 실행하여 JSON 보고서 확인
2. 디자이너별 최신 공식 프로필 URL, 관측 날짜 갱신
3. GSC/네이버에서 실제 검색어와 콘텐츠 성과를 확보한 후 측정 가능한 항목만 통합
4. 운영 배포는 별도 코드 리뷰 및 사용자 승인 후 진행
