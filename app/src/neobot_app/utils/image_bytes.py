"""图片字节的轻量校验（不依赖 Pillow）。"""

from __future__ import annotations

#: 常见图片格式的魔数前缀
IMAGE_MAGIC_PREFIXES = (
    b"\xff\xd8\xff",        # JPEG
    b"\x89PNG\r\n\x1a\n",   # PNG
    b"RIFF",                # WebP（RIFF 容器，需再校验 WEBP 标识）
    b"GIF87a",              # GIF
    b"GIF89a",              # GIF
    b"BM",                  # BMP
)

_MIN_IMAGE_BYTES = 16


def looks_like_image(content: bytes) -> bool:
    """按文件头魔数判断字节内容是否像图片。

    用于「读取本地文件」这类边界：内容形态校验可以挡住把配置/密钥/数据库
    当作图片读出来的路径，且不引入 Pillow 解码开销。
    """
    if len(content) < _MIN_IMAGE_BYTES:
        return False
    if content.startswith(b"RIFF"):
        return len(content) >= 12 and content[8:12] == b"WEBP"
    return any(content.startswith(magic) for magic in IMAGE_MAGIC_PREFIXES)
