from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

engine = create_async_engine("sqlite+aiosqlite:///db.sqlite3")
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()