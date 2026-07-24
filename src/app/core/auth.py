from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:

    return password_hasher.hash(plain_password)


def verify_password(plain_pass: str, hashed_pass: str) -> bool:

    return password_hasher.verify(plain_pass, hashed_pass)
