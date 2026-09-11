//go:build lastwar_native_template

package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"lastwar-client/internal/auth"
	"lastwar-client/internal/pcap"
	"lastwar-client/internal/sfs"
	"net"
	"net/netip"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

type sessionConfig struct {
	IP          string `json:"ip"`
	Port        int    `json:"port"`
	Zone        string `json:"zone"`
	GameUID     string `json:"gameUid"`
	DeviceID    string `json:"deviceId"`
	ShumeiBoxID string `json:"shumeiBoxId"`
	AccessToken string `json:"accessToken"`
	IOSMode     bool   `json:"iosMode"`
}

type playerReport struct {
	GameUID     string `json:"gameUid,omitempty"`
	Pseudo      string `json:"pseudo,omitempty"`
	ServerID    string `json:"serverId,omitempty"`
	AllianceID  string `json:"allianceId,omitempty"`
	AllianceTag string `json:"allianceTag,omitempty"`
	Rank        any    `json:"rank,omitempty"`
	HQLevel     *int64 `json:"hqLevel,omitempty"`
	Power       *int64 `json:"power,omitempty"`
	X           *int64 `json:"x,omitempty"`
	Y           *int64 `json:"y,omitempty"`
	ShieldState any    `json:"shieldState,omitempty"`
	ObservedAt  string `json:"observedAt,omitempty"`
}

type report struct {
	OK                bool           `json:"ok"`
	Mode              string         `json:"mode"`
	LoginResponse     string         `json:"loginResponse"`
	InitReceived      bool           `json:"initReceived"`
	NativeFields      int            `json:"nativeFields"`
	CopiedNative      int            `json:"copiedNative"`
	FreshDynamic      int            `json:"freshDynamic"`
	Zone              string         `json:"zone"`
	ServerID          string         `json:"serverId"`
	ResolvedAddress   string         `json:"resolvedAddress"`
	TopFields         int            `json:"topFields,omitempty"`
	Heroes            int            `json:"heroes,omitempty"`
	Buildings         int            `json:"buildings,omitempty"`
	Science           int            `json:"science,omitempty"`
	Pseudo            string         `json:"pseudo,omitempty"`
	InitTopKeys       []string       `json:"initTopKeys,omitempty"`
	ScanTemplateFound bool           `json:"scanTemplateFound,omitempty"`
	ScanCommand       string         `json:"scanCommand,omitempty"`
	ScanPerformed     bool           `json:"scanPerformed,omitempty"`
	Players           []playerReport `json:"players,omitempty"`
	ErrorCode         any            `json:"errorCode,omitempty"`
}

var dynamicKeys = map[string]bool{
	"_id":          true,
	"cmdBaseTime":  true,
	"SecurityCode": true,
	"OneCode":      true,
	"CoreV":        true,
	"psh":          true,
}

var pseudoKeys = map[string]bool{
	"pseudo":       true,
	"nickname":     true,
	"nick":         true,
	"playername":   true,
	"gamename":     true,
	"gameusername": true,
	"rolename":     true,
	"username":     true,
	"user_name":    true,
}

var uidKeys = keySet("uid", "gameuid", "game_uid", "userid", "user_id", "playerid", "player_id", "roleid", "role_id")
var serverKeys = keySet("serverid", "server_id", "server", "sid", "zoneid", "zone_id", "zone")
var allianceIDKeys = keySet("allianceid", "alliance_id", "unionid", "union_id", "guildid", "guild_id")
var allianceTagKeys = keySet("alliancetag", "alliance_tag", "uniontag", "union_tag", "guildtag", "guild_tag", "abbr", "abbreviation", "shortname")
var rankKeys = keySet("rank", "alliancerank", "alliance_rank", "unionrank", "union_rank", "position", "job")
var hqKeys = keySet("hqlevel", "hq_level", "headquarterlevel", "headquarter_level", "citylevel", "city_level", "baselevel", "base_level")
var powerKeys = keySet("power", "combatpower", "combat_power", "fightpower", "fight_power", "powernum", "power_num")
var xKeys = keySet("x", "posx", "pos_x", "coordx", "coord_x")
var yKeys = keySet("y", "posy", "pos_y", "coordy", "coord_y")
var pointKeys = keySet("pointid", "point_id", "worldpointid", "world_point_id", "posid", "pos_id")
var worldPosKeys = keySet("worldpos", "world_pos", "worldposition", "world_position")
var shieldKeys = keySet("shield", "shieldstate", "shield_state", "shieldstatus", "shield_status")

