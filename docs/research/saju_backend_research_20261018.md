# fortune-ai-companion: 사주 계산·DB 백엔드 설계 조사
조사 기준: 2026-10-18. 10월 25일 마감은 2026-10-25로 가정한다. 아래는 공개 원천 검토와 구현 설계안이며, 실제 앱 저장소 조사·API 인증 호출·전 날짜 대조 테스트를 수행한 결과가 아니다.

## 1. 추천 결론

사주 전체 결과 DB를 구매하거나 LLM이 생년월일로 팔자를 계산하게 하기보다, **한국 역법 원천 + 정책이 명시된 결정론 계산기 + 자체 저작 해석 지식 + 대화 계층**을 분리한다.

- 원천층: KASI 한국 양음력·윤달·일진 자료, 절기 시각, IANA 시간대 이력.
- 계산층: 입력 정규화 → 연·월·일·시주 → 오행·십성 등의 명시적 규칙. 같은 입력·정책·데이터 버전이면 같은 JSON.
- 해석층: 검수한 짧은 해석 문서에서 해당 규칙 근거만 검색. LLM은 계산값을 바꾸지 않고 한국어로 설명.
- 관계층: 사용자가 말한 선호·경계·대화 맥락과 캐릭터 설정. 사주에서 추정한 성격을 사용자 사실로 영구 저장하지 않는다.
- MVP: 사주 4주/시간미상 처리, 오행 단순분포, 십성, 짧은 연애 대화 소재까지. 용신·격국·신강약·대운·궁합 종합점수는 규칙 검수 후 후속으로 미룬다.

‘정확도’는 역법/정책에 맞는 재현성과 해석 근거 일치로 측정한다. 실제 연애·미래 예측 능력이나 과학적 타당성을 의미하지 않는다.

## 2. 원천 DB: 무엇을 어디서 받나

### 2.1 한국천문연구원 음양력 정보

