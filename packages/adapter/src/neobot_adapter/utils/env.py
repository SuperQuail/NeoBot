import os

def get_websocket_url():
    return 'ws://'+str(os.getenv("NEO_BOT_ADAPTER_HOST"))+':'+str(os.getenv("NEO_BOT_ADAPTER_PORT"))