func main() {
	scanMode := len(os.Args) == 5 && os.Args[3] == "--scan-player"
	if (!scanMode && len(os.Args) != 3) || (scanMode && strings.TrimSpace(os.Args[4]) == "") {
		emit(report{OK: false, Mode: "native-template-readonly-v2", LoginResponse: "INVALID_ARGS"})
		os.Exit(2)
	}
	capturePath, sessionPath := os.Args[1], os.Args[2]
	query := ""
	seed := ""
	if scanMode {
		query = strings.TrimSpace(os.Args[4])
		seed = strings.TrimSpace(os.Getenv("LASTWAR_NATIVE_SCAN_SEED"))
		if seed == "" {
			seed = query
		}
	}

	var cfg sessionConfig
	sb, err := os.ReadFile(sessionPath)
	if err != nil {
		fail("SESSION_READ_FAILED", err)
	}
	if err := json.Unmarshal(sb, &cfg); err != nil {
		fail("SESSION_JSON_INVALID", err)
	}
	if strings.TrimSpace(cfg.AccessToken) == "" {
		fail("TOKEN_REQUIRED", nil)
	}

	data, err := os.ReadFile(capturePath)
	if err != nil {
		fail("CAPTURE_READ_FAILED", err)
	}
	packets, err := pcap.Parse(data)
	if err != nil {
		fail("CAPTURE_PARSE_FAILED", err)
	}
	convs := pcap.Conversations(packets)

	var nativeRoot, nativeLogin, nativeParams *sfs.SFSObject
	var server pcap.Endpoint
	var found bool

	for _, conv := range convs {
		if conv.TLS {
			continue
		}
		client, err := conv.Client(netip.Addr{})
		if err != nil {
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
			if root.GetInt("c") != 0 || root.GetInt("a") != 1 {
				continue
			}
			pv, ok := root.Get("p")
			if !ok {
				continue
			}
			login, ok := pv.Val.(*sfs.SFSObject)
			if !ok || login == nil {
				continue
			}
			ppv, ok := login.Get("p")
			if !ok {
				continue
			}
			params, ok := ppv.Val.(*sfs.SFSObject)
			if !ok || params == nil {
				continue
			}
			pkg := params.GetString("packageName")
			if pkg != "com.fun.lastwar.gp" && pkg != "com.lastwar.ios" {
				continue
			}
			if login.GetString("zn") != cfg.Zone {
				continue
			}

			nativeRoot, nativeLogin, nativeParams = root, login, params
			server = conv.A
			if server.Addr == client {
				server = conv.B
			}
			found = true
			break
		}
		if found {
			break
		}
	}
	if !found {
		fail("NATIVE_LOGIN_TEMPLATE_NOT_FOUND", nil)
	}

	var scanRoot *sfs.SFSObject
	scanCommand := ""
	unsafeCommand := ""
	if scanMode {
		scanRoot, scanCommand, unsafeCommand = findScanTemplate(convs, server, seed)
	}

	serverID := strings.TrimPrefix(cfg.Zone, "APS")
	generated := auth.BuildLoginParams(auth.LoginParamsInput{
		FutureID:    1,
		DeviceID:    cfg.DeviceID,
		AirKey:      "lwDid_" + base64Std(cfg.DeviceID),
		GameUid:     cfg.GameUID,
		AccessTok:   cfg.AccessToken,
		ServerID:    serverID,
		ShumeiBoxId: cfg.ShumeiBoxID,
		IOSMode:     cfg.IOSMode,
	})

	finalParams := sfs.NewSFSObject()
	copiedNative := 0
	freshDynamic := 0
	for _, key := range nativeParams.Keys() {
		nv, _ := nativeParams.Get(key)
		if dynamicKeys[key] {
			if gv, ok := generated.Get(key); ok {
				finalParams.PutValue(key, gv)
				freshDynamic++
				continue
			}
		}
		finalParams.PutValue(key, nv)
		copiedNative++
	}

	finalLogin := sfs.NewSFSObject()
	for _, key := range nativeLogin.Keys() {
		if key == "p" {
			finalLogin.PutSFSObject("p", finalParams)
			continue
		}
		v, _ := nativeLogin.Get(key)
		finalLogin.PutValue(key, v)
	}

	finalRoot := sfs.NewSFSObject()
	for _, key := range nativeRoot.Keys() {
		if key == "p" {
			finalRoot.PutSFSObject("p", finalLogin)
			continue
		}
		v, _ := nativeRoot.Get(key)
		finalRoot.PutValue(key, v)
	}

	body, err := sfs.EncodeObject(finalRoot)
	if err != nil {
		fail("LOGIN_ENCODE_FAILED", err)
	}
	frame, err := sfs.EncodePacket(body)
	if err != nil {
		fail("LOGIN_FRAME_FAILED", err)
	}

	base := report{
		Mode:            "native-template-readonly-v2",
		NativeFields:    len(nativeParams.Keys()),
		CopiedNative:    copiedNative,
		FreshDynamic:    freshDynamic,
		Zone:            cfg.Zone,
		ServerID:        serverID,
		ResolvedAddress: server.String(),
		ScanCommand:     scanCommand,
	}
	if scanMode && scanRoot != nil {
		base.ScanTemplateFound = true
	}
	if scanMode && scanRoot == nil && unsafeCommand != "" {
		base.ScanCommand = unsafeCommand
		base.LoginResponse = "PLAYER_SCAN_TEMPLATE_UNSAFE"
		emit(base)
		os.Exit(5)
	}
	if scanMode && scanRoot == nil {
		base.LoginResponse = "PLAYER_SCAN_TEMPLATE_NOT_FOUND"
		emit(base)
		os.Exit(5)
	}

	conn, err := net.DialTimeout("tcp", server.String(), 10*time.Second)
	if err != nil {
		failWith(base, "DIAL_FAILED", err)
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(25 * time.Second))

	if _, err := conn.Write(frame); err != nil {
		failWith(base, "LOGIN_WRITE_FAILED", err)
	}

	loginOK := false
readLoginLoop:
	for i := 0; i < 240; i++ {
		rb, err := sfs.ReadPacket(conn)
		if err != nil {
			if ne, ok := err.(net.Error); ok && ne.Timeout() {
				break
			}
			failWith(base, "READ_FAILED", err)
		}
		obj, err := sfs.DecodeObject(rb)
		if err != nil {
			continue
		}

		if obj.GetInt("c") == 0 && obj.GetInt("a") == 1 {
			pv, _ := obj.Get("p")
			p, _ := pv.Val.(*sfs.SFSObject)
			if p == nil {
				base.LoginResponse = "INVALID"
				emit(base)
				os.Exit(3)
			}
			if ec, ok := p.Get("ec"); ok {
				base.LoginResponse = "REJECTED"
				base.ErrorCode = scalarNumber(ec.Val)
				emit(base)
				os.Exit(2)
			}
			base.LoginResponse = "OK"
			loginOK = true
			continue
		}

		if loginOK && obj.GetInt("c") == 1 {
			pv, ok := obj.Get("p")
			if !ok {
				continue
			}
			ext, ok := pv.Val.(*sfs.SFSObject)
			if !ok || ext == nil || ext.GetString("c") != "init" {
				continue
			}
			ppv, ok := ext.Get("p")
			if !ok {
				continue
			}
			initObj, ok := ppv.Val.(*sfs.SFSObject)
			if !ok || initObj == nil {
				continue
			}

			keys := append([]string(nil), initObj.Keys()...)
			sort.Strings(keys)
			if len(keys) > 256 {
				keys = keys[:256]
			}
			base.OK = true
			base.InitReceived = true
			base.TopFields = len(initObj.Keys())
			base.Heroes = arrayLen(initObj, "userHero")
			base.Buildings = arrayLen(initObj, "building_new")
			base.Science = arrayLen(initObj, "science_new")
			base.Pseudo = findPseudo(initObj, 0)
			base.InitTopKeys = keys
			if !scanMode {
				emit(base)
				return
			}
			break readLoginLoop
		}
	}

	if !loginOK {
		base.LoginResponse = "NO_RESPONSE"
		emit(base)
		os.Exit(4)
	}
	if !scanMode {
		base.OK = true
		base.LoginResponse = "OK"
		base.InitReceived = false
		emit(base)
		return
	}
	if !base.InitReceived {
		base.LoginResponse = "PLAYER_SCAN_INIT_REQUIRED"
		base.OK = false
		emit(base)
		os.Exit(6)
	}

	players, err := runPlayerScan(conn, scanRoot, seed, query, serverID)
	if err != nil {
		base.OK = false
		base.LoginResponse = err.Error()
		emit(base)
		os.Exit(7)
	}
	base.OK = true
	base.LoginResponse = "OK"
	base.ScanPerformed = true
	base.Players = players
	emit(base)
}

