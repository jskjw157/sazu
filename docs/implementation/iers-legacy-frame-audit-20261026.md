# 공개 IAU1980 EOP로 분리한 Horizons 잔차 연구 — 2026-10-26 KST

**연구용·운영 승인 차단. 새 수치 해결 0건, 기존 미해결 289건 유지.**

## 결과와 해석

공개 USNO `finals.all`의 **IAU1980 기준 Bulletin A dPsi/dEps**를 별도의 연구 모델에만 넣었다. PR #12의 세차·장동/겉보기 광자 벡터 기준을 유지하고 20개 고정 관측과 비교했다. 17건에 일별 자료가 있고 1962·3, 1972·12, 1972·13은 이 원천 범위 밖이다. 지원된 17건의 Horizons−대안 모델 잔차는 **−4.100~+2.294 mas, 중앙값 +0.268 mas**다. 1975·23, 1976·20, 1980·3의 양쪽 표본은 모두 `P`(prediction), 나머지 14건은 `I`다. 플래그를 과거 시점의 관측 정확도 보증으로 해석하지 않는다.

이는 기존 약 −46~−50 mas 차이에서 **명시적으로 정의한 구형 모델과 공개 EOP가 차이의 큰 부분을 설명할 수 있다는 추가 진단 근거**다. 다른 EOP 시리즈로 유사해졌다는 사실로 Horizons 내부 계산·당시 EOP·태양 사건의 실제 TT 오차가 재현됐다고 말하지 않는다. ±1.14초나 고정 각도 보정은 제품에 적용하지 않았다.

## 이미 완료된 연구와 이번 추가 범위

