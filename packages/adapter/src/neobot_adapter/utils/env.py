import os

def get_websocket_url():
    return 'ws://'+str(os.getenv("NEO_BOT_ADAPTER_HOST"))+':'+str(os.getenv("NEO_BOT_ADAPTER_PORT"))

def get_websocket_host():
    return str(os.getenv("NEO_BOT_ADAPTER_HOST"))

def get_websocket_port():
    return str(os.getenv("NEO_BOT_ADAPTER_PORT"))