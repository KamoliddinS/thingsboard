
from time import sleep
from threading import Thread
from json import dumps, loads
from zlib import crc32
from hashlib import sha256, sha384, sha512, md5
from mmh3 import hash, hash128
from math import ceil
from database import db_firmware, db_update, db_credential
from database.database import get_db
from database.models import Firmware, Update, DeviceCredential
from sqlalchemy.orm.session import Session
import datetime
import os




db = next(get_db())

#firmware_from {'title': 'payload', 'version': '1'}
#firmware_to {'fw_checksum': '73d0a58fc1100effd38329ec49334cf1acd7423c64cab0254f92e34260211e31', 'fw_size': 71728776, 'fw_title': 'payload', 'fw_checksum_algorithm': 'SHA256', 'fw_version': '3'}


def upgrade_firmware(firmware_from, firmware_to, path_to_firmware):

    #enable sudo
    os.system("sudo -i")

    # get list of all deepstream apps
    deepstream_apps = os.listdir( path_to_firmware + "/deepstream-apps")
    # current deepstream apps
    current_deepstream_apps = os.listdir("/opt/nvidia/deepstream/deepstream/sources/apps/sample_apps/")

    #remove the old deepstream apps
    # for app in current_deepstream_apps:
    #     os.system("rm -r /opt/nvidia/deepstream/deepstream/sources/apps/sample_apps/" + app)

    # remove the deepstream app
    os.system(f"rm -r /opt/nvidia/deepstream/deepstream/sources/apps/sample_apps/{deepstream_apps[0]}")
    # copy the new deepstream apps
    for app in deepstream_apps:
        os.system("cp -r " + path_to_firmware + "/deepstream-apps/" + app + " /opt/nvidia/deepstream/deepstream/sources/apps/sample_apps/")


    # copy https_server_service_orch to /home/srv
    # remove the old https_server_service_orch
    if os.path.exists("/srv/https_server_service_orch"):
        os.system("sudo rm -r /srv/https_server_service_orch")
    os.system("sudo cp -r " + path_to_firmware + "/https_server_service_orch /srv/")





    if os.path.exists("/etc/systemd/system/https_server_service_orch.service"):
        os.system("systemctl restart https_server_service_orch")
    else:

        os.system(" cp /srv/https_server_service_orch/https_server_service_orch.service /etc/systemd/system/")

        os.system("systemctl start http_server_service_orch")
        os.system("systemctl enable https_server_service_orch")
        os.system("systemctl restart https_server_service_orch")




    old_firmware =db_firmware.get_by_version(db, firmware_from.version)

    new_firmware = None
    if old_firmware is None:
        new_firmware = Firmware(
            title = firmware_to['fw_title'],
            version = firmware_to['fw_version'],
            is_active = True,
            path = "firmware/" + firmware_to['fw_version'] + ".bin",
            created_at = datetime.datetime.now(),
            updated_at = datetime.datetime.now()
        )
        db_firmware.create(db= db, firmware= new_firmware)
    else:
        old_firmware.is_active = False
        db_firmware.update(db, old_firmware)
        new_firmware = Firmware(
            title = firmware_to['fw_title'],
            version = firmware_to['fw_version'],
            is_active = True,
            path = "firmware/" + firmware_to['fw_version'] + ".bin",
            created_at = datetime.datetime.now(),
            updated_at = datetime.datetime.now()
        )
        db_firmware.create(new_firmware)



    return new_firmware


