<div align="right">
  <a href="./README.md">English</a> | <a href="./README.ko.md">한국어</a>
</div>    

# Base Repository Library

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-informational)
![License](https://img.shields.io/github/license/4jades/base-repository)
![Release](https://img.shields.io/github/v/release/<org>/<repo>)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)


SQLAlchemy를 래핑해 기본 CRUD와 조회 DSL을 제공하는 Repository 라이브러리입니다.
Repository를 상속하면, 조회/생성/수정/삭제를 바로 쓸 수 있습니다.

- 간단한 CRUD를 매번 만들 필요가 없습니다.
- 필요한 Repo 함수가 있으면 프로젝트에서 직접 추가해 확장할 수 있습니다.
- Pydantic 스키마와 SQLAlchemy ORM 간 변환을 위한 Mapper 도입을 지원합니다.

# 의존성 지원 버전

아래 테이블은 각 파이썬 버전 별 최소 의존성을 나타냅니다.

더 자세한 [테스트 환경](./tox.ini) 및 [결과](./docs/dependency_test.md) 를 확인하세요.


| 파이썬 버전       | sqlalchemy         | pydantic          |
|----------------|--------------------|-------------------|
| 3.10           | >= 1.4             | >= 1.10           |
| >= 3.13        | >= 1.4             | >= 2.8            |


## Links
- [How to use](./docs/how_to_use.md)
- [Performance](./docs/about_performance.md)
---

## Installation

```bash
# PyPI 배포 전
pip install -U "base-repository @ git+https://github.com/4jades/base-repository.git"

# PyPI 배포 후
pip install -U base-repository
```

---

## Quick Start


### 1) Filter와 Repo 정의하기


```python
from dataclasses import dataclass
from pydantic import BaseModel
from base_repository import BaseRepoFilter
from base_repository.repository import BaseRepository

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

class UserRepo(BaseRepository[UserModel]):
    filter_class = UserFilter
    mapping_schema = UserSchema  # 선택: 기본 반환을 Pydantic으로
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


### 3) 바로 CRUD 쓰기

```python
repo = UserRepo()

# Create
created = await repo.create({"name": "Alice", "email": "a@test.com"})

# Get one
user = await repo.get(UserFilter(name=["Alice", "Bob"]))
user_orm = await repo.get(UserFilter(name="Alice"), convert_domain=False)

# List (OFFSET paging)
q = (
    repo.list()
        .where(UserFilter(name="A"))
        .order_by(["id"])
        .paging(page=1, size=20)
)
users = await repo.execute(q)

# List (CURSOR paging)
q1 = (
    repo.list()
        .order_by(["id"])
        .with_cursor(None)
        .limit(20)
)
users1 = await repo.execute(q1)

# Update / Delete / Count
cnt = await repo.count(UserFilter(name="Alice"))
updated_rows = await repo.update(UserFilter(name="Bob"), {"email": "bob@new"})
deleted_rows = await repo.delete(UserFilter(name="Alice"))
```

---
