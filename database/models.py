from .database import Base
from sqlalchemy import Column, Integer, String, DateTime




class Firmware(Base):
  __tablename__ = "firmware"
  id = Column(Integer, primary_key=True, index=True)
  title = Column(String)
  version = Column(String)
  is_active = Column(Integer)
  path = Column(String)
  created_at = Column(DateTime)
  updated_at = Column(DateTime)


class Update(Base):
  __tablename__ = "update"
  id = Column(Integer, primary_key=True, index=True)
  version_from = Column(String)
  version_to = Column(String)

  created_at = Column(DateTime)
  updated_at = Column(DateTime)


class DeviceCredential(Base):
  __tablename__ = "device_credential"
  id = Column(Integer, primary_key=True, index=True)
  device_id = Column(String)
  device_serial_number = Column(String)
  device_mac_address = Column(String)

  server_url = Column(String)
  server_username = Column(String)
  server_password = Column(String)

  thingsboard_url = Column(String)
  thingsboard_port = Column(String)
  thingsboard_access_token = Column(String)
