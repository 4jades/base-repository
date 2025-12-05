<div align="right">
  <a href="./about_performance.md">English</a> | <a href="./about_performance.ko.md">한국어</a>
</div>    

## Performance Test

BaseRepository는 SQLAlchemy를 래핑한 라이브러리이므로 성능 검증의 초점은 아래 2가지입니다.

1. 래핑 오버헤드가 얼마나 작은가 (CPU-bound)
2. 동일한 목적의 코드 대비 성능 차이가 얼마나 나는가 (DB-bound 포함)
   * 2-1. SQLAlchemy 베스트 프랙티스 쿼리/사용 패턴 대비
   * 2-2. 다른 래핑 라이브러리(SQLModel) 대비  
     단, SQLModel 비교는 SQLModel이 “직접 제공하는 기능” 범위에서만 수행합니다.

---

### 성능 테스트 환경

- python = 3.11
- pydantic = 2.12.0,
- sqlalchemy = 2.0.44,
- DB = mysql:8.0, PostgreSQL 16, SQLite 3.45
- Platform = macOS-15.6-arm64-arm-64bit

### NOTE
> 본 성능 테스트는 일부 대표 케이스에 한해 수행되었습니다. 따라서 결과는 특정 환경과 조건에서의 비교 지표이며, 라이브러리 전 기능 및 모든 운영 환경에 대한 일반적인 성능 보증을 의미하지 않습니다.

---

### 1. CPU-bound 테스트 (래핑 오버헤드 검증)

#### 1.1 공통 측정 방식  [→ 결과 바로가기](#attached-cpu-results)
- DB I/O는 전부 제거(모킹)하고, 순수 파이썬 수행 시간만 측정합니다.
- 측정 지표는 mean, p95, p99 입니다.
- 각 케이스는 ITERATIONS = 50으로 반복 측정합니다.
- 기본 사이즈는 `[10, 50, 100, 200, 500, 1000, 5000]` 입니다.
- 결과는 그래프(로컬 생성물)와 jsonl 원본 데이터를 통해 확인할 수 있습니다.

#### 1.2 Read: get_list 성능  [→ 결과 바로가기](#attached-cpu-results)
여러 건을 조회(fetch)하는 경로에서의 오버헤드를 측정합니다.

- BaseRepository 대상 API
  - `get_list` (내부적으로 chaining 기반 list 호출을 사용하므로 대표 측정 포인트로 선택)
- 옵션
  - `order_by = id`, `limit = 50`, `offset = 0`
  - DB를 실제로 조회하지 않으므로 row 내용(value 등)은 CPU 실행을 위한 임의 값입니다.

비교군
- SQLAlchemy (동일 기능 직접 구현)
- BaseRepository (ORM 반환까지)
- BaseRepository (ORM -> schema 변환까지 포함)

메모
- offset 기반만 측정했으며 cursor 방식 CPU-bound 테스트는 미수행 (TODO)

#### 1.3 Converting: ORM -> schema 변환 성능  [→ 결과 바로가기](#attached-cpu-results)
BaseRepository의 schema converting 비용을 별도로 측정합니다.

비교군
- SQLAlchemy + Pydantic 변환
- BaseRepository 변환
- SQLModel 변환

테스트 스키마
```python
class ResultStrictSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int | None = None
    item_id: int
    sub_category_id: int | None
    result_value: str | None
    is_abnormal: bool | None
    tenant_id: int
    checkup_id: int
```

측정 조건

* SQLModel은 “여러 객체를 한 번에 변환”하는 유틸이 없어 반복문 기반으로 처리합니다.
* 공정성을 위해 Pydantic, BaseRepository, SQLModel 모두 동일하게 반복문 기반 변환 시간을 측정합니다.
* 변환 대상 개수는 `[10, 50, 100, 200, 500, 1000, 5000]`, ITERATIONS = 50 입니다.

#### 1.4 Create: bulk create 준비 비용  [→ 결과 바로가기](#attached-cpu-results)

DB 실행은 제외하고, “입력 데이터 -> ORM 객체 구성 및 create 경로 준비”까지의 CPU 비용을 측정합니다.

테스트 케이스

* bulk create from dict
* bulk create from schema
* bulk create from model

사용 스키마

```python
class ResultCreateSchema(BaseModel):
    item_id: int
    sub_category_id: int
    result_value: str
    is_abnormal: bool
    tenant_id: int
    checkup_id: int
```

