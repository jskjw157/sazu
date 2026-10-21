# Express + Python 실행 안내

## 현재 범위

Express + TypeScript가 외부 API를 맡고 Python/FastAPI는 기존 S1 계산 모듈만 감싼 내부 서비스입니다. 계산 코드는 Python 한 곳에 남습니다. PostgreSQL은 Express에서만 접근합니다.

**연구·통합 검증용입니다. 사용자 로그인, 결제, 개인 데이터 저장, 원국/대운 계산, 승인 데이터 배포와 운영 출시는 아직 구현하지 않았습니다.** `RESEARCH_API_TOKEN`은 서버 간/개발자 연구 접근키이며 브라우저 앱에 넣을 사용자 인증 토큰이 아닙니다. 모든 응답의 `production_authorized`는 false입니다.

| 외부 Express | 내부 Python | 의미 |
|---|---|---|
| `POST /v1/research/calendar` | `POST /internal/v1/calendar` | 한국 음양력 변환; 윤달 미상 후보 보존 |
| `POST /v1/research/normalize-time` | `POST /internal/v1/normalize-time` | 시각 정규화; unknown/gap/fold 보존 |
| `GET /health/live` | `GET /health/live` | 프로세스 생존. 출시 승인 아님 |
| `GET /health/ready` | 인증된 `GET /health/ready` + PostgreSQL `SELECT 1` | 의존성 연결 상태. 출시 승인 아님 |

원천 다운로드/로컬 파일 검사/environment/절기 대량 생성 CLI는 HTTP로 노출하지 않습니다. `/v1/pillars` 같은 미구현 기능은 404입니다.

## 로컬 Docker 실행

Node 24.22.0, Python 3.13.5, PostgreSQL 17 기반입니다. Docker Engine 28 이상과 Compose v2를 사용해 로컬에서 검증하세요. 이미지 태그의 불변 digest 고정과 전체 공급망 보안 검토는 출시 전 추가 작업입니다.

프로젝트 루트에서 `.env.example`을 참고해 `.env`를 작성합니다. 네 비밀번호/키는 각각 `secrets.token_hex(32)` 등으로 생성한 **서로 다른 64자리 소문자 hex**를 사용합니다. `.env`는 Git과 Docker build context에서 제외합니다.

```sh
cp .env.example .env
# RESEARCH_API_TOKEN / CALCULATOR_TOKEN / POSTGRES_ADMIN_PASSWORD /
# POSTGRES_APP_PASSWORD를 각각 새 값으로 채운 뒤 .env 권한을 제한합니다.
chmod 600 .env
docker compose config --quiet
docker compose up --build --wait
```

기본 공개 바인딩은 `127.0.0.1:3000` 하나입니다. Python 8000과 PostgreSQL 5432는 호스트에 publish하지 않습니다. 계산용 네트워크와 DB 네트워크는 별도 internal network이며 Python은 DB 네트워크에 참여하지 않습니다. 이는 호스트 관리자나 임의 Docker 권한 보유자에 대한 보안 경계가 아닙니다.

```sh
# 서버 환경에 RESEARCH_API_TOKEN을 안전하게 주입한 개발자 클라이언트 예
curl --fail-with-body http://127.0.0.1:3000/v1/research/calendar \
  -H "Authorization: Bearer $RESEARCH_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"kind":"korean_lunar","year":2017,"month":5,"day":1,"leap":"unknown"}'
```

`.env`는 Compose용이며 단순 curl 프로세스에는 자동으로 주입되지 않습니다. 셸 기록에 실제 키를 직접 타이핑하지 마세요. 연구 접근키를 프론트엔드 환경변수로 배포하지 마세요.

`docker compose stop`은 데이터를 유지합니다. `down -v`는 DB 볼륨을 삭제하므로 실제 자료가 생긴 뒤에는 무심코 사용하지 마세요. DB 초기 역할 생성 SQL은 새 볼륨에서만 실행되므로 기존 볼륨의 비밀번호는 .env 수정만으로 바뀌지 않습니다.

