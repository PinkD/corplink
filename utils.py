from hashlib import md5


def device_id_from_name(id: str) -> str:
    return md5(id.encode()).hexdigest()
