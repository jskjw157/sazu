# 첫 CI 연동 오류와 수정 기록

기준: 최초 구현 커밋 `a3741d58d169c329e79d573ce8b1a0efda89f570` 이후 후속 수정.

GitHub Actions [run 39502737895](https://github.com/jskjw157/sazu/actions/runs/39502737895)의 astronomy job은 실제 Skyfield 1.55와 공식 DE440s 파일을 준비하고 checksum까지 통과했으나, `SpiceKernel`에 context manager 프로토콜이 없다는 `TypeError`로 실패했다. 이 실패를 감추거나 비교 기대값을 바꾸지 않았다.

공식 [SpiceKernel 문서](https://rhodesmill.org/skyfield/api-ephemeris.html)의 `close()` 계약에 따라 `contextlib.closing(load_file(...))`을 사용하도록 수정했다. 파일 검증 중 오류가 발생해도 닫히는지를 별도 단위 회귀시험으로 추가했다. 수정 전 해당 단위 시험은 같은 TypeError로 실패했고, 수정 후 전체 로컬 결과는 **175 passed, 1 skipped**다. 로컬 skipped 1개는 여전히 kernel 미제공에 따른 실제 천문 수치 통합시험이다. 수정 후 원격 수치 결과는 PR의 새 CI 실행에서 별도로 확인해야 한다.

- 최종 로컬 source tree: `073f96b90531b2eb72a4cef83cb74eb17831baa3`
- 최종 로컬 tests tree: `bdf7f8dee56f3bb2998257513fd5059158058563`
- 동일 고정 epoch의 별도 프로세스로 wheel을 두 번 빌드한 SHA-256: `044ce19283c97c1675d4d2ba664f4e6e1102e27c695e5e62a55f4e5c6b73d08c`.
- 같은 Python 프로세스에서 연속 빌드하려는 시도는 setuptools의 제거된 작업 디렉터리 재사용으로 두 번째 빌드가 실패했다. 별도 프로세스 재실행으로 완료했으며 실패를 성공으로 기록하지 않는다.
- `verification-20261021.json`의 174개/이전 wheel hash는 최초 구현의 보존된 실행 스냅샷이다. 이 후속 테스트와 합산하지 않는다.

한국 달력 코드·47,848일 왕복 결과·공식 자료 독립 대조의 미완료 상태는 이 수정으로 달라지지 않는다. main 병합·운영 배포는 하지 않는다.