## 직접 실행 및 테스트

```sh
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
cd apps/api && npm ci --ignore-scripts && npm test && cd ../..
python -m pytest -q
python tools/test_service_boundary.py
```

마지막 명령은 임시 Python/Node 프로세스와 임의 연구키를 생성하고 종료합니다. 실사용자 데이터를 사용하지 않습니다. 로컬 DB가 없는 시나리오에서는 readiness 503을 기대하며, 실제 DB 연결·컨테이너 빌드·포트 격리는 별도의 Compose CI에서 검사합니다.

직접 실행 시 `SAZU_MODE=research`, 별도 `CALCULATOR_TOKEN`과 `RESEARCH_API_TOKEN`, 고정 `PYTHON_BASE_URL`, `DATABASE_URL`이 필요합니다. Python은 `python -m uvicorn sazu.http_service:create_app_from_env --factory --no-access-log`로 실행하고 Express는 `apps/api`에서 `npm run build && npm start`로 실행합니다. 두 프로세스는 각자의 최소 환경변수만 받게 구성하세요.

## 경계 정책

- 버전: `sazu.foundation.v1`. Express가 내부 인증키와 프로토콜 헤더를 붙이며 외부 인증키·cookie·사용자 요청 ID는 전달하지 않습니다.
- 본문은 UTF-8 JSON 최대 16 KiB, 압축은 허용하지 않습니다. 입력은 DB/파일에 자동 저장하지 않습니다.
- Express는 형태를 검사한 뒤 원문 JSON 문자열을 보냅니다. 중복 키·2024.0처럼 Python 규칙에서 거절할 값이 재직렬화로 정상 입력으로 바뀌지 않습니다.
- 응답은 최대 256 KiB이고 전체 내부 호출(헤더와 body 포함)에 기본 3초 제한을 둡니다. 리다이렉트·자동 재시도·상용 API fallback은 없습니다.
- 응답 스키마, 요청 ID, protocol, production=false, 입력 echo/zone/precision을 검사합니다. 비정상 upstream 응답은 성공으로 반환하지 않습니다.
- 기본 동시 호출 32개, 프로세스당 분당 120개 예산입니다. 여러 인스턴스를 위한 분산 rate limiter는 아직 없으며 이 제한을 전체 서비스 한도로 오해하지 않습니다.
- 요청 취소는 내부 HTTP를 중단하고 슬롯을 반환합니다. 이미 실행 중인 Python thread 계산 자체를 강제 종료하는 기능은 아닙니다.
- 외부/내부 인증키는 서로 달라야 합니다. mode=production은 시작 단계에서 거절됩니다. 사용자별 권한·사용량·삭제는 후속 구현입니다.
- PostgreSQL 앱 계정은 로그인/접속만 가능하고 superuser/DB 생성/역할 생성 권한은 없습니다. 현재 저장 테이블이나 migration 실행을 주장하지 않습니다.
- SQL/네트워크/입력 오류의 원문이나 키는 외부 응답에 포함하지 않습니다. 운영용 TLS/mTLS·회전·RBAC·분산 추적·보안 검토는 추가로 필요합니다.

## 검증의 의미

Python 기존 시험, HTTP 단위시험, Node transport 시험, 실제 두 프로세스 통합시험, Compose topology/DB 검증을 분리합니다. 위 테스트가 한국천문연구원 독립 전기간 대조나 사주의 예측력을 입증하지는 않습니다. 기존 JPL 파일 미확보 skip 및 승인 데이터 부재는 그대로 유지합니다.

공식 참고: Express error handling, Node AbortSignal/fetch, FastAPI security, Docker Compose networks 및 PostgreSQL psql 문서. 현재 구현은 선택한 hybrid 경계를 연결한 것이며 앱 전체 상용 완료가 아닙니다.
