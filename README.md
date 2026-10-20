# sazu — 사주 원천 데이터 및 DB 구축 자료

한국어 AI 연애·운세 모바일 웹 앱을 위한 **사주 역법 데이터, 계산 규칙, 해석 콘텐츠, 검증 방법**을 정리한 연구·설계 저장소입니다.

> **상태: 조사·설계 / 검증 표본 보관.** 이 저장소의 예시는 상용 계산 엔진이나 공식 데이터셋의 전체 적재·승인을 의미하지 않습니다. 운세 해석의 과학적 예측력을 증명하지 않습니다.

## 자료 목록

| 경로 | 내용 |
|---|---|
| [docs/architecture/saju_db_blueprint.md](docs/architecture/saju_db_blueprint.md) | PostgreSQL DB 구조·콘텐츠 원고·조건사전·검증 계획 |
| [docs/research/saju_backend_research_20261018.md](docs/research/saju_backend_research_20261018.md) | 초기 사주 계산·DB 백엔드 설계 조사(원본) |
| [docs/research/saju_source_commercial_research_20261020.md](docs/research/saju_source_commercial_research_20261020.md) | KASI·오픈소스·상용 API 비교와 도입 기준 |
| [data/verification/saju_source_verification_20261020.json](data/verification/saju_source_verification_20261020.json) | 제한된 실행 검증·경계 사례·패키지 버전 기록 |
| [data/examples/saju_db_examples.json](data/examples/saju_db_examples.json) | 출처·원고·조건·특징·정책·평가 항목의 **검수 전 예시** |
| [planning/saju_db_workbook.xlsx](planning/saju_db_workbook.xlsx) | 7개 시트의 DB 자료 작성/검수 작업표 |
| [docs/DATA_STATUS.md](docs/DATA_STATUS.md) | 수집/검증/상용 이용 상태와 해야 할 일 |

## 우선 권장 아키텍처

1. **달력**: KASI 공식 음양력·윤달 자료와 한국 음력 변환 라이브러리를 교차 검증
2. **절기**: Skyfield + JPL 천문력으로 생성, KASI 공식 절기 시각과 대조
3. **시간대**: 출생 당시 현지 시간대 및 DST는 IANA tzdb에 따라 계산
4. **사주 원국**: 입춘·절입·일주·시주 등 **명시한 규칙 버전**으로 결정론 계산
5. **해석**: 사람이 검수한 원고·적용 조건을 사용하며 LLM은 설명/캐릭터 표현에 한정

## 중요한 경계

- KASI 공식 **원본 TXT 전체**, 외부 천문력 바이너리, 대량 음양력 변환표는 **이 저장소에 포함하지 않았습니다.** 파일 확보/검증 기록은 있으나 재배포 허용범위·출처·정밀도를 추가 확인해야 합니다.
- 예제 JSON·엑셀은 실제 프로덕션 DB나 계산 API가 아닙니다.
- 검증 기록의 소수 표본 통과를 전체 기간 정확도나 연애/미래 예측력으로 해석하지 마세요.
- 외부 라이브러리·데이터의 저작권, 원본 라이선스·출처표시, 상용 API 계약은 각각 별도로 확인해야 합니다.
- 출생정보·대화·인증키·개인정보는 공개 저장소에 커밋하지 마세요.

## 시작 순서

[DATA_STATUS.md](docs/DATA_STATUS.md)에서 미확정 항목 확인 → [소스 비교 보고서](docs/research/saju_source_commercial_research_20261020.md) 검토 → [DB 구축안](docs/architecture/saju_db_blueprint.md)으로 구조 설계 → [작성 템플릿](planning/saju_db_workbook.xlsx)에서 정책/원고 검수 → [검증 JSON](data/verification/saju_source_verification_20261020.json) 기반 회귀시험을 추가하세요.

작성 기준일: **2026-10-20**. 공개 저장소에 실데이터를 추가하기 전에는 원본의 허락범위와 사용자 데이터 포함 여부를 다시 확인하세요.
