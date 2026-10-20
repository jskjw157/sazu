# S1 구현 상태와 실행 방법

작성일: 2026-10-21. **실행 가능한 연구·검증용 기반 코드**이며, 사주 원국/앱 전체의 상용 출시 완료가 아닙니다.

상용 사주·운세 API는 구현·시험·장애 대체에 사용하지 않습니다. 기존 PR #1의 설계를 기반으로 한 별도 구현 브랜치이며 main 병합·운영 배포는 수행하지 않습니다.

## 구현한 것

| 모듈 | 현재 동작 |
|---|---|
| `calendar.py` | 한국 음양력 변환, 윤달 미상 후보, 엄격한 날짜/타입 검사, 요청별 상태 격리, 실제 라이브러리 버전·파일 해시 |
| `tzif.py`, `temporal.py` | 설치한 tzdata 파일 직접 로딩, 과거 offset/DST, gap/fold, 시간 미상의 UTC 구간 합집합, 정밀도/포함 경계 보존 |
| `contracts.py`, `serde.py` | 불변 입력·원천 계약, 중복 JSON 키·비유한 수·묵시 타입 변환 거절, 결정론 직렬화 |
| `sources.py` | 로컬 파일 크기/해시·심볼릭 링크 검사, 명시적 HTTPS 배치 수집, 호스트/리다이렉트/크기/재시도 제한, 부분 파일 공개 방지 |
| `solar_terms.py` | 24기/황경 매핑, 고정 UTC+9·24:00·분 반올림 구간, 연간 누락/중복/버전 혼합 검사, 로컬 Skyfield/JPL 어댑터 |
| `validation.py`, `datasets.py` | 날짜 집합 전체 비교, 공통 원천 계보 차단, 후보 산출물 무결성, 운영 승인 차단 |
| `cli.py` | 크기가 제한된 JSON stdin, 구조화된 결과/오류, 자동 출생정보 저장·로그 없음 |

`normalize_reference_record()`는 **6개 필드로 분리된 절기 레코드**의 정규화 함수입니다. KASI TXT 전체 문서 파서나 인증 API 수집기가 완성된 것은 아닙니다.

`DatasetCandidate`는 검증 후보입니다. 서명/권한 기반 활성화, 증거 내용과 coverage의 인증, PostgreSQL 배포본 관리는 아직 구현하지 않았습니다. 따라서 `require_production_release()`는 항상 `RELEASE_NOT_APPROVED`로 차단합니다. JSON의 임의 `approved=true`로 이를 우회하는 경로는 없습니다.

## 실제 검증과 미실행 구분

로컬 재검증 결과는 [검증 기록](docs/implementation/verification-20261021.json)에 기록했습니다.

- 최종 pytest: **174 passed, 1 skipped**. 네트워크 연결을 차단한 단위/회귀 테스트와 실제 CLI subprocess 테스트를 포함합니다.
- **1920-01-01~2050-12-31 전체 47,848일**의 양력→음력→양력 왕복 결과: 불일치 0. 동일 라이브러리의 **내부 일관성** 검증이며 공식 자료와 독립 대조한 결과가 아닙니다.
- 같은 환경에서 고정 `SOURCE_DATE_EPOCH`로 wheel 두 번 빌드: 동일 SHA-256. wheel에서 직접 모듈을 불러오는 smoke test 성공. 의존성을 새로 내려받은 완전 격리 설치 시험과는 다릅니다.
- `compileall` 성공. 로컬 Ruff·정적 타입 검사·Hypothesis·독립 리뷰는 실행하지 않았습니다. CI 정의가 존재한다는 사실만으로 CI 성공을 주장하지 않습니다.
- Skyfield/JPL 숫자 계산 통합 시험은 로컬 kernel 및 패키지 부재로 미실행입니다. CI는 별도 작업에서 공식 JPL 파일의 해시를 확인한 뒤 과거 모델 출력 48건과 비교하도록 정의했습니다. 이 비교도 새 KASI 공식 대조가 아니라 **모델 회귀 검증**입니다.

