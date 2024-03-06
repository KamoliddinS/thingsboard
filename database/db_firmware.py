from sqlalchemy.orm.session import Session
import datetime
from database.models import Firmware


def create(db: Session, firmware):
    new_firmware = Firmware(
        title = firmware.title,
        version = firmware.version,
        is_active = firmware.is_active,
        path = firmware.path,
        created_at = datetime.datetime.now(),
        updated_at = datetime.datetime.now()
    )
    db.add(new_firmware)
    db.commit()
    db.refresh(new_firmware)
    return new_firmware
def update(db: Session, firmware):
    firmware_db = db.query(Firmware).filter(Firmware.id == firmware.id).first()
    firmware_db.title = firmware.title
    firmware_db.version = firmware.version
    firmware_db.is_active = firmware.is_active
    firmware_db.path = firmware.path
    firmware_db.created_at = firmware.created_at
    firmware_db.updated_at = firmware.updated_at
    db.commit()
    db.refresh(firmware_db)
    return firmware_db

def get_all(db: Session):
    return db.query(Firmware).all()

def get_latest(db: Session):
    return db.query(Firmware).order_by(Firmware.created_at.desc()).first()

def get_active(db: Session):
    return db.query(Firmware).filter(Firmware.is_active == True).first()
def get_by_id(db: Session, id: int):
    return db.query(Firmware).filter(Firmware.id == id).first()

def get_by_version(db: Session, version: str):
    return db.query(Firmware).filter(Firmware.version == version).first()
