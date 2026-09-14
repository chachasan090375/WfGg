package main

import (
	"net/http"
	"strings"
)

// AUTO_CARTOGRAPHER_V633_TICK
// One signed, READONLY tick driven by the Cloudflare scheduled agent. The game
// credential is used only for this request and is never persisted by the VPS.
type autoCartographerV633TickRequest struct {
	Token string `json:"token"`
}

func (s *server) autoCartographerV633TickHTTP(w http.ResponseWriter, _ *http.Request, body []byte) {
	var input autoCartographerV633TickRequest
	if err := decodeJSON(body, &input); err != nil || len(strings.TrimSpace(input.Token)) < 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "GAME_TOKEN_REQUIRED"})
		return
	}
	result, err := s.autoCartographerV633Tick(strings.TrimSpace(input.Token))
	if err != nil {
		writeGameError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *server) autoCartographerV633Tick(token string) (map[string]any, error) {
	if collectorJobsBusyV633() {
		autoCartographerV633Log("TICK_SKIPPED", "reason", "COLLECTOR_BUSY")
		return map[string]any{"ok": true, "status": "skipped", "reason": "COLLECTOR_BUSY"}, nil
	}

	fp, summary, err := s.autoCartographerV633Fingerprint(token)
	if err != nil {
		autoCartographerV633Log("TICK_ERROR", "error", err.Error())
		return nil, err
	}
	now := utcNow()

	autoCartographerV633Runtime.Lock()
	loadAutoCartographerV633Locked()
	st := &autoCartographerV633Runtime.state
	st.Enabled = true
	st.IntervalSeconds = 60
	st.ProbeRegions = append([]int(nil), autoCartographerV633ProbeRegions...)
	st.LastProbeAt = now

	if st.LastFingerprint == "" {
		st.LastFingerprint = fp
		st.LastChangeAt = now
		st.CandidateFingerprint = ""
		st.CandidateCount = 0
		_ = saveAutoCartographerV633Locked()
		autoCartographerV633Runtime.Unlock()
		autoCartographerV633Log("BASELINE", "fingerprint", fp)
		return map[string]any{"ok": true, "status": "baseline", "fingerprint": fp, "probe": summary}, nil
	}

	if fp == st.LastFingerprint {
		st.CandidateFingerprint = ""
		st.CandidateCount = 0
		if known, ok := st.Contexts[fp]; ok {
			known.LastSeen = now
			st.Contexts[fp] = known
		}
		_ = saveAutoCartographerV633Locked()
		autoCartographerV633Runtime.Unlock()
		autoCartographerV633Log("UNCHANGED", "fingerprint", fp)
		return map[string]any{"ok": true, "status": "unchanged", "fingerprint": fp, "probe": summary}, nil
	}

	if fp == st.CandidateFingerprint {
		st.CandidateCount++
	} else {
		st.CandidateFingerprint = fp
		st.CandidateCount = 1
	}
	confirmations := st.CandidateCount
	_ = saveAutoCartographerV633Locked()
	autoCartographerV633Runtime.Unlock()

	autoCartographerV633Log("CHANGE_CANDIDATE", "fingerprint", fp, "confirmations", confirmations)
	if confirmations < 2 {
		return map[string]any{"ok": true, "status": "candidate", "fingerprint": fp, "confirmations": confirmations, "probe": summary}, nil
	}

	s.autoCartographerV633FullMap(token, fp)
	autoCartographerV633Log("CHANGE_CONFIRMED", "fingerprint", fp)
	return map[string]any{"ok": true, "status": "mapped", "fingerprint": fp, "confirmations": confirmations, "probe": summary}, nil
}