비교군

* SQLAlchemy 직접 구현
* BaseRepository

#### 1.5 Update: bulk update 준비 비용  [→ 결과 바로가기](#attached-cpu-results)

Create와 동일하게 DB 실행은 제외하고 update 경로 준비까지의 CPU 비용을 측정합니다.

테스트 케이스

* bulk update from dict
* bulk update from model

업데이트 payload 예시

```python
{
    "result_value": f"updated-{i}",
    "is_abnormal": bool(i % 2),
}
```

비교군 및 사이즈/반복 조건은 Create와 동일합니다.

---

### 2. DB-bound 테스트 (실제 DB 포함 성능 검증)

#### 2.1 환경 및 공통 조건  [→ 결과 바로가기](#attached-db-results)

* 목표: 실제 DB에서 CRUD 수행 시간을 측정합니다. (네트워크, 드라이버, 트랜잭션 포함)
* 비교군

  * SQLAlchemy (베스트 프랙티스 패턴)
  * BaseRepository
  * SQLModel (직접 제공 기능만)
* 공통 조건

  * 동일 데이터셋, 동일 스키마 조건 고정
  * 인덱스 없음 (성능 차이를 쿼리 플래너/인덱스 효과로 가리지 않기 위함)
* 테스트 수행한 DB

  * MySQL 8.0 (아래 테스트 케이스)
  * PostgreSQL 16
  * SQLite 3.45
* 실행 환경

  * Docker Compose
* 시드 데이터

  * 테이블 당 1십만 row 
  * 테이블 당 1백만 row 
  * 테이블 당 1천만 row (아래 테스트 케이스)
  * 테이블 당 5천만 row
  * 테이블 당 1억 row

#### 2.2 타겟 테이블 스키마 및 시드 생성 규칙  [→ 결과 바로가기](#attached-db-results)

타겟 테이블은 `PerfResult`이며, 생성되는 컬럼 및 값 규칙은 아래와 같습니다.

```python
PERF_RESULT_COLUMNS = [
    ("payload",   lambda i: f"row-{i}"),
    ("value",     lambda i: f"{i}"),
    ("category",  lambda i: f"cat{i % 10}"),
    ("status",    lambda i: f"status{i % 3}"),
    ("tag",       lambda i: f"tag{i % 5}"),
    ("group_no",  lambda i: f"{i % 20}"),
    ("flag",      lambda i: f"{1 if i % 2 == 0 else 0}"),
    ("value2",    lambda i: f"{i * 2}"),
    ("extra",     lambda i: f"extra-{i % 7}"),
]
```

#### 2.3 측정 지표 및 측정 구간  [→ 결과 바로가기](#attached-db-results)

* 지표: mean, p95, p99
* 트랜잭션 포함 측정 구간(공통)

  * `start -> 객체 생성 + API 호출 + commit + 결과 반환 -> end`
* schema converting 기능은 DB-bound 테스트에서는 비활성화했습니다. (DB I/O 중심 비교를 위해)

#### 2.4 DB 테스트 케이스

##### (1) bulk_create  [→ 결과 바로가기](#attached-db-results)

* 비교군: SQLAlchemy, BaseRepository, SQLModel
* 측정 구간: start -> 객체 생성 + create 호출 + commit + 결과 반환 -> end
* 입력 크기: `INSERT_ROW_VALUES = [100, 500, 1_000, 5_000]`
* 반복: `ITERATIONS = 100`

##### (2) bulk_update  [→ 결과 바로가기](#attached-db-results)

* 비교군: SQLAlchemy, BaseRepository, SQLModel
* 측정 구간: bulk_create와 동일 (commit 포함)
* 업데이트 쿼리 예시

```python
stmt = (
    sa_update(PerfResult)
    .where(PerfResult.id <= n)
    .values(value2=999)
)
```

##### (3) fetch (get_one)  [→ 결과 바로가기](#attached-db-results)
* 비교군: SQLAlchemy, BaseRepository, SQLModel
* get 쿼리 예시

```python
    row = (await session.execute(select(PerfResult).where(PerfResult.id == target_id))).scalar_one_or_none()
```


##### (4) fetch (get_list)  [→ 결과 바로가기](#attached-db-results)

