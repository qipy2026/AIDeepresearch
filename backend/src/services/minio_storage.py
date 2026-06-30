"""MinIO 对象存储：上传文件持久化。"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Optional

from minio import Minio

_client: Optional[Minio] = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        _client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    return _client


def _get_bucket() -> str:
    return os.getenv("MINIO_BUCKET", "enterprise-docs")


def ensure_bucket() -> None:
    """确保存储桶存在。"""
    client = _get_client()
    bucket = _get_bucket()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def upload_file(file_path: str, object_name: Optional[str] = None) -> str:
    """上传本地文件到 MinIO，返回 object_name。"""
    client = _get_client()
    bucket = _get_bucket()
    ensure_bucket()
    obj = object_name or Path(file_path).name
    client.fput_object(bucket, obj, file_path)
    return obj


def upload_bytes(data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
    """上传字节数据到 MinIO，返回 object_name。"""
    client = _get_client()
    bucket = _get_bucket()
    ensure_bucket()
    client.put_object(bucket, object_name, BytesIO(data), length=len(data), content_type=content_type)
    return object_name


def download_file(object_name: str, file_path: str) -> str:
    """从 MinIO 下载文件到本地。"""
    client = _get_client()
    bucket = _get_bucket()
    client.fget_object(bucket, object_name, file_path)
    return file_path


def list_objects(prefix: str = "") -> list[str]:
    """列出存储桶中的文件。"""
    client = _get_client()
    bucket = _get_bucket()
    try:
        objects = client.list_objects(bucket, prefix=prefix, recursive=True)
        return [o.object_name for o in objects]
    except Exception:
        return []


def delete_object(object_name: str) -> None:
    """删除存储桶中的文件。"""
    client = _get_client()
    bucket = _get_bucket()
    try:
        client.remove_object(bucket, object_name)
    except Exception:
        pass
