"""密码哈希与 JWT 工具。

commit 1 只用到密码哈希（bootstrap admin）；commit 2 会扩展 JWT 与依赖注入。
"""

import bcrypt

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    # bcrypt 限制密码 72 字节，超长截断（与业界主流实现一致）
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
