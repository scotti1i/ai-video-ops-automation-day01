"""稳定前缀的人类可辨内部编号。"""

from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"
