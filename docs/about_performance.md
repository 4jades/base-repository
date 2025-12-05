<div align="right">
  <a href="./about_performance.md">English</a> | <a href="./about_performance.ko.md">한국어</a>
</div>    

## Performance Test

BaseRepository is a library that wraps SQLAlchemy, so the performance validation focuses on two things:

1. How small the wrapping overhead is (CPU-bound)
2. How it performs compared to other code that serves the same purpose (including DB-bound)
   - 2-1. Compared to SQLAlchemy best-practice query and usage patterns
   - 2-2. Compared to other wrapper libraries (SQLModel)  
     Note: SQLModel comparisons are limited to the feature set SQLModel directly provides.

---

### Performance Test Environment

- python = 3.11  
- pydantic = 2.12.0  
- sqlalchemy = 2.0.44  
- DB = mysql:8.0, PostgreSQL 16, SQLite 3.45  
- Platform = macOS-15.6-arm64-arm-64bit

### NOTE
> This performance test was executed only for a subset of representative cases.  
> Therefore, the results serve as comparative indicators under specific environments and conditions and do not guarantee general performance across all features or production environments.

---

## 1. CPU-bound Tests (Wrapping Overhead Verification)

### 1.1 Common Measurement Method  [→ Jump to results](#attached-cpu-results)
- All DB I/O is removed (mocked), measuring only pure Python execution time.
- Metrics: mean, p95, p99
- Each case is measured with `ITERATIONS = 50`.
- Default sizes: `[10, 50, 100, 200, 500, 1000, 5000]`
- Results can be verified through local graphs and raw jsonl output.

### 1.2 Read: get_list performance  [→ Jump to results](#attached-cpu-results)
Measures overhead on the "fetch multiple rows" path.

- BaseRepository target API
  - `get_list` (selected because it internally uses the chaining-based list flow)
- Options
  - `order_by = id`, `limit = 50`, `offset = 0`
  - Rows are dummy values since DB I/O is excluded.

Baselines
- SQLAlchemy (direct implementation of equivalent behavior)
- BaseRepository (returning ORM objects)
- BaseRepository (including ORM → schema conversion)

Notes
- Only offset-based paging was measured. Cursor-based CPU-bound tests are TODO.

---

### 1.3 Converting: ORM → schema conversion performance  
[→ Jump to results](#attached-cpu-results)

Baselines
- SQLAlchemy + Pydantic conversion
- BaseRepository conversion
- SQLModel conversion

Test schema
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

Measurement conditions

* SQLModel has no utility for bulk converting many objects, so conversion is performed in a loop.
* For fairness, Pydantic, BaseRepository, and SQLModel all measure conversion time using a loop.
* Sizes: `[10, 50, 100, 200, 500, 1000, 5000]`, `ITERATIONS = 50`.

---

### 1.4 Create: bulk create preparation cost

[→ Jump to results](#attached-cpu-results)

Measures CPU cost up to “input data → ORM object creation and create-path preparation”.

Test cases

* bulk create from dict
* bulk create from schema
* bulk create from model

Schema

```python
class ResultCreateSchema(BaseModel):
    item_id: int
    sub_category_id: int
    result_value: str
    is_abnormal: bool
    tenant_id: int
    checkup_id: int
```

Baselines

* SQLAlchemy direct implementation
* BaseRepository

---

### 1.5 Update: bulk update preparation cost

[→ Jump to results](#attached-cpu-results)

Same measurement concept as Create.
DB execution is excluded.

Test cases

* bulk update from dict
* bulk update from model

Payload example

```python
{
    "result_value": f"updated-{i}",
    "is_abnormal": bool(i % 2),
}
```

---

## 2. DB-bound Tests (Real DB Performance)

### 2.1 Environment and Common Conditions

[→ Jump to results](#attached-db-results)

Goal: measure CRUD performance with a real DB (network, driver, transaction included)

Baselines

* SQLAlchemy (best-practice patterns)
* BaseRepository
* SQLModel (only features it directly supports)

Common conditions

* Same dataset and schema across all baselines
* No indexes (to avoid masking differences with query planner effects)

Databases tested

* MySQL 8.0 (used in the test cases below)
* PostgreSQL 16
* SQLite 3.45

Runtime environment

* Docker Compose

Seed data (rows per table)

* 100,000
* 1,000,000
* 10,000,000 (used in following test cases)
* 50,000,000
* 100,000,000

---

### 2.2 Target table schema and seed generation rules

[→ Jump to results](#attached-db-results)

Target table: `PerfResult`

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

---

### 2.3 Metrics and measurement window

[→ Jump to results](#attached-db-results)

Metrics

* mean, p95, p99

Measurement window (transaction included)

```
start → object creation + API call + commit + return results → end
```

Schema conversion is disabled for DB-bound tests.

---

## 2.4 DB Test Cases

---

### (1) bulk_create

[→ Jump to results](#attached-db-results)

Baselines

* SQLAlchemy
* BaseRepository
* SQLModel

Input size
`INSERT_ROW_VALUES = [100, 500, 1_000, 5_000]`

Iterations
`ITERATIONS = 100`

---

### (2) bulk_update

[→ Jump to results](#attached-db-results)

Update query example:

```python
stmt = (
    sa_update(PerfResult)
    .where(PerfResult.id <= n)
    .values(value2=999)
)
```

---

### (3) fetch (get_one)

[→ Jump to results](#attached-db-results)

```python
row = (await session.execute(
    select(PerfResult).where(PerfResult.id == target_id)
)).scalar_one_or_none()
```

---

### (4) fetch (get_list)

[→ Jump to results](#attached-db-results)

Fetch performance varies significantly depending on WHERE and ORDER BY composition.
Cases are separated.

---

#### Case 1: 8 WHERE + 1 ORDER BY

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

---

#### Case 2: 3 WHERE + 3 ORDER BY

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

---

#### Case 3: 8 ORDER BY

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

---

### (5) delete one

[→ Jump to results](#attached-db-results)

```python
res = await session.execute(
    delete(PerfResult).where(PerfResult.id == target_id)
)
```

---

### (6) count all

[→ Jump to results](#attached-db-results)

```python
cnt = await session.scalar(select(func.count()).select_from(PerfResult))
```

---

### (7) count with 3 WHERE predicates

[→ Jump to results](#attached-db-results)

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

## 3. Result Graphs and Datasets

### 3.1 Artifact Paths

* CPU jsonl: `tests/perf/results/cpu/<RUN_ID>.jsonl`
* DB jsonl: `tests/perf/results/db/<RUN_ID>.jsonl`

NOTE: Report images (`tests/perf/report/**`) are not committed.
They are generated locally during benchmark execution.

---

### 3.2 Attached Results


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