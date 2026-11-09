# 실제 마케팅 퍼널 데이터 검증 — 2026-11-09

## 범위 및 근거
- 조회 기간: 2026-11-01 ~ 2026-11-09 (GA4 / Google Search Console)
- GA4 연결: Windsor.ai Google Analytics 4, account `563083363` (홈페이지), measurement ID `G-HJ7ZN6WJWH`
- Search Console: `https://minjae38987.github.io/minjae-hair-site/`
- 이 문서는 수동으로 확인한 집계 스냅샷입니다. API 자동 연동이나 유료 고객 자동 집계가 아닙니다.
- 일부 데이터는 지연될 수 있으며 실험/기술 테스트 트래픽이 포함될 수 있습니다.

## GA4 실제 반환값
| 날짜 | 세션 | 페이지 조회 | 예약 링크 클릭 이벤트 |
|---|---:|---:|---:|
| 2026-11-07 | 1 | 3 | 0 (반환 없음) |
| 2026-11-08 | 6 | 17 | 17 |
| 합계(반환 데이터 기준) | **7** | **20** | **17** |

### 11월 8일 유입경로
| source/medium | 세션 | 예약 링크 클릭 이벤트 |
|---|---:|---:|
| `(direct) / (none)` | 4 | 12 |
| `chatgpt.com / ai-assistant` | 2 | 5 |

11월 7일 직접 유입 1세션 추가. 따라서 전체 세션은 직접 유입 5세션 + ChatGPT 유입 2세션.

### 페이지별 조회(전체 기간)
- `/minjae-hair-site/`: 5
- `/minjae-hair-site/styles/mens-down-perm-guide/`: 5
- `/minjae-hair-site/styles/mens-leaf-cut-before-after/`: 5
- `/minjae-hair-site/styles/mens-leaf-volume-perm/`: 5

**해석 주의:** 페이지 4개가 각각 정확히 5뷰, 11/8의 예약 링크 클릭 17회이므로 검증 중 반복 클릭이 포함됐을 *가능성*이 있습니다. 이것만으로 테스트 트래픽이라고 확정할 수는 없습니다. 클릭 17회 ≠ 고유 17명 ≠ 예약 17건 ≠ 유료 신규 17명.

## Search Console 실제 반환값
- 검색어(query) 차원: 반환 행 0개 → **검색 유입 0으로 확정할 수 없음**.
- 페이지(page) 차원: 홈페이지 `https://minjae38987.github.io/minjae-hair-site/`에 **노출 3회, 클릭 1회**.
- 검색어별 클릭/순위의 상세 분석 불가. 3회는 네이버 검색이 아닌 **Google Search Console** 기준.

## 운영·코드 상태
- GitHub 홈페이지 `minjae38987/minjae-hair-site` Draft PR #14, 미병합.
- PR #14 CI `42581272312`: success. 코드 검증이지 실적 검증이 아님.
- ChatCut `minjae38987/-2` 최근 PR 검사 3종은 failed, 모두 약 3~4초 만에 종료되고 job step 배열이 비어 있음. 이는 실행 환경/시작 단계 문제 가능성을 시사하지만 **원인은 미확정**. 잡 로그는 404 BlobNotFound.
- iSH V2 issue #22의 당일 신규 `PING` 응답 OK, 신규 `GIT_DIAG` 응답 OK. Python 3.9.16, git remote read OK.
- iSH V1 허용된 테스트는 별도 요청했으며 결과는 응답을 확인해야 함.

## 실제 고객 KPI
- 11월 목표: 유료 신규 100명.
- 11월 5일 당시 사용자 보고: 신규 1명(과거 수치).
- 연결된 11월 추적표의 저장 자료에서 실적 입력 0일. 현재 최신 유료 신규 실적 **미측정**.
- 리뷰 41건 및 최근 스타일링 41건은 11월 8일 기록된 공개 표시이며, 실제 신규 방문과 직접 대응하지 않음.

## 다음 조치
1. GA4에 기술 테스트와 실제 고객 유입을 구분할 수 있는 기간·유입원 분석을 유지한다(클릭 수를 예약 완료로 대체 금지).
2. Search Console 페이지 기준 데이터 축적을 확인한다(검색어 차원 미반환을 0회로 해석 금지).
3. 네이버 예약·매장 결제에서 확정예약/유료신규 방문을 개인식별 정보 제외 **집계값**으로 받는다.
4. ChatCut은 3초 내 CI 종료 원인을 GitHub Actions 정책/제한, 워크플로 조건, GitHub 측 실행 인프라 순으로 점검한다. 원인 확인 전 무제한 재실행 금지.
5. iSH에는 허용된 검증만 요청하고 Windows CapCut 실제 편집·고객 데이터 조작은 하지 않는다.
