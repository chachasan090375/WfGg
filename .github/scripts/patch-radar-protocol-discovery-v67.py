#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
COLLECTOR = CONNECTOR / 'cmd/radar-connector/collector_jobs.go'
V3 = CONNECTOR / 'native-template/player_scan_v3.go'
V4 = CONNECTOR / 'native-template/player_scan_v4.go'
SRC = Path('.radar-release-src/v67-source/connector-go')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


def install_v67_sources() -> None:
    pairs = [
        (SRC / 'internal/protocol/region_diagnostics_v67.go', CONNECTOR / 'internal/protocol/region_diagnostics_v67.go'),
        (SRC / 'internal/protocol/region_diagnostics_v67_test.go', CONNECTOR / 'internal/protocol/region_diagnostics_v67_test.go'),
        (SRC / 'cmd/radar-connector/collector_region_diagnostics_v67.go', CONNECTOR / 'cmd/radar-connector/collector_region_diagnostics_v67.go'),
    ]
    for src, dst in pairs:
        if not src.is_file():
            raise SystemExit(f'V67_SOURCE_MISSING={src}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def patch_collector() -> None:
    text = COLLECTOR.read_text(encoding='utf-8')
    if 'WFGG_RADAR_PROTOCOL_DISCOVERY_V67' in text:
        print('RADAR_V67_COLLECTOR=ALREADY_PRESENT')
        return

    text = replace_once(
        text,
        '\tRegionFailures   []collectorRegionFailure `json:"regionFailures,omitempty"`\n',
        '\tRegionFailures   []collectorRegionFailure      `json:"regionFailures,omitempty"`\n\tRegionDiagnostics []collectorRegionDiagnosticV67 `json:"regionDiagnostics,omitempty"`\n',
        'collector diagnostics field',
    )

    text = replace_once(
        text,
        '''\t\tplayers, err := regionScanner.ScanPlayerRegion(ctx, token, "*", region)\n\t\tif err != nil {\n''',
        '''\t\t// WFGG_RADAR_PROTOCOL_DISCOVERY_V67\n\t\tplayers, regionDiag, err := scanCollectorRegionV67(ctx, s.game, regionScanner, token, region)\n\t\tif err != nil {\n\t\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\t\tj.RegionDiagnostics = append(j.RegionDiagnostics, publicCollectorRegionDiagnosticV67(region, regionDiag, 0))\n\t\t\t})\n''',
        'collector region scan call',
    )

    text = replace_once(
        text,
        '''\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.PlayersSeen += accepted\n\t\t\tj.RegionsCompleted++\n\t\t})\n''',
        '''\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.PlayersSeen += accepted\n\t\t\tj.RegionsCompleted++\n\t\t\tj.RegionDiagnostics = append(j.RegionDiagnostics, publicCollectorRegionDiagnosticV67(region, regionDiag, accepted))\n\t\t})\n''',
        'collector successful region diagnostics',
    )
    COLLECTOR.write_text(text, encoding='utf-8')
    print('RADAR_V67_COLLECTOR=PATCHED')


def patch_v3_decoder() -> None:
    text = V3.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_WILDCARD_DISCOVERY_V67'
    if marker not in text:
        text = replace_once(
            text,
            '''func v3PlayerMatches(p playerReport, query string) bool {\n\tq := strings.TrimSpace(query)\n\treturn (p.GameUID != "" && p.GameUID == q) || strings.EqualFold(strings.TrimSpace(p.Pseudo), q)\n}\n''',
            '''func v3PlayerMatches(p playerReport, query string) bool {\n\tq := strings.TrimSpace(query)\n\t// WFGG_RADAR_WILDCARD_DISCOVERY_V67: wildcard is a Collector enumeration\n\t// request, not a literal pseudo. Only structurally decoded player cities\n\t// with both UID and pseudo are accepted.\n\tif q == "*" {\n\t\treturn strings.TrimSpace(p.GameUID) != "" && strings.TrimSpace(p.Pseudo) != ""\n\t}\n\treturn (p.GameUID != "" && p.GameUID == q) || strings.EqualFold(strings.TrimSpace(p.Pseudo), q)\n}\n''',
            'v3 wildcard semantics',
        )
        text = replace_once(
            text,
            'if depth > 12 || v == nil || len(*out) >= 32 {',
            'if depth > 12 || v == nil || len(*out) >= 4096 {',
            'v3 enumeration bound',
        )
    V3.write_text(text, encoding='utf-8')
    print('RADAR_V67_WILDCARD=PATCHED')


def patch_v4_sweep() -> None:
    text = V4.read_text(encoding='utf-8')
    if 'WFGG_RADAR_REGION_SELECTOR_V67' not in text:
        text = replace_once(text, 'WFGG_SCAN_V43 requests=', 'WFGG_SCAN_V67 requests=', 'v67 diagnostic marker')
        text = replace_once(text, 'detail10_present=%d detail10_missing=%d', 'detail3_present=%d detail3_missing=%d', 'v67 detail labels')
        text = replace_once(text, 'detailRaw, ok := protoBytesV3(m, 10)', 'detailRaw, ok := protoBytesV3(m, 3)', 'v67 player detail field')

        text = replace_once(
            text,
            '''\tplayers := scanCapturedMapV3(convs, server, query, fallbackServer, observedAt)\n\tif len(players) == 0 && len(mapTemplates) > 0 {\n\t\tvar err error\n\t\tplayers, err = replayMapTemplatesV3(conn, mapTemplates, query, fallbackServer, observedAt)\n\t\tif err != nil {\n\t\t\treturn nil, err\n\t\t}\n\t}\n\n\tif len(players) == 0 {\n''',
            '''\t// WFGG_RADAR_REGION_SELECTOR_V67: Collector region calls must use live\n\t// synthetic map requests for exactly one origin. Captured/replayed PCAP map\n\t// data remains available only to legacy targeted searches.\n\tregionScoped := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_ORIGIN_INDEX")) != ""\n\tplayers := []playerReport{}\n\tif !regionScoped {\n\t\tplayers = scanCapturedMapV3(convs, server, query, fallbackServer, observedAt)\n\t\tif len(players) == 0 && len(mapTemplates) > 0 {\n\t\t\tvar err error\n\t\t\tplayers, err = replayMapTemplatesV3(conn, mapTemplates, query, fallbackServer, observedAt)\n\t\t\tif err != nil {\n\t\t\t\treturn nil, err\n\t\t\t}\n\t\t}\n\t}\n\n\tif len(players) == 0 {\n''',
            'v4 region-scoped live scan',
        )

        text = replace_once(
            text,
            '''\tif len(players) == 0 {\n\t\treturn []playerReport{}, nil\n\t}\n\n\tfor i := range players {\n''',
            '''\tif len(players) == 0 {\n\t\treturn []playerReport{}, nil\n\t}\n\t// Collector wildcard discovery performs profile enrichment later in bounded\n\t// batches; avoid N individual profile requests inside the native map sweep.\n\tif query == "*" {\n\t\treturn players, nil\n\t}\n\n\tfor i := range players {\n''',
            'v4 wildcard enrichment bypass',
        )

        text = replace_once(
            text,
            '''\torigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n''',
            '''\tlegacyOrigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n\tregionGrid := [][2]int{\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {1000, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n\torigins := legacyOrigins\n\tif raw := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_ORIGIN_INDEX")); raw != "" {\n\t\tidx, err := strconv.Atoi(raw)\n\t\tif err != nil || idx < 0 || idx >= len(regionGrid) {\n\t\t\treturn nil, errors.New("PLAYER_SCAN_ORIGIN_INDEX_INVALID")\n\t\t}\n\t\torigins = [][2]int{regionGrid[idx]}\n\t}\n''',
            'v4 authoritative origin selector',
        )

        text = replace_once(
            text,
            '''\t\t\tif len(out) > 0 {\n\t\t\t\treturn out, nil\n\t\t\t}\n''',
            '''\t\t\tif len(out) > 0 && query != "*" {\n\t\t\t\treturn out, nil\n\t\t\t}\n''',
            'v4 wildcard full-origin sweep',
        )
    V4.write_text(text, encoding='utf-8')
    print('RADAR_V67_REGION_SELECTOR=PATCHED')
    print('RADAR_V67_DIAGNOSTICS=SAFE_AGGREGATES_ONLY')


install_v67_sources()
patch_collector()
patch_v3_decoder()
patch_v4_sweep()
print('RADAR_PROTOCOL_DISCOVERY_V67=READY')
