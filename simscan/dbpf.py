"""DBPF (The Sims 4 .package) reader.

Verified against real Sims 4 custom-content packages. Reads the resource
index and decompresses payloads (uncompressed / zlib / EA RefPack) without
the game and without network access.

Binary layout notes (DBPF 2.1):
  header 96 bytes; index entry count at 0x24, index position low at 0x28,
  index size at 0x2C, index position high at 0x40.
  Index flags may hoist type/group/instance-high out of the entries.
"""
import os
import struct
import zlib

CONST_TYPE, CONST_GROUP, CONST_INST_EX = 1, 2, 4


class PackageError(Exception):
    pass


def refpack_decompress(buf: bytes) -> bytes:
    """EA RefPack/QFS, Sims-4 flavour (first two bytes swapped)."""
    if len(buf) < 6 or buf[1] != 0xFB:
        raise PackageError("not a refpack stream")
    flags = buf[0]
    iptr = 2
    osize = 0
    for _ in range(4 if flags & 0x80 else 3):
        osize = (osize << 8) | buf[iptr]
        iptr += 1
    obuf = bytearray(osize)
    optr = 0
    n = len(buf)
    while iptr < n and optr < osize:
        cc0 = buf[iptr]
        iptr += 1
        num_plain = num_copy = copy_off = 0
        if cc0 <= 0x7F:
            cc1 = buf[iptr]; iptr += 1
            num_plain = cc0 & 0x03
            num_copy = ((cc0 & 0x1C) >> 2) + 3
            copy_off = ((cc0 & 0x60) << 3) + cc1
        elif cc0 <= 0xBF:
            cc1 = buf[iptr]; cc2 = buf[iptr + 1]; iptr += 2
            num_plain = (cc1 & 0xC0) >> 6
            num_copy = (cc0 & 0x3F) + 4
            copy_off = ((cc1 & 0x3F) << 8) + cc2
        elif cc0 <= 0xDF:
            cc1 = buf[iptr]; cc2 = buf[iptr + 1]; cc3 = buf[iptr + 2]; iptr += 3
            num_plain = cc0 & 0x03
            num_copy = ((cc0 & 0x0C) << 6) + cc3 + 5
            copy_off = ((cc0 & 0x10) << 12) + (cc1 << 8) + cc2
        elif cc0 <= 0xFB:
            num_plain = ((cc0 & 0x1F) << 2) + 4
            num_copy = 0
        else:
            num_plain = cc0 & 3
            num_copy = 0
        obuf[optr:optr + num_plain] = buf[iptr:iptr + num_plain]
        iptr += num_plain
        optr += num_plain
        for _ in range(num_copy):
            obuf[optr] = obuf[optr - 1 - copy_off]
            optr += 1
    return bytes(obuf)


class Resource:
    __slots__ = ("type_id", "group_id", "instance", "offset", "raw_len",
                 "size", "compression", "pack_offset")

    def __init__(self, type_id, group_id, instance, offset, raw_len, size,
                 compression, pack_offset=0):
        self.type_id = type_id
        self.group_id = group_id
        self.instance = instance
        self.offset = offset
        self.raw_len = raw_len
        self.size = size
        self.compression = compression
        self.pack_offset = pack_offset

    @property
    def key(self):
        return (self.type_id, self.group_id, self.instance)

    @property
    def hex(self):
        return f"{self.type_id:08X}:{self.group_id:08X}:{self.instance:016X}"

    @property
    def short_hex(self):
        return f"{self.type_id:08X}:{self.instance:016X}"


