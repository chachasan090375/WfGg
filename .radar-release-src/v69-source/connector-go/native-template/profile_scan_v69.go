//go:build lastwar_native_template

package main

import (
	"errors"
	"lastwar-client/internal/sfs"
	"net"
	"strings"
	"time"
)

// WFGG_RADAR_NATIVE_PROFILE_V69
// Native profile mode sends the captured read-only get.user.info.multi command
// directly. It never routes profile UIDs through the map/player search path.
type profileDiagnosticsV69 struct {
	Requested       int  `json:"requested"`
	Packets         int  `json:"packets"`
	DecodeErrors    int  `json:"decodeErrors"`
	CommandMatches  int  `json:"commandMatches"`
	ProfilesResolved int `json:"profilesResolved"`
	UIDsReplaced    bool `json:"uidsReplaced"`
}

func parseProfileUIDsV69(raw string) ([]string, error) {
	parts := strings.Split(strings.TrimSpace(raw), ",")
	seen := map[string]bool{}
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		uid := strings.TrimSpace(part)
		if uid == "" || seen[uid] {
			continue
		}
		if len(uid) > 96 {
			return nil, errors.New("PLAYER_PROFILE_BATCH_INVALID")
		}
		seen[uid] = true
		out = append(out, uid)
		if len(out) > 50 {
			return nil, errors.New("PLAYER_PROFILE_BATCH_INVALID")
		}
	}
	if len(out) == 0 {
		return nil, errors.New("PLAYER_PROFILE_BATCH_INVALID")
	}
	return out, nil
}

func replaceProfileUIDValueV69(v sfs.SFSValue, uids []string) (sfs.SFSValue, bool) {
	switch old := v.Val.(type) {
	case []string:
		return sfs.SFSValue{Type: v.Type, Val: append([]string(nil), uids...)}, true
	case string:
		// Preserve the captured wire type. A string-backed template is treated
		// as a comma-separated multi value; array-backed templates remain arrays.
		return sfs.SFSValue{Type: v.Type, Val: strings.Join(uids, ",")}, true
	case *sfs.SFSArray:
		a := sfs.NewSFSArray()
		itemType := sfs.SFSUtfString
		if old != nil && len(old.Items()) > 0 {
			itemType = old.Items()[0].Type
		}
		for _, uid := range uids {
			a.AddValue(sfs.SFSValue{Type: itemType, Val: uid})
		}
		return sfs.SFSValue{Type: v.Type, Val: a}, true
	default:
		return v, false
	}
}

func cloneProfileBatchObjectV69(src *sfs.SFSObject, uids []string, requestID int64) (*sfs.SFSObject, int) {
	if src == nil {
		return nil, 0
	}
	out := sfs.NewSFSObject()
	replaced := 0
	for _, key := range src.Keys() {
		v, ok := src.Get(key)
		if !ok {
			continue
		}
		nv, n := cloneProfileBatchValueV69(v, key, uids, requestID)
		replaced += n
		out.PutValue(key, nv)
	}
	return out, replaced
}

func cloneProfileBatchArrayV69(src *sfs.SFSArray, uids []string, requestID int64) (*sfs.SFSArray, int) {
	if src == nil {
		return nil, 0
	}
	out := sfs.NewSFSArray()
	replaced := 0
	for _, v := range src.Items() {
		nv, n := cloneProfileBatchValueV69(v, "", uids, requestID)
		replaced += n
		out.AddValue(nv)
	}
	return out, replaced
}

func cloneProfileBatchValueV69(v sfs.SFSValue, key string, uids []string, requestID int64) (sfs.SFSValue, int) {
	lk := strings.ToLower(strings.TrimSpace(key))
	if lk == "_id" {
		return sfs.SFSValue{Type: v.Type, Val: v3NumberLike(v.Val, requestID)}, 0
	}
	if lk == "allservers" {
		return sfs.SFSValue{Type: v.Type, Val: true}, 0
	}
	if lk == "uids" {
		if nv, ok := replaceProfileUIDValueV69(v, uids); ok {
			return nv, 1
		}
	}
	switch t := v.Val.(type) {
	case *sfs.SFSObject:
		o, n := cloneProfileBatchObjectV69(t, uids, requestID)
		return sfs.SFSValue{Type: v.Type, Val: o}, n
	case *sfs.SFSArray:
		a, n := cloneProfileBatchArrayV69(t, uids, requestID)
		return sfs.SFSValue{Type: v.Type, Val: a}, n
	default:
		return v, 0
	}
}

func runProfileScanV69(conn net.Conn, template *sfs.SFSObject, rawUIDs string) ([]playerReport, profileDiagnosticsV69, error) {
	uids, err := parseProfileUIDsV69(rawUIDs)
	diag := profileDiagnosticsV69{}
	if err != nil {
		return nil, diag, err
	}
	diag.Requested = len(uids)
	if template == nil {
		return nil, diag, errors.New("PLAYER_PROFILE_TEMPLATE_NOT_FOUND")
	}

	requestID := time.Now().UnixNano() & 0x3fffffff
	cloned, replaced := cloneProfileBatchObjectV69(template, uids, requestID)
	diag.UIDsReplaced = replaced > 0
	if cloned == nil || replaced == 0 {
		return nil, diag, errors.New("PLAYER_PROFILE_UIDS_FIELD_NOT_FOUND")
	}
	body, err := sfs.EncodeObject(cloned)
	if err != nil {
		return nil, diag, errors.New("PLAYER_PROFILE_ENCODE_FAILED")
	}
	frame, err := sfs.EncodePacket(body)
	if err != nil {
		return nil, diag, errors.New("PLAYER_PROFILE_FRAME_FAILED")
	}

	_ = conn.SetDeadline(time.Now().Add(8 * time.Second))
	if _, err := conn.Write(frame); err != nil {
		return nil, diag, errors.New("PLAYER_PROFILE_WRITE_FAILED")
	}

	observedAt := time.Now().UTC().Format(time.RFC3339Nano)
	resolved := map[string]playerReport{}
	for i := 0; i < 600 && len(resolved) < len(uids); i++ {
		rb, err := sfs.ReadPacket(conn)
		if err != nil {
			if ne, ok := err.(net.Error); ok && ne.Timeout() {
				break
			}
			return nil, diag, errors.New("PLAYER_PROFILE_READ_FAILED")
		}
		diag.Packets++
		obj, err := sfs.DecodeObject(rb)
		if err != nil {
			diag.DecodeErrors++
			continue
		}
		cmd, ok := extensionCommand(obj)
		if !ok || cmd != v3ProfileCommand {
			continue
		}
		diag.CommandMatches++
		for _, uid := range uids {
			if _, ok := resolved[uid]; ok {
				continue
			}
			if p, ok := findProfileV3(obj, uid, observedAt, 0); ok {
				resolved[uid] = p
			}
		}
	}

	out := make([]playerReport, 0, len(resolved))
	for _, uid := range uids {
		if p, ok := resolved[uid]; ok {
			out = append(out, p)
		}
	}
	diag.ProfilesResolved = len(out)
	if diag.CommandMatches == 0 {
		return nil, diag, errors.New("PLAYER_PROFILE_RESPONSE_NOT_OBSERVED")
	}
	return out, diag, nil
}
