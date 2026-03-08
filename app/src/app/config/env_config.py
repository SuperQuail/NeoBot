from typing import Optional

class env_config:
    # Adapter 配置
    HOST = {'value': '127.0.0.1', 'type': Optional[str], 'description': "Adapter 连接的主机地址"}
    PORT = {'value': 8080, 'type': Optional[int], 'description': "Adapter 连接的端口号"}