실행 환경 초기화로 업로드 전 작업파일이 소실되어, 보존된 8개 소스를 Git blob과 동일하게 복원하고 테스트와 미업로드 파일을 재구성했습니다. 그 후 발견한 날짜 범위·정밀도/메타데이터 오류는 실패를 재현하고 수정했습니다. 위 수치는 최종 보관된 테스트에 대한 재실행 결과이며 이전 임시 로그 수치를 합산하지 않았습니다.

## 설치와 사용

Python **3.13.5**, Linux/WSL2 기준입니다. 원천 파일 검사에서 Linux의 `O_NOFOLLOW`를 사용합니다. 다른 운영체제의 파일시스템 보안 동작은 별도 검증이 필요합니다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest -q
```

```bash
printf '%s' '{"kind":"korean_lunar","year":2017,"month":5,"day":1,"leap":"unknown"}' | python -m sazu calendar
printf '%s' '{"local_date":"2026-11-01","zone":"America/New_York","precision":"instant","local_time":"01:30"}' | python -m sazu normalize-time
printf '%s' '{}' | python -m sazu environment
python tools/check_calendar_range.py
```

윤달 미상 예시는 두 날짜를, 중복 시각 예시는 두 UTC 후보를 반환합니다. 날짜 후보마다 시간 정규화를 명시적으로 호출해야 하며, 두 모듈을 통합하는 HTTP 서비스/출생 프로필 저장 계층은 후속 범위입니다.

명령: `calendar`, `normalize-time`, `reference-term`, `verify-source`, `generate-terms`, `acquire-source`, `environment`. 출생 입력에 대한 정상 명령은 외부 네트워크가 필요하지 않습니다. **`acquire-source`만 운영자가 명시적으로 실행하는 네트워크 배치 명령**입니다. 파일 경로를 받는 CLI는 신뢰된 로컬 운영자를 위한 도구이며 인증 없이 외부 HTTP 엔드포인트로 노출하면 안 됩니다.

천문 통합 시험은 `requirements-astro.lock`과 사용 허용 범위를 확인한 JPL 파일을 로컬에 준비한 다음 `SAZU_KERNEL=/absolute/path/de440s.bsp python -m pytest -q tests/integration/test_skyfield_local.py`로 실행합니다. 파일을 Git에 올리지 않습니다.

## 의존성과 증거의 한계

현재 실행에 사용한 한국 음력 라이브러리는 **0.3.1**입니다. 과거 조사 문서의 0.4.0을 이번 환경에서 실행했다고 표시하지 않습니다. 없는 윤달을 평달로 바꾸는 상위 동작은 어댑터에서 반환 값과 역변환을 확인하여 거절합니다. 기존 연구 JSON을 새 버전에 맞추어 덮어쓰지 않았습니다.

`requirements-*.lock`은 **정확한 버전 목록**이며 wheel 해시까지 고정한 완전한 의존성 lock이 아닙니다. 실제 달력 소스·tzdata 파일·kernel/시간 자료의 해시는 별도로 추적합니다. 완전한 공급망 검토와 배포용 lock, 취약점 검사, SBOM은 출시 전 남은 작업입니다.

오픈소스 코드 라이선스, 내장 테이블의 출처, 공식 데이터의 이용권은 별개입니다. 현재 데이터의 상용 이용권이나 과거 날짜 전체의 물리적 정확성이 승인되었다고 주장하지 않습니다.

## 남은 작업

1. KASI 인증/허용된 독립 자료 확보, 양음력 전수 대조와 절기 전수 대조, 공식 원문 파서 및 권리 검토.
2. 실제 JPL/Skyfield 통합 실행, 원천·시간 모델 변경 영향 검토, 필요한 테스트/속성시험 확대.
3. 검증 증거와 지원 행렬을 인증하는 배포본 활성화, PostgreSQL migration·자체 HTTP API.
4. S2의 명명된 사주 규칙과 원국 계산, 이후 해석·기억·사용자 화면. 이번 코드가 이 기능들을 구현한 것은 아닙니다.

상세 계획: [구현 계획](docs/superpowers/plans/2026-10-21-foundation-implementation.md). 실행 가능한 기능과 출시 승인 여부를 분리해서 후속 개발합니다.
