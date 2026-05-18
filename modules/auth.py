from py5paisa import FivePaisaClient
import uuid
import os
import json
from dotenv import load_dotenv

load_dotenv()

cred = {
    "APP_NAME":       os.getenv("APP_NAME",       "5P58004979"),
    "APP_SOURCE":     os.getenv("APP_SOURCE",      "24930"),
    "USER_ID":        os.getenv("USER_ID",         "47xt4VnND2x"),
    "PASSWORD":       os.getenv("PASSWORD",        "B356hBPBrAK"),
    "USER_KEY":       os.getenv("USER_KEY",        "PyA72PuyUjYUiNavyRlN0bdLnc7aFeKp"),
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY",  "wnzELKnWbdH3KYdgAyW0EwLdVpnk2O1D")
}

authenticated_clients = {}

# Persist session so app restarts don't force re-login
SESSION_FILE = os.path.join(os.path.dirname(__file__), '..', '.5paisa_session.json')


def _save_session(client):
    """Save JWT + client_code to disk after successful login."""
    try:
        jwt = (getattr(client, 'access_token', None) or
               getattr(client, 'Jwt_token',    None))
        data = {
            "jwt":         jwt,
            "client_code": getattr(client, 'client_code', None),
        }
        if data["jwt"]:
            with open(SESSION_FILE, 'w') as f:
                json.dump(data, f)
    except Exception:
        pass


def _restore_client():
    """Recreate a FivePaisaClient from saved JWT. Returns client or None."""
    try:
        if not os.path.exists(SESSION_FILE):
            return None
        with open(SESSION_FILE) as f:
            data = json.load(f)
        jwt = data.get("jwt")
        if not jwt:
            return None
        c = FivePaisaClient(cred=cred)
        c.Jwt_token    = jwt
        c.access_token = jwt
        c.client_code  = data.get("client_code", "")
        try:
            c.set_access_token(jwt)
        except Exception:
            pass
        # Quick test — fetch SENSEX LTP to validate token
        result = c.fetch_market_feed([{"Exch": "B", "ExchangeType": "C", "ScripCode": 999901}])
        if result is not None:
            return c
    except Exception:
        pass
    return None


def try_restore_session():
    """
    Try to restore a previous session.
    Returns client_id (str) if successful, None otherwise.
    Stores the client in authenticated_clients.
    """
    client = _restore_client()
    if client:
        client_id = str(uuid.uuid4())
        authenticated_clients[client_id] = client
        return client_id
    return None


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
        _save_session(c)          # persist for future restarts
        client_id = str(uuid.uuid4())
        authenticated_clients[client_id] = c
        return {"success": True, "client_id": client_id}
    except Exception as e:
        return {"success": False, "error": f"Auth failed: {str(e)}"}