func findScanTemplate(convs []pcap.Conversation, server pcap.Endpoint, seed string) (*sfs.SFSObject, string, string) {
	if strings.TrimSpace(seed) == "" {
		return nil, "", ""
	}
	unsafe := ""
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
			if !ok || !containsExactString(root, seed, 0) {
				continue
			}
			if readonlyScanCommand(cmd) {
				return root, cmd, unsafe
			}
			if unsafe == "" {
				unsafe = cmd
			}
		}
	}
	return nil, "", unsafe
}

func extensionCommand(root *sfs.SFSObject) (string, bool) {
	if root == nil || root.GetInt("c") != 1 {
		return "", false
	}
	pv, ok := root.Get("p")
	if !ok {
		return "", false
	}
	ext, ok := pv.Val.(*sfs.SFSObject)
	if !ok || ext == nil {
		return "", false
	}
	cmd := strings.TrimSpace(ext.GetString("c"))
	return cmd, cmd != ""
}

func readonlyScanCommand(cmd string) bool {
	c := strings.ToLower(strings.TrimSpace(cmd))
	if c == "" || strings.HasPrefix(c, "push.") {
		return false
	}
	parts := strings.FieldsFunc(c, func(r rune) bool { return r == '.' || r == '_' || r == '-' || r == '/' })
	blocked := map[string]bool{
		"add": true, "del": true, "delete": true, "set": true, "change": true,
		"attack": true, "march": true, "donate": true, "buy": true, "purchase": true,
		"claim": true, "reward": true, "join": true, "quit": true, "kick": true,
		"upgrade": true, "train": true, "heal": true, "collect": true, "send": true,
		"use": true, "consume": true, "create": true, "dismiss": true, "appoint": true,
	}
	for _, p := range parts {
		if blocked[p] {
			return false
		}
	}
	for _, marker := range []string{"search", "find", "detail", "info", "profile", "query"} {
		if strings.Contains(c, marker) {
			return true
		}
	}
	return strings.HasPrefix(c, "world.get.") || strings.HasPrefix(c, "user.get.") || strings.HasPrefix(c, "player.get.") || strings.HasPrefix(c, "role.get.")
}

