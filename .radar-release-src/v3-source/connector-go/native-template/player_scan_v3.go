//go:build lastwar_native_template

package main

import (
	"bytes"
	"errors"
	"lastwar-client/internal/pcap"
	"lastwar-client/internal/sfs"
	"net"
	"net/netip"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	v3MapCommand     = "world.get.block"
	v3ProfileCommand = "get.user.info.multi"
	v3MaxMapRequests = 192
)

type protoField struct {
	n *uint64
	b []byte
}

type protoMessage map[int][]protoField

func findPlayerScanV3Templates(convs []pcap.Conversation, server pcap.Endpoint) ([]*sfs.SFSObject, *sfs.SFSObject) {
	maps := make([]*sfs.SFSObject, 0, 64)
	var profile *sfs.SFSObject
	seen := map[string]bool{}
	for _, conv := range convs {
		if conv.TLS {
			continue
		}
		client, err := conv.Client(netip.Addr{})
		if err != nil {
			continue
		}
		remote := conv.A
		if remote.Addr == client {
			remote = conv.B
		}
		if server.String() != "" && remote.String() != server.String() {
			continue
		}
		c2s, _ := conv.Reassemble(client)
		r := bytes.NewReader(c2s)
		for {
			body, err := sfs.ReadPacket(r)
			if err != nil {
				break
			}
			root, err := sfs.DecodeObject(body)
			if err != nil {
				continue
			}
			cmd, ok := extensionCommand(root)
			if !ok {
				continue
			}
			switch cmd {
			case v3MapCommand:
				if len(maps) >= v3MaxMapRequests {
					continue
				}
				key := v3RequestSignature(root)
				if !seen[key] {
					seen[key] = true
					maps = append(maps, root)
				}
			case v3ProfileCommand:
				if profile == nil {
					profile = root
				}
			}
		}
	}
	return maps, profile
}

func v3RequestSignature(root *sfs.SFSObject) string {
	params := extensionParams(root)
	if params == nil {
		return strconv.Itoa(len(root.Keys()))
	}
	parts := []string{v3ScalarAt(params, "serverId"), v3ScalarAt(params, "worldId"), v3ScalarAt(params, "x"), v3ScalarAt(params, "y"), v3ScalarAt(params, "viewLvl"), v3ScalarAt(params, "leftBottom"), v3ScalarAt(params, "rightTop")}
	return strings.Join(parts, ":")
}

func extensionParams(root *sfs.SFSObject) *sfs.SFSObject {
	if root == nil || root.GetInt("c") != 1 {
		return nil
	}
	pv, ok := root.Get("p")
	if !ok {
		return nil
	}
	ext, _ := pv.Val.(*sfs.SFSObject)
	if ext == nil {
		return nil
	}
	pp, ok := ext.Get("p")
	if !ok {
		return nil
	}
	params, _ := pp.Val.(*sfs.SFSObject)
	return params
}

func v3ScalarAt(o *sfs.SFSObject, key string) string {
	if o == nil {
		return ""
	}
	v, ok := o.Get(key)
	if !ok {
		return ""
	}
	return scalarString(v.Val)
}

func runPlayerScanV3(conn net.Conn, convs []pcap.Conversation, server pcap.Endpoint, mapTemplates []*sfs.SFSObject, profileTemplate *sfs.SFSObject, query, fallbackServer string) ([]playerReport, error) {
	query = strings.TrimSpace(query)
	if query == "" {
		return nil, errors.New("PLAYER_QUERY_REQUIRED")
	}
	observedAt := time.Now().UTC().Format(time.RFC3339Nano)

	players := scanCapturedMapV3(convs, server, query, fallbackServer, observedAt)
	if len(players) == 0 {
		var err error
		players, err = replayMapTemplatesV3(conn, mapTemplates, query, fallbackServer, observedAt)
		if err != nil {
			return nil, err
		}
	}
	if len(players) == 0 {
		return []playerReport{}, nil
	}

	for i := range players {
		if players[i].GameUID == "" {
			continue
		}
		if p, ok := capturedProfileV3(convs, server, players[i].GameUID, observedAt); ok {
			mergePlayerProfileV3(&players[i], p)
			continue
		}
		if profileTemplate != nil {
			p, ok, err := requestProfileV3(conn, profileTemplate, players[i].GameUID, observedAt)
			if err != nil {
				return nil, err
			}
			if ok {
				mergePlayerProfileV3(&players[i], p)
			}
		}
	}
	return players, nil
}

