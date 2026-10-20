# sazu — 자체 계산 기반 사주·AI 연애 앱

한국어 AI 연애·운세 모바일 웹 앱을 위한 **사주 역법 데이터, 계산 규칙, 해석 콘텐츠, 검증 방법**을 정리하고 구현하는 저장소입니다.

> **현재 상태: 연구자료 + 상세 설계 검토안. 실행 가능한 제품 코드·계산 API·운영 DB는 아직 없습니다.** 문서와 예시는 상용 계산 엔진 검수, 공식 데이터셋의 전체 대조·승인 또는 운세 해석의 과학적 예측력을 입증하지 않습니다.

## 현재 결정

**상용 사주·만세력·궁합·운세 API를 사용하지 않습니다. 개발공수와 임시 출시일보다 완성도·재현성·검증을 우선하며, 오픈소스를 역할별로 재사용합니다.** 무료 공식 공공데이터의 수집·검증과 우리 서버의 자체 API는 별개입니다.

- [ADR-0001: 사용자 확정 방향과 API 제외 범위](docs/decisions/0001-no-commercial-fortune-api.md)
- [S1 상세 설계 검토안: 원천·한국 달력·절기·시간대·배포본](docs/superpowers/specs/2026-10-21-self-hosted-foundation-design.md)
- [품질 중심 개발 단계와 완료 증거](docs/QUALITY_ROADMAP.md)
- [AGENTS.md: 후속 개발 작업 지침](AGENTS.md)

새 상세 설계는 검토안입니다. 구현 계획·제품 코드·테스트 실행·배포 완료와 구분합니다. 과거 보고서의 상용 API 추천이나 10월 25일 임시 일정은 현재 방향을 덮어쓰지 않습니다.

## 권장 구조

`공식 원천 → 정규화 → 검증된 배포본 → 결정론 계산 규칙 → 승인된 해석 → 캐릭터 표현`

1. **한국 달력**: KASI 공식 자료와 한국 음력 변환 라이브러리를 대조하고 어댑터로 격리합니다.
2. **절기**: Skyfield + 고정 JPL 천문력으로 배치 생성하고 공식 절기 시각과 비교합니다.
3. **시간대**: 출생 당시의 IANA 자료와 실제 로딩 파일을 고정해 gap/fold·미상 구간을 처리합니다.
4. **사주 원국**: 입춘·절입·일주·시주 등 명시한 규칙 버전으로 계산합니다. 상세 규칙 엔진은 S2의 별도 설계 대상입니다.
5. **해석**: 검수한 원고와 적용 조건을 사용하며, LLM은 계산 원천이 아니라 설명/캐릭터 표현을 담당합니다.

Python 핵심 로직은 한 곳에 두고 이후 자체 API와 TypeScript 앱이 같은 계약을 사용하도록 설계합니다. 무거운 천문 계산을 매 대화마다 반복하지 않습니다. 현재는 이 구조를 구현한 코드가 아니라 설계입니다.

## 보관 중인 연구·작업 자료

| 경로 | 내용 |
|---|---|
| [docs/architecture/saju_db_blueprint.md](docs/architecture/saju_db_blueprint.md) | 기존 PostgreSQL DB 구조·원고·조건사전·검증 계획 |
| [docs/research/saju_backend_research_20261018.md](docs/research/saju_backend_research_20261018.md) | 초기 사주 계산·DB 백엔드 설계 조사 원본 |
| [docs/research/saju_source_commercial_research_20261020.md](docs/research/saju_source_commercial_research_20261020.md) | KASI·오픈소스·상용 API 비교의 역사 기록. 상용 API 도입안은 현재 실행 범위에서 제외 |
| [data/verification/saju_source_verification_20261020.json](data/verification/saju_source_verification_20261020.json) | 과거 제한된 실행 검증·경계 사례·버전 기록. 이번 설계 작성에서 재실행하지 않음 |
| [data/examples/saju_db_examples.json](data/examples/saju_db_examples.json) | 원고·조건·특징·정책·평가 항목의 검수 전 예시 |
| [planning/saju_db_workbook.xlsx](planning/saju_db_workbook.xlsx) | 7개 시트의 기존 작성/검수 작업표. 일정·수량은 역사적 제안 |
| [docs/DATA_STATUS.md](docs/DATA_STATUS.md) | 2026-10-20 당시 확보·검증 상태 |
| [docs/SOURCE_REGISTRY.md](docs/SOURCE_REGISTRY.md) | 공식 자료 및 당시 조사 후보 목록 |

## 중요한 경계

- KASI 원본 TXT 전체, JPL 천문력 바이너리, 전기간 음양력 변환표는 이 저장소에 포함하지 않았습니다. 원천별 권리·정밀도·무결성·검증 증거를 별도로 관리합니다.
- JSON·엑셀의 초안을 승인된 규칙·명리 원고·운영 DB로 취급하지 않습니다.
- 왕복 변환, 소수 표본 일치, 독립 원천 대조, 출시 승인은 서로 다른 상태입니다.
- 분 단위 반올림 값을 초 단위 정답으로 바꾸거나 시간 미상 입력에 정오를 넣지 않습니다.
- 상용 운세 API는 시험·장애 대체 경로에서도 사용하지 않습니다.
- 개인정보·실제 출생기록·대화·인증키는 공개 저장소에 커밋하지 않습니다.

## 시작 순서

[현재 결정](docs/decisions/0001-no-commercial-fortune-api.md) → [S1 설계 검토안](docs/superpowers/specs/2026-10-21-self-hosted-foundation-design.md) → [단계별 완료 기준](docs/QUALITY_ROADMAP.md) → 해당 단계의 구현 계획·실패 테스트·검증.

과거 연구자료 기준일: 2026-10-20. 현재 방향·설계 문서 작성일: 2026-10-21.