[공공데이터포털 원문](https://www.data.go.kr/data/15012679/openapi.do)은 양력→음력, 음력→양력, 특정 음력일, 율리우스적일 등을 제공한다. 공개 명세에는 음력 년월일·윤달·월일수·세차·월간지·일진 등이 있다. REST/XML, 무료, 이용허락범위 제한 없음, 개발계정 신청 가능 트래픽 10,000, 개발/운영 자동승인으로 표시된다. 실제 운영 할당량과 호출 주기는 발급 계정에서 확인한다.

중요: 이것은 천문·역법 데이터이지 사주 해석 DB가 아니다. 공개 필드 ‘간지(월)’를 바로 절입 기준 사주 월주로 간주하지 않는다. 연주 또한 음력 설 기준 세차와 입춘 시각 기준을 구분한다.

구현 제안:
- 요청마다 사용자의 출생정보를 외부 API에 보내지 않고, 승인된 사용범위에서 공통 달력 테이블을 사전 수집·검증·캐시한다.
- 날짜별 `solar_date, lunar_year, lunar_month, lunar_day, leap_month, lunar_month_days, day_ganji, julian_day, source_id` 저장.
- 제공기간은 화면에서 확정되지 않았으므로 목표 1900~2050 전 범위 수집 가능 여부를 먼저 확인. 부족한 기간은 미지원 또는 검증된 대체 데이터로 명시한다.
- HTTP 200이어도 XML 결과코드/건수/필수필드 검사. 요청키와 인증정보는 서버 비밀 저장소에서 관리한다.

### 2.2 절기: ‘날짜’보다 ‘입절 시각’이 중요

[특일 정보 공식 목록](https://www.data.go.kr/data/15012690/openapi.do)은 24절기를 포함하며 무료/이용허락범위 제한 없음으로 표시한다. 이번에 열린 기본 상세는 기념일 오퍼레이션이었다. 따라서 **24절기 오퍼레이션의 실제 응답 필드·KST 시각·과거 제공범위를 공식 가이드와 승인 API로 확인하는 일을 첫 구현 게이트로 남긴다.** 날짜만 받은 상태를 시각까지 검증한 것으로 처리하면 안 된다.

[KASI 월력요항 안내](https://astro.kasi.re.kr/life/post/almanac?year=2026)는 공식 발표 자료이며 2020년 이후 관보 링크를 제공한다고 설명한다. 이 조회에서는 2026 개별 본문 접근이 완전히 성립하지 않아 해당 연도 관보를 읽었다고 주장하지 않는다. [KASI 과거 월력요항](https://astro.kasi.re.kr/life/pageView/1)에는 절기 태양황경과 한국표준시 날짜·시각이 제공된다.

[KASI 2026 달력자료](https://astro.kasi.re.kr/kor/life/post/calendarData?search_year=2026)는 입춘을 2월 4일 05:02로 표시하지만 **페이지 스스로 공식 발표 자료가 아니라고 경고**한다. 이는 검증 후보 fixture이며 공식 확정값으로 인증한 사례가 아니다. 공식 월력요항/역서와 교차 확인 후 승격한다.

절기 캐시 제안:
- 연 24개 사건. 1900~2050 inclusive는 3,624개. 앞뒤 해 포함 확보.
- `term_code, solar_longitude_deg, instant_utc, original_local_time, original_zone, precision_seconds, rounding_policy, source_id, source_revision, status`.
- 분 단위 원천이면 초를 `00`으로 채웠다고 초 단위 정확도가 생기지 않는다. 절입 근처 출생은 원천의 표시 정밀도와 출생시간 정밀도를 함께 고려해 후보 결과/불확실성을 표시한다.
- 기존 확정 원천이 변경되면 덮어쓰기보다 새 revision 생성 → 영향받은 결과 재계산 후보 표시.

### 2.3 라이선스 관리

API 이용허락범위, 라이브러리 코드 라이선스, 내장 천문표의 출처, 번역/해석 문장 저작권을 각각 구분한다. 한 항목이 MIT라고 모든 외부 데이터·콘텐츠까지 MIT인 것은 아니다.

`source_registry`에 URL, 제공자, 자료 종류, 취득일, 라이선스 URL/스냅샷 해시, 상업이용·재배포·변경 가능 여부, attribution 문구, 담당 검토자, 검토상태를 둔다. 다른 운세앱 풀이를 수집·재가공해 자체 RAG로 넣지 않는다. 고전 원문과 현대 번역문도 별개로 확인한다. 이 문서는 법률 검토를 대신하지 않는다.

## 3. 공개 라이브러리: 실제 코드에서 확인한 차이

### A. usingsky/korean_lunar_calendar_py: 한국 양음력 변환 어댑터 후보

- [README](https://github.com/usingsky/korean_lunar_calendar_py/blob/master/README.md?plain=1): 한국식 음양력 변환, 윤달, 오프라인 테이블. 양력 1000-02-13~2050-12-31, 음력 1000-01-01~2050-11-18을 명시.
- [실제 소스](https://github.com/usingsky/korean_lunar_calendar_py/blob/master/korean_lunar_calendar/korean_lunar_calendar.py)의 `__getGapJa`는 `lunarYear/lunarMonth`로 년·월 간지 인덱스를 만든다. **이 간지 문자열을 사주 연·월주로 복사하면 안 된다.** 입춘/절입/출생 시각 계산 엔진을 대체하지 못한다.
- setter 성공 여부를 확인하지 않으면 이전 성공 상태를 읽을 수 있어 변환 객체를 요청 간 공유하지 않는 것이 안전하다.
- [MIT LICENSE](https://github.com/usingsky/korean_lunar_calendar_py/blob/master/LICENSE). 배포 시 저작권·허가 고지 보존.
- [PyPI](https://pypi.org/project/korean-lunar-calendar/)와 [commit 이력](https://github.com/usingsky/korean_lunar_calendar_py/commits/master/): 0.4.0, 2026-06-15 릴리스 확인. 업데이트가 있다는 사실이지 SLA나 무오류 보증은 아니다.
- 범위 전체 KASI 일치율은 이번 조사에서 측정하지 않았다. README의 기관 영문 약어 표기는 KARI지만 연결 대상은 KASI이며 국가기관의 공식 인증 제품으로 해석하지 않는다.

### B. 6tail/lunar-python: 규칙 참고·독립 비교 후보

- [저장소](https://github.com/6tail/lunar-python)와 [LICENSE](https://github.com/6tail/lunar-python/blob/master/LICENSE): MIT, 중국 음력/절기/팔자/십성/대운 등 폭넓은 기능.
- [EightChar 실제 코드](https://github.com/6tail/lunar-python/blob/master/lunar_python/EightChar.py): 연·월은 Exact 메서드를 사용하고, `sect=2`가 기본이며 일주 선택에 따라 두 메서드를 구분한다.
- [공식 작성자 문서](https://6tail.cn/calendar/lunar.bazi.html): sect 1은 23시대 일주를 다음날, sect 2는 당일로 처리한다. **둘 다 23시대 시주는 다음날 일간 기준**으로 설명한다. 따라서 ‘sect 2 = 모든 계산을 단순 자정 기준’이라고 구현하면 다르다.
- [Yun 소스](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/Yun.py): 순역 및 기운 계산에도 성별 인자와 별도 sect가 있다. 사주 일경계 sect와 대운 sect를 한 설정값으로 섞지 않는다.
- [테스트 소스](https://github.com/6tail/lunar-python/blob/master/test/EightCharTest.py): 1988-02-15 23:30, 간지/대운/역산 사례 등이 있으나 한국 시간대 역사·KASI 전 날짜 일치를 보증하는 테스트가 아니다.
- [PyPI](https://pypi.org/project/lunar-python/) 1.4.8, 2025-11-05; [변경 이력](https://github.com/6tail/lunar-python/blob/master/CHANGELOG.md)에 절기·윤달/간지·대운 관련 수정 기록 존재. 릴리스 버전/의존성 해시를 고정하고 업그레이드 때 golden diff를 검토한다.

추천: 중국 음력 입력을 한국 음력 입력의 대체물로 직접 쓰지 않는다. 한국 음력→양력은 한국 원천에서 해결한다. 6tail은 시간대/절기/일경계 의미를 어댑터에서 검증한 범위에 한해 참고한다. 출생시각을 무조건 한 시간 빼서 넣는 방식은 월경계와 일·시주가 서로 다른 기준을 쓰게 만들 수 있어 금지한다.

## 4. 반드시 정해야 하는 계산 정책

아래는 천문학의 유일한 정답이 아니라 제품이 선택하고 공개해야 할 사주 계산 관례다. `policy_version`에 묶고 변경 시 사용자 결과를 조용히 덮어쓰지 않는다.

| 항목 | MVP 제안 | 예외 처리 |
|---|---|---|
| 달력 | solar / korean_lunar 명시 | 음력은 윤달 여부 필수. 모름이면 후보 또는 재질문 |
| 시간대 | 출생 당시 도시의 IANA zone | 현재 위치/현재 UTC+9로 대체하지 않음 |
| 연주 | 입춘 순간 이전/이후 | 입춘 날짜 00시로 일괄 전환 금지 |
| 월주 | 12개 절입 순간 기준 | 24절기 모두에서 월을 바꾸거나 음력 1일에 바꾸지 않음 |
| 일주 | MVP는 일경계 정책 1종을 명시 선택 | 23시경계/야자시 분리 결과를 검증 후 옵션화 |
| 시주 | 2시간 지지 구간 + 선택된 시주 일간 규칙 | 23시~01시 자시의 날짜 연계 명시 |
| 태양시 | 기본은 출생지 법정시에서 DST를 제거한 표준시 기준 제안 | 경도보정/진태양시는 별도 정책으로 출시 전 결정 |
| 시간 미상 | time_precision=unknown | 정오를 진짜 출생시간처럼 채우지 않음 |
| 오래된 날짜 | 지원범위와 역법을 문서화 | 그레고리/율리우스 전환은 별도 범위로 제한 |
| 대운 | MVP 제외 추천 | 순역 성별 관례·기운환산·세는나이 별도 합의 |

### 입력 정규화 절차

1. 사용자가 입력한 날짜·달력·윤달·출생 현지 벽시계 시간·정밀도를 원본 그대로 보존.
2. 음력이면 한국 달력에서 양력 날짜를 구한다. 해외 출생 음력의 기준 국가가 모호하면 묻는다.
3. 출생 도시 → IANA zone. 역사적 offset/DST를 적용하여 실제 UTC instant를 만든다.
4. DST 종료의 중복 시각은 fold 또는 두 후보, 시작의 존재하지 않는 시각은 오류/재입력. 라이브러리가 임의로 보정하게 두지 않는다.
5. UTC instant는 절기 사건 UTC와 비교한다. 일·시주용 wall-clock은 별도 정책으로 도출한다. 표준시 사용 정책이라면 DST 제거 후 계산하며 실제 UTC instant를 다시 왜곡하지 않는다.
6. 태양시 선택 시 경도보정과 균시차 적용값을 trace에 보존한다. 연·월 절기 비교는 물리적 instant끼리 유지한다.
7. 정책에 따라 간지·파생 규칙 생성, 모든 사용 경계/원천 ID 기록.

[IANA 공식 설명](https://www.iana.org/time-zones)은 역사적 UTC offset/DST를 다루는 데이터베이스임을 명시한다. [Asia 원천](https://data.iana.org/time-zones/tzdb/asia)에는 Asia/Seoul의 1954~1961 UTC+08:30과 1987~1988 서머타임 규칙 등이 있어 모든 한국 출생을 UTC+9로 처리하는 것은 틀린다. tzdb 버전을 결과에 저장한다.

태양시의 경우 ‘한국은 30분 빼기’를 진태양시와 동일시하지 않는다. [NOAA 식](https://gml.noaa.gov/grad/solcalc/solareqns.PDF)은 경도와 UTC offset 외에 equation of time을 사용한다. 대략적 구조는 현지시각 분 + 균시차 + 4×동경도 − 60×UTC오프셋시간이다. 단위·경도 부호·날짜 넘김·DST 중복 제거를 테스트한다. [NOAA 계산기](https://gml.noaa.gov/grad/solcalc/)는 현재 유지보수 중단 안내가 있으므로 그대로 production 의존 API로 채택하지 않는다. 정밀 천문엔진은 별도 후보/라이선스 검토 후 도입한다.

### 시간 미상은 시주 하나만 없애면 끝나지 않는다

하루 전체 시간 구간을 가능한 출생 구간으로 두고 연·월 절입 및 선택한 일경계가 구간 안에 있는지 본다. 평범한 날은 연·월·일이 고정되고 시주만 없을 수 있지만, 입춘/절입일 또는 23시 일경계 정책에서는 연·월·일까지 복수 후보가 생긴다. 공통으로 확정되는 특징만 해석하고 가중확률은 근거 없이 부여하지 않는다.

## 5. 계산 엔진의 구체 구성

서버 코드 내부 모듈 제안:
- calendar_adapter: 한국 양음력, 윤달 검증, 날짜별 일진 참조.
- birth_time_normalizer: tzdb, fold/gap, 정밀도, 후보 구간.
- solar_term_repository: 확정/후보 절기 시각 캐시.
- pillar_engine: 정책별 년월일시주 순수함수.
- feature_engine: 오행·음양·십성·지장간/합충 등 승인한 규칙만.
- explanation_trace: 어떤 경계·인덱스·관계표로 계산했는지 구조화.
- interpretation_service: 검수 콘텐츠 필터링/검색/LLM 렌더링.

기초 산식 설계:
- 천간은 0~9, 지지는 0~11, 육십갑자는 0~59로 저장. 한글/한자는 표시 테이블에서 매핑.
- 연주: 입춘 경계로 선택한 간지년을 기준으로 갑자 앵커(예: 1984)를 통한 modulo 60. 앵커와 입춘 이전 처리 fixture 검증.
- 월주: 인월부터의 절기 순번 0~11 + 오호둔 규칙 테이블. 같은 해 1월 소한 이후 축월은 전 간지년 연간을 사용해야 함.
- 일주: 검증한 기준 날짜의 육십갑자 인덱스 + civil-day 차이를 modulo 60. UTC 날짜나 Unix timestamp의 일수 나눗셈을 그대로 쓰지 않는다. 기준 날짜는 KASI 일진 검증 후 고정.
- 시지: 정책시각의 자시 구간부터 2시간 인덱스. 시간 천간은 오서둔 표/식, 23시대에 사용할 일간을 명시.
- 십성: 일간과 대상 천간의 오행 생극 관계 및 음양 같음/다름 매핑. 지지는 승인된 지장간 목록 각각에 대해 계산.
- 단순 오행개수와 지장간 가중 오행비중은 다른 지표. `visible_element_counts`와 `weighted_element_balance`를 분리하고 후자는 가중표 근거가 정해질 때만 출시.

‘수(水)가 0개니까 무조건 이별한다’ 같은 결정적 판정은 계산 계층에도 해석 계층에도 넣지 않는다. 합충이 있으면 관계 feature를 기록할 뿐 실제 사건 확률로 바꾸지 않는다.

## 6. PostgreSQL 중심 DB 설계안

처음부터 별도 벡터 DB나 대규모 운세 문장 조합표가 필요하지 않다. 작은 규칙 콘텐츠는 관계형 조건 검색으로 시작하고 필요할 때 pgvector를 추가한다.

| 테이블 | 핵심 필드 | 비고 |
|---|---|---|
| source_registry | id, provider, url, license, revision, checksum, verified_at | 공공 원천·코드·콘텐츠 출처 분리 |
| calendar_day | date PK, lunar Y/M/D, is_leap, day_cycle_index, source_revision | immutable snapshot별 unique |
| solar_term | year, term_code, instant_utc, precision, source_revision | (year,term,revision) unique |
| rule_set | id, semantic_version, policy_json, code_sha, content_hash, approved_at | immutable |
| birth_profile | id, owner_id, encrypted_input, calendar, time_precision, revision | 민감도 높은 원본 접근 제한 |
| normalized_birth | profile_revision, tzid, tzdb_version, UTC candidates, normalization_trace | 프로필 수정 시 새 revision |
| natal_chart | id, profile_revision, rule_set, data_revision, canonical_hash, result_json, ambiguity | 재현 가능한 계산 snapshot |
| chart_feature | chart_id, rule_id, feature_code, value, evidence_json | 해석 검색 키 |
| knowledge_entry | id, rule_tags, original_text, source/license, reviewer, locale, version | 독자 작성/권리 확보 콘텐츠 |
| interpretation | chart_id, knowledge_version, model, prompt_version, output_json, cited_entry_ids | 생성 결과/비용/품질 추적 |
| character_profile | id, persona_version, tone, fictional_background, boundaries | 모든 이용자에게 적용되는 허구 설정 |
| relationship_memory | owner_id, character_id, fact, evidence_message_id, consent/state, expiry | 사용자 실제 발화 사실만 구분 저장 |
| evaluation_case | input, expected, reference, reviewer, status | golden 데이터 |

출생일·시각은 조합 수가 작아 일반 SHA 해시만으로 익명화되지 않는다. 캐시에는 HMAC 등 서버 비밀 기반 식별자 또는 비식별 chart ID를 사용한다. 공용 캐시에는 원본 개인정보를 넣지 않는다. 사용자별 권한 격리, 원본 암호화, 로그 마스킹, 보존기간, 탈퇴 시 원본·파생·임베딩 제거 경로를 설계한다. RAG에는 생년월일 자체보다 필요한 계산 features만 전달하도록 최소화한다. 외부 모델 제공자에게 무엇이 전송되는지는 별도 고지/정책 검토 대상이다.

## 7. API 계약 예시

`POST /v1/birth-profiles/validate`
- 입력: calendar, date, is_leap_month, local_time 또는 null, time_precision, birthplace city ID, tzid 후보.
- 출력: normalized candidates, missing_fields, warnings. 저장하지 않는 미리보기 가능.

`POST /v1/natal-charts`
- 입력: birth_profile_id + revision, policy_version.
- 출력: chart_id, pillars, features, ambiguity, calculation_trace, version_manifest.
- 정책 모르면 서버 현재 기본값을 쓰되 응답에 정확한 version 기록. 과거 요청 재현은 immutable version 지정.

`GET /v1/natal-charts/{id}` / `GET /v1/natal-charts/{id}/explanation`
- 소유권 검사. 계산값/근거와 해석 텍스트를 별도 반환.

`POST /v1/interpretations`
- 입력: chart_id, topic=relationship, character_id 선택.
- 출력: grounded_claims[{text,evidence_feature_ids,knowledge_entry_ids}], uncertainty_notice, conversation_starter.
- LLM 장애 시 검수 template fallback. 계산 성공/해석 실패 상태를 분리.

`POST /v1/conversations/{id}/messages`
- 확정 chart features + 선택한 캐릭터 + 허용된 관계기억만 읽음.
- 사용자의 새로운 발화로 생년월일을 추측 변경하거나 chart 결과를 수정하지 않음.

응답 오류 제안: INVALID_LUNAR_DATE, LEAP_MONTH_REQUIRED, UNSUPPORTED_DATE_RANGE, NONEXISTENT_LOCAL_TIME, AMBIGUOUS_LOCAL_TIME, TERM_DATA_UNAVAILABLE, UNSUPPORTED_POLICY. 시간미상은 정상적인 부분 결과이며 서버 오류가 아니다.

## 8. 해석/RAG/연애 파트너 결합

처음 50~100개의 검수 항목을 목표로 하되 완전한 전통명리 지식 DB라고 부르지 않는다.

각 항목 구조: `condition / scope / interpretation / non_deterministic_wording / helpful_question / forbidden_claim / source / reviewer / version`.

예: 조건이 표현 관련 십성 feature라면 ‘표현을 통한 관계 맺기라는 관점으로 읽을 수 있어요. 실제로는 말로 표현하는 편인가요?’ 같은 탐색적 문장. 사용자 답이 다르면 발화를 우선하며 출생정보로 반박하지 않는다.

검색 순서:
1. 확정 feature만 필터링.
2. 주제·언어·지원 정책/규칙 버전으로 좁힘.
3. 관련 문서를 제한적으로 검색.
4. 생성 결과가 참조한 feature가 실제 chart에 있는지 기계 검증.
5. 생년월일·천간지지·숫자를 LLM이 새로 계산했거나 없는 시주를 단정하면 실패.
6. 실패 시 재시도 1회 또는 검수 template.

사주/별자리/타로는 별도 `divination_context`로 구분한다. 타로 추출은 서버 난수·덱 버전·추출 시각·재추첨 정책으로 재현 가능한 이벤트를 남기고, 사주에서 타로 결과를 결정하지 않는다. 별자리를 생일 구간 기반 태양궁만 지원하면 그렇게 표시하고 정밀 출생차트와 혼동시키지 않는다.

캐릭터는 사주를 대화 소재로 사용할 수 있지만 ‘사주가 나와만 만나라고 한다’, 이별·질병·사망 확정, 고립 유도, 질투/위기 조장형 결제 압박을 금지한다. 안전 정책은 사주 규칙보다 상위 계층에 둔다.

## 9. 검증 계획과 출시 게이트

### 9.1 Golden corpus

| 테스트 | 최소 범위 제안 | 기대 결과 원천 |
|---|---|---|
| 양음력 왕복 | 지원기간 모든 날짜 + 윤달 전체 | KASI 검증 데이터/고정 fixture |
| 잘못된 입력 | 없는 윤달, 2/30, 범위 초과 | 검증 스키마 |
| 입춘/12절입 | 각 경계 앞·정각·뒤 및 ±1분/원천정밀도 | 공식 절기 시각+정책 |
| 자시/시주 | 22:59,23:00,23:59,00:00,00:59,01:00 | 전문가 승인 정책별 기대값 |
| 역사적 한국시간 | 1954/1961 offset 전환,1987/1988 DST | 고정 IANA 버전 |
| 해외시간 | DST gap/fold, 날짜변경선, 반시간/45분 zone | IANA+정규화 fixture |
| 시간미상 | 평일·입춘일·절입일 | 구간내 가능한 후보의 집합 |
| 태양시 | 경도·균시차·날짜넘김·DST 중복 방지 | 독립 계산 비교 |
| 해석 grounding | 존재하지 않는 feature 금지, 시주미상 단정 금지 | JSON 검증+사람 평가 |
| 보안/삭제 | 다른 계정 chart 접근 거부, 삭제 전파 | 통합 테스트 |

제안 수치: 1900~2050 일별 자료는 약 5.5만 행이라 로컬 전수 왕복 테스트가 부담스럽지 않다. 역법 일치와 시간경계 케이스는 전부 통과해야 출시한다. 최초 golden 200~500개는 중요 경계와 정책 비교 위주로 만들고, 독립 전문가가 승인한 기대값과 자동생성 property test를 구분한다.

두 라이브러리가 같은 결과를 준다고 정답이 보증되지 않는다. 같은 원천/알고리즘을 복제했을 수 있다. 오류를 ①원천 차이 ②정책 차이 ③시간대 ④구현 버그로 분류하고, 앱 간 일치율을 과학적 정확도로 홍보하지 않는다.

### 9.2 운영 품질 지표

- deterministic mismatch=0, undefined-policy result=0, leakage=0.
- supported date coverage, boundary ambiguity rate, API 원천 누락/수집 실패율.
- 계산 API p95 목표(예: 캐시 후 100ms 이내)는 성능시험으로 확인할 내부 목표이지 보장값이 아님.
- LLM grounding 위반율, 정책 위반율, 해석 사용자 수정률, 생성당 토큰·비용.
- 데이터/코드 업그레이드는 shadow 계산 → 이전 버전 차이표 → 승인 후 활성화. 변경 이유 노출.

## 10. 10월 25일까지의 실행안

전제: 백엔드 개발자 1명, 기존 인증/배포/DB 기본틀 존재, 한국어/한국 출생 우선, 명리 검수자 짧은 검토 가능. 새 앱 전체 구축 일정이 아니다.

- 10/18: 정책 결정 기록, 지원범위, API 권한/라이선스 확인, 실제 stack 점검. 결과: rule-set v0.1 설계.
- 10/19: 달력/절기 샘플 ingestion, 원천 revision, 윤달 validation. 결과: 출처 포함 fixture 30개.
- 10/20: 시간대 정규화, 년월일시주 순수함수, 시간미상. 결과: 계산 API draft.
- 10/21: 경계/DST 테스트, 라이브러리 대조, 정책 차이 수정. 결과: golden 200개 이상+실패 원인표.
- 10/22: 오행/십성의 승인 범위, trace, DB/API 통합. 결과: 재현 가능한 chart snapshot.
- 10/23: 자체 작성 해석 50개 내외, template 우선/LLM 선택, 근거 검증. 결과: 연애 소재 응답 데모.
- 10/24: 삭제/권한/PII 로그·장애 fallback 테스트, 검수. 결과: 릴리스 후보와 알려진 한계.
- 10/25: 정책명세·ERD·OpenAPI·출처대장·테스트 리포트·데모로 마감. 원천 검증 미완료면 검증 가능한 날짜 범위의 데모로 제한하고 production-ready라고 하지 않는다.

시간이 모자라면: 대운/신살/궁합점수/진태양시/글로벌 출생의 정식 지원/벡터검색을 제외한다. 다만 ‘지원하지 않음’을 명시하고 UTC+9로 조용히 계산하지 않는다. 기획/DB연동 마감과 상용 출시 마감을 분리하는 것이 현실적이다.

## 11. 비용 추정: 견적이 아닌 가정 기반 예산 모델

공식 API와 MIT 코드 자체 사용료는 위 출처 기준 무료지만 검수·개발·호스팅·LLM 비용은 별개다. 현재 모델 가격을 확인하지 않은 상태에서 특정 공급자 실제 요금을 견적으로 제시하지 않는다.

예시 계획 가정:
- 계산/DB 개발 5~8인일 + 검수/QA 2~4인일. 일단가를 내부 예산상 30만~60만원으로 가정하면 210만~720만원. 시장단가 조사 결과가 아니라 범위 산정을 위한 가정.
- 작은 베타 인프라 월 3만~15만원 예산 가정. 기존 인프라와 무료티어 여부에 따라 다름. 공급자 견적은 별도 확인.
- 생성 비용 공식: 월 건수 × (평균 입력토큰 × 입력단가/백만 + 출력토큰 × 출력단가/백만), 재시도/캐시/임베딩/모더레이션 별도.
- 예시 가상단가 입력 $1/백만, 출력 $5/백만, 건당 1,500입력+500출력이면 $0.004/건, 1만건 $40, 10만건 $400. 실제 모델 가격이 아니다.
- 실제 연애챗은 ‘생애 1회 사주풀이’보다 호출 수가 훨씬 많을 수 있다. 사주 설명은 chart/rule/content version별 캐시하고 대화는 맥락 길이·요약 정책·턴수별 예산을 따로 잡는다.

## 12. 지금 팀에서 결정할 사항

1. 출시 범위: 국내 성인/한국 출생 우선인가, 해외·역사적 출생까지 포함인가?
2. 기준: DST 제거 표준시/법정시/경도보정/진태양시 중 무엇을 기본으로 할 것인가?
3. 일경계와 23시대 시주 기준은 무엇인가? 검수 담당자는 누구인가?
4. 음력 윤달 모름/출생시간 모름/도시 모름의 UI와 부분 결과는 허용하는가?
5. 10월25일 완료 정의는 설계+DB연동 데모인가, 실제 상용 API인가?
6. stack/DB/배포 환경은 기존 무엇인가? 설계의 Python 후보는 추천이며 기존 TS 서버라면 어댑터나 검증된 포트로 바꿀 수 있다.
7. 어떤 자체 저작 해석을 누가 승인하며, 참고문헌/권리 근거를 남길 것인가?
8. 사용자 원본 출생정보 보존기간, 외부 모델 전달 범위, 삭제·수정 경로는 무엇인가?

## 조사 한계

공개 웹 문서와 코드 경로를 검토했지만 API 인증키를 발급하거나 호출하지 않았다. 저장소 checkout/테스트 실행·전수 정확도 측정·공식 관보 전체 수집·법률 검토를 하지 않았다. 라이브러리 지원범위/릴리스는 작성자/패키지 원천의 선언이며 독립 인증이 아니다. 제품 관례는 위 정책 선택과 검수로 확정해야 한다.