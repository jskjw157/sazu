# Horizons vs Skyfield 절기 20건의 계산 모델 진단 (2026-10-23)

**연구용. 운영 승인·수치 오류 확정·명리 결과 확정에 사용하지 않음.**

## 대상과 근거

KASI 장기 TXT와 Skyfield/JPL DE440s의 분 표시 불일치 중 현대 20건을 다룬다. 최초 314건 중 25건은 역사적 UTC 변환 수정으로 해소됐지만 289건은 승인 차단 상태다. 이번 연구는 1962~2024년 20건의 천문 계산 계층만 진단한다. 보관된 이전 3,144개 TT 사건 기록의 SHA-256은 5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f 이다. 고정된 20개 TT는 Skyfield에서 찾은 사건 시각이지 독립적인 정답이 아니다. KASI 원문이나 원래 반올림 구간은 변경하지 않는다.

## 두 종류의 비교

**기하학적 ICRF 벡터:** JPL Horizons VECTORS, 태양 COMMAND=10, 지구중심 CENTER=500@399, VEC_CORR=NONE, REF_PLANE=FRAME, REF_SYSTEM=ICRF, OUT_UNITS=AU-D, TIME_TYPE=TDB. Skyfield의 지구와 태양의 ICRF barycentric 위치 차이를 *동일한 TDB 순간*에 비교한다. Horizons의 사용 천문력이 DE440s와 다를 수 있어 응답 헤더·SHA를 기록한다.

**겉보기 절기 황경:** Horizons OBSERVER quantity 31은 IAU76/80 ecliptic-of-date. Skyfield almanac_east_asia.solar_terms는 IAU2000B 장동 모델에서 겉보기 날짜 황경을 구한다. **서로 동일한 황경 좌표계가 아니다.** 같은 TT의 중심·±120초를 조회해 Horizons 모델의 절기 기준 각도 통과 오프셋을 국소 보간으로 추정하지만, 이것은 모델·프레임 종속 진단치일 뿐 실제 TT 오차나 KASI/NAOJ 수치의 최종 정답이 아니다.

## 실험 명령

오프라인 단위시험: python -m pytest -q tests/test_horizons_term_probe.py

운영 경로가 아닌 연구 CI에서 SHA-256 검증된 JPL DE440s를 로컬에 준비하고, 다음 명령을 실행한다.

    python -m tools.horizons_term_probe --epochs data/verification/modern_20_tt_epochs_20261023.json --cases data/verification/modern_20_naoj_cases_20261023.json --kernel /verified/local/de440s.bsp --output /tmp/horizons-term-report.json

요청은 공식 HTTPS API(https://ssd.jpl.nasa.gov/api/horizons.api)에만 보내며, quoted TLIST JD·TLIST_TYPE=JD·명시적인 TT 또는 TDB를 사용한다. 요청 범위/메타데이터·두 응답 SHA·공식 헤더·20개 행을 JSON으로 보존하되 JPL kernel 자체를 재배포하지 않는다.

## 출시 기준 및 한계

입력 해시와 20개 키를 교차 확인하고, 행 누락/중복·응답 형식 변경·잘못된 시간척도·네트워크 실패에서는 수치 합격을 주장하지 않는다. 결과는 production_authorized=false 이고 기존 공식 수치 게이트의 실패를 바꾸지 않는다. 사용자 서비스 API나 상용 사주 API는 변경하거나 호출하지 않는다. 다음 단계로 *동일한* IAU76/80 프레임·nutation·광행차·중력편향·커널 버전에서 독립 TT 근을 구해야 초 수준 오류를 엄밀히 판단할 수 있다.

출처: https://ssd-api.jpl.nasa.gov/doc/horizons.html ; https://ssd.jpl.nasa.gov/horizons/manual.html ; https://github.com/skyfielders/python-skyfield/blob/master/skyfield/almanac_east_asia.py
