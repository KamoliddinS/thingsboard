from sqlalchemy.orm.session import Session
import datetime
from database.models import Update


def create(db: Session, update):
    new_update = Update(
        version_from = update.version_from,
        version_to = update.version_to,
        created_at = datetime.datetime.now(),
        updated_at = datetime.datetime.now()
    )
    db.add(new_update)
    db.commit()
    db.refresh(new_update)
    return new_update


def get_all(db: Session):
    return db.query(Update).all()


def get_by_id(db: Session, id: int):
    return db.query(Update).filter(Update.id == id).first()