func scanCapturedMapV3(convs []pcap.Conversation, server pcap.Endpoint, query, fallbackServer, observedAt string) []playerReport {
	seen := map[string]bool{}
	out := make([]playerReport, 0, 4)
	for _, conv := range convs {
		if conv.TLS {
			continue
		}
		client, err := conv.Client(netip.Addr{})
		if err != nil {
			continue
		}
		remote := conv.A
		if remote.Addr == client {
			remote = conv.B
		}
		if server.String() != "" && remote.String() != server.String() {
			continue
		}
		_, s2c := conv.Reassemble(client)
		r := bytes.NewReader(s2c)
		for {
			body, err := sfs.ReadPacket(r)
			if err != nil {
				break
			}
			root, err := sfs.DecodeObject(body)
			if err != nil {
				continue
			}
			cmd, ok := extensionCommand(root)
			if !ok || cmd != v3MapCommand {
				continue
			}
			collectMapPlayersV3(root, query, fallbackServer, observedAt, &out, seen, 0, 1000, fallbackServer)
		}
	}
	return out
}

func replayMapTemplatesV3(conn net.Conn, templates []*sfs.SFSObject, query, fallbackServer, observedAt string) ([]playerReport, error) {
	if len(templates) == 0 {
		return nil, errors.New("PLAYER_SCAN_TEMPLATE_NOT_FOUND")
	}
	requestID := int64(time.Now().UnixNano() & 0x3fffffff)
	for i, template := range templates {
		cloned := cloneV3Object(template, v3CloneMap, "", requestID+int64(i)+1)
		body, err := sfs.EncodeObject(cloned)
		if err != nil {
			return nil, errors.New("PLAYER_SCAN_ENCODE_FAILED")
		}
		frame, err := sfs.EncodePacket(body)
		if err != nil {
			return nil, errors.New("PLAYER_SCAN_FRAME_FAILED")
		}
		if _, err := conn.Write(frame); err != nil {
			return nil, errors.New("PLAYER_SCAN_WRITE_FAILED")
		}
		time.Sleep(15 * time.Millisecond)
	}

	_ = conn.SetDeadline(time.Now().Add(12 * time.Second))
	seen := map[string]bool{}
	out := make([]playerReport, 0, 4)
	for i := 0; i < 1200; i++ {
		rb, err := sfs.ReadPacket(conn)
		if err != nil {
			if ne, ok := err.(net.Error); ok && ne.Timeout() {
				break
			}
			return nil, errors.New("PLAYER_SCAN_READ_FAILED")
		}
		obj, err := sfs.DecodeObject(rb)
		if err != nil {
			continue
		}
		cmd, ok := extensionCommand(obj)
		if !ok || cmd != v3MapCommand {
			continue
		}
		collectMapPlayersV3(obj, query, fallbackServer, observedAt, &out, seen, 0, 1000, fallbackServer)
		if len(out) > 0 {
			return out, nil
		}
	}
	return out, nil
}

