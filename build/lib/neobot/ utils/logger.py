from loguru import logger

def get_module_logger(
        module_name: str
)-> LoguruLogger:
    return logger.bind(module=module_name)