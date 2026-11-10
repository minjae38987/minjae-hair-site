# 빠른 읽기 전용 장애 전환 V5 — 검토용

## 변화
- HEALTH_CHECK / LUMI_PUBLIC: Actions 실제 요청 댓글이 생성된 시각을 기준으로 **40초** 무응답 시 iSH로 전환
- 코드 검증: Actions 실제 요청 댓글 생성 시각을 기준으로 **90초** 무응답 시 iSH로 전환
- 요청 ID·task·runner가 일치하는 명시적 Actions 오류가 확인되면 다음 코디네이터 루프에서 iSH로 전환
- 작업 성공은 타임아웃보다 우선해 처리; iSH 결과 제한 시간도 iSH 요청 발송 시점부터 계산
- 기존 최대 요청 보관 시간(1800초), iSH 결과 대기(읽기 작업 240초, 코드 검증 420초), 20초 폴링, 파일 접근 범위, 코드 SHA 검증 및 읽기 전용 제한 유지
- 다른 계정/문제/프로토콜의 메시지에는 반응하지 않음

## 운영상 주의
GitHub Actions가 응답하지 않는 것만으로 사용량 제한이라고 확정할 수 없다. 지연 중인 Actions와 iSH가 **동시에 실행될 수 있으므로** 기존과 같이 **읽기 전용·멱등성 작업**에서만 빠른 전환을 적용한다. 고객 파일·블로그·영상 업로드 등 변경 작업을 자동 전환하도록 확대하지 않는다.

위 40초·90초는 최적화 초기값이며 실제 SLA 분석이나 장치 테스트로 검증된 보장 시간은 아니다. iSH의 20초 폴링 및 iPadOS 앱 정지에 따라 지연될 수 있다.

## 배포 전
```sh
python3 -m py_compile tools/ish-failover-coordinator.py tools/test-ish-failover-coordinator.py
python3 tools/test-ish-failover-coordinator.py
python3 tools/test-ish-code-runner.py
```
스테이징 설치 검증은 `tools/start-ish-worker.sh`의 기존 fail-closed 절차를 사용한다. 해당 스크립트는 `ish-worker-stable` 브랜치의 커밋을 가져오므로 **PR만 열어서는 실제 iSH 실행 코드가 바뀌지 않는다.** 검증 후 병합하고 launcher 재시작을 해야 적용된다.

## 안전 확인
1. 읽기 전용 HEALTH_CHECK 한 건의 Actions 정상 처리
2. 인위적 무응답 조건의 40초 iSH 전환(중복 발송 여부 확인)
3. CODE_VERIFY 의 90초 전환과 SHA 일치 검증
4. 지연된 결과가 와도 최종 응답 한 건만 발행
5. 실패 시 PR 되돌리기 또는 안정 브랜치 이전 커밋으로 복귀

## 테스트 상태
테스트 소스 추가 및 GitHub 업로드 확인은 가능하지만, CI/iSH의 실제 Python 실행 결과를 확보하지 못했다면 '미검증'으로 표시한다.
