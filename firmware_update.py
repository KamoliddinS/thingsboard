from paho.mqtt.client import Client
from time import sleep, time
from json import dumps, loads
from zlib import crc32
from hashlib import sha256, sha384, sha512, md5
from mmh3 import hash, hash128
from math import ceil
from threading import Thread
from random import randint
from update_utils import upgrade_firmware
#tarxz extraction
from tarfile import TarFile
from lzma import LZMAFile
from os import remove, path, mkdir, chmod
import os
from utils import get_data
import logging
from database.db_firmware import get_active, get_latest
from database.db_update import create as create_update, get_all as get_all_update, get_by_id as get_update_by_id
from database.db_credential import create as create_credential, get_only_one
from database import models
from database.database import SessionLocal, engine
from database.database import get_db

#set up logging
logging.basicConfig(level=logging.INFO)

# file logger
file_handler = logging.FileHandler("/var/log/thingsboard_manager.log")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logger = logging.getLogger(__name__)
logger.addHandler(file_handler)




client = get_db().__next__()
models.Base.metadata.create_all(bind=engine)


latest_firmware = get_active(client)

device_credential = get_only_one(client)

if device_credential is not None:
    dict_device_credential = device_credential.__dict__
    logger.info(f"Device credential: {dict_device_credential}")


if latest_firmware is not None:

    dict_latest_firmware = latest_firmware.__dict__
    logger.info(f"Latest firmware: {dict_latest_firmware}")

if latest_firmware is None:
    latest_firmware = models.Firmware()
    latest_firmware.title = "payload"
    latest_firmware.version = "1"


FW_CHECKSUM_ATTR = "fw_checksum"
FW_CHECKSUM_ALG_ATTR = "fw_checksum_algorithm"
FW_SIZE_ATTR = "fw_size"
FW_TITLE_ATTR = "fw_title"
FW_VERSION_ATTR = "fw_version"
FW_STATE_ATTR = "fw_state"

REQUIRED_SHARED_KEYS = f"{FW_CHECKSUM_ATTR},{FW_CHECKSUM_ALG_ATTR},{FW_SIZE_ATTR},{FW_TITLE_ATTR},{FW_VERSION_ATTR}"


def collect_required_data():
    config = {}
    config["host"] = device_credential.thingsboard_url
    config["port"] = int(device_credential.thingsboard_port)
    config["token"] = device_credential.thingsboard_access_token
    chunk_size =65735
    config["chunk_size"] = int(chunk_size) if chunk_size else 0
    return config


def verify_checksum(firmware_data, checksum_alg, checksum):
    if firmware_data is None:
        logger.error("Firmware data wasn't provided!")
        return False
    if checksum is None:
        logger.error("Checksum wasn't provided!")
        return False
    checksum_of_received_firmware = None
    logger.info(f"Checksum algorithm: {checksum_alg}")
    if checksum_alg.lower() == "sha256":
        checksum_of_received_firmware = sha256(firmware_data).digest().hex()
    elif checksum_alg.lower() == "sha384":
        checksum_of_received_firmware = sha384(firmware_data).digest().hex()
    elif checksum_alg.lower() == "sha512":
        checksum_of_received_firmware = sha512(firmware_data).digest().hex()
    elif checksum_alg.lower() == "md5":
        checksum_of_received_firmware = md5(firmware_data).digest().hex()
    elif checksum_alg.lower() == "murmur3_32":
        reversed_checksum = f'{hash(firmware_data, signed=False):0>2X}'
        if len(reversed_checksum) % 2 != 0:
            reversed_checksum = '0' + reversed_checksum
        checksum_of_received_firmware = "".join(reversed([reversed_checksum[i:i+2] for i in range(0, len(reversed_checksum), 2)])).lower()
    elif checksum_alg.lower() == "murmur3_128":
        reversed_checksum = f'{hash128(firmware_data, signed=False):0>2X}'
        if len(reversed_checksum) % 2 != 0:
            reversed_checksum = '0' + reversed_checksum
        checksum_of_received_firmware = "".join(reversed([reversed_checksum[i:i+2] for i in range(0, len(reversed_checksum), 2)])).lower()
    elif checksum_alg.lower() == "crc32":
        reversed_checksum = f'{crc32(firmware_data) & 0xffffffff:0>2X}'
        if len(reversed_checksum) % 2 != 0:
            reversed_checksum = '0' + reversed_checksum
        checksum_of_received_firmware = "".join(reversed([reversed_checksum[i:i+2] for i in range(0, len(reversed_checksum), 2)])).lower()
    else:
        logger.error(f"Unsupported checksum algorithm: {checksum_alg}")
        return False

    return checksum_of_received_firmware == checksum




