from collections.abc import Iterator

from minio import Minio


class ObjectStore:
    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class MemoryStore(ObjectStore):
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        return self.objects[key][0]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class MinioStore(ObjectStore):
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool) -> None:
        self.bucket = bucket
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        import io

        self.client.put_object(self.bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, key: str) -> None:
        self.client.remove_object(self.bucket, key)


def iter_chunks(chunks: Iterator[bytes]) -> bytes:
    return b"".join(chunks)
