# 공식 대조 연결·1960년·Bulletin C72 정책 수정

작성일 2026-10-22. 기준 PR #7 `aac6e77a0ea88827d0dfcbfbb06a9f5a2ca2d5a8`.
범위: 기존 미반영 대조 패치와 조사에서 근거가 확보된 시간 정책 두 가지.
상용 사주 API 미사용. 원천·천문 TT 계산·분 반올림 셀·운영 승인 기준 변경 없음.

## 실제 변경

1. `source_audit compare`와 공식 대조 도구가 현재 `term_clock` 정책을 사용한다.
   `compare-legacy` 및 보고서의 `legacy_comparison`으로 기존 증거를 보존한다.
2. ERFA/SOFA convention의 시작을 1960-01-01로 확장한다. MJD 36934에서
   `1.417818+(36934-37300)*0.001296=0.943482`초를 적용한다.
   1959년 이전은 여전히 미확정이며 UT1을 UTC로 이름만 바꾸지 않는다.
3. `reviewed_at=2026-10-22`와 `utc_offset_confirmed_through=2026-12-31`을 분리한다.
   IERS Bulletin C72(2026-07-06)의 12월 말 윤초 없음 발표를 근거로 한다.
   2027년 이후는 보수적으로 조건부 상태를 유지한다. 머신 날짜나 환경변수로
   승인 범위를 늘리지 않는다. 기존 `reviewed_through` 인자는 명시적 범위 축소만 허용한다.
4. 모델 ID에 새 정책 `erfa-historical-utc-v2-c72`, 역사적 시작, 검토일,
   발표 ID/URL/발행일/검토한 사실/유효기간/가정 정책을 포함한다.
   `bulletin_claims_sha256`는 정규화한 사실의 해시이지 원문 파일의 해시가 아니다.
5. 원천 판본 대조표를 `data/verification/reference-disagreements-20261022.json`에
   연구 기록으로 보존한다. 이 표를 이용해 자동으로 정답을 갈아 끼우지 않는다.

## 경계 시험에서 확인한 추가 주의점

1960-12-31에는 ERFA의 5ms mini-leap quasi-JD 규칙이 있다.
`utctai.c`는 작은 점프도 quasi-JD에 포함하지만 `d2dtf.c`는 0.5초보다 큰
점프만 출력에서 다시 스케일링한다. 따라서 단순 affine 민간시각 fixture는
정오 2.5ms, 하루 끝 5ms 차이를 만들었다. 그 기대값이 일반 86400초 날짜를
가정했다는 원인을 확인했다. 허용오차를 넓히거나 계산값을 보정하지 않았다.
이런 과거 단계 전환일은 `historical_utc_step_day`, `comparable_as_utc=false`로
명시하고 TT를 보존한다. 현재 3,144개 절기 replay 중 해당 상태는 0개다.
SOFA 변환 지원과 KASI 시각 관례·물리 정확도 검증은 별개다.

## 로컬 검증과 수치 증거

- 기준 전체시험 369 passed / 2 kernel-dependent skipped.
- 기존 대조 패치 RED:22 failed/17 passed → 적용 후390 passed/2 skipped.
- 새 시간 정책 테스트의 실패와 후속 통과를 관측. 원천값/분 셀은 동일하다.
- 최종 로컬 전체시험 수와 원격 CI 결과는 PR의 최신 실행 증거를 기준으로 본다.
- 현재 작업 환경에 JPL 파일이 없어 실제 kernel 시험은 원격 CI에서 실행한다.

해시 검증한 보관 기록 3,144개를 **실제 새 product clock 코드**로 재생했다.
새 KASI 원문 취득이나 새로운 독립 천문 관측 검증이 아니다.

| 집계 | 결과 |
|---|---:|
| 비교 가능한 UTC | 1,608 |
| 수치 일치 / 차이 | 1,588 / 20 |
| 1920–1959 시계 미확정 | 960 |
| 2027–2050 UTC 조건부 | 576 |
| 원래314건 중 누적 해소 | 25 |
| 원래314건 중 미해결/차단 | 289 = 과거257 + 비교 가능한20 + 미래12 |
| 새 수치 불일치 | 0 |

1960년의5개는 기존20개에 추가되는 개선이며 총45개가 아니다.
2026년 후반5개는 숫자가 원래 일치했던 항목의 분류 개선이며 불일치 해결에 합산하지 않는다.
재생 보고서의 `status=blocked`, `production_authorized=false`는 그대로 유지된다.
공식 대조 보고서는 수치 차이가 있으면 `failed`, 시계만 미확정이면 `blocked`다.

## 남은 작업

- 최신 KASI 원문 재취득 및 전체 수치 대조.
- 현대20건의 공식 판본·좌표 프레임·보정 단계별 잔차 조사. 분 셀 밖의 거리는
  물리적 참값 오차가 아니다. 상수 보정/분 셀 확대/다수결 정답 선정 금지.
- 1920–1959 KASI 시각 관례와 ΔT 모델 확정. 검증 없는 UT1 치환 금지.
- 원천 이용권, 공식 음양력 전기간 대조, 신뢰된 release 승인.
- 독립 추가 코드 리뷰, 운영 배포는 이번 로컬 검증의 주장 범위가 아니다.

## 원문 근거

- ERFA 2.0.1 `dat.c`: https://raw.githubusercontent.com/liberfa/erfa/v2.0.1/src/dat.c
- `utctai.c`: https://raw.githubusercontent.com/liberfa/erfa/v2.0.1/src/utctai.c
- `d2dtf.c`: https://raw.githubusercontent.com/liberfa/erfa/v2.0.1/src/d2dtf.c
- `dtf2d.c`: https://raw.githubusercontent.com/liberfa/erfa/v2.0.1/src/dtf2d.c
- IERS C72: https://hpiers.obspm.fr/iers/bul/bulc/bulletinc.72

연결된 Express HTTP·Node 로직·DB schema는 변경하지 않았다. 자동 병합·운영 배포 없음.
