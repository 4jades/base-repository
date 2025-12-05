from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class SessionProvider(Protocol):
    def get_session(self) -> AsyncSession:
        ...
