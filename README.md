# sazu — 자체 계산 기반 사주·AI 연애 앱

**상용 사주·만세력·궁합·운세 API를 사용하지 않습니다.** 공식 원천과 오픈소스를 역할별로 활용하고 개발공수보다 재현성과 검증을 우선합니다.

> 현재 상태: **S1 연구·검증용 Python 패키지와 CLI 구현**. 사주 원국 엔진, 운영 DB, 모바일 앱, 상용 출시 승인은 아직 완료되지 않았습니다. 모든 CLI 성공 응답에도 `production_authorized=false`를 표시합니다.

## 구현과 검증

한국 음양력·윤달 후보 변환, 고정 tzdata 기반 시각 정규화, 절기 레코드·로컬 천문 계산 어댑터, 원천 파일 무결성/명시적 수집, 후보 데이터 검증을 제공합니다.

- [현재 구현 범위·설치·제한 사항](IMPLEMENTATION.md)
- [최종 실행 검증 기록](docs/implementation/verification-20261021.json)
- [파일별 구현 계획](docs/superpowers/plans/2026-10-21-foundation-implementation.md)
- [Python 소스](src/sazu), [테스트](tests), [CI 정의](.github/workflows/foundation.yml)

로컬 최종 회귀시험은 **174 passed, 1 skipped**입니다. **1920~2050년 전체 47,848일**의 양음력 왕복은 불일치가 없었으나, 같은 라이브러리의 내부 일관성 검증입니다. KASI 독립 전수 대조나 운세 예측력 검증이 아닙니다. 천문 숫자 계산의 로컬 통합 시험은 kernel/패키지 부재로 미실행이며, 원격 CI 결과는 PR에서 따로 확인해야 합니다.

```bash
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest -q
printf '%s' '{"kind":"korean_lunar","year":2017,"month":5,"day":1,"leap":"unknown"}' | python -m sazu calendar
```

Python 3.13.5의 별도 가상환경을 권장합니다. 실제 실행한 의존성 버전, 정확한 명령과 남은 검증은 IMPLEMENTATION.md를 확인하세요.

## 설계 기준

[ADR-0001](docs/decisions/0001-no-commercial-fortune-api.md) · [S1 설계](docs/superpowers/specs/2026-10-21-self-hosted-foundation-design.md) · [품질 로드맵](docs/QUALITY_ROADMAP.md) · [개발 지침](AGENTS.md)

`공식 원천 → 정규화 → 검증된 배포본 → 결정론 계산 규칙 → 승인된 해석 → 캐릭터 표현`이 전체 목표입니다. 현재 S1 코드가 이 전체 흐름을 완성한 것은 아닙니다. 승인된 배포본 활성화가 없으므로 운영 사용은 차단합니다. 입력 미상·정밀도 부족·자료 누락을 임의 값이나 상용 API로 보완하지 않습니다.

## 보존된 조사·작업 자료

| 경로 | 내용 |
|---|---|
| [DB 구축안](docs/architecture/saju_db_blueprint.md) | PostgreSQL 구조·콘텐츠·검수 설계 |
| [초기 백엔드 조사](docs/research/saju_backend_research_20261018.md) | 최초 조사 원본 |
| [원천·오픈소스·API 조사](docs/research/saju_source_commercial_research_20261020.md) | 역사 기록. 상용 API 도입 제안은 현재 범위에서 제외 |
| [기존 계산 비교](data/verification/saju_source_verification_20261020.json) | 과거 제한된 표본·버전 기록. 이번 최종 테스트 수에 합산하지 않음 |
| [원고·조건 예제](data/examples/saju_db_examples.json) | 검수 전 초안, 운영 데이터 아님 |
| [엑셀 작업표](planning/saju_db_workbook.xlsx) | 기존 7개 시트. 일정·수량은 과거 제안 |
| [데이터 현황](docs/DATA_STATUS.md) | 2026-10-20 당시 상태 |
| [출처대장](docs/SOURCE_REGISTRY.md) | 원천·후보 목록 |

KASI 원문 전체, JPL 바이너리, 개인정보·실제 출생기록·인증키는 포함하지 않습니다. 원천 이용권·계산 정확성·운영 승인은 별도로 검토합니다. 과거 보고서와 새 실행 결과를 구분합니다.
