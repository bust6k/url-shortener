from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import shortuuid
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from fastapi.responses import FileResponse
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    database_url: str = "postgresql+asyncpg://shortener:shortener@localhost:5432/shortener"
    base_url: str = "http://localhost:8000"


settings = Settings()


class Base(DeclarativeBase):
    pass


class Url(Base):
    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    target: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    clicks: Mapped[list[Click]] = relationship(
        back_populates="url", cascade="all, delete-orphan"
    )


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    url_id: Mapped[int] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    url: Mapped[Url] = relationship(back_populates="clicks")


engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="URL Shortener", version="0.1.0", lifespan=lifespan)


class ShortenRequest(BaseModel):
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def max_len(cls, v: HttpUrl) -> HttpUrl:
        if len(str(v)) > 2048:
            raise ValueError("url too long")
        return v


class ShortenResponse(BaseModel):
    code: str
    short: str
    target: str


class ClickOut(BaseModel):
    clicked_at: datetime
    user_agent: str | None
    ip: str | None


class StatsResponse(BaseModel):
    code: str
    target: str
    total_clicks: int
    created_at: datetime
    last_clicks: list[ClickOut]


def _generate_code() -> str:
    return shortuuid.ShortUUID(alphabet="23456789abcdefghjkmnpqrstuvwxyz").random(length=7)


@app.post("/shorten", response_model=ShortenResponse, status_code=status.HTTP_201_CREATED)
async def shorten(payload: ShortenRequest, db: AsyncSession = Depends(get_db)):
    target = str(payload.url)
    for _ in range(5):
        code = _generate_code()
        exists = await db.scalar(select(Url.id).where(Url.code == code))
        if exists is None:
            break
    else:
        raise HTTPException(status_code=500, detail="could not generate unique code")

    url = Url(code=code, target=target)
    db.add(url)
    await db.commit()
    await db.refresh(url)

    return ShortenResponse(code=url.code, short=f"{settings.base_url}/{url.code}", target=url.target)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/stats/{code}", response_model=StatsResponse)
async def stats(code: str, db: AsyncSession = Depends(get_db)):
    url = await db.scalar(select(Url).where(Url.code == code))
    if url is None:
        raise HTTPException(status_code=404, detail="not found")

    total = await db.scalar(select(func.count(Click.id)).where(Click.url_id == url.id))

    recent = (
        await db.scalars(
            select(Click).where(Click.url_id == url.id).order_by(Click.clicked_at.desc()).limit(10)
        )
    ).all()

    return StatsResponse(
        code=url.code,
        target=url.target,
        total_clicks=total or 0,
        created_at=url.created_at,
        last_clicks=[ClickOut(clicked_at=c.clicked_at, user_agent=c.user_agent, ip=c.ip) for c in recent],
    )



@app.get("/{code}")
async def follow(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    url = await db.scalar(select(Url).where(Url.code == code))
    if url is None:
        raise HTTPException(status_code=404, detail="not found")

    db.add(
        Click(
            url_id=url.id,
            user_agent=request.headers.get("user-agent", "")[:512] or None,
            ip=request.client.host if request.client else None,
        )
    )
    await db.commit()

    return RedirectResponse(url=url.target, status_code=status.HTTP_302_FOUND)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(Path(__file__).parent / "index.htm")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)



