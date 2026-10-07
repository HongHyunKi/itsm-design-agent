# 대표 입력·기준 출력과 디버깅

이 시나리오는 **개발·디버깅용 기준 사례**입니다. ‘베스트 출력’은 사람이 작성한 검토 가능한 설계 제안이며, 모델이 항상 똑같은 JSON을 반환한다는 뜻은 아닙니다.

- [request.json](request.json): 서비스 요청·장애 등록, 상태 변경·재개, 변경 이력, 저장 불필요 안내, 미정 보관 정책을 포함하는 합성 입력
- [expected.json](expected.json): 요구사항 4개·기능 4개·테이블 2개의 기준 설계, FK·추적·검토 결과, 사람이 확인할 업무 조건
- [루트 실행 명령](../../debug-design) · [실행 코드](../scripts/debug_design.py): API와 동일한 `app.services.design.graph`의 실제 단계·분기를 실행
- [실행 계획과 실측](../../docs/plans/tasks/002-시나리오-디버깅.md)

## 먼저 비용 없이 실행

이 문서의 명령은 모두 **저장소 루트(`itsm-design-agent/`)**에서 실행합니다. 최초 설치는 루트 README를 따르세요. 실행 명령이 `backend/.venv/bin/python`을 직접 사용하므로 가상환경을 따로 활성화할 필요가 없으며 서버·DB·Langfuse도 필요하지 않습니다.

```bash
./debug-design
```

`./debug-design --help`로 전체 옵션을 확인할 수 있습니다. 기본값은 `--mode reference`입니다. **모델 응답만 기준 파일로 대체**하며 Pydantic 검사·참조 검사·그래프 분기·ERD/DDL 변환은 실제 코드를 실행합니다. 외부 모델 호출은 0회이고 토큰 수 0은 실측치가 아닌 재생 모드 표시입니다. 실서비스 API의 mock 모드로 추가된 기능은 아닙니다.

터미널에 단계 시작·종료·소요 시간과 `report.html` 경로가 출력됩니다. 그 파일을 브라우저로 열면 됩니다. macOS에서는 출력된 경로를 복사해 `open 경로/report.html`로 열 수도 있습니다.

각 실행은 `backend/.debug-runs/<실행ID>/`에 별도로 저장합니다.

| 파일 | 볼 내용 |
| --- | --- |
| report.html | 실행 조건, 단계별 입출력·검증 판단·모델 호출, 기준과 실제 결과 비교 |
| report.json | 원본 진단 데이터. 실패 시에도 중간 결과 보존 |
| events.jsonl | 진행 중 즉시 기록되는 단계·모델 시작/종료 이벤트 |
| draft-model.mmd | render까지 완료된 경우 동일 모델에서 생성한 Mermaid 원본 |
| draft-schema.sql | render까지 완료된 경우 생성한 미검증 DDL. 실행하지 않음 |

**읽는 순서:** 모드·실패 코드 → 실행·구조 계약 검사 → 실패한 단계 펼치기 → 모델에 보낸 데이터와 응답 → 검토 후보 → 기준 출력과 업무 조건 비교.
`completed_with_warnings`는 그래프 처리 완료입니다. 구조 계약 검사와 업무 의미 검토 결과는 별도로 확인하세요. 리뷰 단계 실패 뒤에도 이미 생성한 ERD·DDL은 디버깅용 중간 초안으로 남을 수 있습니다.

## 실제 Claude 실행

로컬 `backend/.env`에 키를 설정한 뒤 실행합니다. 실제 호출 비용이 발생합니다.

```bash
./debug-design --mode live --max-tokens 8192
```

기본 `.env`의 `ANTHROPIC_MAX_TOKENS=2048`은 변경하지 않습니다. 이 대표 입력은 단일 짧은 요청보다 출력이 크므로 **이번 실행만 8192**를 명시합니다. 실제 최초 생성 출력은 3296토큰이었습니다. 설정 원래값과 적용값을 보고서에 함께 기록합니다. `--max-tokens`를 생략하면 `.env` 설정을 그대로 사용합니다.

생성과 검토는 각 1회이며 실패 후 자동 재시도하거나 기준 결과로 대체하지 않습니다. `live`는 실제 호출 경로이고 `reference`는 비용 없는 재현 경로입니다. API 키 미설정·구조 실패·모델 오류 등은 종료 코드 1, 그래프 완료는 0입니다. 잘못된 CLI 옵션은 2입니다. 코드 0이 의미 품질의 완전성을 보장하지는 않습니다.

API 자체의 최종 응답도 확인하려면 서버를 실행한 뒤 같은 입력을 보낼 수 있습니다.

```bash
curl --fail-with-body http://127.0.0.1:8000/api/v1/design \
  -H 'Content-Type: application/json' \
  --data-binary @backend/scenarios/request.json
```

API는 서버의 `.env` 출력 한도를 사용합니다. 위 CLI 옵션은 서버 설정에 영향을 주지 않습니다. 단계별 보고서는 CLI에서만 생성합니다.

## 오류를 의도적으로 재현

```bash
./debug-design --fault bad-reference
./debug-design --fault semantic-omission
```

| `--fault` | 예상 흐름 |
| --- | --- |
| bad-reference | 존재하지 않는 FK → validate 실패 → render/review 생략 |
| missing-trace | 추적 행 누락 → validate 실패 → render/review 생략 |
| invalid-json | 생성 JSON 오류 → validate 실패 → render/review 생략 |
| truncated | 출력 한도 오류 주입 → generate 실패 → 이후 생략 |
| api-error | 외부 API 오류 주입 → generate 실패 → 이후 생략 |
| review-reference | 생성·검증·변환 성공 → review의 잘못된 참조로 실패 |
| semantic-omission | 변경자 저장을 제거한 구조적으로 유효한 설계 → review에서 누락 후보 표시 |

오류 주입은 `reference`에서만 허용합니다. `semantic-omission`의 리뷰도 미리 작성한 기준 응답입니다. LLM이 결함을 실제로 탐지했다는 증거가 아닙니다. 기준 파일 원본을 수정하지 않으며 실행 복사본만 바꿉니다.

## 판단과 추적 범위

현재 그래프에는 모델이 도구를 선택하는 tool calling이 없습니다. 보고서는 **Anthropic 호출 2개**와 **Python의 검증·변환 실행**을 구분합니다. 관찰 대상은 실제 실행 이벤트, 전달 프롬프트·데이터, 공개된 응답, 근거·가정·질문·추적 이유·검토 제안입니다. 모델의 숨겨진 내부 사고 과정을 기록하거나 재구성하지 않습니다.

자동 검사는 스키마·참조, 동일 모델 변환, FK 존재, 저장 불필요 추적, 호출 완료 등 구조·실행 계약에 한정합니다. 컬럼 개수나 문구의 완전 일치를 품질 점수로 쓰지 않습니다. 제외 범위·업무 규칙·가정의 타당성은 `manual_checks`로 사람이 비교합니다.

전체 프롬프트·입출력은 **명시적으로 실행한 로컬 디버거**에만 기록합니다. CLI의 Langfuse 전송은 비활성이고 운영 API의 메타데이터 추적 정책은 바뀌지 않습니다. 알려진 키는 마스킹하며 보고서는 Git·Docker 빌드에서 제외합니다. `scenarios`는 합성 데이터 전용으로 유지하세요. HTML에는 외부 스크립트가 없고 출력 문자열은 이스케이프합니다.
