#!/usr/bin/env python3
# V6.3.6 cluster-aware passive guard; push marker for isolated build.
from pathlib import Path

p = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/autocartographer_v634_passive.go')
s = p.read_text()

old = '''    regions := make([]passiveV634Region, 0, 9)
    parts := make([]string, 0, 9)
    for i := 0; i < 9; i++ {
        r, ok := scan.regions[i]
        if !ok { passiveV634Runtime.Unlock(); return }
        regions = append(regions, r)
        parts = append(parts, fmt.Sprintf("r%d:%s", i, r.DominantServerID))
    }
    uidCount, serverCount := len(scan.uids), len(scan.servers)
    delete(passiveV634Runtime.scans, jobID)
    passiveV634Runtime.Unlock()

    fp := strings.Join(parts, "|")
'''

new = '''    regions := make([]passiveV634Region, 0, 9)
    clusterSet := map[string]struct{}{}
    meaningfulRegions := 0
    for i := 0; i < 9; i++ {
        r, ok := scan.regions[i]
        if !ok { passiveV634Runtime.Unlock(); return }
        regions = append(regions, r)
        sid := strings.TrimSpace(r.DominantServerID)
        if r.Decoded > 0 && sid != "" {
            meaningfulRegions++
            clusterSet[sid] = struct{}{}
        }
    }
    uidCount, serverCount := len(scan.uids), len(scan.servers)
    delete(passiveV634Runtime.scans, jobID)
    passiveV634Runtime.Unlock()

    // The nine protocol partitions are not assumed to be nine zones of one
    // server. They may expose a logical server cluster. Reject empty/partial
    // searches and fingerprint the observed server set independently of the
    // partition ordering.
    if uidCount == 0 || serverCount == 0 || meaningfulRegions < 5 || len(clusterSet) < 2 {
        now := passiveV634Now()
        fmt.Printf("%s INFO AUTO_CARTOGRAPHER_V636_CLUSTER stage=IGNORED_INCOMPLETE jobId=%s uniqueUIDs=%d distinctServers=%d meaningfulPartitions=%d clusterServers=%d source=EXISTING_COLLECTOR_SCAN\\n", now, jobID, uidCount, serverCount, meaningfulRegions, len(clusterSet))
        return
    }

    clusterIDs := make([]string, 0, len(clusterSet))
    for sid := range clusterSet { clusterIDs = append(clusterIDs, sid) }
    sort.Strings(clusterIDs)
    fp := "cluster:" + strings.Join(clusterIDs, ",")
'''

if s.count(old) != 1:
    raise SystemExit(f'V636_CLUSTER_PATCH_EXPECTED_1_GOT_{s.count(old)}')

s = s.replace(old, new, 1)
s = s.replace('"version": "6.3.5",', '"version": "6.3.6",', 1)
s = s.replace('"mode": "PASSIVE_CHANGE_DETECTOR",', '"mode": "PASSIVE_CLUSTER_CHANGE_DETECTOR",', 1)
s = s.replace('"detectionSource": "EXISTING_COLLECTOR_SCAN",', '"detectionSource": "EXISTING_COLLECTOR_SCAN_CLUSTER_SIGNATURE",', 1)
p.write_text(s)

print('AUTO_CARTOGRAPHER_V636_CLUSTER_GUARD=PATCHED')
print('AUTO_CARTOGRAPHER_V636_EMPTY_SCAN_BASELINE=REJECTED')
print('AUTO_CARTOGRAPHER_V636_PARTITIONS_ARE_ZONES=NO')
print('AUTO_CARTOGRAPHER_V636_CLUSTER_SIGNATURE=READY')
