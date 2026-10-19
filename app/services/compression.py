"""
Q17 Feature 1: Asset Compression
Preserved from original compression.py – compresses descriptions and cover
images before storage, decompresses only on demand.
"""
import zlib
from io import BytesIO
from PIL import Image


def compress_text(text: str, level: int = 6) -> bytes:
    if text is None:
        text = ''
    return zlib.compress(text.encode('utf-8'), level)


def decompress_text(blob: bytes) -> str:
    if not blob:
        return ''
    return zlib.decompress(blob).decode('utf-8')


def compress_bytes(data: bytes, level: int = 6) -> bytes:
    if not data:
        return b''
    return zlib.compress(data, level)


def decompress_bytes(blob: bytes) -> bytes:
    if not blob:
        return b''
    return zlib.decompress(blob)


def compression_stats(raw_size: int, compressed_size: int) -> dict:
    if raw_size == 0:
        return {'raw_bytes': 0, 'compressed_bytes': 0, 'saved_bytes': 0, 'saved_pct': 0.0}
    saved = raw_size - compressed_size
    return {
        'raw_bytes': raw_size,
        'compressed_bytes': compressed_size,
        'saved_bytes': saved,
        'saved_pct': round((saved / raw_size) * 100, 1),
    }


def process_cover_image(file_storage, max_dim: int = 800, quality: int = 85, max_mb: int = 10) -> tuple:
    """
    Validate, resize, and compress a cover image upload.
    Returns (compressed_bytes, raw_size) or raises ValueError.
    """
    ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    content_type = file_storage.content_type or ''
    if content_type not in ALLOWED_MIME:
        raise ValueError(f'Unsupported image type: {content_type}. Use JPEG, PNG, GIF, or WebP.')

    raw_data = file_storage.read()
    raw_size = len(raw_data)
    if raw_size == 0:
        raise ValueError('Empty file uploaded.')
    if raw_size > max_mb * 1024 * 1024:
        raise ValueError(f'That image is {raw_size / 1024 / 1024:.1f} MB. The limit is {max_mb} MB '
                         '(an admin can change it under Settings).')

    try:
        img = Image.open(BytesIO(raw_data))
        img.load()      # decode now so a truncated or fake file fails here, not later
    except (OSError, ValueError, Image.DecompressionBombError):
        # content_type comes from the browser and can be faked; Pillow is the real check
        raise ValueError('That file is not a valid image. Use a JPEG, PNG, GIF, or WebP file.')
    # Resize if needed
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    # Convert to RGB for JPEG
    if img.mode in ('RGBA', 'P', 'LA'):
        img = img.convert('RGB')

    buf = BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    processed = buf.getvalue()

    compressed = compress_bytes(processed)
    return compressed, len(processed)
