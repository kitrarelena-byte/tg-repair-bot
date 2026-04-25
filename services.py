from sqlalchemy import select, func
from database import SessionLocal
from models import Report, User

async def get_or_create_user(tg_id):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = res.scalar()

        if not user:
            user = User(telegram_id=tg_id)
            session.add(user)
            await session.commit()

        return user


async def create_report(user_id, model, repair, sell):
    async with SessionLocal() as session:
        profit = sell - repair
        r = Report(
            model=model,
            repair_price=repair,
            sell_price=sell,
            profit=profit,
            user_id=user_id
        )
        session.add(r)
        await session.commit()
        return r


async def get_reports(user_id):
    async with SessionLocal() as session:
        res = await session.execute(
            select(Report).where(Report.user_id == user_id)
        )
        return res.scalars().all()


async def analytics(user_id):
    async with SessionLocal() as session:
        total = await session.execute(
            select(func.sum(Report.profit)).where(Report.user_id == user_id)
        )

        return {"total": total.scalar() or 0}