# 공식 대조 경로의 역사적 UTC 수정 연결

작성일: 2026-10-22. 대상 원격 기준: PR #7 `aac6e77a0ea88827d0dfcbfbb06a9f5a2ca2d5a8`.
상태: **로컬 패치 작성·테스트 완료, 원격 저장소에 미반영. 원천 수치 승인 실패 유지.**

> 이 문서는 이전 로컬 패치 작성 당시의 기록이다. 이후 적용 및 새 정책 결과는
> [clock-policy-20261022.md](clock-policy-20261022.md)를 참고한다.

## 확인된 연결 오류

PR #7은 `generate-terms` CLI를 `generate_reviewed_terms`로 연결했다. 그러나
`source_audit compare`는 `generate_terms`의 기존 UTC 표시를 `compare_term_range`로
대조하고 있었다. `tools/audit_official_terms.py` 및 공식 대조 CI도 그 경로를 사용한다.
즉, 기본 생성 명령과 공식 검증 명령이 서로 다른 시간 변환 정책을 평가했다.

## 변경

- `sazu.reviewed_term_audit.compare_reviewed_term_range`를 추가한다.
- 기존 계산의 TT 사건, 원천, 해시, 연간 키·순서 검사를 보존한 채 PR #7의
  ERFA 시간 변환을 적용한다. 별도의 천문 계산식을 만들지 않는다.
- `source_audit compare`의 기본 경로를 새 비교기로 연결한다.
- 이전 비교는 `source_audit compare-legacy`로 명시적으로 보존한다.
- 기존 비교 보고서 전체를 `legacy_comparison`에 남긴다.
- 확인 가능한 UTC의 수치 일치, 실제 수치 불일치, 미확정 과거 시계, 조건부 미래
  시계를 구분한다. 미확정·조건부 행은 `matched` 및 해결 건수에 넣지 않는다.
- CI 요약에 미확정·조건부·원래 불일치·해소·미해소 건수를 함께 표시한다.
- 공식 대조 실행 기록에 PyERFA 버전과 clock/comparator 코드 해시를 추가한다.
- 원문, 기존 `[-30,30)` 분 반올림 구간, 태양 위치 계산 및 운영 승인 기준은 변경하지 않는다.

## TDD 및 실제 실행

새 비교·연결 테스트 20개의 실패를 먼저 확인하고 구현 후 통과했다.
이어 CI 요약이 미확정 행을 누락하는 실패를 재현하고 요약 출력을 수정했다.
최종 새 테스트는 **21개**다.

최종 실행:

- Python 전체: **390 passed, 2 skipped, 0 failed**, 22.46초.
- Ruff: 통과.
- `compileall`: 통과.
- `git diff --check`: 통과.
- 건너뛴 2개: 기존 실제 JPL kernel 기반 통합시험. 이번 작업 환경에 해당 파일 없음.
- 이번 패치의 Node 코드·HTTP 인터페이스·DB·Docker 서비스 구조는 변경하지 않았다.
  이번 패치로 원격 CI·실제 Docker 통합시험을 실행했다고 주장하지 않는다.
- 독립적인 추가 코드 리뷰는 미실행. 자체 검토 및 자동 테스트다.

작업 환경은 CI 소스 스냅샷에 PR #7의 관련 런타임·시험 파일을 재구성했다.
그 파일들의 Git blob 해시가 원격 PR #7과 동일함을 확인했다. 전체 원격 checkout과
모든 설정 파일이 동일하다는 주장은 하지 않는다. 패치 대상 기존 파일들은 해당
기준의 내용과 일치하며 새 파일을 포함한 `git apply --check`를 별도 깨끗한 트리에서 검증한다.

## 3,144건 보관 기록 재검산

새 원문을 받은 검증이 아니다. CI run 39654192006의 기록을 SHA-256으로 확인하고
저장된 TT와 기존 표시값 차이를 다시 적용했다. 기존 기록의 분 표시값 복구 잔차는
0.0초였다. 원문 TXT나 kernel 바이너리를 이 패키지에 포함하지 않는다.

- probe SHA-256: `5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f`
- 과거 공식 원천 SHA-256: `508761248c7d18eb1ca1bcb1fcace2ba29f3f511d085321ae1e633c74d8e9e34`
- 원래 결과: 3,144건 중 2,830개 일치 / 314개 불일치.
- 새 비교 경로 재생: 확인 가능한 UTC 1,579건 중 **1,559개 일치 / 20개 불일치**.
- 과거 시계 미확정: **984건** (1920–1960).
- 미래 UTC 조건부: **581건**. 숫자상 569개 일치 / 12개 불일치는 진단용이며 승인된 일치 수가 아니다.
- 원래 314개 불일치 중 기존 PR #7의 수정으로 해결된 것은 **20개**.
- 나머지 **294개는 여전히 미해결/차단**: 과거 시계 262개 + 확인 가능한 UTC 수치 차이 20개 + 미래 조건부 차이 12개.
- 새 수치 불일치 추가: 0개.
- `status=failed`, `production_authorized=false` 유지.

이 패치는 기존 20개 수치 수정을 검증 경로에 연결하는 것이지, 별도의 20개를
추가로 고쳤다는 뜻이 아니다. 과거의 PR #6과 PR #7 결과 역시 서로 합산하지 않는다.

## 남은 원인 조사

확인 가능한 UTC에서 남은 20개는 1962년 경칩 1개와 1972–2025의 19개다.
이를 원천 판본·천문 모델·분 표시 정책과 분리해 검토해야 한다. 표시에 가까워지도록
상수를 더하거나 허용오차를 늘리는 변경은 하지 않았다. 1961년 이전 시각을 UT1으로
다시 이름 붙이거나 미래 윤초가 확정된 것으로 처리하지 않았다.

## 적용과 검증

현재 패치는 아래 원격 커밋을 기준으로 한다. 먼저 작업 내용을 보존하고 별도 브랜치에서 적용한다.

```sh
git fetch origin
git switch -c fix/reviewed-audit-integration aac6e77a0ea88827d0dfcbfbb06a9f5a2ca2d5a8
git apply --check /path/to/sazu-reviewed-audit-fix.patch
git apply /path/to/sazu-reviewed-audit-fix.patch
python -m pytest -q
python -m ruff check src tests tools
```

실제 승인된 원문과 kernel 파일이 준비된 환경에서 기존
`python tools/audit_official_terms.py --kasi ... --kernel ... --acquired-at ...`를 실행하면
이제 새 clock-aware 비교가 기본 적용된다. 이 결과를 관측하기 전 새 공식 전기간
대조 완료라고 표시하지 않는다. 숫자 실패/미확정 exit code는 계속 1/2다.
