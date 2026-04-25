from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    role = Column(String, default="user")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    model = Column(String)
    repair_price = Column(Float)
    sell_price = Column(Float)
    profit = Column(Float)
    date = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer)


class Part(Base):
    __tablename__ = "parts"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Float)
    user_id = Column(Integer)