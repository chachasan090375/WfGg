#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-recursive-uid-match.py /path/to/wfgg-broker-main.go")

    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")

    pattern = re.compile(
        r"func objectContainsUID\(obj \*sfs\.SFSObject, requestedUID string\) bool \{.*?\n\}\n\nfunc roleMetadata",
        re.S,
    )

    replacement = r'''func objectContainsUID(obj *sfs.SFSObject, requestedUID string) bool {
	return nestedValueContainsUID(obj, requestedUID, 0)
}

func nestedValueContainsUID(value any, requestedUID string, depth int) bool {
	if value == nil || depth > 6 {
		return false
	}

	switch v := value.(type) {
	case *sfs.SFSObject:
		if v == nil {
			return false
		}
		for _, key := range v.Keys() {
			item, ok := v.Get(key)
			if !ok {
				continue
			}
			normalizedKey := strings.ToLower(strings.NewReplacer("_", "", "-", "").Replace(key))
			if uidBearingKey(normalizedKey) && digitsOnly(scalarString(item.Val)) == requestedUID {
				return true
			}
			if nestedValueContainsUID(item.Val, requestedUID, depth+1) {
				return true
			}
		}
	case *sfs.SFSArray:
		if v == nil {
			return false
		}
		for _, item := range v.Items() {
			if nestedValueContainsUID(item.Val, requestedUID, depth+1) {
				return true
			}
		}
	}
	return false
}

func uidBearingKey(key string) bool {
	switch key {
	case "uid", "gameuid", "playerid", "roleid", "characterid", "accountid", "userid", "rid":
		return true
	default:
		return strings.HasSuffix(key, "uid")
	}
}

func roleMetadata'''

    patched, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"recursive UID patch: expected exactly 1 function block, found {count}")

    path.write_text(patched, encoding="utf-8")


if __name__ == "__main__":
    main()