func collectMapPlayersV3(v any, query, fallbackServer, observedAt string, out *[]playerReport, seen map[string]bool, depth, area int, serverID string) {
	if depth > 12 || v == nil || len(*out) >= 32 {
		return
	}
	switch t := v.(type) {
	case *sfs.SFSObject:
		if a := int(t.GetInt("maxAreaSize")); a > 0 && a <= 10000 {
			area = a
		}
		if sid := v3ScalarAt(t, "serverId"); sid != "" {
			serverID = strings.TrimPrefix(sid, "APS")
		}
		for _, key := range t.Keys() {
			item, ok := t.Get(key)
			if ok {
				collectMapPlayersV3(item.Val, query, fallbackServer, observedAt, out, seen, depth+1, area, serverID)
			}
		}
	case *sfs.SFSArray:
		for _, item := range t.Items() {
			collectMapPlayersV3(item.Val, query, fallbackServer, observedAt, out, seen, depth+1, area, serverID)
		}
	case []byte:
		if p, ok := playerFromMapBlobV3(t, area, serverID, fallbackServer, observedAt); ok && v3PlayerMatches(p, query) {
			key := p.GameUID + "\x00" + strings.ToLower(p.Pseudo)
			if !seen[key] {
				seen[key] = true
				*out = append(*out, p)
			}
	}
}

func playerFromMapBlobV3(blob []byte, area int, serverID, fallbackServer, observedAt string) (playerReport, bool) {
	m, ok := parseProtoV3(blob, 0)
	if !ok {
		return playerReport{}, false
	}
	kind, ok := protoUintV3(m, 2)
	if !ok || kind != 6 {
		return playerReport{}, false
	}
	detailRaw, ok := protoBytesV3(m, 10)
	if !ok {
		return playerReport{}, false
	}
	detail, ok := parseProtoV3(detailRaw, 1)
	if !ok {
		return playerReport{}, false
	}
	uid := protoScalarV3(detail, 1)
	name := strings.TrimSpace(protoStringV3(detail, 14))
	if uid == "" || name == "" {
		return playerReport{}, false
	}
	if area <= 0 {
		area = 1000
	}
	p := playerReport{GameUID: uid, Pseudo: name, ServerID: strings.TrimPrefix(serverID, "APS"), AllianceID: protoScalarV3(detail, 7), AllianceTag: protoStringV3(detail, 15), ObservedAt: observedAt}
	if p.ServerID == "" {
		p.ServerID = strings.TrimPrefix(protoScalarV3(m, 102), "APS")
	}
	if p.ServerID == "" {
		p.ServerID = strings.TrimPrefix(protoScalarV3(m, 103), "APS")
	}
	if p.ServerID == "" {
		p.ServerID = strings.TrimPrefix(fallbackServer, "APS")
	}
	if n, ok := protoUintV3(detail, 4); ok {
		x := int64(n)
		p.HQLevel = &x
	}
	if packed, ok := protoUintV3(m, 1); ok {
		x, y := int64(packed%uint64(area)), int64(packed/uint64(area))
		p.X, p.Y = &x, &y
	}
	return p, true
}

func capturedProfileV3(convs []pcap.Conversation, server pcap.Endpoint, uid, observedAt string) (playerReport, bool) {
	for _, conv := range convs {
		if conv.TLS {
			continue
		}
		client, err := conv.Client(netip.Addr{})
		if err != nil {
			continue
		}
		remote := conv.A
		if remote.Addr == client {
			remote = conv.B
		}
		if server.String() != "" && remote.String() != server.String() {
			continue
		}
		_, s2c := conv.Reassemble(client)
		r := bytes.NewReader(s2c)
		for {
			body, err := sfs.ReadPacket(r)
			if err != nil {
				break
			}
			root, err := sfs.DecodeObject(body)
			if err != nil {
				continue
			}
			cmd, ok := extensionCommand(root)
			if !ok || cmd != v3ProfileCommand {
				continue
			}
			if p, ok := findProfileV3(root, uid, observedAt, 0); ok {
				return p, true
			}
		}
	}
	return playerReport{}, false
}

func requestProfileV3(conn net.Conn, template *sfs.SFSObject, uid, observedAt string) (playerReport, bool, error) {
	cloned := cloneV3Object(template, v3CloneProfile, uid, int64(time.Now().UnixNano()&0x3fffffff))
	body, err := sfs.EncodeObject(cloned)
	if err != nil {
		return playerReport{}, false, errors.New("PLAYER_PROFILE_ENCODE_FAILED")
	}
	frame, err := sfs.EncodePacket(body)
	if err != nil {
		return playerReport{}, false, errors.New("PLAYER_PROFILE_FRAME_FAILED")
	}
	_ = conn.SetDeadline(time.Now().Add(6 * time.Second))
	if _, err := conn.Write(frame); err != nil {
		return playerReport{}, false, errors.New("PLAYER_PROFILE_WRITE_FAILED")
	}
	for i := 0; i < 360; i++ {
		rb, err := sfs.ReadPacket(conn)
		if err != nil {
			if ne, ok := err.(net.Error); ok && ne.Timeout() {
				break
			}
			return playerReport{}, false, errors.New("PLAYER_PROFILE_READ_FAILED")
		}
		obj, err := sfs.DecodeObject(rb)
		if err != nil {
			continue
		}
		cmd, ok := extensionCommand(obj)
		if !ok || cmd != v3ProfileCommand {
			continue
		}
		if p, ok := findProfileV3(obj, uid, observedAt, 0); ok {
			return p, true, nil
		}
	}
	return playerReport{}, false, nil
}

func findProfileV3(v any, uid, observedAt string, depth int) (playerReport, bool) {
	if depth > 12 || v == nil {
		return playerReport{}, false
	}
	switch t := v.(type) {
	case *sfs.SFSObject:
		if got := v3ScalarAt(t, "uid"); got != "" && got == uid {
			p := playerReport{GameUID: got, Pseudo: strings.TrimSpace(t.GetString("name")), ServerID: strings.TrimPrefix(firstNonEmptyV3(v3ScalarAt(t, "serverId"), v3ScalarAt(t, "currentServer"), v3ScalarAt(t, "srcServer")), "APS"), AllianceID: v3ScalarAt(t, "allianceId"), AllianceTag: t.GetString("allianceAbbrName"), ObservedAt: observedAt}
			if n, ok := v3IntField(t, "mainBuildingLevel", "level"); ok {
				p.HQLevel = &n
			}
			if n, ok := v3IntField(t, "power"); ok {
				p.Power = &n
			}
			return p, true
		}
		for _, key := range t.Keys() {
			item, ok := t.Get(key)
			if ok {
				if p, ok := findProfileV3(item.Val, uid, observedAt, depth+1); ok {
					return p, true
				}
			}
		}
	case *sfs.SFSArray:
		for _, item := range t.Items() {
			if p, ok := findProfileV3(item.Val, uid, observedAt, depth+1); ok {
				return p, true
			}
		}
	}
	return playerReport{}, false
}

func mergePlayerProfileV3(base *playerReport, profile playerReport) {
	if base == nil {
		return
	}
	if profile.Pseudo != "" {
		base.Pseudo = profile.Pseudo
	}
	if profile.ServerID != "" {
		base.ServerID = profile.ServerID
	}
	if profile.AllianceID != "" {
		base.AllianceID = profile.AllianceID
	}
	if profile.AllianceTag != "" {
		base.AllianceTag = profile.AllianceTag
	}
	if profile.HQLevel != nil {
		base.HQLevel = profile.HQLevel
	}
	if profile.Power != nil {
		base.Power = profile.Power
	}
}

func v3PlayerMatches(p playerReport, query string) bool {
	q := strings.TrimSpace(query)
	return (p.GameUID != "" && p.GameUID == q) || strings.EqualFold(strings.TrimSpace(p.Pseudo), q)
}

type v3CloneMode int

const (
	v3CloneMap v3CloneMode = iota
	v3CloneProfile
)

func cloneV3Object(src *sfs.SFSObject, mode v3CloneMode, uid string, requestID int64) *sfs.SFSObject {
	if src == nil {
		return nil
	}
	out := sfs.NewSFSObject()
	for _, key := range src.Keys() {
		v, ok := src.Get(key)
		if !ok {
			continue
		}
		nv := cloneV3Value(v, mode, uid, requestID, key)
		out.PutValue(key, nv)
	}
	return out
}

func cloneV3Array(src *sfs.SFSArray, mode v3CloneMode, uid string, requestID int64) *sfs.SFSArray {
	if src == nil {
		return nil
	}
	out := sfs.NewSFSArray()
	for _, v := range src.Items() {
		out.AddValue(cloneV3Value(v, mode, uid, requestID, ""))
	}
	return out
}

func cloneV3Value(v sfs.SFSValue, mode v3CloneMode, uid string, requestID int64, key string) sfs.SFSValue {
	lk := strings.ToLower(strings.TrimSpace(key))
	if lk == "_id" {
		return sfs.SFSValue{Type: v.Type, Val: v3NumberLike(v.Val, requestID)}
	}
	if mode == v3CloneMap && lk == "timestamp" {
		return sfs.SFSValue{Type: v.Type, Val: v3NumberLike(v.Val, 0)}
	}
	if mode == v3CloneProfile && lk == "allservers" {
		return sfs.SFSValue{Type: v.Type, Val: true}
	}
	if mode == v3CloneProfile && lk == "uids" {
		switch old := v.Val.(type) {
		case []string:
			return sfs.SFSValue{Type: v.Type, Val: []string{uid}}
		case string:
			return sfs.SFSValue{Type: v.Type, Val: uid}
		case *sfs.SFSArray:
			a := sfs.NewSFSArray()
			if old != nil && len(old.Items()) > 0 {
				a.AddValue(sfs.SFSValue{Type: old.Items()[0].Type, Val: uid})
			} else {
				a.AddValue(sfs.SFSValue{Type: sfs.SFSUtfString, Val: uid})
			}
			return sfs.SFSValue{Type: v.Type, Val: a}
		}
	}
	switch t := v.Val.(type) {
	case *sfs.SFSObject:
		return sfs.SFSValue{Type: v.Type, Val: cloneV3Object(t, mode, uid, requestID)}
	case *sfs.SFSArray:
		return sfs.SFSValue{Type: v.Type, Val: cloneV3Array(t, mode, uid, requestID)}
	default:
		return v
	}
}

func v3NumberLike(old any, n int64) any {
	switch old.(type) {
	case byte:
		return byte(n)
	case int16:
		return int16(n)
	case int32:
		return int32(n)
	case int64:
		return n
	case float32:
		return float32(n)
	case float64:
		return float64(n)
	default:
		return old
	}
}

func v3IntField(o *sfs.SFSObject, keys ...string) (int64, bool) {
	for _, key := range keys {
		v, ok := o.Get(key)
		if !ok {
			continue
		}
		if n, ok := scalarInt64(v.Val); ok {
			return n, true
		}
	}
	return 0, false
}

func firstNonEmptyV3(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

func parseProtoV3(buf []byte, depth int) (protoMessage, bool) {
	if len(buf) == 0 || depth > 5 {
		return nil, false
	}
	m := protoMessage{}
	pos := 0
	for pos < len(buf) {
		key, next, ok := readVarintV3(buf, pos)
		if !ok || key == 0 {
			return nil, false
		}
		pos = next
		field, wire := int(key>>3), int(key&7)
		var pf protoField
		switch wire {
		case 0:
			n, npos, ok := readVarintV3(buf, pos)
			if !ok {
				return nil, false
			}
			pos = npos
			pf.n = &n
		case 1:
			if pos+8 > len(buf) {
				return nil, false
			}
			n := uint64(0)
			for i := 7; i >= 0; i-- {
				n = (n << 8) | uint64(buf[pos+i])
			}
			pos += 8
			pf.n = &n
		case 2:
			ln, npos, ok := readVarintV3(buf, pos)
			if !ok || ln > uint64(len(buf)-npos) {
				return nil, false
			}
			pos = npos
			pf.b = append([]byte(nil), buf[pos:pos+int(ln)]...)
			pos += int(ln)
		case 5:
			if pos+4 > len(buf) {
				return nil, false
			}
			n := uint64(buf[pos]) | uint64(buf[pos+1])<<8 | uint64(buf[pos+2])<<16 | uint64(buf[pos+3])<<24
			pos += 4
			pf.n = &n
		default:
			return nil, false
		}
		m[field] = append(m[field], pf)
	}
	return m, len(m) > 0
}

func readVarintV3(buf []byte, pos int) (uint64, int, bool) {
	var out uint64
	for shift := uint(0); shift < 64 && pos < len(buf); shift += 7 {
		b := buf[pos]
		pos++
		out |= uint64(b&0x7f) << shift
		if b&0x80 == 0 {
			return out, pos, true
		}
	}
	return 0, pos, false
}

func protoUintV3(m protoMessage, field int) (uint64, bool) {
	for _, v := range m[field] {
		if v.n != nil {
			return *v.n, true
		}
	}
	return 0, false
}

func protoBytesV3(m protoMessage, field int) ([]byte, bool) {
	for _, v := range m[field] {
		if v.b != nil {
			return v.b, true
		}
	}
	return nil, false
}

func protoStringV3(m protoMessage, field int) string {
	b, ok := protoBytesV3(m, field)
	if !ok || !utf8.Valid(b) {
		return ""
	}
	s := strings.TrimSpace(string(b))
	for _, r := range s {
		if r < 0x20 && r != '\t' && r != '\n' && r != '\r' {
			return ""
		}
	}
	return s
}

func protoScalarV3(m protoMessage, field int) string {
	if s := protoStringV3(m, field); s != "" {
		return s
	}
	if n, ok := protoUintV3(m, field); ok {
		return strconv.FormatUint(n, 10)
	}
	return ""
}
