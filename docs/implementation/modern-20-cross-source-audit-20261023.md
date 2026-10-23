# 현대 절기 20건 — KASI 장기 TXT와 NAOJ 공식 발표표 전수 교차 대조 (2026-10-23)

연구 기록이며 **운영 승인 아님**. 기존 [PR #9](https://github.com/jskjw157/sazu/pull/9) 위에 추가하고 계산 알고리즘·반올림 구간·원천값은 수정하지 않는다.

## 근거 및 방법

- KASI 장기 TXT (2026-09-01) 해시 `508761248c7d18eb1ca1bcb1fcace2ba29f3f511d085321ae1e633c74d8e9e34`. 이번에 KASI 원본 파일을 다시 다운로드하지 않고 이전에 SHA를 확인한 재생 기록을 사용.
- 3,144행 TT 연구 probe 해시 `5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f`; 모델은 Skyfield 1.55 + JPL DE440s + 역사적 UTC 변환.
- NAOJ [공식 연도별 발표 PDF 목록](https://eco.mtk.nao.ac.jp/koyomi/yoko/archives.html) 중 1962–2001 문서의 해당 절기 행을 화면 확인, 2007–2024는 공식 연도별 HTML 표 확인. 한국·일본 시간은 동일한 UTC+9 표시를 사용.
- 분 표시값만 대조한다. 계산 전의 정확한 초값이나 진정한 물리적 순간의 정확도를 입증하지 않으며, 동일한 공통 모델 계보가 있을 수 있다.

## 결과

- 20건 모두 **분 단위 반올림 경계로부터 0.060341~1.009786초** 벗어남. 이 값은 *참 시각에서의 오차*가 아닌 발표된 분의 반올림 구간에 대한 차이임.
- NAOJ 공표값이 KASI 장기 TXT와 같은 항목: **12/20**.
- NAOJ 공표값이 계산 후보의 분 표시와 같은 항목: **8/20**.
- 서로 다른 공식 판본과 수치 후보 중 한쪽을 자동 정답으로 채택하는 보정은 금지. **이번 조사에서 0건을 추가로 ‘해결’ 처리함.** 이전 원래 314건 중 누적25건 수정, 잔여289건 미해결·차단 상태 유지.

| 절기 | KASI 장기표(UTC+9) | 우리 계산의 분 표시 | NAOJ 공식표 | NAOJ 일치 | 근거 |
|---|---|---|---|---|---|
| 1962 경칩 | 10:30 | 10:29 | **10:30** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1962.pdf) p.2 |
| 1972 대서 | 03:03 | 03:02 | **03:03** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1972.pdf) p.2 |
| 1972 입추 | 19:29 | 19:28 | **19:29** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1972.pdf) p.2 |
| 1975 소한 | 08:18 | 08:17 | **08:18** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1975.pdf) p.2 |
| 1976 소설 | 13:22 | 13:21 | **13:22** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1976.pdf) p.2 |
| 1980 경칩 | 19:17 | 19:16 | **19:17** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1980.pdf) p.2 |
| 1981 입동 | 21:09 | 21:08 | **21:09** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1981.pdf) p.2 |
| 1988 소한 | 12:04 | 12:03 | **12:04** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1988.pdf) p.2 |
| 1989 우수 | 01:21 | 01:20 | **01:21** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1989.pdf) p.2 |
| 1990 추분 | 15:56 | 15:55 | **15:56** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1990.pdf) p.3 |
| 1996 대한 | 03:53 | 03:52 | **03:52** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1996.pdf) p.2 |
| 1999 추분 | 20:32 | 20:31 | **20:31** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko1999.pdf) p.2 |
| 2001 경칩 | 21:33 | 21:32 | **21:32** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/pdf/yoko2001.pdf) p.2 |
| 2007 한로 | 01:12 | 01:11 | **01:12** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/2007/rekiyou072.html) |
| 2009 소서 | 08:14 | 08:13 | **08:13** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/2009/rekiyou092.html) |
| 2010 입동 | 21:43 | 21:42 | **21:42** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/2010/rekiyou102.html) |
| 2013 한로 | 11:59 | 11:58 | **11:58** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/2013/rekiyou132.html) |
| 2014 우수 | 03:00 | 02:59 | **02:59** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/2014/rekiyou142.html) |
| 2018 소설 | 18:02 | 18:01 | **18:02** | KASI | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/2018/rekiyou182.html) |
| 2024 소설 | 04:57 | 04:56 | **04:56** | 우리 표시 | [공표자료](https://eco.mtk.nao.ac.jp/koyomi/yoko/2024/rekiyou242.html) |

## 개발 결론과 후속 실험

1. 모든 결과를 KASI 또는 우리 모델에 맞추는 ±1초·분 일괄 보정은 **근거 없음**. 공표값이 반반에 가깝게 갈리며, 어느 쪽인지 시기에 따라 다르다.
2. KASI 장기표, KASI 공식 연도별 월력요항·역서, NAOJ 발간 연도별 구판의 **판본/발표 시점·시간척도·반올림 조건**을 각각 메타데이터로 관리한다.
3. 같은 TT에서 태양 황경을 비교하고, 태양 겉보기 황경이 15도 경계에 도달한 TT를 독립적으로 비교해 모델·좌표 프레임 차이를 확인한다. [JPL Horizons 문서](https://ssd.jpl.nasa.gov/horizons/manual.html)에 따르면 quantity 31은 IAU76/80 날짜 황도이므로 Skyfield와 무조건 동등한 값으로 취급하지 않는다.
4. KASI에 공식 월력요항과 역사적 시간척도, 2024 소설 판본 차이, 이용권을 문의한 메일은 2026-10-23 발송. 회신 전에는 공식 판본 충돌을 미해결로 유지한다.
5. 미확정 입춘/12절 경계와 출생정보 정밀도가 겹치면 사주 연·월주를 단일 확정 결과로 강요하지 않는다.

## 검증 대상

`data/verification/modern_20_naoj_cases_20261023.json` — 원본 전체 PDF/TXT를 재배포하지 않은 20개 항목별 연구용 교차 대조 기록.

`tests/test_modern_20_naoj_research.py` — 20개 키, 출처 URL, 시간 표시, 12/8 분포, release=false를 테스트.

**미완료:** KASI 본 기관의 해석 회신, 전체 3,144건 KASI 원문 새 취득, 출처별 계산 모델 독립성, 현대 20건 실제 초 단위 원인 확정, 원천 이용권 및 상용 승인. 
