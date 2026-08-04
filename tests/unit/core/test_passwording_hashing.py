from src.app.core.auth import hash_password, verify_password


def test_hash_password_returns_hashed_str():

    password = "secret_password"

    hash = hash_password(password)

    assert hash != password


def test_verify_correct_password():

    password = "secret_password"

    hash = hash_password(password)

    assert verify_password(password, hash) is True


def test_verify_password_with_incorrect_password():

    password = "secret_password"

    hash = hash_password(password)

    submitted_pass = "public_password"

    assert verify_password(submitted_pass, hash) is False


def test_unique_hash():

    password = "secret_password"

    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != hash2
