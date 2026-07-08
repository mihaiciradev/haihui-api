from app.core.security import generate_opaque_token, hash_opaque_token, hash_secret, verify_secret
from app.core.totp import generate_totp_secret, verify_totp


def test_password_hash_roundtrip():
    hashed = hash_secret("correct-horse")
    assert verify_secret("correct-horse", hashed)
    assert not verify_secret("wrong", hashed)


def test_opaque_token_is_high_entropy_and_hash_is_deterministic():
    raw, hashed = generate_opaque_token()
    assert len(raw) >= 32
    assert hash_opaque_token(raw) == hashed
    raw2, hashed2 = generate_opaque_token()
    assert raw != raw2
    assert hashed != hashed2


def test_totp_accepts_valid_code_rejects_bogus():
    import pyotp

    secret = generate_totp_secret()
    assert verify_totp(secret, pyotp.TOTP(secret).now())
    assert not verify_totp(secret, "000000")
