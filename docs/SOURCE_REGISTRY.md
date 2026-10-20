# 외부 원천·오픈소스 출처 대장 (검토 상태)

조사 기준: **2026-10-20**. 본 문서는 **링크·도입 조건을 기록**한 것이며 제3자 파일이나 소스를 저장소에 재배포하는 허가 문서가 아닙니다.

| 용도 | 제공자·도구 | 공식 주소 | 코드·원천 구분 / 확인 필요 사항 |
|---|---|---|---|
| 한국 양음력/윤달 | KASI 공공데이터 API | https://www.data.go.kr/data/15012679/openapi.do | 공개 이용허락 문구 확인, 실제 인증 응답·지원 범위 미검증 |
| 한국 24절기 | KASI 역서 24기 파일 | https://astro.kasi.re.kr/kor/almanac/pageView/26 | 과거 24기 파일 형식 분석 기록 있음; 원본 상용 적재·재배포 허용범위 별도 확인 |
| 24절기 조회 API | KASI 특일 정보 | https://www.data.go.kr/data/15012690/openapi.do | 실제 시각 필드·지원범위 미확정 |
| 한국식 음력 변환 | usingsky/korean_lunar_calendar_py | https://github.com/usingsky/korean_lunar_calendar_py | MIT 코드; 내장 테이블 출처·KASI 일치·지원기간 검수 |
| 절기 천문 계산 | Skyfield | https://rhodesmill.org/skyfield/almanac.html | MIT 코드; 천문력과 시간 데이터 별도 버전·조건 관리 |
| 천문력 | JPL DE440s | https://ssd.jpl.nasa.gov/planets/eph_export.html | 외부 바이너리 전체 재배포 전 공식 조건 확인 |
| 시간대 | IANA tzdb | https://www.iana.org/time-zones | 역사적 법정시·서머타임, 패키지 버전 추적 |
| 경량 천문 계산 | Astronomy Engine | https://github.com/cosinekitty/astronomy | MIT 코드, 표본 비교 결과 참조 |
| 중국 역법·팔자 규칙 참고 | 6tail/lunar-python | https://github.com/6tail/lunar-python | MIT 코드; 한국 음력·시각 처리와 차이 주의 |
| 중국 천문역 계산 참고 | sxtwl_cpp | https://github.com/yuangu/sxtwl_cpp | BSD-3-Clause, 타 엔진과 원천 계보 중복 주의 |
| 한국 만세력 후보 | manseryeok-js | https://github.com/urstory/manseryeok-js | 시험한 1.0.8 버전 경계 오류로 그대로 채택 보류 |
| 한국 사주 후보 | sajupy | https://github.com/0ssw1/sajupy | 내장 CSV 시각 기준·원출처 추가 확인 필요 |
| 점성술 고급 엔진 | Swiss Ephemeris | https://www.astro.com/swisseph/ | AGPL 또는 전문 라이선스·B2B 재공급 조건 주의 |
| 상용 원국/풀이 API | SAZU | https://www.sazu.app/manse-api | 고정 샘플 Sandbox와 실제 입력 구분, 경쟁 서비스 금지 조항 등 확인 |
| 상용 사주 API | 운세위키 | https://unsewiki.com/api-service | 유료 API 별도 B2B 권리·요금·시간대 확인 |
| 상용 사주 API | Ablecity | https://ablecity.kr/pricing | 공개 일정/승인형 Sandbox 이용 조건 확인 |
| 상용 운세 문구 API | UN7 | https://un7.kr/doc/ | 문구 공급과 정밀 원국 계산을 구별 |

## 활용 원칙

- **코드 라이선스와 데이터 라이선스는 별개**다. 라이브러리가 MIT라도 내장표·다운로드한 공식 파일의 권한을 자동으로 보장하지 않는다.
- 출처·버전·원문 해시·획득일·정밀도·적용 시간대·권한검수자를 기록한다.
- 타 업체 운세 문구를 무단으로 수집·재학습·재판매하지 않는다.
- 실제 사용자 출생정보를 외부 API에 보내려면 별도의 데이터 처리 조건을 확인한다.
- 원천 파일의 직접 다운로드는 합당한 허락과 이용 조건을 확인한 후 비공개 저장소/스토리지에서 진행한다.

더 자세한 비교: [사주 원천·API 조사보고서](research/saju_source_commercial_research_20261020.md).