| 근거 | 이미 확인한 부분 | 여전히 확인하지 않은 부분 |
|---|---|---|
| [PR #11](https://github.com/jskjw157/sazu/pull/11) | 같은 TT 황경 20건, 같은 TDB의 ICRF 기하 벡터 | 겉보기 ICRF 광자 방향 및 출력 프레임의 완전한 동등성 |
| [PR #12](https://github.com/jskjw157/sazu/pull/12) | 같은 Skyfield 광자 벡터를 IAU2000A/B와 무보정 IAU76/80으로 투영 | 관측 CPO, ICRF와 구 J2000의 연결, JPL 분점 관례 |
| [PR #13](https://github.com/jskjw157/sazu/pull/13) | 고정 JPL EOP2 20건, MJD(TAI), IAU2006/2000A dX/dY | 구 IAU76/80 프레임 재현. 현대 dX/dY를 구형 dPsi로 단순 대체할 수 없음 |
| 이번 연구 | 공개 **IAU1980** dPsi/dEps 17건, MJD(UTC) 변환, 예측/누락 구분, 조건부 행렬·황경 응답 | Horizons `eop.261022.p270118`와 동일한 자료·보간·원점의 재현 |

기존 PR의 원천 fixture, 제품 계산 코드, KASI 기준, 분 허용구간, Express API, 배포 차단 조건은 수정하지 않았다. 이번 변경은 `tools/`, `tests/`, 연구 문서에 한정한다.

## 원천 정의·재현 조건

- URL: https://maia.usno.navy.mil/ser7/finals.all
- 확보 바이트 SHA-256: `d1e3293efcb2a4bc2a39b8aa73279e6d04ace357f1cd51eb7df5bac36bc727d7`
- 3,773,912 bytes, 20,074 일별 행, MJD 41684~61757. 이 전체 날짜 범위에 CPO가 모두 존재한다는 뜻은 아니다. 미래 빈 CPO는 결측으로 유지한다.
- 공식 형식: https://maia.usno.navy.mil/ser7/readme.finals — MJD **UTC**, A dPsi 98–106열, A dEps 117–125열, 단위 **mas**, 별도 I/P 플래그 및 오차열. Bulletin B로 자동 대체하지 않는다.
- IAU1980 기준임을 확인한 공식 메타데이터: https://datacenter.iers.org/versionMetadata.php?filename=latestVersionMeta/7_FINALS.ALL_IAU1980_V2013_017.txt
- TT→TAI→SOFA UTC quasi-JD를 PyERFA 2.0.1.5로 변환해 MJD(UTC)를 계산한다. PR #13의 TT−32.184초인 **TAI 인덱스**를 사용하지 않으며 UT1도 대입하지 않는다. 고정 표본의 보간 구간에는 윤초 경계가 없다. 일반 윤초 경계 보간 정확도를 검증한 도구라고 확대하지 않는다.
- 두 일별 값의 선형 보간은 명시적인 **연구 가정**이며 JPL 내부 보간이라고 주장하지 않는다. 예측 플래그, 양쪽 오차, 양쪽 dPsi/dEps와 MJD를 JSON에 남긴다. 오차 상관을 모르므로 독립 표본 오차 전파나 물리 불확실성 한계를 만들지 않는다.
- `finals.all` URL은 변경 가능한 최신 링크다. 다른 바이트가 오면 고정 해시 검사로 차단한다. 같은 원본의 장기 보관 URL은 확보하지 않았다. JSON의 양쪽 표본으로 보간 산술은 재검토할 수 있으나 원본 전체 재취득·인증과는 다르다. 원본 전체 파일/커널은 Git에 포함하지 않았다.
- 실행 JSON의 UTC 시각과 환경을 실제 기록했다. 문서 제목 날짜는 한국시간 검토일이다.

## 변환식과 검증 가능한 범위

사용한 대안은 `Rx(eps80 + deps80 + dEps) · N(eps80, dpsi80 + dPsi, deps80 + dEps) · P76`이다. 각도는 모두 rad로 넘기고 EOP의 mas는 먼저 단위 변환한다. PyERFA/SOFA 수동 회전 부호를 사용한다. 0 보정이면 PR #12의 행렬과 일치한다.

[ERFA numat 원문](https://github.com/liberfa/erfa/blob/master/src/numat.c)은 `Rx(eps)`, `Rz(-dpsi)`, `Rx(-(eps+deps))` 순서의 구성과 mean→true 벡터 방향을 정의한다. 동일한 보정 황도경사각을 마지막 투영에도 쓸 때 dEps가 상쇄되고 **황경 변화는 +dPsi**가 된다. 벡터별 테스트에서 부호·각도 wrap·mas/rad 단위를 검증했다. 이는 이 행렬 구성의 대수적 결과이며 Horizons가 같은 구성/분점을 쓴다는 증명은 아니다. dEps를 TOD 적위나 다른 변환에서 생략해도 된다는 뜻도 아니다.

ICRF 광자 벡터를 구 dynamical J2000에 추가 bias 없이 넣는 PR #12의 가정을 유지한다. IAU2006의 frame-bias 행렬이나 설명서의 약 −53 mas를 구형 모델에 무조건 더하지 않았다. 어떤 연결이 JPL EOP에 이미 포함되는지 모르므로 중복 적용을 피하고 **미확인 조건**으로 남긴다.

## 실제 수치 (mas)

| 연도·절기ID | A 플래그 (양끝) | 보간 dPsi | Horizons−무보정76/80 | Horizons−공개EOP 대안 |
|---|---|---:|---:|---:|
| 1975·23 | P/P | 39.230 | 41.067 | 1.837 |
| 1976·20 | P/P | 27.269 | 29.562 | 2.294 |
| 1980·3 | P/P | 9.941 | 12.197 | 2.256 |
| 1981·19 | I/I | 6.142 | 2.042 | -4.100 |
| 1988·23 | I/I | -2.630 | -0.763 | 1.867 |
| 1989·2 | I/I | -2.028 | -2.017 | 0.011 |
| 1990·16 | I/I | -15.982 | -15.916 | 0.066 |
| 1996·24 | I/I | -30.044 | -29.777 | 0.268 |
| 1999·16 | I/I | -56.634 | -56.736 | -0.101 |
| 2001·3 | I/I | -52.251 | -52.530 | -0.279 |
| 2007·17 | I/I | -66.524 | -65.619 | 0.905 |
| 2009·11 | I/I | -65.944 | -65.695 | 0.249 |
| 2010·19 | I/I | -69.983 | -70.253 | -0.271 |
| 2013·17 | I/I | -88.126 | -86.852 | 1.274 |
| 2014·2 | I/I | -80.177 | -80.654 | -0.477 |
| 2018·20 | I/I | -108.917 | -108.451 | 0.466 |
| 2024·20 | I/I | -114.009 | -113.185 | 0.823 |

**표의 소수 자릿수는 계산 재검토용이다.** 고정 Horizons 황경 float들은 10⁻⁷도(0.36 mas) 격자에 놓여 있다. JSON은 원시 숫자 문자열의 끝자리 0과 출력 반올림 관례를 보존하지 않는다. 행별 출력 정밀도나 ±반격자 물리 오차 상한을 확정하지 않았으며 서브 mas 일치/잔차를 관측 정확도 승인으로 쓰지 않는다.

## 실제 부족한 조건·공개 자료로 검증할 수 있는 다음 단계

| 조건 | 현재 판단 | 다음 검증 |
|---|---|---|
| IAU1980 EOP의 가용성·단위·시각 | finals 17건 확인, 3건 없음 | 초기 3건은 별도 구형 시리즈를 검증해야 함. 누락을 0이나 EOP2로 메우지 않음 |
| 초기 3건의 다른 공개 원천 | IERS **14 C04 IAU1980** 보관 메타데이터가 1962-01-01~2026-01-05를 명시. 2026-02-05 갱신 중단 자료임 | 공식 데이터 파일 다운로드는 이번 환경에서 HTTP400으로 실패. 원문 해시·헤더·초 단위 dPsi/dEps·오차 검증 미실행. 확보한 것처럼 숫자를 제시하지 않음 |
| JPL 고정 EOP 판본 | `eop.261022.p270118` 미확보 | 공개 USNO/C04 또는 EOP2를 동일 스냅샷이라고 부를 수 없음. 옛 Horizons 수치의 완전 재현은 계속 미확정 |
| 분점·프레임 원점·ICRF 연결 | 구 P76/80에 넣는 축의 관례 미확인 | 공개 정의에 따라 연결별 결과를 별도 비교. 모델 명칭만으로 bias 유무를 추정하지 않음 |
| 광자 방향의 차이 | PR #11의 기하 벡터는 빛시간·광행차·중력편향을 검증하지 않음 | 새 동시 응답에서 Horizons **quantity45(겉보기 ICRF RA/Dec)**와 2(TOD),31(황경)을 같은 TT/관측중심/airless 조건으로 수집하면 광자 방향과 프레임 영향을 분리 가능. 단일 태양 방향으로 3차원 회전을 유일하게 결정했다고 주장하지 않음 |
| JPL 내부 보간·자료 경계 처리 | 이번 선형 UTC 보간과 동등성 미확인 | 동일 응답의 EOP 버전·입력 TT·출력 자릿수 및 원시 토큰 보존, 인접 시각 민감도 검증 |
| 실제 TT 근·KASI 비교·승인 | 미확인 | 같은 정의에서 독립 근을 구하기 전에는 17건/20건을 해결 수로 더하지 않음 |

14 C04 근거: https://datacenter.iers.org/versionMetadata.php?filename=latestVersionMeta/223_EOP_C04_14.62-NOW.IAU1980223.txt 및 https://data.iers.org/products/eop/long-term/c04_14/iau1980/ . **IAU2000A 기준 dPsi/dEps라고 적힌 다른 C04와 구별해야 한다.** 변수 이름이 같아도 기준 모델은 다를 수 있다.

Horizons 공식 정의: https://ssd.jpl.nasa.gov/horizons/manual.html 의 TOD, quantities 2/31/45, High Precision EOP Model. 약 −53 mas는 서로 다른 채택 황도에 따른 좌표 원점 설명이며 상수 보정 명령이 아니다. 설명서는 EOP 판본에 따라 결과가 변할 수 있다고 한다. JPL 직접 기술 지원이 없어도 위 공개 원천 가용성·단위·행렬 대수·공개 출력 동시 대조는 진행할 수 있지만, 제공되지 않은 옛 스냅샷과 내부 관례까지 확인했다고 할 수는 없다.

## 실행·검토

RED: 새 모듈 부재 ImportError를 실제 실행했다. 합성 결측 fixture가 잘못 I 플래그를 남긴 2건은 공식 결측 형식(공백 플래그)으로 바로잡았고, 실제 원문을 그 기대값에 맞춰 변경하지 않았다.

초기 Python 3.12.14 환경에서 관련 35개는 통과했지만, 전체 suite는 별도 target 경로 의존성을 CLI subprocess가 상속하지 못해 26실패/439통과였다. 테스트나 제품 코드를 완화하지 않고 **저장소 요구 Python 3.13.5 + requirements-dev.lock/astro.lock + editable install**의 격리 환경을 준비했다. 최종 전체 suite는 실제 커널을 제공해 **465 passed, skip 0**, Ruff `src tests tools` 통과. 원래 코드를 바꾸지 않고 환경 문제를 해소했다.

독립 checker `/root/verify_iers_research`는 원래 요구·raw 파일·실제 diff를 검토하고 관련35개/Ruff 및 원본자료·결과 재생을 확인했다. 실제17개 광자 벡터에 전체 행렬을 적용한 결과와 dPsi 가산 단축의 최대 차이는 약3.07×10⁻⁷ mas였다. 이는 독립 자료 정확도 승인이 아닌 계산 경로 일관성 검사다. 이후 JSON에 양끝 보정값·출력 정밀도 한계를 추가하고 Python3.13.5에서 다시 실행했다.

재실행 (원천 파일과 커널을 명시적으로 준비해야 하며 자동 다운로드 없음):

```bash
python -m pytest -q tests/test_iers_legacy_frame_audit.py tests/test_horizons_frame_reconciliation.py tests/test_jpl_eop2_epoch_audit.py
python -m tools.iers_legacy_frame_audit \
  --eop /verified/local/finals.all \
  --observations data/verification/horizons_20_central_observations_20261023.json \
  --references data/verification/modern_20_naoj_cases_20261023.json \
  --kernel /verified/local/de440s.bsp \
  --output /tmp/iers-legacy-frame-audit.json
```

`--kernel`을 생략하면 EOP 가용성/보간만 기록하고 numerical_projection_executed=false로 남긴다. 원천 해시 불일치·결측·잘못된 플래그·중복/누락 일자·잘못된 날짜 라벨·비유한 수·허용되지 않은 고정 관측 변경은 실패/차단한다. 새 소스 채택은 별도 검토와 연구 revision을 요구한다.
