# 교육 기반 마케팅 퍼널 V2

## 문제와 개선
- 기존 V1 템플릿은 측정하지 않은 데이터를 숫자 0으로 표시해 목표 달성률을 왜곡할 위험이 있었음
- V2에서 **공란은 미측정, 숫자 0은 측정한 0**으로 구분
- GA4 `naver_booking_click`은 예약 의도 이벤트로만 취급하며 유료 신규 인원으로 환산하지 않음
- 유입 경로별 중복 인원을 제거할 데이터가 없으므로 크로스채널 전환율을 계산하지 않음
- 테스트 유입이 의심되는 데이터는 `includes_tests`, 분리 불가한 경우 `unknown`

## 실행
```bash
python3 -m unittest discover -s tests -p 'test_marketing_evidence_v2.py' -v
python3 scripts/marketing_evidence_v2.py \
  --input marketing/funnel-evidence-example.csv \
  --report output/marketing-evidence-v2.md \
  --json output/marketing-evidence-v2.json \
  --briefs output/customer-briefs-v2.json
```
고객별 이름·연락처·영상은 입력하지 않음. 문서와 CSV는 통계만 저장.

## 고객 유형별 가설
1. 뜨는 옆머리 → B형 문제 해결 → 실제 모류·비포·애프터 증거
2. 볼륨 없는 직모 → A형 결과 비교 → 실제 시술 과정·결과
3. 스타일 실패 불안 → C형 상담 기술 → 상담 근거·시술 결과

이는 콘텐츠 실험 가설이지 성과가 검증된 광고 문구가 아님. 모든 게시·영상 배포는 별도 사용자 승인 필요.

## 책임
- AI: 원본을 과장하지 않는 기획 초안, 값 검증, 통계 집계
- 민재: 실제 고객 니즈 기록, 시술 근거 확인, 촬영/게시 동의, 유료 결제 실적 검증
- 매장: 네이버 예약·정산의 권한 있는 실제 집계 확인

## 실측 스냅샷
2026-11-08 GA4 속성 563083363 `naver_booking_click` 17회. 기술 테스트 트래픽 포함 가능성을 배제하지 못함. 확정 예약과 유료 신규는 미측정.

## 배포 정책
이 브랜치는 기존 PR #14 위에 쌓는 검토용 개발 작업. 운영 `main`에 자동 병합하지 않고 기존 ChatCut 영상 렌더/아이패드 호환 설정도 변경하지 않음.
