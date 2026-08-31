from __future__ import annotations

import re
import struct
from pathlib import Path


def typ(o):
    return str(getattr(getattr(o, "type", None), "name", "") or "")


def pid(o):
    return int(getattr(o, "path_id", 0) or 0)


def sfname(o):
    af = getattr(o, "assets_file", None)
    return str(getattr(af, "name", "") or getattr(af, "file_name", "") or "")


def pname(o):
    try:
        return str(o.peek_name() or "")
    except Exception:
        return ""


def safe(s):
    z = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("._")
    return z[:120] or "asset"


def geti(d, *keys, default=0):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return int(d[k])
            except Exception:
                return d[k]
    return default


def getv(d, *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def component_spec(fmt):
    specs = {
        0: ("f", 4, "float"),
        1: ("e", 2, "float"),
        2: ("B", 1, "unorm8"),
        3: ("b", 1, "snorm8"),
        4: ("H", 2, "unorm16"),
        5: ("h", 2, "snorm16"),
        6: ("B", 1, "uint"),
        7: ("b", 1, "sint"),
        8: ("H", 2, "uint"),
        9: ("h", 2, "sint"),
        10: ("I", 4, "uint"),
        11: ("i", 4, "sint"),
    }
    if int(fmt) not in specs:
        raise ValueError("vertex-format-" + str(fmt))
    return specs[int(fmt)]


def normalize_value(x, kind):
    if kind == "unorm8":
        return float(x) / 255.0
    if kind == "snorm8":
        return max(-1.0, float(x) / 127.0)
    if kind == "unorm16":
        return float(x) / 65535.0
    if kind == "snorm16":
        return max(-1.0, float(x) / 32767.0)
    return float(x)


def derive_streams(channels, vertex_count, data_len):
    active = []
    for i, ch in enumerate(channels or []):
        if not isinstance(ch, dict):
            continue
        dim = geti(ch, "dimension", "m_Dimension") & 0xF
        if dim <= 0:
            continue
        st = geti(ch, "stream", "m_Stream")
        fmt = geti(ch, "format", "m_Format")
        _, sz, _ = component_spec(fmt)
        off = geti(ch, "offset", "m_Offset")
        active.append((i, st, off, dim, sz))
    if not active:
        raise ValueError("no-active-channels")
    stream_count = 1 + max(x[1] for x in active)
    streams = []
    offset = 0
    for s in range(stream_count):
        xs = [x for x in active if x[1] == s]
        if xs:
            stride_sum = sum(dim * sz for _, _, _, dim, sz in xs)
            stride_end = max(off + dim * sz for _, _, off, dim, sz in xs)
            stride = max(stride_sum, stride_end)
        else:
            stride = 0
        streams.append({"stream": s, "offset": offset, "stride": stride})
        offset += vertex_count * stride
        offset = (offset + 15) & ~15
    if streams and streams[-1]["offset"] > data_len:
        raise ValueError("stream-layout-oob")
    return streams, active


def decode_channel(data, vertex_count, channel, stream):
    coff = geti(channel, "offset", "m_Offset")
    fmt = geti(channel, "format", "m_Format")
    dim = geti(channel, "dimension", "m_Dimension") & 0xF
    code, size, kind = component_spec(fmt)
    soff = stream["offset"]
    stride = stream["stride"]
    vals = []
    for vi in range(vertex_count):
        pos = soff + vi * stride + coff
        need = dim * size
        if pos < 0 or pos + need > len(data):
            raise ValueError(f"channel-oob vi={vi} pos={pos} need={need} data={len(data)}")
        raw = struct.unpack_from("<" + code * dim, data, pos)
        vals.append(tuple(normalize_value(x, kind) for x in raw))
    return vals


def triangulate(indices, submeshes, index_size, vertex_count):
    faces = []
    meta = []
    if not submeshes:
        submeshes = [{"firstByte": 0, "indexCount": len(indices), "topology": 0, "baseVertex": 0}]
    for si, sm in enumerate(submeshes):
        if not isinstance(sm, dict):
            continue
        firstb = geti(sm, "firstByte", "m_FirstByte")
        count = geti(sm, "indexCount", "m_IndexCount")
        topo = geti(sm, "topology", "m_Topology")
        base = geti(sm, "baseVertex", "m_BaseVertex")
        start = firstb // index_size
        arr = indices[start : start + count]
        before = len(faces)
        if topo == 0:
            for j in range(0, len(arr) - 2, 3):
                tri = (arr[j] + base, arr[j + 1] + base, arr[j + 2] + base)
                if min(tri) >= 0 and max(tri) < vertex_count and len(set(tri)) == 3:
                    faces.append(tri)
        elif topo == 1:
            for j in range(0, len(arr) - 2):
                tri = (arr[j] + base, arr[j + 1] + base, arr[j + 2] + base)
                if j & 1:
                    tri = (tri[1], tri[0], tri[2])
                if min(tri) >= 0 and max(tri) < vertex_count and len(set(tri)) == 3:
                    faces.append(tri)
        elif topo == 2:
            for j in range(0, len(arr) - 3, 4):
                q = [x + base for x in arr[j : j + 4]]
                if min(q) >= 0 and max(q) < vertex_count:
                    faces.append((q[0], q[1], q[2]))
                    faces.append((q[0], q[2], q[3]))
        meta.append({"submesh": si, "topology": topo, "indexCount": count, "baseVertex": base, "faces": len(faces) - before})
    return faces, meta


def raw_mesh_to_obj(o):
    d = o.read_typetree(wrap=False, check_read=False)
    if not isinstance(d, dict):
        raise ValueError("typetree-not-dict")
    name = str(d.get("m_Name") or pname(o) or ("Mesh_" + str(pid(o))))
    vd = d.get("m_VertexData") or {}
    if not isinstance(vd, dict):
        raise ValueError("no-m_VertexData")
    vc = geti(vd, "m_VertexCount", "vertexCount")
    channels = getv(vd, "m_Channels", "channels", default=[]) or []
    data = bytes(getv(vd, "m_DataSize", "dataSize", default=b"") or b"")
    if vc <= 0 or not data:
        raise ValueError(f"no-inline-vertex-data vc={vc} bytes={len(data)}")
    streams, active = derive_streams(channels, vc, len(data))
    if not channels or (geti(channels[0], "dimension", "m_Dimension") & 0xF) < 3:
        raise ValueError("position-channel-missing")
    positions = decode_channel(data, vc, channels[0], streams[geti(channels[0], "stream", "m_Stream")])
    normals = None
    if len(channels) > 1 and (geti(channels[1], "dimension", "m_Dimension") & 0xF) >= 3:
        normals = decode_channel(data, vc, channels[1], streams[geti(channels[1], "stream", "m_Stream")])
    uvs = None
    if len(channels) > 4 and (geti(channels[4], "dimension", "m_Dimension") & 0xF) >= 2:
        uvs = decode_channel(data, vc, channels[4], streams[geti(channels[4], "stream", "m_Stream")])
    ib = bytes(d.get("m_IndexBuffer") or b"")
    if not ib:
        raise ValueError("index-buffer-empty")
    index_format = geti(d, "m_IndexFormat", default=0)
    index_size = 2 if index_format == 0 else 4
    code = "H" if index_size == 2 else "I"
    usable = len(ib) - (len(ib) % index_size)
    indices = list(struct.unpack("<" + code * (usable // index_size), ib[:usable]))
    faces, submeta = triangulate(indices, d.get("m_SubMeshes") or [], index_size, vc)
    if not faces:
        raise ValueError("no-triangle-faces")
    has_uv = bool(uvs and len(uvs) == vc)
    has_n = bool(normals and len(normals) == vc)
    lines = ["# WFGG reusable raw TypeTree OBJ", f"o {safe(name)}"]
    for v in positions:
        lines.append(f"v {float(v[0]):.9g} {float(v[1]):.9g} {float(v[2]):.9g}")
    if has_uv:
        for uv in uvs:
            lines.append(f"vt {float(uv[0]):.9g} {float(uv[1]):.9g}")
    if has_n:
        for n in normals:
            lines.append(f"vn {float(n[0]):.9g} {float(n[1]):.9g} {float(n[2]):.9g}")
    for a, b, c in faces:
        a += 1; b += 1; c += 1
        if has_uv and has_n:
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
        elif has_uv:
            lines.append(f"f {a}/{a} {b}/{b} {c}/{c}")
        elif has_n:
            lines.append(f"f {a}//{a} {b}//{b} {c}//{c}")
        else:
            lines.append(f"f {a} {b} {c}")
    info = {
        "name": name,
        "vertexCount": vc,
        "faceCount": len(faces),
        "indexCount": len(indices),
        "indexFormat": index_format,
        "indexSize": index_size,
        "subMeshes": submeta,
        "hasUV0": has_uv,
        "hasNormals": has_n,
        "vertexDataBytes": len(data),
        "indexBytes": len(ib),
        "streams": streams,
        "activeChannels": [
            {"channel": i, "stream": st, "offset": off, "dimension": dim, "componentBytes": sz}
            for i, st, off, dim, sz in active
        ],
    }
    return "\n".join(lines) + "\n", info


def write_raw_obj(o, destination: Path):
    text, info = raw_mesh_to_obj(o)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, "utf-8", newline="")
    return info
