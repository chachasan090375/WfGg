#!/usr/bin/env python3
from pathlib import Path

JOBS = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')

s = JOBS.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_DISCOVERY_V61'
if marker not in s:
    old = '''\tif strings.HasPrefix(strings.ToLower(strings.TrimSpace(query)), "@servers:") {\n\t\ts.handleServerExplorer(ctx, token, query, jobID)\n\t\treturn\n\t}\n'''
    new = '''\t// SERVER_EXPLORER_DISCOVERY_V61\n\t// Convenience discovery window around one explicit known server. V6.1 is\n\t// intentionally small: center +/- 5, reusing the already validated V6\n\t// single-session @servers path without adding a new network primitive.\n\tif strings.HasPrefix(strings.ToLower(strings.TrimSpace(query)), "@discover:") {\n\t\traw := strings.TrimSpace(query[len("@discover:"):])\n\t\tcenter, err := strconv.Atoi(raw)\n\t\tif err != nil || center <= 5 || center > 999994 {\n\t\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\t\tj.Status = "FAILED"; j.Phase = "SERVER_DISCOVERY_FAILED"; j.Error = "SERVER_DISCOVERY_CENTER_INVALID"; j.FinishedAt = utcNow()\n\t\t\t})\n\t\t\treturn\n\t\t}\n\t\trangeQuery := "@servers:" + strconv.Itoa(center-5) + "-" + strconv.Itoa(center+5)\n\t\tslog.Info("SERVER_DISCOVERY_V61_SENTINEL", "jobId", jobID, "stage", "START", "center", center, "low", center-5, "high", center+5, "planned", 11)\n\t\ts.handleServerExplorer(ctx, token, rangeQuery, jobID)\n\t\tslog.Info("SERVER_DISCOVERY_V61_SENTINEL", "jobId", jobID, "stage", "DONE", "center", center, "planned", 11)\n\t\treturn\n\t}\n\tif strings.HasPrefix(strings.ToLower(strings.TrimSpace(query)), "@servers:") {\n\t\ts.handleServerExplorer(ctx, token, query, jobID)\n\t\treturn\n\t}\n'''
    if s.count(old) != 1:
        raise SystemExit(f'V61_DISCOVERY_ROUTE expected 1 match, got {s.count(old)}')
    s = s.replace(old, new, 1)
    JOBS.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_DISCOVERY_V61=PATCHED')
print('SERVER_EXPLORER_DISCOVERY_WINDOW=11')
print('SERVER_EXPLORER_DISCOVERY_REUSES_V6_SINGLE_SESSION=YES')
