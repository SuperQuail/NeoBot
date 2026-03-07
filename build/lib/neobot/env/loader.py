import pathlib
import shutil
from os import system
import sys
from neobot.utils.logger import get_module_logger

logger = get_module_logger("env_loader")

env_spec = {
    "Host":{
        "required":True,"description":"监听主机地址"
    },
    "Port":{
        "required":True,"description":"监听端口"
    },
}

def load_config()-> dict:
    if not check_file("../../.env"):
        if not check_file("../../templates/temp_.env"):
            logger.error("未找到配置文件")
            sys.exit(1)

def check_file(file_path) -> bool:
    if not pathlib.Path(file_path).exists():
        return False
    return True

config = load_config()