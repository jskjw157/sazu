# Issue #5 — 역사적 UTC 변환 결함 수정과 남은 불일치

기록일: 2026-10-22. **314건 전체 해결 보고가 아니다. 확인 가능한 시간 변환 결함을 수정한 결과다.**
상용 사주 API 사용, main 병합, 운영 배포, 데이터 출시 승인은 하지 않는다.

## 확인한 결함

기존 `generate_terms()`가 Skyfield의 `utc_datetime()`를 모든 연도에 그대로 적용했다.
시험한 Skyfield 1.55의 1972년 이전 UTC 출력은 첫 윤초 표의 TAI−UTC 10초를
외삽하므로 1961–1971년의 실제 UTC 주파수 드리프트·단계 조정을 재현하지 않는다.
IERS `UTC-TAI.history`는 이 기간을 13개 구간의 상수+일별 기울기로 명시한다.
예: 1961-01-01 00:00 UTC의 TAI−UTC는 1.422818초이지 10초가 아니다.

이 차이는 태양 위치 자체가 아니라 **같은 TT 사건을 민간 시각으로 변환하는 과정**의 결함이다.
태양 위치/절입 해법, KASI 표시값, 비교 셀 `[표시값−30초, 표시값+30초)`는 변경하지 않았다.

## 수정

- `sazu.term_clock`: PyERFA 2.0.1.5 / ERFA 2.0.1 / SOFA 20231011의
  TT→TAI→UTC 변환을 재사용한다. 새로운 보정 상수를 피팅하지 않는다.
- 입력 JD를 두 부분으로 유지하고 비유한 수·bool·과도한 정수 등을 거절한다.
- 실제 윤초 테이블 fingerprint를 검사한다. 리뷰하지 않은 테이블 또는 다른 구현 버전을
  같은 정책으로 승인하지 않으며 자동 윤초 업데이트를 하지 않는다.
- 지원한 역사적 UTC 구간 이전(1961년 이전)은 TT를 보존하지만 `instant_utc=null`,
  `historical_clock_unresolved`로 반환한다. UT1을 UTC로 재명명하지 않는다.
  이것은 해당 연도의 태양 위치 계산이 불가능하다는 뜻이 아니라 **민간 시각 연결 정책이 미해결**이라는 뜻이다.
- 고정 검토일 2026-10-22 이후의 출력은 `future_utc_assumption`으로 분리한다.
  검토일은 시스템 현재 날짜에 따라 바뀌지 않고 요청이 미래로 임의 확대할 수 없다.
  Bulletin C 72의 2026년 12월 말 무윤초 안내를 확인했지만, 이 변경은 보수적으로 검토일까지만 분류한다.
- `datetime`으로 표현할 수 없는 윤초는 23:59:59로 조용히 바꾸지 않는다.
- 기본 `python -m sazu generate-terms`는 새 변환 경로를 사용한다. 응답은 `clock` 객체에
  값·상태·정책 ID를 포함한다. 이전 `instant_utc`만 읽던 소비자는 변경된 계약을 따라야 한다.
- 기존 `solar_terms.generate_terms`와 공식 비교 명령은 **과거 수치 증거 재현 전용**으로 남긴다.
  비교 보고서에 `clock_projection=legacy_skyfield_utc_for_replay_only`를 표시한다.
  원래 314건 실패를 새 수정으로 가장하거나 이전 검증 기록을 덮어쓰지 않는다.
- Express/HTTP 경계·계정·DB 역할은 변경하지 않는다. 천문 관련 패키지는 선택적 astronomy
  의존성이며 HTTP 요청 경로에서 원격 자료를 자동 다운로드하지 않는다.

## 실행 근거와 한계

현재 GitHub runner에서 KASI 원문 재취득은 `curl: (52) Empty reply from server`로 실패했다.
HTTP/1.1·IPv4·제한된 재시도를 포함해 확인했고, 외부 사이트 실패를 수치 불일치로 집계하지 않았다.

대신 이전 공식 대조 보고서(파일 SHA 아래)를 사용했다. 실제 JPL을 다시 내려받아
고정 SHA를 확인하고 **3,144개 원래 계산 사건의 digest가 이전 보고서와 완전히 같은지** 검사했다.
일치한 행은 해당 계산값의 유일한 분 반올림 셀, 불일치 행은 보관된 delta로 이전 비교를 재생했다.
따라서 아래 결과는 **새 KASI 원문 전수 대조가 아니라, 동일 모델의 확인된 이전 증거 재생**이다.