class Package:
    """Read-only view of a .package file."""

    def __init__(self, path, read_data=True):
        self.path = path
        self.name = os.path.basename(path)
        self.resources = []
        self.version = "?"
        self.index_position = 0
        self.data = b""
        try:
            self.size = os.path.getsize(path)
        except OSError:
            self.size = 0
        if read_data:
            with open(path, "rb") as fh:
                self.data = fh.read()
        self._parse()

    def _parse(self):
        d = self.data
        if d[:4] != b"DBPF":
            raise PackageError("not a DBPF package")
        major, minor = struct.unpack_from("<II", d, 4)
        self.version = f"{major}.{minor}"
        count = struct.unpack_from("<I", d, 0x24)[0]
        pos_low = struct.unpack_from("<I", d, 0x28)[0]
        self.index_size = struct.unpack_from("<I", d, 0x2C)[0]
        pos_high = struct.unpack_from("<I", d, 0x40)[0]
        index_pos = pos_high if pos_high else pos_low
        self.index_position = index_pos

        if count == 0:
            return
        if index_pos <= 0 or index_pos >= len(d):
            raise PackageError(
                f"index position 0x{index_pos:X} outside file "
                f"(len {len(d)})")

        p = index_pos
        flags = struct.unpack_from("<I", d, p)[0]
        p += 4
        ctype = cgroup = cinst_ex = 0
        if flags & CONST_TYPE:
            ctype = struct.unpack_from("<I", d, p)[0]; p += 4
        if flags & CONST_GROUP:
            cgroup = struct.unpack_from("<I", d, p)[0]; p += 4
        if flags & CONST_INST_EX:
            cinst_ex = struct.unpack_from("<I", d, p)[0]; p += 4

        for _ in range(count):
            try:
                if flags & CONST_TYPE:
                    t = ctype
                else:
                    t = struct.unpack_from("<I", d, p)[0]; p += 4
                if flags & CONST_GROUP:
                    g = cgroup
                else:
                    g = struct.unpack_from("<I", d, p)[0]; p += 4
                if flags & CONST_INST_EX:
                    iex = cinst_ex
                else:
                    iex = struct.unpack_from("<I", d, p)[0]; p += 4
                inst_lo = struct.unpack_from("<I", d, p)[0]; p += 4
                offset = struct.unpack_from("<I", d, p)[0]; p += 4
                raw_len = struct.unpack_from("<I", d, p)[0]; p += 4
                size = struct.unpack_from("<I", d, p)[0]; p += 4
                if raw_len & 0x80000000:
                    comp = struct.unpack_from("<HH", d, p); p += 4
                else:
                    comp = (0, 1)
                raw_len &= 0x7FFFFFFF
            except struct.error:
                # Truncated index entry: keep what we have rather than
                # throwing away the whole package.
                break
            if comp[0] == 0xFFE0:          # deleted entry
                continue
            self.resources.append(Resource(
                t, g, (iex << 32) | inst_lo, offset, raw_len, size, comp))

    def payload(self, res: Resource) -> bytes:
        """Decompress one resource. Raises PackageError on bad data."""
        raw = self.data[res.offset:res.offset + res.raw_len]
        if len(raw) < res.raw_len:
            raise PackageError("resource extends past end of file")
        c = res.compression[0]
        try:
            if c == 0x0000:
                return raw
            if c in (0xFFFF, 0xFFFE):
                return refpack_decompress(raw)
            if c == 0x5A42:
                return zlib.decompress(raw, 15, res.size)
        except (zlib.error, PackageError, IndexError) as e:
            raise PackageError(f"decompress failed (codec 0x{c:04X}): {e}")
        raise PackageError(f"unknown compression codec 0x{c:04X}")

    def try_payload(self, res: Resource):
        """Decompress, returning None instead of raising."""
        try:
            return self.payload(res)
        except Exception:
            return None

    def __repr__(self):
        return f"<Package {self.name} {len(self.resources)} resources>"


def parse_stbl(data: bytes) -> dict:
    """STBL v5 string table -> {key: text}.

    Header: 'STBL' | u16 version | u8 compression | u16 entry_count | pad,
    entries begin at 0x15: u32 key, u8 flags, u16 byte_length, UTF-8 text.
    Strings are UTF-8, not UTF-16.
    """
    if data[:4] != b"STBL":
        raise PackageError("not an STBL resource")
    count = struct.unpack_from("<H", data, 7)[0]
    out, pos = {}, 0x15
    for _ in range(count):
        try:
            key = struct.unpack_from("<I", data, pos)[0]
            pos += 5
            length = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            out[key] = data[pos:pos + length].decode("utf-8", errors="replace")
            pos += length
        except (struct.error, IndexError):
            break
    return out
