import hashlib
import json


def checksum(snapshot):
    """冻结快照的规范 SHA256：键排序、保留中文，提交与校验共用。"""
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
