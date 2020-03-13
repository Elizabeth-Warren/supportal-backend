import json
import os
import time
import uuid

import jwt
from django.conf import settings
from jwt.algorithms import RSAAlgorithm

# RSA key pair copied from pyjwt test:
# https://github.com/jpadilla/pyjwt/tree/master/tests/keys

with open(
    os.path.join(settings.BASE_DIR, "supportal", "tests", "jwk_rsa_private_key.json")
) as f:
    JWK_PRIVATE_KEY = json.load(f)


def auth_header(token):
    return b"Bearer " + token


def create_id_jwt(user, expires_in_seconds=3600, key_id=None):
    """Create a Cognito id token for a User"""
    now_unix_ts = int(time.time())
    return _create_jwt(
        {
            "token_use": "id",
            "iss": settings.COGNITO_USER_POOL_URL,
            "sub": user.username,
            "aud": settings.COGNITO_USER_LOGIN_CLIENT_ID,
            "event_id": str(uuid.uuid4()),
            "auth_time": now_unix_ts,
            "iat": now_unix_ts,
            "exp": now_unix_ts + expires_in_seconds,
            "email_verified": True,
            "email": user.email,
            "cognito:username": user.username,
        },
        key_id=key_id,
    )


def create_access_jwt(client_id, expires_in_seconds=3600):
    """Create a Cognito access token for a superuser"""
    now_unix_ts = int(time.time())
    return _create_jwt(
        {
            "token_use": "access",
            "iss": settings.COGNITO_USER_POOL_URL,
            "sub": client_id,
            "event_id": str(uuid.uuid4()),
            "auth_time": now_unix_ts,
            "iat": now_unix_ts,
            "exp": now_unix_ts + expires_in_seconds,
            "client_id": client_id,
        }
    )


def _create_jwt(payload, key_id=None):
    if key_id is None:
        key_id = JWK_PRIVATE_KEY["kid"]

    key = json.dumps(JWK_PRIVATE_KEY)
    secret = RSAAlgorithm.from_jwk(key)
    return jwt.encode(
        payload, secret, algorithm="RS256", headers={"kid": key_id, "alg": "RS256"}
    )


def id_auth(user):
    return {"HTTP_AUTHORIZATION": auth_header(create_id_jwt(user))}
