"""TOTP/MFA do SuperAdmin + rate limit de login por IP."""
import base64
import hashlib
import hmac
import struct
import time

from app.local_identity import generate_totp_secret, _totp, verify_totp


def _code(secret: str, at: int | None = None) -> str:
    key = base64.b32decode(secret)
    counter = int((at or time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    n = struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF
    return f"{n % 1_000_000:06d}"


def test_totp_aceita_codigo_atual_e_vizinho():
    secret = generate_totp_secret()
    now = int(time.time() // 30) * 30
    assert verify_totp(secret, _code(secret, now))
    assert verify_totp(secret, _code(secret, now - 30))   # janela anterior
    assert not verify_totp(secret, _code(secret, now + 90))  # fora da janela
    assert not verify_totp(secret, "000000") or _code(secret, now) == "000000"


def test_verify_totp_segredo_invalido_nao_quebra():
    assert verify_totp("!!!", "123456") is False
    assert verify_totp("JBSWY3DPEHPK3PXP", "abc") is False
