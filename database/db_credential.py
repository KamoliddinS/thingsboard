
from sqlalchemy.orm.session import Session
import datetime
from database.models import DeviceCredential

def create(db: Session, device_credential):
    new_device_credential = DeviceCredential(
        device_id = device_credential.device_id,
        device_serial_number = device_credential.device_serial_number,
        device_mac_address = device_credential.device_mac_address,
        server_url = device_credential.server_url,
        server_username = device_credential.server_username,
        server_password = device_credential.server_password,
        thingsboard_url = device_credential.thingsboard_url,
        thingsboard_port = device_credential.thingsboard_port,
        thingsboard_access_token = device_credential.thingsboard_access_token,
        created_at = datetime.datetime.now(),
        updated_at = datetime.datetime.now()
    )
    db.add(new_device_credential)
    db.commit()
    db.refresh(new_device_credential)
    return new_device_credential


def update(db: Session, device_credential):
    device_credential_db = db.query(DeviceCredential).filter(DeviceCredential.id == device_credential.id).first()
    device_credential_db.device_id = device_credential.device_id
    device_credential_db.device_serial_number = device_credential.device_serial_number
    device_credential_db.device_mac_address = device_credential.device_mac_address
    device_credential_db.server_url = device_credential.server_url
    device_credential_db.server_username = device_credential.server_username
    device_credential_db.server_password = device_credential.server_password
    device_credential_db.thingsboard_url = device_credential.thingsboard_url
    device_credential_db.thingsboard_port = device_credential.thingsboard_port
    device_credential_db.thingsboard_access_token = device_credential.thingsboard_access_token
    device_credential_db.updated_at = datetime.datetime.now()
    db.commit()
    db.refresh(device_credential_db)
    return device_credential_db


def get_only_one(db: Session):
    if db.query(DeviceCredential).count() > 0:
        return db.query(DeviceCredential).first()
    else:
        return None