func runPlayerScan(conn net.Conn, template *sfs.SFSObject, seed, query, serverID string) ([]playerReport, error) {
	cloned, replaced := cloneReplaceObject(template, seed, query)
	if cloned == nil || replaced == 0 {
		return nil, errors.New("PLAYER_SCAN_QUERY_REPLACEMENT_FAILED")
	}
	body, err := sfs.EncodeObject(cloned)
	if err != nil {
		return nil, errors.New("PLAYER_SCAN_ENCODE_FAILED")
	}
	frame, err := sfs.EncodePacket(body)
	if err != nil {
		return nil, errors.New("PLAYER_SCAN_FRAME_FAILED")
	}
	_ = conn.SetDeadline(time.Now().Add(15 * time.Second))
	if _, err := conn.Write(frame); err != nil {
		return nil, errors.New("PLAYER_SCAN_WRITE_FAILED")
	}
	observedAt := time.Now().UTC().Format(time.RFC3339Nano)
	seen := map[string]bool{}
	players := make([]playerReport, 0, 8)
	for i := 0; i < 240; i++ {
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
		collectPlayers(obj, query, serverID, observedAt, &players, seen, 0)
		if len(players) > 0 {
			return players, nil
		}
	}
	return players, nil
}

func cloneReplaceObject(src *sfs.SFSObject, seed, query string) (*sfs.SFSObject, int) {
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
		nv, n := cloneReplaceValue(v, seed, query)
		replaced += n
		out.PutValue(key, nv)
	}
	return out, replaced
}