class FirmwareClient(Client):
    def __init__(self, chunk_size = 0):
        super().__init__()
        self.on_connect = self.__on_connect
        self.on_message = self.__on_message
        self.__chunk_size = chunk_size

        self.__request_id = 0
        self.__firmware_request_id = 0

        self.current_firmware_info = {
            "current_" + FW_TITLE_ATTR: latest_firmware.title,
            "current_" + FW_VERSION_ATTR: latest_firmware.version,
            }
        self.firmware_data = b''
        self.__target_firmware_length = 0
        self.__chunk_count = 0
        self.__current_chunk = 0
        self.firmware_received = False
        self.__updating_thread = Thread(target=self.__update_thread, name="Updating thread")
        self.__updating_thread.daemon = True
        self.__updating_thread.start()

    def __on_connect(self, client, userdata, flags, result_code, *extra_params):
        logger.info(f"Connected with result code {result_code}")
        self.subscribe("v1/devices/me/attributes/response/+")
        self.subscribe("v1/devices/me/attributes")
        self.subscribe("v2/fw/response/+")
        self.subscribe("v2/sf/response/+")
        self.subscribe("v1/devices/me/rpc/request/+")
        self.send_telemetry(self.current_firmware_info)
        self.request_firmware_info()

    def __on_message(self, client, userdata, msg):
        update_response_pattern = "v2/fw/response/" + str(self.__firmware_request_id) + "/chunk/"
        if msg.topic.startswith("v1/devices/me/attributes"):

            self.firmware_info = loads(msg.payload)
            # print(f'Firmware info: {self.firmware_info}')
            #Firmware info: {'shared': {'fw_checksum': '73d0a58fc1100effd38329ec49334cf1acd7423c64cab0254f92e34260211e31', 'fw_size': 71728776, 'fw_title': 'payload', 'fw_checksum_algorithm': 'SHA256', 'fw_version': '3'}}

            if "/response/" in msg.topic:
                self.firmware_info = self.firmware_info.get("shared", {}) if isinstance(self.firmware_info, dict) else {}
            if (self.firmware_info.get(FW_VERSION_ATTR) is not None and self.firmware_info.get(FW_VERSION_ATTR) != self.current_firmware_info.get("current_" + FW_VERSION_ATTR)) or \
                    (self.firmware_info.get(FW_TITLE_ATTR) is not None and self.firmware_info.get(FW_TITLE_ATTR) != self.current_firmware_info.get("current_" + FW_TITLE_ATTR)):
                logger.info(f"New firmware info: {self.firmware_info}")
                self.firmware_data = b''
                self.__current_chunk = 0

                self.current_firmware_info[FW_STATE_ATTR] = "DOWNLOADING"
                self.send_telemetry(self.current_firmware_info)
                sleep(1)

                self.__firmware_request_id = self.__firmware_request_id + 1
                self.__target_firmware_length = self.firmware_info[FW_SIZE_ATTR]
                self.__chunk_count = 0 if not self.__chunk_size else ceil(self.firmware_info[FW_SIZE_ATTR]/self.__chunk_size)
                self.get_firmware()

        elif msg.topic.startswith(update_response_pattern):
            firmware_data = msg.payload

            self.firmware_data = self.firmware_data + firmware_data
            self.__current_chunk = self.__current_chunk + 1

            logger.info(f'Getting chunk with number: {self.__current_chunk}. Chunk size is : {self.__chunk_size} byte(s).')
            if len(self.firmware_data) == self.__target_firmware_length:
                self.process_firmware()

            else:
                # check the size should not exceed the target firmware length
                if len(self.firmware_data) > self.__target_firmware_length:
                    logger.error("Firmware data size exceeded the target firmware length!")
                    self.request_firmware_info()
                    return

                self.get_firmware()


        # rpc request
        elif msg.topic.startswith("v1/devices/me/rpc/request/"):
            rpc_request = loads(msg.payload)
            if rpc_request.get("method") == "getTelemetry":
                attributes, telemetry = get_data()
                self.send_attributes(attributes)
                self.send_telemetry(telemetry)

    def process_firmware(self):
        self.current_firmware_info[FW_STATE_ATTR] = "DOWNLOADED"
        self.send_telemetry(self.current_firmware_info)
        logger.info("Firmware downloaded!")
        sleep(1)

        verification_result = verify_checksum(self.firmware_data, self.firmware_info.get(FW_CHECKSUM_ALG_ATTR), self.firmware_info.get(FW_CHECKSUM_ATTR))

        if verification_result:
            logger.info("Checksum verification passed!")
            self.current_firmware_info[FW_STATE_ATTR] = "VERIFIED"
            self.send_telemetry(self.current_firmware_info)
            sleep(1)
        else:
            logger.error("Checksum verification failed!")
            self.current_firmware_info[FW_STATE_ATTR] = "FAILED"
            self.send_telemetry(self.current_firmware_info)
            self.request_firmware_info()
            return
        self.firmware_received = True


    def get_firmware(self):
        payload = '' if not self.__chunk_size or self.__chunk_size > self.firmware_info.get(FW_SIZE_ATTR, 0) else str(self.__chunk_size).encode()
        self.publish(f"v2/fw/request/{self.__firmware_request_id}/chunk/{self.__current_chunk}", payload=payload, qos=1)

    def send_telemetry(self, telemetry):
        return self.publish("v1/devices/me/telemetry", dumps(telemetry), qos=1)

    def send_attributes(self, attributes):
        return self.publish("v1/devices/me/attributes", dumps(attributes), qos=1)
    def request_firmware_info(self):
        logger.info("Requesting firmware info...")
        self.__request_id = self.__request_id + 1
        self.publish(f"v1/devices/me/attributes/request/{self.__request_id}", dumps({"sharedKeys": REQUIRED_SHARED_KEYS}))

    def __update_thread(self):
        while True:
            if self.firmware_received:
                self.current_firmware_info[FW_STATE_ATTR] = "UPDATING"
                self.send_telemetry(self.current_firmware_info)
                sleep(1)

                path_to_save = path.join(path.dirname(__file__), "firmware")
                if not path.exists(path_to_save):
                    mkdir(path_to_save)

                firmware_name = self.firmware_info.get(FW_TITLE_ATTR) + "_" + self.firmware_info.get(FW_VERSION_ATTR) + ".tar.xz"

                with open(path.join(path_to_save, firmware_name), "wb") as firmware_file:
                    firmware_file.write(self.firmware_data)

                #give file permissions
                chmod(path.join(path_to_save, firmware_name), 0o777)

                #extract the tar.xz file
                tar = TarFile.open(path.join(path_to_save, firmware_name))
                tar.extractall(f"{path_to_save}/{self.firmware_info.get(FW_TITLE_ATTR)}_{self.firmware_info.get(FW_VERSION_ATTR)}")
                tar.close()
                remove(path.join(path_to_save, firmware_name))

                firmware_list = os.listdir(f"{path_to_save}")

                #leave only the latest 2 firmware versions
                # payload_1, payload_2, payload_3
                try:
                    if len(firmware_list) > 2:
                        firmware_list.sort()
                        for firmware in firmware_list[:-2]:
                            logger.info(f"Removing firmware: {firmware}")
                            os.system(f"rm -r {path_to_save}/{firmware}")

                except Exception as e:
                    logger.error(f"Error: {e}")

                path_to_firmware = f"{path_to_save}/{self.firmware_info.get(FW_TITLE_ATTR)}_{self.firmware_info.get(FW_VERSION_ATTR)}"

                try:
                    upgrade_firmware(latest_firmware, self.firmware_info, path_to_firmware)
                except Exception as e:
                    logger.error(f"Error: {e}")
                self.current_firmware_info = {
                    "current_" + FW_TITLE_ATTR: self.firmware_info.get(FW_TITLE_ATTR),
                    "current_" + FW_VERSION_ATTR: self.firmware_info.get(FW_VERSION_ATTR),
                    FW_STATE_ATTR: "UPDATED"
                }
                self.send_telemetry(self.current_firmware_info)
                self.firmware_received = False
                logger.info("Firmware updated!")
                sleep(1)


if __name__ == '__main__':
    config = collect_required_data()

    client = FirmwareClient(config["chunk_size"])
    client.username_pw_set(config["token"])
    client.connect(config["host"], config["port"])
    client.loop_forever()