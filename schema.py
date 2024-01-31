from contextlib import asynccontextmanager
from functools import partial
from typing import Dict, Any

import strawberry
from strawberry.types import Info
from fastapi import FastAPI
from strawberry.fastapi import BaseContext, GraphQLRouter
from databases import Database

from settings import Settings


class Context(BaseContext):
    db: Database

    def __init__(
        self,
        db: Database,
    ) -> None:
        self.db = db



@strawberry.type
class Author:
    name: str


@strawberry.type
class Book:
    title: str
    author: Author


@strawberry.type
class Query:

    @strawberry.field
    async def books(
        self,
        info: Info[Context, None],
        author_ids: list[int] | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> list[Book]:
        base_query = """
           SELECT b.title, a.name 
           FROM books b 
           JOIN authors a ON b.author_id = a.id
       """

        conditions = []
        values: Dict[str, Any] = {}

        if author_ids:
            conditions.append("a.id = ANY(:author_ids)")
            values["author_ids"] = tuple(author_ids)

        if search:
            conditions.append("(b.title ILIKE :search OR a.name ILIKE :search)")
            values["search"] = f"%{search}%"

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        if limit is not None:
            base_query += " LIMIT :limit"
            values["limit"] = limit

        query = base_query + ";"
        results = await info.context.db.fetch_all(query=query, values=values)

        books = [Book(title=result['title'], author=Author(name=result['name'])) for result in results]
        return books


CONN_TEMPLATE = "postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
settings = Settings()  # type: ignore
db = Database(
    CONN_TEMPLATE.format(
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        port=settings.DB_PORT,
        host=settings.DB_SERVER,
        name=settings.DB_NAME,
    ),
)

@asynccontextmanager
async def lifespan(
    app: FastAPI,
    db: Database,
):
    async with db:
        yield

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(  # type: ignore
    schema,
    context_getter=partial(Context, db),
)

app = FastAPI(lifespan=partial(lifespan, db=db))
app.include_router(graphql_app, prefix="/graphql")