| 구간 | 이전 불일치 | 이번 처리 |
|---|---:|---|
| 1920–1960 | 262 | 역사적 민간 시각 정의 미해결. 해결 수로 세지 않는다 |
| 1961–1971 | 21 | ERFA 변환으로 20건 해소, 1건 유지 |
| 1972–2025 | 19 | 남은 수치/반올림 경계 차이. 허용오차 유지 |
| 2026–2050 | 12 | 미래 모델 및 남은 수치 차이. 확정 UTC로 승격하지 않는다 |
| 총계 | 314 | **20건 해소, 294건 미해결/차단 유지** |

1961–1971년 전체 264개는 **243/264 → 263/264**로 개선됐다. 새 불일치는 0이다.
남은 1962년 경칩의 표시 분값 대비 차이는 약 −30.345446초로, 여전히 기존 셀 밖이다.
이 값을 임의 반올림하거나 셀을 확대해 통과시키지 않았다.

새 분류 전체: 3,144행 중 UTC 비교 가능 1,579행(1,559 일치/20 불일치),
역사적 시계 미해결 984행, 검토일 이후 조건부 미래 출력 581행.
**보류한 행을 제외한 일치율을 전체 정확도로 광고하면 안 된다.** 원래314건 중 보류274건도
미해결294건에 포함한다. `status=blocked`, `production_authorized=false`, 보고서 종료코드1을 유지한다.

## 회귀 검증

IERS의 독립 구간 상수·기울기로 만든 UTC/TT fixture, 실제 윤초, 미상 역사적 시계,
미래 검토일, 변조된 테이블, CLI 경로, 비교 보고서의 미해결 집계를 시험한다.
누락된 모듈/기존 CLI 경로/잘못된 테이블 허용/미검토 horizon 허용 등의 실패를 먼저 실행한 뒤 수정했다.
천문력 없이 실행한 전체 로컬 결과와 실제 kernel 통합 결과는 PR의 실행 기록을 구분해서 확인한다.
새 독립 코드 리뷰는 수행하지 않았으며 자체 코드 검토와 실제 테스트 증거만 사용했다.

```bash
python -m pip install -r requirements-dev.lock
python -m pytest -q
python -m ruff check src tests tools
# 로컬에 검토된 kernel을 준비했을 때만:
SAZU_KERNEL=/operator/path/de440s.bsp python -m pytest -q tests/integration/test_skyfield_local.py
# 이전 진단 artifact를 갖고 있을 때만. 실패 코드1은 미해결 분류를 유지한다는 의미:
PYTHONPATH=src python -m tools.audit_clock_repair --probe /operator/path/clock-probe.json
```

## 출처 및 재현 ID

- [IERS 역사적 UTC](https://hpiers.obspm.fr/iers/bul/bulc/UTC-TAI.history)
- [IERS Bulletin C 72](https://datacenter.iers.org/data/html/bulletinc-072.html)
- [ERFA taiutc 구현](https://github.com/liberfa/erfa/blob/v2.0.1/src/taiutc.c)
- [ERFA dat 구현](https://github.com/liberfa/erfa/blob/v2.0.1/src/dat.c)
- [PyERFA 2.0.1.5](https://pypi.org/project/pyerfa/2.0.1.5/)
- [Skyfield 시간척도](https://rhodesmill.org/skyfield/time.html)
- [진단 재생 CI](https://github.com/jskjw157/sazu/actions/runs/39654192006)
- [이전 공식 비교 CI](https://github.com/jskjw157/sazu/actions/runs/39562263067)

이전 보고서 SHA256: `1d775590cab5d641429f12188043ebbfe8579b680a557eb727c2a22e119a8b82`.
후보 사건 digest: `c136a26bac55f6fec41ed377ba433e446abcf574f85f8265f17dbfc344902546`.
재생 probe SHA256: `5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f`.
동일 모델·동일 파일이 아니면 재생 도구는 거절한다. 전체 KASI TXT/JPL BSP는 이 PR에 포함하지 않는다.

원천별 권리 검토, 독립 전기간 검증, 남은 차이의 설명, 운영 승인, 사주 원국 구현은 별도 미완료다.
[이슈 #5](https://github.com/jskjw157/sazu/issues/5)는 닫지 않는다.
