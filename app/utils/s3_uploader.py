# app/utils/s3_uploader.py
import io, os, uuid, boto3, mimetypes
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app
from werkzeug.utils import secure_filename

from PIL import Image
try:
    import pillow_heif              # pip install pillow-heif==0.13.0
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None              # HEIC 未対応環境でもロードエラーを防ぐ

__all__ = ["upload_file_to_s3", "build_s3_url", "convert_heic_to_jpeg"]  # ← 追加

# ──────────────────────────────────────────
# 内部: S3 クライアント
# ──────────────────────────────────────────
def _build_s3_client() -> boto3.client:
    region = current_app.config.get("AWS_REGION", os.getenv("AWS_REGION", "ap-northeast-1"))
    access_key = current_app.config.get("AWS_ACCESS_KEY_ID")
    secret_key = current_app.config.get("AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        return boto3.client("s3", region_name=region,
                            aws_access_key_id=access_key,
                            aws_secret_access_key=secret_key)
    return boto3.client("s3", region_name=region)

# ──────────────────────────────────────────
# **公開** HEIC→JPEG 変換関数  ← 名前を先頭に _ 付けない
# ──────────────────────────────────────────
def convert_heic_to_jpeg(filestorage) -> tuple[io.BytesIO, str]:
    """FileStorage (HEIC/HEIF) → BytesIO(JPEG), ext='.jpg'"""
    if not pillow_heif:
        raise RuntimeError("pillow-heif がインストールされていません")

    filestorage.seek(0)
    src_bytes = filestorage.read()

    heif = pillow_heif.read_heif(src_bytes)
    img  = Image.frombytes(heif.mode, heif.size, heif.data, "raw")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    buf.seek(0)
    return buf, ".jpg"

# ──────────────────────────────────────────
# アップロード
# ──────────────────────────────────────────
def upload_file_to_s3(file_obj, *, folder="materials") -> str:
    s3     = _build_s3_client()
    bucket = current_app.config["S3_BUCKET"]

    safe_name = secure_filename(file_obj.filename or "upload")
    ext = os.path.splitext(safe_name)[1].lower()

    # HEIC/HEIF → JPEG
    if ext in (".heic", ".heif"):
        file_obj, ext = convert_heic_to_jpeg(file_obj)  # BytesIO
        file_obj.filename = f"{uuid.uuid4().hex}.jpg"
        mime = "image/jpeg"
    else:
        file_obj.seek(0)
        mime = file_obj.mimetype or mimetypes.types_map.get(ext, "application/octet-stream")

    key = f"{folder}/{uuid.uuid4().hex}{ext}"
    try:
        s3.upload_fileobj(file_obj, bucket, key, ExtraArgs={"ContentType": mime})
    except (BotoCoreError, ClientError):
        current_app.logger.exception("S3 upload failed")
        raise RuntimeError("S3 upload failed")

    return key

# ──────────────────────────────────────────
# URL 組み立て
# ──────────────────────────────────────────
def build_s3_url(key: str) -> str:
    if not key:
        return ""
    bucket = current_app.config["S3_BUCKET"]
    region = current_app.config.get("AWS_REGION", "ap-northeast-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
