from py5paisa import FivePaisaClient
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

cred = {
    "APP_NAME": os.getenv("APP_NAME", "5P58004979"),
    "APP_SOURCE": os.getenv("APP_SOURCE", "24930"),
    "USER_ID": os.getenv("USER_ID", "47xt4VnND2x"),
    "PASSWORD": os.getenv("PASSWORD", "B356hBPBrAK"),
    "USER_KEY": os.getenv("USER_KEY", "PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp"),
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", "wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D")
}

authenticated_clients = {}


def process_callback(args):
    request_token = (
        args.get('RequestToken') or
        args.get('requestToken') or
        args.get('request_token')
    )
    if not request_token:
        return {"success": False, "error": f"No token received. Got params: {dict(args)}"}
    try:
        c = FivePaisaClient(cred=cred)
        c.get_oauth_session(request_token)
        client_id = str(uuid.uuid4())
        authenticated_clients[client_id] = c
        return {"success": True, "client_id": client_id}
    except Exception as e:
        return {"success": False, "error": f"Auth failed: {str(e)}"}
