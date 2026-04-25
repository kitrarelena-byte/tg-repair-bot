from sqlalchemy import String, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from db import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True)
    role: Mapped[str] = mapped_column(String, default="user")


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String)
    repair_price: Mapped[float] = mapped_column(Float)
    sell_price: Mapped[float] = mapped_column(Float)
    profit: Mapped[float] = mapped_column(Float)