import bcrypt

def hash_password(plain_password: str) -> str:
    """
    Хэшируем пароль и возвращаем строковый результат.
    """
    salt = bcrypt.gensalt()  # по умолчанию cost=12
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Сравниваем plaintext с хэшем.
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"),
                          hashed_password.encode("utf-8"))
