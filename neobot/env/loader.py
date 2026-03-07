import os
import pathlib
import shutil
from os import system
import sys
from dotenv import load_dotenv
from neobot.utils.logger import get_module_logger

logger = get_module_logger("env_loader")

env_spec = {
    "HOST":{
        "required":True,"description":"监听主机地址"
    },
    "PORT":{
        "required":True,"description":"监听端口"
    },
}

def load_env()-> dict:
    env_path = pathlib.Path("../../.env")
    if not check_file(env_path):
        if not check_file("../../templates/temp_.env"):
            logger.error("未找到配置文件")
            sys.exit(1)
        else:
            logger.info("未找到配置文件,已创建默认配置文件")
            shutil.copyfile("../../templates/temp_.env", "../../.env")
    else:
        logger.info("已找到配置文件,尝试读取")
        load_dotenv(env_path,override= True)
        env = {}
        missing_required = []

        for key, spec in env_spec.items():
            # 从环境变量读取
            value = os.getenv(key)

            #检查必须项
            if env_spec[key]["required"] and value is None:
                logger.error(f"必须环境变量{key}未设置")
                missing_required.append(key)
                continue

            # 处理可选项缺失：使用默认值
            if value is None:
                value = spec.get("default")
                # 如果既不是必须项又没有默认值，设为 None（可根据需要调整）
                if value is None:
                    env[key] = None
                    continue
            # 类型转换（如果指定了 type）
            if "type" in spec and value is not None:
                try:
                    if spec["type"] == bool:
                        # 处理布尔值：字符串 'true'/'false' 或 '1'/'0'
                        if isinstance(value, str):
                            value = value.lower() in ('true', '1', 'yes')
                        else:
                            value = bool(value)
                    else:
                        value = spec["type"](value)
                except (ValueError, TypeError) as e:
                    logger.error(f"配置项 {key} 的值 '{value}' 无法转换为 {spec['type'].__name__}: {e}")

            env[key] =  value

        if missing_required:
            logger.error(f"缺少必填项：{', '.join(missing_required)}")
            sys.exit(1)
    logger.info("env文件读取成功")
    return  env

def check_file(file_path) -> bool:
    if not pathlib.Path(file_path).exists():
        return False
    return True

env = load_env()
logger.debug(env)