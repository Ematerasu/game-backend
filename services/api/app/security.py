import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Header, status
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-default")
JWT_ALG = "HS256"
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "120"))

bearer = HTTPBearer(auto_error=False)

def create_access_token(sub: str, roles: list[str] = ["player"]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TTL_MIN)).timestamp())
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def parse_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    

def get_current_player(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    payload = parse_token(creds.credentials)
    if "player" not in payload.get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a player token")
    return payload["sub"]


def require_app_key(x_api_key: str | None = None):
    expected = os.getenv("APP_API_KEY")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    
async def check_api_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != os.getenv("API_KEY", "dev"):
        raise HTTPException(status_code=401, detail="invalid api key")
