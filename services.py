from database import SessionLocal
from models import Report, User, Part

def get_user(tg_id):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == tg_id).first()
    if not user:
        user = User(telegram_id=tg_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user


def add_report(model, repair_price, sell_price):
    db = SessionLocal()
    profit = sell_price - repair_price

    r = Report(
        model=model,
        repair_price=repair_price,
        sell_price=sell_price,
        profit=profit
    )

    db.add(r)
    db.commit()
    db.close()


def get_reports():
    db = SessionLocal()
    data = db.query(Report).all()
    db.close()
    return data


def add_part(name, price):
    db = SessionLocal()
    p = Part(name=name, price=price)
    db.add(p)
    db.commit()
    db.close()


def get_parts():
    db = SessionLocal()
    data = db.query(Part).all()
    db.close()
    return data