func cloneReplaceArray(src *sfs.SFSArray, seed, query string) (*sfs.SFSArray, int) {
	if src == nil {
		return nil, 0
	}
	out := sfs.NewSFSArray()
	replaced := 0
	for _, v := range src.Items() {
		nv, n := cloneReplaceValue(v, seed, query)
		replaced += n
		out.AddValue(nv)
	}
	return out, replaced
}

func cloneReplaceValue(v sfs.SFSValue, seed, query string) (sfs.SFSValue, int) {
	switch t := v.Val.(type) {
	case string:
		if strings.EqualFold(strings.TrimSpace(t), strings.TrimSpace(seed)) {
			return sfs.SFSValue{Type: v.Type, Val: query}, 1
		}
		return v, 0
	case *sfs.SFSObject:
		o, n := cloneReplaceObject(t, seed, query)
		return sfs.SFSValue{Type: v.Type, Val: o}, n
	case *sfs.SFSArray:
		a, n := cloneReplaceArray(t, seed, query)
		return sfs.SFSValue{Type: v.Type, Val: a}, n
	default:
		return v, 0
	}
}

func containsExactString(v any, target string, depth int) bool {
	if depth > 10 || v == nil {
		return false
	}
	switch t := v.(type) {
	case *sfs.SFSObject:
		for _, key := range t.Keys() {
			item, ok := t.Get(key)
			if ok && containsExactString(item.Val, target, depth+1) {
				return true
			}
		}
	case *sfs.SFSArray:
		for _, item := range t.Items() {
			if containsExactString(item.Val, target, depth+1) {
				return true
			}
		}
	case string:
		return strings.EqualFold(strings.TrimSpace(t), strings.TrimSpace(target))
	}
	return false
}

func collectPlayers(v any, query, fallbackServer, observedAt string, out *[]playerReport, seen map[string]bool, depth int) {
	if depth > 10 || v == nil || len(*out) >= 32 {
		return
	}
	switch t := v.(type) {
	case *sfs.SFSObject:
		if p, ok := playerFromObject(t, query, fallbackServer, observedAt); ok {
			key := p.GameUID + "\x00" + strings.ToLower(p.Pseudo) + "\x00" + ptrIntString(p.X) + ":" + ptrIntString(p.Y)
			if !seen[key] {
				seen[key] = true
				*out = append(*out, p)
			}
		}
		for _, key := range t.Keys() {
			item, ok := t.Get(key)
			if ok {
				collectPlayers(item.Val, query, fallbackServer, observedAt, out, seen, depth+1)
			}
		}
	case *sfs.SFSArray:
		for _, item := range t.Items() {
			collectPlayers(item.Val, query, fallbackServer, observedAt, out, seen, depth+1)
		}
	}
}