fetch는 where/order 구성이 달라지면 결과가 크게 달라질 수 있어 케이스를 분리했습니다. (추후 추가되어야합니다.)
각 케이스는 SQLAlchemy, BaseRepository, SQLModel 3개를 동일 조건으로 비교하며, 호출 후 commit 및 결과 반환까지 포함해 측정합니다.

1. 10개 필드 중 8개 where + order_by 1개

```python
stmt = (
    select(PerfResult)
    .where(
        PerfResult.id.in_([1, 2, 3, 4]),
        PerfResult.category.in_(["cat-1", "cat-2"]),
        PerfResult.status.in_(["status-1", "status-2"]),
        PerfResult.tag.in_(["tag-0", "tag-1"]),
        PerfResult.group_no.in_([10, 11, 12]),
        PerfResult.value == 100,
        PerfResult.value2 == 1_000_000,
        PerfResult.flag.in_([0, 1]),
    )
    .order_by(PerfResult.id.asc())
    .limit(1_000)
    .offset(0)
)
```

2. where 3개 + order_by 3개

```python
stmt = (
    select(PerfResult)
    .where(
        PerfResult.category == "cat-1",
        PerfResult.status == "status-1",
        PerfResult.flag == 1,
    )
    .order_by(
        PerfResult.category.asc(),
        PerfResult.value2.desc(),
        PerfResult.id.asc(),
    )
    .limit(1_000)
    .offset(0)
)
```

3. order_by 8개

```python
stmt = (
    select(PerfResult)
    .order_by(
        PerfResult.category.asc(),
        PerfResult.status.asc(),
        PerfResult.tag.asc(),
        PerfResult.group_no.asc(),
        PerfResult.flag.desc(),
        PerfResult.value.desc(),
        PerfResult.value2.desc(),
        PerfResult.id.asc(),
    )
    .limit(1_000)
    .offset(0)
)
```

##### (5) delete one [→ 결과 바로가기](#attached-db-results)

* 비교군: SQLAlchemy, BaseRepository, SQLModel
* 삭제 쿼리 예시

```python
    res = await session.execute(delete(PerfResult).where(PerfResult.id == target_id))
```

##### (6) count all [→ 결과 바로가기](#attached-db-results)

* 비교군: SQLAlchemy, BaseRepository, SQLModel
* count 쿼리 예시

```python
    cnt = await session.scalar(select(func.count()).select_from(PerfResult))
```


##### (7) count where 구문 3개 [→ 결과 바로가기](#attached-db-results)

* 비교군: SQLAlchemy, BaseRepository, SQLModel
* count 쿼리 예시

```python
    stmt = (
        select(func.count())
        .select_from(PerfResult)
        .where(
            PerfResult.category == "cat-1",
            PerfResult.status == "status-1",
            PerfResult.flag == 1,
        )
    )
```

---

### 3. 결과 그래프 및 데이터셋 첨부

#### 3.1 아티팩트 경로

* CPU jsonl: `tests/perf/results/cpu/<RUN_ID>.jsonl`
* DB jsonl: `tests/perf/results/db/<RUN_ID>.jsonl`

NOTE: 리포트 이미지(`tests/perf/report/**`)는 저장소에 포함하지 않습니다. 벤치마크 실행 시 로컬에서 생성됩니다.

---

#### 3.2 결과 첨부


#### <a id="attached-cpu-results"></a>CPU BOUND    


- run_id: `20251127T050031Z`, iter: `50`, unit: `ms`  
  → <a href="./perf_results/run_20251127T050031Z/" target="_blank" rel="noreferrer">
       View full HTML report
    </a>

#### <a id="attached-db-results"></a>USE DB    

- **MySQL** — run_id: `20251126T065306Z`, iter: `100`, unit: `ms`, seed: `10000000`  
  → <a href="./perf_results/run_20251126T065306Z/" target="_blank" rel="noreferrer">
       View full HTML report
     </a>

- **PostgreSQL** — run_id: `20251205T025441Z`, iter: `100`, unit: `ms`, seed: `100000`  
  → <a href="./perf_results/run_20251205T025441Z/" target="_blank" rel="noreferrer">
       View full HTML report
     </a>

- **SQLite** — run_id: `20251205T030413Z`, iter: `100`, unit: `ms`, seed: `100000`  
  → <a href="./perf_results/run_20251205T030413Z/" target="_blank" rel="noreferrer">
       View full HTML report
     </a>