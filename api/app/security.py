import base64
import hashlib
import hmac
import json
import os
import struct
import time


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text):
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_password(password, salt=None, iterations=200000):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "%s$%s$%d" % (base64.b64encode(salt).decode(), base64.b64encode(digest).decode(), iterations)


def verify_password(password, stored):
    salt_b64, digest_b64, iterations = stored.split("$")
    salt = base64.b64decode(salt_b64)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(expected, base64.b64decode(digest_b64))


def make_token(sub, role, secret, ttl_minutes=15):
    now = int(time.time())
    payload = {"sub": sub, "role": role, "iat": now, "exp": now + ttl_minutes * 60}
    body = b64url(json.dumps(payload, separators=(",", ":")).encode())
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    signing = ("%s.%s" % (header, body)).encode()
    sig = hmac.new(secret.encode(), signing, hashlib.sha256).digest()
    return "%s.%s.%s" % (header, body, b64url(sig))


def read_token(token, secret):
    try:
        header, body, sig = token.split(".")
        signing = ("%s.%s" % (header, body)).encode()
        expected = hmac.new(secret.encode(), signing, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, b64url_decode(sig)):
            return None
        payload = json.loads(b64url_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def totp_code(secret, at=None, step=30, digits=6):
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = int((at or time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(value).zfill(digits)


def verify_totp(secret, code, window=1):
    now = time.time()
    return any(hmac.compare_digest(totp_code(secret, now + w * 30), str(code).strip()) for w in range(-window, window + 1))