func playerFromObject(o *sfs.SFSObject, query, fallbackServer, observedAt string) (playerReport, bool) {
	pseudo, ok := lookupStringRecursive(o, normalizedSet(pseudoKeys), 3)
	if !ok {
		if name, nameOK := lookupStringRecursive(o, keySet("name"), 2); nameOK && strings.EqualFold(strings.TrimSpace(name), strings.TrimSpace(query)) {
			if _, uidOK := lookupScalarRecursive(o, uidKeys, 2); uidOK {
				pseudo, ok = name, true
			}
		}
	}
	if !ok || !strings.EqualFold(strings.TrimSpace(pseudo), strings.TrimSpace(query)) {
		return playerReport{}, false
	}

	p := playerReport{Pseudo: strings.TrimSpace(pseudo), ServerID: fallbackServer, ObservedAt: observedAt}
	if v, ok := lookupScalarRecursive(o, uidKeys, 3); ok {
		p.GameUID = scalarString(v)
	}
	if v, ok := lookupScalarRecursive(o, serverKeys, 3); ok {
		if s := scalarString(v); s != "" {
			p.ServerID = strings.TrimPrefix(s, "APS")
		}
	}
	if v, ok := lookupScalarRecursive(o, allianceIDKeys, 3); ok {
		p.AllianceID = scalarString(v)
	}
	if v, ok := lookupScalarRecursive(o, allianceTagKeys, 3); ok {
		p.AllianceTag = scalarString(v)
	}
	if v, ok := lookupScalarRecursive(o, rankKeys, 3); ok {
		p.Rank = scalarPublic(v)
	}
	if v, ok := lookupScalarRecursive(o, hqKeys, 3); ok {
		if n, ok := scalarInt64(v); ok {
			p.HQLevel = int64Ptr(n)
		}
	}
	if v, ok := lookupScalarRecursive(o, powerKeys, 3); ok {
		if n, ok := scalarInt64(v); ok {
			p.Power = int64Ptr(n)
		}
	}
	if v, ok := lookupScalarRecursive(o, xKeys, 2); ok {
		if n, ok := scalarInt64(v); ok {
			p.X = int64Ptr(n)
		}
	}
	if v, ok := lookupScalarRecursive(o, yKeys, 2); ok {
		if n, ok := scalarInt64(v); ok {
			p.Y = int64Ptr(n)
		}
	}
	if p.X == nil || p.Y == nil {
		if v, ok := lookupScalarRecursive(o, pointKeys, 3); ok {
			if pointID, ok := scalarInt64(v); ok && pointID >= 1 && pointID <= 1000000 {
				n := pointID - 1
				x, y := n%1000, n/1000
				p.X, p.Y = int64Ptr(x), int64Ptr(y)
			}
		}
	}
	if v, ok := lookupScalarRecursive(o, worldPosKeys, 3); ok {
		if wp, ok := scalarInt64(v); ok && wp > 0 {
			u := uint64(wp)
			pointID := int64(u & 0xffffffff)
			if p.ServerID == "" {
				p.ServerID = strconv.FormatUint(u>>32, 10)
			}
			if (p.X == nil || p.Y == nil) && pointID >= 1 && pointID <= 1000000 {
				n := pointID - 1
				p.X, p.Y = int64Ptr(n%1000), int64Ptr(n/1000)
			}
		}
	}
	if v, ok := lookupScalarRecursive(o, shieldKeys, 3); ok {
		p.ShieldState = scalarPublic(v)
	}
	return p, true
}

func lookupStringRecursive(o *sfs.SFSObject, aliases map[string]bool, depth int) (string, bool) {
	v, ok := lookupScalarRecursive(o, aliases, depth)
	if !ok {
		return "", false
	}
	s, ok := v.(string)
	return strings.TrimSpace(s), ok && strings.TrimSpace(s) != ""
}

func lookupScalarRecursive(o *sfs.SFSObject, aliases map[string]bool, depth int) (any, bool) {
	if o == nil || depth < 0 {
		return nil, false
	}
	for _, key := range o.Keys() {
		v, ok := o.Get(key)
		if !ok {
			continue
		}
		if aliases[normKey(key)] && isScalar(v.Val) {
			return v.Val, true
		}
	}
	if depth == 0 {
		return nil, false
	}
	for _, key := range o.Keys() {
		v, ok := o.Get(key)
		if !ok {
			continue
		}
		switch t := v.Val.(type) {
		case *sfs.SFSObject:
			if got, ok := lookupScalarRecursive(t, aliases, depth-1); ok {
				return got, true
			}
		case *sfs.SFSArray:
			for i, item := range t.Items() {
				if i >= 64 {
					break
				}
				if child, ok := item.Val.(*sfs.SFSObject); ok {
					if got, ok := lookupScalarRecursive(child, aliases, depth-1); ok {
						return got, true
					}
				}
			}
		}
	}
	return nil, false
}

