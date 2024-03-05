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

from database.db_firmware import create as create_firmware, get_all as get_all_firmware, get_by_id as get_firmware_by_id
from database.db_update import create as create_update, get_all as get_all_update, get_by_id as get_update_by_id
from database.db_credential import create as create_credential, get_only_one
from database import models
from database.database import SessionLocal, engine
from database.database import get_db

client = get_db().__next__()
models.Base.metadata.create_all(bind=engine)


latest_firmware = get_all_firmware(client)

device_credential = get_only_one(client)

if device_credential is not None:
    print(device_credential.device_id)

    print(device_credential.device_mac_address)
    print(device_credential.device_serial_number)
    print(device_credential.server_url)
    print(device_credential.server_username)
    print(device_credential.server_password)
    print(device_credential.thingsboard_url)
    print(device_credential.thingsboard_port)
    print(device_credential.thingsboard_access_token)

print(device_credential)


FW_CHECKSUM_ATTR = "fw_checksum"
FW_CHECKSUM_ALG_ATTR = "fw_checksum_algorithm"
FW_SIZE_ATTR = "fw_size"
FW_TITLE_ATTR = "fw_title"
FW_VERSION_ATTR = "fw_version"

FW_STATE_ATTR = "fw_state"

REQUIRED_SHARED_KEYS = f"{FW_CHECKSUM_ATTR},{FW_CHECKSUM_ALG_ATTR},{FW_SIZE_ATTR},{FW_TITLE_ATTR},{FW_VERSION_ATTR}"


def collect_required_data():
    config = {}
    print("\n\n", "="*80, sep="")
    print(" "*20, "ThingsBoard getting firmware example script.", sep="")
    print("="*80, "\n\n", sep="")
    # host = "tb.cradle-vision.com"
    config["host"] = device_credential.thingsboard_url
    # host = 1883
    config["port"] = device_credential.thingsboard_port
    # token = "TBRHy3jdRsDIJWoRRJmD"
    config["token"] = device_credential.thingsboard_access_token
    chunk_size =65735
    config["chunk_size"] = int(chunk_size) if chunk_size else 0
    print("\n", "="*80, "\n", sep="")
    return config


def verify_checksum(firmware_data, checksum_alg, checksum):
    if firmware_data is None:
        print("Firmware wasn't received!")
        return False
    if checksum is None:
        print("Checksum was't provided!")
        return False
    checksum_of_received_firmware = None
    print(f"Checksum algorithm is: {checksum_alg}")
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
        print("Client error. Unsupported checksum algorithm.")
    print(checksum_of_received_firmware)
    random_value = randint(0, 5)
    # if random_value > 3:
    #     print("Dummy fail! Do not panic, just restart and try again the chance of this fail is ~20%")
    #     return False
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
            "current_" + FW_TITLE_ATTR: "Initial",
            "current_" + FW_VERSION_ATTR: "v0"
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
        print(f"Requesting firmware info from {config['host']}:{config['port']}..")
        self.subscribe("v1/devices/me/attributes/response/+")
        self.subscribe("v1/devices/me/attributes")
        self.subscribe("v2/fw/response/+")
        self.subscribe("v2/sf/response/+")
        self.subscribe("v1/devices/me/rpc/request/+")
        self.send_telemetry(self.current_firmware_info)
        self.request_firmware_info()

    def __on_message(self, client, userdata, msg):
        update_response_pattern = "v2/fw/response/" + str(self.__firmware_request_id) + "/chunk/"
        print(f"Received message from {msg.topic}: {msg.payload}")
        if msg.topic.startswith("v1/devices/me/attributes"):
            print("Firmware info received!")
            self.firmware_info = loads(msg.payload)
            if "/response/" in msg.topic:
                self.firmware_info = self.firmware_info.get("shared", {}) if isinstance(self.firmware_info, dict) else {}
            if (self.firmware_info.get(FW_VERSION_ATTR) is not None and self.firmware_info.get(FW_VERSION_ATTR) != self.current_firmware_info.get("current_" + FW_VERSION_ATTR)) or \
                    (self.firmware_info.get(FW_TITLE_ATTR) is not None and self.firmware_info.get(FW_TITLE_ATTR) != self.current_firmware_info.get("current_" + FW_TITLE_ATTR)):
                print("Firmware is not the same")
                self.firmware_data = b''
                self.__current_chunk = 0

                self.current_firmware_info[FW_STATE_ATTR] = "DOWNLOADING"
                self.send_telemetry(self.current_firmware_info)
                sleep(1)

                self.__firmware_request_id = self.__firmware_request_id + 1
                self.__target_firmware_length = self.firmware_info[FW_SIZE_ATTR]
                self.__chunk_count = 0 if not self.__chunk_size else ceil(self.firmware_info[FW_SIZE_ATTR]/self.__chunk_size)
                self.get_firmware()
                print(self.current_firmware_info)
        elif msg.topic.startswith(update_response_pattern):
            firmware_data = msg.payload

            self.firmware_data = self.firmware_data + firmware_data
            self.__current_chunk = self.__current_chunk + 1

            print(f'Getting chunk with number: {self.__current_chunk}. Chunk size is : {self.__chunk_size} byte(s).')

            if len(self.firmware_data) == self.__target_firmware_length:
                self.process_firmware()

            else:
                self.get_firmware()


        # dev line

        # rpc request
        elif msg.topic.startswith("v1/devices/me/rpc/request/"):
            print("RPC request received!")
            rpc_request = loads(msg.payload)
            if rpc_request.get("method") == "getTelemetry":
                print("Sending telemetry..")
                attributes, telemetry = get_data()
                self.send_attributes(attributes)
                self.send_telemetry(telemetry)

    def process_firmware(self):
        self.current_firmware_info[FW_STATE_ATTR] = "DOWNLOADED"
        self.send_telemetry(self.current_firmware_info)
        print(self.current_firmware_info)
        sleep(1)

        verification_result = verify_checksum(self.firmware_data, self.firmware_info.get(FW_CHECKSUM_ALG_ATTR), self.firmware_info.get(FW_CHECKSUM_ATTR))

        if verification_result:
            print("Checksum verified!")
            self.current_firmware_info[FW_STATE_ATTR] = "VERIFIED"
            self.send_telemetry(self.current_firmware_info)
            sleep(1)
        else:
            print("Checksum verification failed!")
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
        print("Requesting firmware info..")
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
                if len(firmware_list) > 2:
                    firmware_list.sort()
                    for i in range(len(firmware_list) - 2):
                        remove(f"{path_to_save}/{firmware_list[i]}")

                path_to_firmware = f"{path_to_save}/{self.firmware_info.get(FW_TITLE_ATTR)}_{self.firmware_info.get(FW_VERSION_ATTR)}"
                upgrade_firmware(self.current_firmware_info["current_" + FW_VERSION_ATTR], self.firmware_info.get(FW_VERSION_ATTR), path_to_firmware)

                self.current_firmware_info = {
                    "current_" + FW_TITLE_ATTR: self.firmware_info.get(FW_TITLE_ATTR),
                    "current_" + FW_VERSION_ATTR: self.firmware_info.get(FW_VERSION_ATTR),
                    FW_STATE_ATTR: "UPDATED"
                }
                self.send_telemetry(self.current_firmware_info)
                self.firmware_received = False
                sleep(1)


if __name__ == '__main__':
    config = collect_required_data()

    client = FirmwareClient(config["chunk_size"])
    client.username_pw_set(config["token"])
    client.connect(config["host"], config["port"])
    client.loop_forever()