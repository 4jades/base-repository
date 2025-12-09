<div align="right">
  <a href="./README.md">English</a> | <a href="./README.ko.md">한국어</a>
</div>    

# Base Repository

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-informational)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![License](https://img.shields.io/github/license/4jades/base-repository)


SQLAlchemy를 래핑해 기본 CRUD와 조회 DSL을 제공하는 Repository 라이브러리입니다.
Repository를 상속하면, 조회/생성/수정/삭제를 바로 쓸 수 있습니다.

- 간단한 CRUD를 매번 만들 필요가 없습니다.
- MyPy 친화적입니다. 제네릭에 맞는 리턴 타입을 지원합니다.
- 필요한 Repo 함수가 있으면 프로젝트에서 직접 추가해 확장할 수 있습니다.
- Pydantic 스키마와 SQLAlchemy ORM 간 변환을 위한 Mapper 도입을 지원합니다.

## 의존성 지원 버전

아래 테이블은 각 파이썬 버전 별 최소 의존성을 나타냅니다.

더 자세한 [테스트 환경](./tox.ini) 및 [결과](./docs/dependency_test.md) 를 확인하세요.


| 파이썬 버전       | sqlalchemy         | pydantic          |
|----------------|--------------------|-------------------|
| 3.10           | >= 1.4             | >= 1.10           |
| >= 3.13        | >= 1.4             | >= 2.8            |


## Links
- [How to use](https://4jades.github.io/base-repository/how_to_use.html)
- [Performance](https://4jades.github.io/base-repository/about_performance.html)

---

## Installation

```bash
pip install base-repository
```

---

## Quick Start


### 1) Filter와 Repo 정의하기


```python
from dataclasses import dataclass
from pydantic import BaseModel
from base_repository import BaseRepoFilter, BaseRepository

# 이미 프로젝트에 존재하는 SQLAlchemy ORM 모델 및 pydantic 스키마(예시)
class Base(DeclarativeBase):
    pass
class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)

class UserSchema(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

# Base Repository를 쓰기 위해 추가로 정의해야 하는 것들: Filter + Repo
@dataclass
class UserFilter(BaseRepoFilter):
    id: int | iterable[int] | None = None
    name: str | iterable[str] | None = None

class UserRepo(BaseRepository[UserModel, UserSchema]):
    filter_class = UserFilter

# 스키마 매핑을 원치않는다면
class UserRepo(BaseRepository[UserModel]):
    filter_class = UserFilter

# 스키마 1대1 매핑이 아닌 매퍼가 필요하다면
class UserRepo(BaseRepository[UserModel, UserSchema]):
    filter_class = UserFilter
    mapper = Usermapper
```


### 2) 세션 제공자(SessionProvider) 연결하기

Repo가 사용할 `AsyncSession`을 프로젝트에서 어떻게 가져올지 정합니다.  
권장 방식은 `SessionProvider`를 한 번 주입해, Repo가 필요할 때 세션을 가져가게 하는 것입니다.

```python
from typing import Protocol
from base_repository import SessionProvider, BaseRepository

# SessionProvider 구현체 예시
class MysqlSessionProvider(SessionProvider):
    def get_session(self) -> AsyncSession:
        return Mysql.current_session()

BaseRepository.configure_session_provider(MysqlSessionProvider())
```

또는, Repo 생성 시점에 세션을 직접 넘겨도 됩니다.

```python
async with AsyncSession(engine) as session:
    repo = UserRepo(session)
```    

또는, 메소드 호출 시점에 세션을 직접 넘겨도 됩니다.

```python
await repo.create({"name": "Alice", "email": "a@test.com"}, session=session)
```

### 3) 바로 CRUD 쓰기

```python
repo = UserRepo()

# Get one
user = await repo.get(UserFilter(name=["Alice", "Bob"]))
user_orm = await repo.get(UserFilter(name="Alice"), convert_schema=False)

# Get one (required)
user2 = await repo.get_or_fail(UserFilter(id=1))

# Create (dict)
created = await repo.create({"name": "Alice", "email": "a@test.com"})

# Create (schema)
created2 = await repo.create(UserSchema(name="Bob", email="b@test.com"))

# Create (schema -> ORM)
created2_orm = await repo.create(
    UserSchema(name="Bob", email="b@test.com"),
    convert_schema=False,
)

# Create many
created_many = await repo.create_many(
    [
        {"name": "Alice", "email": "a@test.com"},
        UserSchema(name="Bob", email="b@test.com"),
    ]
)

# Create many (skip schema conversion -> ORM list)
created_many_orm = await repo.create_many(
    [
        {"name": "Alice", "email": "a@test.com"},
        {"name": "Bob", "email": "b@test.com"},
    ],
    skip_convert=True,
)

# Create from ORM model (as-is)
created3 = await repo.create_from_model(UserModel(name="Chris", email="c@test.com"))

# List (OFFSET paging)
q = (
    repo.list()
        .where(UserFilter(name="A"))
        .order_by(["id", "name"]) # order_by("id"), order_by(User.id), order_by(User.id.desc()) ..
        .paging(page=1, size=20)
)
users = await repo.execute(q)

# List (CURSOR paging)
q1 = (
    repo.list()
        .order_by(["id", "name"]) # order_by("id"), order_by(User.id), order_by(User.id.desc()) ..
        .with_cursor({})  # first page
        .limit(20)
)
users1 = await repo.execute(q1)

# List (convenience: get_list)
users2 = await repo.get_list(flt=UserFilter(name="A"), order_by=["id", User.name], page=1, size=20)

# List (convenience: get_list + cursor)
users3 = await repo.get_list(order_by="id", cursor={}, size=20)

# Update / Delete / Count
cnt = await repo.count(UserFilter(name="Alice"))
updated_rows = await repo.update(UserFilter(name="Bob"), {"email": "bob@new"})
deleted_rows = await repo.delete(UserFilter(name="Alice"))

# Update (dirty checking)
base = await repo.get_or_fail(UserFilter(id=1), convert_schema=False)
after = await repo.update_from_model(base=base, update={"email": "new@test.com"}, convert_schema=True)

# add / add_all (caller controls flush/commit)
repo.add(User(name="D", email="d@test.com"))
repo.add_all([User(name="E", email="e@test.com"), User(name="F", email="f@test.com")])
await repo.session.flush()
```


---