func isScalar(v any) bool {
	switch v.(type) {
	case string, byte, int16, int32, int64, float32, float64, bool:
		return true
	default:
		return false
	}
}

func scalarString(v any) string {
	switch t := v.(type) {
	case string:
		return strings.TrimSpace(t)
	case byte:
		return strconv.FormatUint(uint64(t), 10)
	case int16:
		return strconv.FormatInt(int64(t), 10)
	case int32:
		return strconv.FormatInt(int64(t), 10)
	case int64:
		return strconv.FormatInt(t, 10)
	default:
		return ""
	}
}

func scalarInt64(v any) (int64, bool) {
	switch t := v.(type) {
	case byte:
		return int64(t), true
	case int16:
		return int64(t), true
	case int32:
		return int64(t), true
	case int64:
		return t, true
	case float32:
		return int64(t), true
	case float64:
		return int64(t), true
	default:
		return 0, false
	}
}

func scalarPublic(v any) any {
	switch t := v.(type) {
	case string, bool, byte, int16, int32, int64, float32, float64:
		return t
	default:
		return nil
	}
}

func int64Ptr(v int64) *int64 { return &v }
func ptrIntString(v *int64) string {
	if v == nil {
		return ""
	}
	return strconv.FormatInt(*v, 10)
}

func keySet(keys ...string) map[string]bool {
	out := make(map[string]bool, len(keys))
	for _, k := range keys {
		out[normKey(k)] = true
	}
	return out
}

func normalizedSet(in map[string]bool) map[string]bool {
	out := make(map[string]bool, len(in))
	for k := range in {
		out[normKey(k)] = true
	}
	return out
}

func normKey(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	return strings.NewReplacer("_", "", "-", "", ".", "").Replace(s)
}

func findPseudo(v any, depth int) string {
	if depth > 6 || v == nil {
		return ""
	}
	switch t := v.(type) {
	case *sfs.SFSObject:
		for _, key := range t.Keys() {
			item, ok := t.Get(key)
			if !ok {
				continue
			}
			norm := normKey(key)
			if pseudoKeys[norm] {
				if s, ok := item.Val.(string); ok {
					s = strings.TrimSpace(s)
					if len(s) >= 2 && len(s) <= 64 {
						return s
					}
				}
			}
			if found := findPseudo(item.Val, depth+1); found != "" {
				return found
			}
		}
	case *sfs.SFSArray:
		for i, item := range t.Items() {
			if i >= 64 {
				break
			}
			if found := findPseudo(item.Val, depth+1); found != "" {
				return found
			}
		}
	}
	return ""
}

func base64Std(s string) string {
	const table = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
	b := []byte(s)
	out := make([]byte, 0, (len(b)+2)/3*4)
	for i := 0; i < len(b); i += 3 {
		var n uint32 = uint32(b[i]) << 16
		rem := len(b) - i
		if rem > 1 {
			n |= uint32(b[i+1]) << 8
		}
		if rem > 2 {
			n |= uint32(b[i+2])
		}
		out = append(out, table[(n>>18)&63], table[(n>>12)&63])
		if rem > 1 {
			out = append(out, table[(n>>6)&63])
		} else {
			out = append(out, '=')
		}
		if rem > 2 {
			out = append(out, table[n&63])
		} else {
			out = append(out, '=')
		}
	}
	return string(out)
}

func arrayLen(o *sfs.SFSObject, key string) int {
	v, ok := o.Get(key)
	if !ok {
		return 0
	}
	if a, ok := v.Val.(*sfs.SFSArray); ok && a != nil {
		return len(a.Items())
	}
	return 0
}

func scalarNumber(v any) any {
	switch n := v.(type) {
	case byte:
		return int(n)
	case int16:
		return int(n)
	case int32:
		return int(n)
	case int64:
		return n
	default:
		return "present"
	}
}

func emit(r report)               { _ = json.NewEncoder(os.Stdout).Encode(r) }
func fail(code string, err error) { failWith(report{Mode: "native-template-readonly-v2"}, code, err) }
func failWith(r report, code string, _ error) {
	r.OK = false
	r.LoginResponse = code
	emit(r)
	os.Exit(1)
}
