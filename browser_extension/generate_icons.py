#!/usr/bin/env python3
"""生成浏览器扩展所需的 PNG 图标（16x16, 48x48, 128x128）。无需第三方库。"""
import struct
import zlib
import os


def make_png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    chunk = chunk_type + data
    crc = zlib.crc32(chunk) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)


def create_solid_png(width: int, height: int, r: int, g: int, b: int) -> bytes:
    sig = b'\x89PNG\r\n\x1a\n'

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = make_png_chunk(b'IHDR', ihdr_data)

    raw = b''
    for _ in range(height):
        raw += b'\x00'
        raw += bytes([r, g, b]) * width

    compressed = zlib.compress(raw)
    idat = make_png_chunk(b'IDAT', compressed)
    iend = make_png_chunk(b'IEND', b'')

    return sig + ihdr + idat + iend


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icons_dir = os.path.join(base_dir, 'icons')
    os.makedirs(icons_dir, exist_ok=True)

    # 蓝紫色主题 #6a4a8a
    sizes = [16, 48, 128]
    for size in sizes:
        data = create_solid_png(size, size, 106, 74, 138)
        path = os.path.join(icons_dir, f'icon{size}.png')
        with open(path, 'wb') as f:
            f.write(data)
        print(f'  {path}')

    print('图标生成完成')


if __name__ == '__main__':
    main()
