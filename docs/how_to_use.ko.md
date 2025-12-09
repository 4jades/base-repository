<div align="right">
  <a href="https://4jades.github.io/base-repository/how_to_use.html">English</a> | <a href="https://4jades.github.io/base-repository/how_to_use.ko.html">한국어</a>
</div>    

# How To Use (사용자 가이드)

## 목차

- [0) 범위](#0-범위)
- [1) 모델--스키마-정의](#1-모델--스키마-정의)
- [2) repository-구현](#2-repository-구현)
- [3) 빠른-시작-step-by-step](#3-빠른-시작-step-by-step)
  - [3.1 세션-바인딩-중요](#31-세션-바인딩-중요)
    - [3.1.1 권장-provider-기반-구성](#311-권장-provider-기반-구성)
    - [3.1.2 옵션-호출-단위로-세션-직접-주입](#312-옵션-호출-단위로-세션-직접-주입)
    - [3.1.3 옵션-provider-없이-repo에-세션-바인딩](#313-옵션-provider-없이-repo에-세션-바인딩)
  - [3.2 트랜잭션커밋-책임-중요](#32-트랜잭션커밋-책임-중요)
  - [3.3 생성단건다건](#33-생성단건다건)
  - [3.4 조회단건](#34-조회단건)
  - [3.5 조회다건---listquery-체이닝](#35-조회다건---listquery-체이닝)
  - [3.6 조회다건---get_list](#36-조회다건---get_list)
  - [3.7 개수-조회](#37-개수-조회)
  - [3.8 update](#38-update)
  - [3.9 삭제](#39-삭제)
- [4) 공개-api-레퍼런스](#4-공개-api-레퍼런스)
  - [4.1 repository-인스턴스-메서드](#41-repository-인스턴스-메서드)
  - [4.2 listquery-체이닝-메서드](#42-listquery-체이닝-메서드)
- [5) baserepofilter](#5-baserepofilter)
- [6) 매핑도메인-변환-옵션](#6-매핑도메인-변환-옵션)
  - [6.1 mapper-사용-시-스키마-검증-동작](#61-mapper-사용-시-스키마-검증-동작)
- [7) 퍼포먼스-테스트](#7-퍼포먼스-테스트)

---

## 0) 범위

- ORM: SQLAlchemy
- 스키마: Pydantic
- 저장소 패턴: `BaseRepository[TModel]`
- 필터: `BaseRepoFilter` (dataclass 기반)
- 조회 DSL: `ListQuery` 체이닝 (`where → order_by → paging` 또는 `with_cursor + limit`)

---

## 1) 모델 & 스키마 정의

```python
# SQLAlchemy ORM
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]

# Pydantic 스키마
class UserSchema(BaseModel):
    id: int
    name: str
    email: str
    model_config = ConfigDict(from_attributes=True)
```

---

## 2) Repository 구현

```python
@dataclass
class UserFilter(BaseRepoFilter):
    id: int | None = None
    name: str | None = None

class UserRepo(BaseRepository[User, UserSchema]): # (기본) schema(UserSchema) 반환 활성화
    filter_class = UserFilter
```

옵션

* `mapper: type[BaseMapper] | None` 제공 시, 스키마↔ORM 변환 규칙을 커스터마이징
* 인스턴스 생성 시 `mapping_schema`, `mapper`, `default_convert_schema`를 덮어쓸 수 있음

---

## 3) 빠른 시작 (Step-by-step)

## 3.1 세션 바인딩 (중요)

BaseRepository의 세션 우선순위

1. `SessionProvider`가 설정되어 있으면, repo는 **항상** `provider.get_session()`을 사용합니다.
2. Provider가 없으면, repo 생성자에서 전달한 `session`(specific session)을 사용합니다.
3. 둘 다 없으면 런타임 에러가 납니다.

추가로, 각 메서드 호출에서 `session=...`을 전달하면 그 호출에서는 **항상** 그 세션이 최우선입니다.

### 3.1.1 (권장) Provider 기반 구성

```python
# 앱 초기화 시점에 1회 설정
UserRepo.configure_session_provider(session_provider)

# 이후 repo는 세션을 직접 들고 있을 필요가 없음
repo = UserRepo()

rows = await repo.get_list(
    flt=UserFilter(name="A"),
    page=1,
    size=10,
)
```

### 3.1.2 (옵션) 호출 단위로 세션 직접 주입

```python
repo = UserRepo()

async with AsyncSession(engine) as session:
    rows = await repo.get_list(
        flt=UserFilter(name="A"),
        page=1,
        size=10,
        session=session,  # 이 호출에서만 사용됨
    )
```

### 3.1.3 (옵션) Provider 없이 repo에 세션 바인딩

```python
async with AsyncSession(engine) as session:
    repo = UserRepo(session=session)
    rows = await repo.get_list(flt=UserFilter(name="A"), page=1, size=10)
```

주의

* Provider가 설정된 상태에서 `UserRepo(session=...)`로 세션을 넣어도 **Provider가 우선**이며, 해당 세션은 무시됩니다(경고 발생).

---

## 3.2 트랜잭션/커밋 책임 (중요)

* BaseRepository는 `commit()`을 호출하지 않습니다.
* `create/create_many/create_from_model/update_from_model`은 `flush()`까지만 수행합니다.
* `update/delete/execute/get/get_list/count`는 `flush/commit`을 수행하지 않습니다.
* 트랜잭션 경계(`commit/rollback`)는 호출자(서비스/유스케이스/미들웨어)가 책임집니다.

---

## 3.3 생성(단건/다건)

```python
# 단건: 스키마 또는 dict
created = await repo.create(UserSchema(name="Alice", email="a@test.com"))
created2 = await repo.create({"name": "Bob", "email": "b@test.com"})

# 다건
bulk = await repo.create_many([
    {"name": "C", "email": "c@test.com"},
    UserSchema(name="D", email="d@test.com"),
])

# ORM 모델 직접
created3 = await repo.create_from_model(User(name="E", email="e@test.com"))
```

PK 처리 규칙

* `create()` / `create_many()`는 autoincrement PK 입력을 무시합니다(컬럼-only payload로 정리 + autoinc pk 제거).
* `create_from_model()`은 ORM 객체를 그대로 add+flush 하므로, PK를 설정해 넘기면 INSERT에 포함될 수 있습니다.

---

## 3.4 조회(단건)

```python
# 단건
row = await repo.get(UserFilter(name="Alice"))  # 기본: 도메인 반환 (mapping_schema 설정 시)
row_raw = await repo.get(UserFilter(name="Alice"), convert_schema=False)  # ORM 반환
```

---

## 3.5 조회(다건 - ListQuery 체이닝)

### OFFSET 페이징

```python
q = (
    repo.list(flt=UserFilter())
        .order_by([User.id.asc()])   # 선택(미지정 시 구현체에서 보강될 수 있음)
        .paging(page=1, size=20)     # page>=1, size>=1
)

# 또는 where 체이닝
q = (
    repo.list()
        .where(UserFilter())
        .order_by([User.id.asc()])
        .paging(page=1, size=20)
)

rows = await repo.execute(q)         # SELECT는 항상 list 반환
```

### CURSOR(Keyset) 페이징

```python
# 첫 페이지: None 또는 {}
q1 = (
    repo.list()
        .order_by([User.id.asc()])   # 커서 이전에 지정
        .with_cursor(None)
        .limit(20)                   # size>=1
)
rows1 = await repo.execute(q1)

# 다음 페이지
next_cursor = {"id": 123}
q2 = (
    repo.list()
        .order_by([User.id.asc()])
        .with_cursor(next_cursor)    # order_by 컬럼 키/순서와 동일해야 함
        .limit(20)
)
rows2 = await repo.execute(q2)
```

### where 사용 패턴

```python
# 여러 필드 조합
q = repo.list().where(UserFilter(id=1, name="Kyu"))

# list(flt=...)와 .where(...)를 같이 쓰면 where()에서 예외가 날 수 있습니다.
# (list()에서 이미 filter가 설정된 상태이기 때문)
```

### order_by 입력 예시(지원되는 다양한 형태)

```python
# 1) 문자열 키
q = repo.list().order_by(["id"]).paging(page=1, size=10)

# 2) Enum.value (문자열) — 예시 Enum
class SortKey(Enum):
    ID = "id"
    NAME = "name"
q = repo.list().order_by([SortKey.ID, SortKey.NAME]).paging(page=1, size=10)

# 3) 모델 컬럼 속성
q = repo.list().order_by([User.name]).paging(page=1, size=10)

# 4) asc()/desc()
q = repo.list().order_by([User.name.desc(), User.id.asc()]).paging(page=1, size=10)

# 5) ColumnElement (expression)
q = repo.list().order_by([User.name.expression]).paging(page=1, size=10)

# 6) 기본값: order_by 생략
q = repo.list().paging(page=1, size=10)
```

### 커서 dict 예시(다중 컬럼)

```python
q = (
  repo.list()
     .order_by([User.id.asc(), User.name.desc()])
     .with_cursor({
         "id": 120,
         "name": "Z",
     })
     .limit(20)
)
rows = await repo.execute(q)
```

불허

* 다른 모델 컬럼, `func(...)`, `text("...")`, 임의 타입
* 커서 값에 `None`
* 커서 키 집합/순서 불일치

---

## 3.6 조회(다건 - get_list)

### OFFSET 페이징

```python
rows = await repo.get_list(
    flt=UserFilter(name="A"),
    order_by=[User.id.asc()],
    page=1,
    size=10,
)

rows = await repo.get_list(
    flt=UserFilter(id=1, name="A"),
)

rows = await repo.get_list(
    order_by=["id", User.name.desc()],
    page=2,
    size=10,
)

rows = await repo.get_list(page=1, size=10)
```

### CURSOR(Keyset) 페이징

```python
rows1 = await repo.get_list(
    order_by=[User.id.asc()],
    cursor={},   # 또는 None (이 경우에도 keyset 모드)
    size=10,
)

rows2 = await repo.get_list(
    order_by=[User.id.asc(), User.name.desc()],
    cursor={"id": 120, "name": "Z"},
    size=10,
)
```

get_list 조합 규칙

1. `cursor`를 전달하면(None 포함) keyset 페이징으로 동작합니다.

* `order_by` 필수
* `size` 필수 (keyset limit)

2. `page`와 `size`를 같이 지정하면 offset 페이징으로 동작합니다.

3. 그 외는 페이징이 적용되지 않습니다.

* `page`만 주는 형태는 페이징이 되지 않으니 지양하세요.

---

## 3.7 개수 조회

```python
cnt = await repo.count(UserFilter(name="Alice"))
```

---

## 3.8 update

```python
# 일괄 UPDATE (단일 UPDATE SQL)
updated = await repo.update(UserFilter(name="Bob"), {"email": "bob@new"})

# 영속 객체 Dirty Checking
obj = await repo.get(UserFilter(name="Alice"), convert_schema=False)
updated_schema = await repo.update_from_model(obj, {"email": "alice@new"})
```

---

## 3.9 삭제

```python
deleted = await repo.delete(UserFilter(name="Alice"))
```

---

## 4) 공개 API 레퍼런스

## 4.1 Repository 인스턴스 메서드

* `configure_session_provider(provider: SessionProvider) -> None` (class method)

  * Provider를 설정하면 repo는 provider에서 세션을 가져옵니다.

* `session -> AsyncSession` (property)

  * Provider가 있으면 provider 세션, 없으면 repo에 바인딩된 specific session을 사용합니다.

* `list(flt: BaseRepoFilter | None = None) -> ListQuery`

  * 조회 DSL 시작점.

* `execute(q_or_stmt, *, session=None, convert_schema=None)`

  * `ListQuery` 또는 statement를 실행합니다.
  * SELECT는 항상 `list`를 반환합니다.

* `get(flt, *, convert_schema=None, session=None)` / `get_or_fail(...)`

  * 단건 조회.

* `get_list(*, flt=None, order_by=None, cursor=None, page=None, size=None, session=None, convert_schema=None)`

  * 편의 함수. 내부에서 `ListQuery`를 조립해 `execute()`까지 수행합니다.

* `count(flt=None, *, session=None)` / `delete(flt, *, session=None)`

  * 개수/삭제.

* `add(obj, *, session=None)` / `add_all(objs, *, session=None)`

  * 세션에 추가만 합니다. flush/commit은 호출자 책임입니다.

* `create(data, *, session=None, convert_schema=None)` / `create_many(items, *, session=None, convert_schema=None)` / `create_from_model(obj, *, session=None, convert_schema=None)`

  * 삽입 + flush까지 수행합니다.
  * `create/create_many`는 autoincrement PK 입력을 무시합니다.
  * `create_from_model`은 ORM을 그대로 추가하므로 PK가 세팅되어 있으면 INSERT에 포함될 수 있습니다.

* `update(flt, update, *, session=None)`

  * 단일 UPDATE SQL로 일괄 수정합니다. 반환: 수정 row 수(rowcount).

* `update_from_model(base, update, *, session=None, convert_schema=None)`

  * 영속 객체에 값을 적용하고 `flush()`합니다. 반환: 도메인 또는 ORM.

---

## 4.2 ListQuery 체이닝 메서드

* `.where(flt: BaseRepoFilter | None) -> ListQuery`

  * 1회만 설정. `None`이면 무시.

* `.order_by(items: Sequence[Any]) -> ListQuery`

  * 정렬 지정. CURSOR 진입 전까지만 허용.
  * 허용 입력: 문자열 키("id"), `Enum.value`(문자열), 모델 컬럼 속성, `asc()/desc()`, 해당 컬럼의 `expression`.
  * 불허 입력: 다른 모델/조인 컬럼, `func(...)`, `text("...")`, 임의 타입.

* `.with_cursor(cursor: dict[str, Any] | None = None) -> ListQuery`

  * CURSOR 모드 진입. `None`/`{}`는 첫 페이지.
  * 필수: `order_by(...)` 선행(빈 리스트 불가).
  * 커서 규칙: 키 집합과 순서가 `order_by` 컬럼과 동일, 값은 `None` 금지.

* `.limit(size: int) -> ListQuery`

  * CURSOR 페이지 크기. `size>=1`. OFFSET 모드와 병용 불가.

* `.paging(*, page: int, size: int) -> ListQuery`

  * OFFSET 모드. `page>=1`, `size>=1`, 1회만 호출. CURSOR와 병용 불가.

---

## 5) BaseRepoFilter

* dataclass 필드를 자동으로 WHERE 조건으로 변환

규칙

* `bool` -> `.is_(val)`
* 시퀀스 -> `.in_(...)` (빈 시퀀스는 생략)
* 단일 값 -> `==`
* `__aliases__`로 필드명->컬럼명 매핑 가능
* `__strict__ = True`면 매핑 실패 시 예외

예시

```python
@dataclass
class UserFilter(BaseRepoFilter):
    id: int | list[int] | None = None
    active: bool | None = None
    __aliases__ = {"org_ids": "org_id"}
```

* 여러 id를 만족하도록 필터링하려면 `UserFilter(id=[1, 2, 3])` 형태로 사용 가능합니다.
* BaseRepoFilter는 값 타입이 시퀀스면 자동으로 IN 조건으로 처리합니다.

---

## 6) 매핑(도메인 변환) 옵션

* `mapping_schema` 지정 시 기본 반환은 Schema(Pydantic)
* `convert_schema=False`로 ORM 반환 가능
* `BaseMapper`를 지정하면 도메인↔ORM 변환을 커스터마이즈

예시

```python
class UserMapper(BaseMapper):
    def to_schema(self, db: User) -> UserSchema:
        return UserSchema(id=db.id, name=db.name, email="Changed")

    def to_orm(self, dm: UserSchema) -> User:
        return User(**dm.model_dump(exclude=["name"]), name="fixed")

class UserRepo(BaseRepository[User, UserSchema]):
    filter_class = UserFilter
    mapper = UserMapper

row = await repo.get(UserFilter(id=1))
assert row.email == "Changed"
```

### 6.1 mapper 사용 시 스키마 검증 동작

`mapper(BaseMapper)`를 지정한 경우, BaseRepository는 `mapping_schema` 필드 이름과
ORM 모델 컬럼 이름의 1:1 일치 여부를 검증하지 않습니다.

의도

* 이름이 다른 스키마 필드를 모델 컬럼으로 매핑하거나
* 여러 필드를 조합해 하나의 컬럼을 채우는 커스텀 변환을 허용하기 위함입니다.

동작 요약

```python
class UserRepo(BaseRepository[User, UserSchema]):
    filter_class = UserFilter
    mapper = UserMapper  # mapper가 존재하면 column-only strict 검증 비활성화
```

---

## 7) 퍼포먼스 테스트

명령어 모음

* makefile의 명령어를 참고하세요.

* perf-list

  * 기존 RUN_ID 리스트 출력
  * 결과는 `tests/perf/results`에 jsonl로 저장

* perf-cpu

  * CPU bound 테스트 실행

* perf-db

  * DB 포함 테스트 실행 (docker 필요)

* perf-view

  * 최근 RUN_ID 결과를 그래프로 표시
  * `RUN_ID={RUN_ID}`를 붙이면 특정 RUN_ID 결과 표시

세팅 방법

1. CPU

* `tests/perf/perf_cpu_only.py` 상단에서 `ROW_VALUES`, `ITERATIONS` 변경 가능

2. DB

* `tests/perf/seed.config.py`에서 `SEED_DATA_ROWS` 변경 가능
* 테이블 필드/규칙을 바꾸면 테스트도 같이 수정해야 합니다(현재 유연 설계 아님).
