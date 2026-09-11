#!/usr/bin/env python3
from pathlib import Path

V4 = Path('/tmp/wfgg-radar/connector-go/native-template/player_scan_v4.go')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)


text = V4.read_text(encoding='utf-8')
text = replace_once(
    text,
    '''\tobservedAt := time.Now().UTC().Format(time.RFC3339Nano)\n\n\tplayers := scanCapturedMapV3(convs, server, query, fallbackServer, observedAt)\n''',
    '''\tobservedAt := time.Now().UTC().Format(time.RFC3339Nano)\n\n\t// Collector profile-only mode: enrich known UIDs without rescanning the map.\n\t// The caller supplies @profile:<uid>[,<uid>...] and the same authenticated\n\t// connection is reused for all requests. No credential is persisted here.\n\tif strings.HasPrefix(query, "@profile:") {\n\t\tif profileTemplate == nil {\n\t\t\treturn nil, errors.New("PLAYER_PROFILE_TEMPLATE_NOT_FOUND")\n\t\t}\n\t\traw := strings.TrimSpace(strings.TrimPrefix(query, "@profile:"))\n\t\tif raw == "" {\n\t\t\treturn nil, errors.New("PLAYER_PROFILE_UIDS_REQUIRED")\n\t\t}\n\t\tparts := strings.Split(raw, ",")\n\t\tif len(parts) > 200 {\n\t\t\treturn nil, errors.New("PLAYER_PROFILE_UIDS_LIMIT")\n\t\t}\n\t\tseenUID := map[string]bool{}\n\t\tout := make([]playerReport, 0, len(parts))\n\t\tfor _, part := range parts {\n\t\t\tuid := strings.TrimSpace(part)\n\t\t\tif uid == "" || seenUID[uid] {\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tseenUID[uid] = true\n\t\t\tp, ok, err := requestProfileV3(conn, profileTemplate, uid, observedAt)\n\t\t\tif err != nil {\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tif ok {\n\t\t\t\tout = append(out, p)\n\t\t\t}\n\t\t}\n\t\treturn out, nil\n\t}\n\n\tplayers := scanCapturedMapV3(convs, server, query, fallbackServer, observedAt)\n''',
    'collector direct profile mode',
)
V4.write_text(text, encoding='utf-8')
print('COLLECTOR_PROFILE_DIRECT=YES')
print('COLLECTOR_PROFILE_DIRECT_LIMIT=200')
