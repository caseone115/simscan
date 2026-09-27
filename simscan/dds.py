"""DDS -> PNG for Sims 4 artwork.

Sims 4 stores images as standard DDS containers but with Sims-specific
FOURCC codes (DST1/DST3/DST5). These map onto the standard DXT1/DXT3/DXT5
block formats, which we decode by hand because Pillow rejects the renamed
FOURCC.

Only the first (largest) mip level is decoded - that is all a UI needs.
"""
import struct

FOURCC_TO_DXT = {
    b"DXT1": "DXT1", b"DXT3": "DXT3", b"DXT5": "DXT5",
    b"DST1": "DXT1", b"DST3": "DXT3", b"DST5": "DXT5",
    b"ATI1": "ATI1", b"ATI2": "ATI2",
}

DDS_MAGIC = b"DDS "


class DdsError(Exception):
    pass


def _rgb565(v):
    r = (v >> 11) & 0x1F
    g = (v >> 5) & 0x3F
    b = v & 0x1F
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255)


def _decode_dxt(payload, width, height, fmt):
    """Return RGBA bytes for one mip level."""
    out = bytearray(width * height * 4)
    bw = max(1, (width + 3) // 4)
    bh = max(1, (height + 3) // 4)
    block_size = 8 if fmt in ("DXT1", "ATI1") else 16
    pos = 0
    for by in range(bh):
        for bx in range(bw):
            if pos + block_size > len(payload):
                return bytes(out)
            block = payload[pos:pos + block_size]
            pos += block_size
            if fmt == "DXT1":
                c0, c1, bits = struct.unpack_from("<HHI", block, 0)
                alpha = None
            elif fmt == "DXT5":
                a0, a1 = block[0], block[1]
                abits = int.from_bytes(block[2:8], "little")
                alphas = _alpha_table(a0, a1)
                c0, c1, bits = struct.unpack_from("<HHI", block, 8)
                alpha = (alphas, abits)
            elif fmt == "DXT3":
                c0, c1, bits = struct.unpack_from("<HHI", block, 8)
                alpha = ("explicit", int.from_bytes(block[0:8], "little"))
            else:
                return bytes(out)

            cols = _colour_table(c0, c1, fmt)
            for py in range(4):
                for px in range(4):
                    x = bx * 4 + px
                    y = by * 4 + py
                    if x >= width or y >= height:
                        continue
                    idx = (bits >> (2 * (py * 4 + px))) & 0x3
                    r, g, b, _ = cols[idx]
                    a = 255
                    if alpha is not None:
                        if alpha[0] == "explicit":
                            a = ((alpha[1] >> (4 * (py * 4 + px))) & 0xF) * 17
                        else:
                            a = alpha[0][(alpha[1] >> (3 * (py * 4 + px))) & 0x7]
                    o = (y * width + x) * 4
                    out[o] = r; out[o + 1] = g; out[o + 2] = b; out[o + 3] = a
    return bytes(out)


def _alpha_table(a0, a1):
    t = [a0, a1]
    if a0 > a1:
        for i in range(1, 7):
            t.append(((7 - i) * a0 + i * a1) // 7)
    else:
        for i in range(1, 5):
            t.append(((5 - i) * a0 + i * a1) // 5)
        t += [0, 255]
    return t[:8]


def _colour_table(c0, c1, fmt):
    p0 = _rgb565(c0)
    p1 = _rgb565(c1)
    cols = [p0, p1]
    if c0 > c1 or fmt != "DXT1":
        cols.append(tuple((2 * p0[i] + p1[i]) // 3 for i in range(3)) + (255,))
        cols.append(tuple((p0[i] + 2 * p1[i]) // 3 for i in range(3)) + (255,))
    else:
        cols.append(tuple((p0[i] + p1[i]) // 2 for i in range(3)) + (255,))
        cols.append((0, 0, 0, 0))
    return cols


def dds_to_rgba(data):
    """Decode a Sims DDS blob to (rgba_bytes, width, height)."""
    if data[:4] != DDS_MAGIC:
        raise DdsError("not a DDS file")
    if len(data) < 128:
        raise DdsError("DDS too short")
    height, width = struct.unpack_from("<II", data, 12)
    fourcc = data[84:88]
    fmt = FOURCC_TO_DXT.get(fourcc)
    if fmt is None:
        raise DdsError(f"unsupported DDS format {fourcc!r}")
    if width == 0 or height == 0 or width > 8192 or height > 8192:
        raise DdsError(f"implausible dimensions {width}x{height}")
    rgba = _decode_dxt(data[128:], width, height, fmt)
    return rgba, width, height


def dds_to_png_bytes(data):
    """Decode to PNG bytes (needs Pillow for encoding only)."""
    from PIL import Image
    rgba, w, h = dds_to_rgba(data)
    im = Image.frombytes("RGBA", (w, h), rgba)
    import io
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue(), w, h
