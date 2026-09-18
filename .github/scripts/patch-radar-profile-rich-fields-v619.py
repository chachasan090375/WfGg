#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
PROTOCOL = CONNECTOR / 'internal/protocol/protocol.go'
NATIVE_MAIN = CONNECTOR / 'native-template/main.go'
PLAYER_V3 = CONNECTOR / 'native-template/player_scan_v3.go'
SRC = Path('.radar-release-src/v619-source/connector-go')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


# Connector-visible Player payload: rich profile fields remain explicitly
# OBSERVED values from get.user.info.multi. AvatarRef is deliberately only a
# reference/id/string when an exact avatar/avatarUrl/avatarId key is present;
# no picture URL or skin mapping is inferred.
text = PROTOCOL.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_PROFILE_RICH_FIELDS_V619'
if marker not in text:
    old = '''	Power       *int64 `json:"power,omitempty"`
	X           *int64 `json:"x,omitempty"`
'''
    new = '''	Power       *int64 `json:"power,omitempty"`
	// WFGG_RADAR_PROFILE_RICH_FIELDS_V619
	ArmyPower   *int64 `json:"armyPower,omitempty"`
	ArmyKill    *int64 `json:"armyKill,omitempty"`
	SVIPLevel   *int64 `json:"svipLevel,omitempty"`
	Country     string `json:"country,omitempty"`
	AvatarRef   string `json:"avatarRef,omitempty"`
	X           *int64 `json:"x,omitempty"`
'''
    text = replace_once(text, old, new, 'protocol Player rich fields')
    PROTOCOL.write_text(text, encoding='utf-8')
    print('RADAR_V619_PROTOCOL_PLAYER=PATCHED')
else:
    print('RADAR_V619_PROTOCOL_PLAYER=ALREADY_PRESENT')

# Native helper JSON must mirror protocol.Player exactly for these fields.
text = NATIVE_MAIN.read_text(encoding='utf-8')
if marker not in text:
    old = '''	Power       *int64 `json:"power,omitempty"`
	X           *int64 `json:"x,omitempty"`
'''
    new = '''	Power       *int64 `json:"power,omitempty"`
	// WFGG_RADAR_PROFILE_RICH_FIELDS_V619
	ArmyPower   *int64 `json:"armyPower,omitempty"`
	ArmyKill    *int64 `json:"armyKill,omitempty"`
	SVIPLevel   *int64 `json:"svipLevel,omitempty"`
	Country     string `json:"country,omitempty"`
	AvatarRef   string `json:"avatarRef,omitempty"`
	X           *int64 `json:"x,omitempty"`
'''
    text = replace_once(text, old, new, 'native playerReport rich fields')
    NATIVE_MAIN.write_text(text, encoding='utf-8')
    print('RADAR_V619_NATIVE_REPORT=PATCHED')
else:
    print('RADAR_V619_NATIVE_REPORT=ALREADY_PRESENT')

# Parse only exact self-describing keys already seen/documented in
# get.user.info.multi. Avatar remains conservative: exact avatar/avatarUrl/
# avatarId only, stored as an opaque string reference.
text = PLAYER_V3.read_text(encoding='utf-8')
parser_marker = 'WFGG_RADAR_PROFILE_RICH_PARSE_V619'
if parser_marker not in text:
    old = '''			if n, ok := v3IntField(t, "power"); ok {
				p.Power = &n
			}
			return p, true
'''
    new = '''			if n, ok := v3IntField(t, "power"); ok {
				p.Power = &n
			}
			// WFGG_RADAR_PROFILE_RICH_PARSE_V619
			if n, ok := v3IntField(t, "armyPower"); ok {
				p.ArmyPower = &n
			}
			if n, ok := v3IntField(t, "armyKill"); ok {
				p.ArmyKill = &n
			}
			if n, ok := v3IntField(t, "svipLevel"); ok {
				p.SVIPLevel = &n
			}
			p.Country = strings.TrimSpace(v3ScalarAt(t, "country"))
			p.AvatarRef = firstNonEmptyV3(
				v3ScalarAt(t, "avatar"),
				v3ScalarAt(t, "avatarUrl"),
				v3ScalarAt(t, "avatarId"),
			)
			return p, true
'''
    text = replace_once(text, old, new, 'profile rich parser')

    old_merge = '''	if profile.Power != nil {
		base.Power = profile.Power
	}
}
'''
    new_merge = '''	if profile.Power != nil {
		base.Power = profile.Power
	}
	if profile.ArmyPower != nil {
		base.ArmyPower = profile.ArmyPower
	}
	if profile.ArmyKill != nil {
		base.ArmyKill = profile.ArmyKill
	}
	if profile.SVIPLevel != nil {
		base.SVIPLevel = profile.SVIPLevel
	}
	if profile.Country != "" {
		base.Country = profile.Country
	}
	if profile.AvatarRef != "" {
		base.AvatarRef = profile.AvatarRef
	}
}
'''
    text = replace_once(text, old_merge, new_merge, 'profile rich merge')
    PLAYER_V3.write_text(text, encoding='utf-8')
    print('RADAR_V619_PROFILE_PARSER=PATCHED')
else:
    print('RADAR_V619_PROFILE_PARSER=ALREADY_PRESENT')

# Tests live outside the old immutable source tree and are copied only into
# qualification/build workspaces.
for rel in (
    'native-template/profile_rich_fields_v619_test.go',
    'internal/protocol/profile_rich_fields_v619_test.go',
):
    src = SRC / rel
    dst = CONNECTOR / rel
    if not src.is_file():
        raise SystemExit(f'V619_SOURCE_MISSING={src}')
    shutil.copyfile(src, dst)

print('RADAR_PROFILE_RICH_FIELDS_V619=READY')
