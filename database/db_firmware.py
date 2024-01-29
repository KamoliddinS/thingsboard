from sqlalchemy.orm.session import Session
import datetime
from database.models import Firmware


def create(db: Session, firmware):
    new_firmware = Firmware(
        title = firmware.title,
        version = firmware.version,
        is_active = False,
        path = firmware.path,
        state_attributes = firmware.state_attributes,
        created_at = datetime.datetime.now(),
        updated_at = datetime.datetime.now()
    )
    db.add(new_firmware)
    db.commit()
    db.refresh(new_firmware)
    return new_firmware

def get_all(db: Session):
    return db.query(Firmware).all()

def get_by_id(db: Session, id: int):
    return db.query(Firmware).filter(Firmware.id == id).first()

