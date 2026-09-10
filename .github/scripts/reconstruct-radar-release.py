import base64
import hashlib
import pathlib
import re

CHUNK_SIZE = 2906
EXPECTED_P00_5 = "46a9c87128f095432613c958261408c60fa475f1b5ec23daea1d9b2db8a0e8a4"
EXPECTED_P03_1 = "2be7c15b6a8bef75e00d8255f4dcb2a93e5cb709f99ea69c3172e1153a050716"
EXPECTED_RELEASE = "234df1dec57f6211bc625855bf13350c9f17fbd843fbe92d8cf1ab7cb5c081ef"


def read(path):
    return pathlib.Path(path).read_bytes()


def checked_replacement(path, expected):
    data = read(path)
    if len(data) != CHUNK_SIZE:
        raise SystemExit(f"BAD_REPLACEMENT_SIZE {path} {len(data)}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise SystemExit(f"BAD_REPLACEMENT_SHA {path} {digest}")
    return data


p00 = bytearray(read("radar-release/parts/part-00.b64"))
p01 = read("radar-release/parts/part-01.b64")
p02 = read("radar-release/parts/part-02.b64")
p03 = bytearray(read("radar-release/parts/part-03.b64"))

for name, data in (("p00", p00), ("p01", p01), ("p02", p02), ("p03", p03)):
    if len(data) != 17436:
        raise SystemExit(f"BAD_PART_SIZE {name} {len(data)}")

p00[5 * CHUNK_SIZE:6 * CHUNK_SIZE] = checked_replacement(
    ".radar-release-src/p00-5.b64", EXPECTED_P00_5
)
p03[1 * CHUNK_SIZE:2 * CHUNK_SIZE] = checked_replacement(
    ".radar-release-src/p03-1.b64", EXPECTED_P03_1
)

raw = bytes(p00) + p01 + p02 + bytes(p03)
clean = re.sub(rb"[^A-Za-z0-9+/=]", b"", raw)
if len(clean) % 4:
    raise SystemExit(f"BAD_BASE64_LENGTH {len(clean)}")

decoded = base64.b64decode(clean, validate=True)
digest = hashlib.sha256(decoded).hexdigest()
print(f"RADAR_RELEASE_FRAGMENT_BYTES={len(raw)}")
print(f"RADAR_RELEASE_BASE64_CHARS={len(clean)}")
print(f"RADAR_RELEASE_DECODED_BYTES={len(decoded)}")
print(f"RADAR_RELEASE_SHA256={digest}")
if digest != EXPECTED_RELEASE:
    raise SystemExit("RADAR_RELEASE_SHA_MISMATCH")

pathlib.Path("/tmp/radar-src.tar.gz").write_bytes(decoded)
print("RADAR_RELEASE=VERIFIED")
