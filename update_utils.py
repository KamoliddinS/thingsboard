
from time import sleep
from threading import Thread
from json import dumps, loads
from zlib import crc32
from hashlib import sha256, sha384, sha512, md5
from mmh3 import hash, hash128
from math import ceil



def upgrade_firmware(version_from, version_to):
    print(f"Updating from {version_from} to {version_to}:")
    for x in range(5):
        sleep(1)
        print(20*(x+1),"%", sep="")
    print(f"Firmware is updated!\n Current firmware version is: {version_to}")
