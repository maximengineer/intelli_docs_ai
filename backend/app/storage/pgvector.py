from __future__ import annotations

from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """Minimal SQLAlchemy type mapping to the pgvector ``vector`` column.

    Kept tiny on purpose: the runtime store uses raw SQL, and this type exists so
    Alembic autogenerate and ``Base.metadata`` understand the column.
    """

    cache_ok = True

    def __init__(self, dimension: int | None = None) -> None:
        self.dimension = dimension

    def get_col_spec(self, **_: object) -> str:
        return "vector" if self.dimension is None else f"vector({self.dimension})"
