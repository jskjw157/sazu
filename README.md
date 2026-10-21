# sazu — Express 메인 API + Python 계산 기반

상용 사주·운세 API 없이 자체 계산하는 한국어 AI 연애·운세 앱의 연구·개발 저장소입니다.

## 현재 구현

- `apps/api`: **Express + TypeScript** 메인 HTTP 경계. 입력/응답 검사, 접근키 분리, 요청 제한, 내부 호출 타임아웃과 실패 처리.
- `src/sazu`: **Python** 계산의 유일한 기준. 기존 한국 음양력·시간대·절기 기반과 비공개 HTTP 어댑터.
- `compose.yaml`: Express만 `127.0.0.1:3000`에 바인딩. Python/DB 포트는 공개하지 않고 계산망과 DB망을 분리.
- PostgreSQL: Express의 연결 점검과 제한된 앱 역할까지. 개인 기록 테이블·migration·저장 기능은 후속 범위.

**현재 제공하는 엔드포인트는 연구용 달력 변환·시간 정규화입니다. 사주 원국·대운·궁합, 사용자 로그인·결제·AI 대화, 공식 전기간 일치 검증·데이터 승인 및 운영 출시는 아직 완료되지 않았습니다.** 연구 접근키는 브라우저용 사용자 인증이 아니며 `production_authorized`는 false입니다.

## 문서

| 자료 | 링크 |
|---|---|
| 실행·Docker·보안 경계 | [Express/Python 안내](docs/implementation/express-python.md) |
| 현재 아키텍처 결정 | [ADR-0002](docs/decisions/0002-express-python-boundary.md) |
| 상용 API 제외 원칙 | [ADR-0001](docs/decisions/0001-no-commercial-fortune-api.md) |
| 이번 구현 계획 | [서비스 연결 계획](docs/superpowers/plans/2026-10-21-express-python-boundary.md) |
| 기존 S1 구현과 제한 | [IMPLEMENTATION.md](IMPLEMENTATION.md) |
| 원천·시간 기반 설계 | [S1 상세 설계](docs/superpowers/specs/2026-10-21-self-hosted-foundation-design.md) |
| 전체 개발 단계 | [QUALITY_ROADMAP.md](docs/QUALITY_ROADMAP.md) |
| 기존 DB 구축안 | [DB 설계](docs/architecture/saju_db_blueprint.md) |
| 조사·검증 자료 | [연구 문서](docs/research/) · [표본 검증 JSON](data/verification/) |
| 원고·정책 작업표 | [XLSX](planning/saju_db_workbook.xlsx) · [JSON 초안](data/examples/saju_db_examples.json) |
| 원천 출처·당시 상태 | [출처대장](docs/SOURCE_REGISTRY.md) · [2026-10-20 상태](docs/DATA_STATUS.md) |

기존 연구자료와 수치 시험을 보존하며 이번 HTTP 통합시험과 혼동하지 않습니다. 왕복 일관성·독립 공식 대조·규칙 검증·출시 승인은 각각 다릅니다. 외부 자료/천문력의 전체 재배포와 실제 사용자 데이터·키의 공개 커밋은 금지합니다.

현재 변경은 검토용 작업 브랜치에서 전달하며 자동 병합·운영 배포를 하지 않습니다. 개발 시 [AGENTS.md](AGENTS.md)를 먼저 읽으세요.

## 2026-10-21 공식 원천 검증 후속

[공식 원천 파서·전기간 대조 결과](docs/implementation/official-source-validation.md)를 추가했습니다. 코드 테스트는 통과했지만 **1920–2050년 절기3,144개 중314개가 공식 표시 분값과 불일치**하여 수치 승인 gate는 실패 상태입니다. 시간척도 진단은 별도 가설이며 운영 계산에는 적용하지 않았습니다. Express/Python 역할과 기존 수치 코어는 유지됩니다.
