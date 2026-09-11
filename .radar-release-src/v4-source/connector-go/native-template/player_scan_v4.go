//go:build lastwar_native_template

package main

import (
	"errors"
	"fmt"
	"lastwar-client/internal/pcap"
	"lastwar-client/internal/sfs"
	"net"
	"os"
	"strconv"
	"strings"
	"time"
)

// V4 removes the last dependency on a captured world.get.block request.
// It builds the documented READONLY map request directly, while retaining
// V3's proven response decoder and get.user.info.multi enrichment path.
const (
	v4WorldSize       = 3000
	v4ServerSize      = 1000
	v4BlockSize       = 20
	v4WindowWidth     = 320
	v4WindowHeight    = 200
	v4ViewLevel       = 1
	v4IntArrayTag     byte = 12 // SFS2X INT_ARRAY wire tag
	v4SweepBudget          = 2800 * time.Millisecond
	v4OriginIdle           = 180 * time.Millisecond
	v4WriteTimeout         = 350 * time.Millisecond
	v4InterWriteDelay      = 3 * time.Millisecond
)

type scanDiagV42 struct {
	Requests        int
	Packets         int
	DecodeErrors    int
	Objects         int
	Arrays          int
	Blobs           int
	ProtoValid      int
	Kind6           int
	Detail10Present int
	Detail10Missing int
	DetailParseOK   int
	DetailParseFail int
	UIDPresent      int
	UIDMissing      int
	Name14Present   int
	Name14Missing   int
	PlayersDecoded  int
	QueryMatches    int
	Origins         int
	ReadTimeouts    int
}

func (d *scanDiagV42) emit() {
	if d == nil {
		return
	}
	// Safe diagnostics only: aggregate counters, never token/session/player values.
	fmt.Fprintf(os.Stderr,
		"WFGG_SCAN_V43 requests=%d packets=%d decode_errors=%d objects=%d arrays=%d blobs=%d proto=%d kind6=%d detail10_present=%d detail10_missing=%d detail_parse_ok=%d detail_parse_fail=%d uid_present=%d uid_missing=%d name14_present=%d name14_missing=%d decoded_players=%d query_matches=%d origins=%d read_timeouts=%d\n",
		d.Requests, d.Packets, d.DecodeErrors, d.Objects, d.Arrays, d.Blobs,
		d.ProtoValid, d.Kind6, d.Detail10Present, d.Detail10Missing,
		d.DetailParseOK, d.DetailParseFail, d.UIDPresent, d.UIDMissing,
		d.Name14Present, d.Name14Missing, d.PlayersDecoded, d.QueryMatches,
		d.Origins, d.ReadTimeouts,
	)
}

func (d *scanDiagV42) observe(v any, query, fallbackServer, observedAt string, depth, area int, serverID string) {
	if d == nil || depth > 12 || v == nil {
		return
	}
	switch t := v.(type) {
	case *sfs.SFSObject:
		d.Objects++
		if a := int(t.GetInt("maxAreaSize")); a > 0 && a <= 10000 {
			area = a
		}
		if sid := v3ScalarAt(t, "serverId"); sid != "" {
			serverID = strings.TrimPrefix(sid, "APS")
		}
		for _, key := range t.Keys() {
			item, ok := t.Get(key)
			if ok {
				d.observe(item.Val, query, fallbackServer, observedAt, depth+1, area, serverID)
			}
		}
	case *sfs.SFSArray:
		d.Arrays++
		for _, item := range t.Items() {
			d.observe(item.Val, query, fallbackServer, observedAt, depth+1, area, serverID)
		}
	case []byte:
		d.Blobs++
		m, ok := parseProtoV3(t, 0)
		if !ok {
			return
		}
		d.ProtoValid++
		kind, ok := protoUintV3(m, 2)
		if !ok || kind != 6 {
			return
		}
		d.Kind6++

		detailRaw, ok := protoBytesV3(m, 10)
		if !ok {
			d.Detail10Missing++
			return
		}
		d.Detail10Present++

		detail, ok := parseProtoV3(detailRaw, 1)
		if !ok {
			d.DetailParseFail++
			return
		}
		d.DetailParseOK++

		uid := protoScalarV3(detail, 1)
		if uid == "" {
			d.UIDMissing++
		} else {
			d.UIDPresent++
		}
		name := strings.TrimSpace(protoStringV3(detail, 14))
		if name == "" {
			d.Name14Missing++
		} else {
			d.Name14Present++
		}
		if uid == "" || name == "" {
			return
		}

		p, ok := playerFromMapBlobV3(t, area, serverID, fallbackServer, observedAt)
		if !ok {
			return
		}
		d.PlayersDecoded++
		if v3PlayerMatches(p, query) {
			d.QueryMatches++
		}
	}
}

func runPlayerScanV4(conn net.Conn, convs []pcap.Conversation, server pcap.Endpoint, mapTemplates []*sfs.SFSObject, profileTemplate *sfs.SFSObject, query, fallbackServer string) ([]playerReport, error) {
	query = strings.TrimSpace(query)
	if query == "" {
		return nil, errors.New("PLAYER_QUERY_REQUIRED")
	}
	observedAt := time.Now().UTC().Format(time.RFC3339Nano)

	players := scanCapturedMapV3(convs, server, query, fallbackServer, observedAt)
	if len(players) == 0 && len(mapTemplates) > 0 {
		var err error
		players, err = replayMapTemplatesV3(conn, mapTemplates, query, fallbackServer, observedAt)
		if err != nil {
			return nil, err
		}
	}

	if len(players) == 0 {
		var err error
		players, err = syntheticMapSweepV4(conn, query, fallbackServer, observedAt)
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

func syntheticMapSweepV4(conn net.Conn, query, fallbackServer, observedAt string) ([]playerReport, error) {
	serverID, err := strconv.Atoi(strings.TrimPrefix(strings.TrimSpace(fallbackServer), "APS"))
	if err != nil || serverID <= 0 {
		return nil, errors.New("PLAYER_SCAN_SERVER_ID_INVALID")
	}

	diag := &scanDiagV42{}
	defer diag.emit()

	origins := [][2]int{
		{1000, 1000},
		{0, 0}, {1000, 0}, {2000, 0},
		{0, 1000}, {2000, 1000},
		{0, 2000}, {1000, 2000}, {2000, 2000},
	}

	seen := map[string]bool{}
	out := make([]playerReport, 0, 4)
	requestID := time.Now().UnixNano() & 0x3fffffff
	sweepDeadline := time.Now().Add(v4SweepBudget)
	defer conn.SetDeadline(time.Time{})

	for _, origin := range origins {
		if !time.Now().Before(sweepDeadline) {
			break
		}
		diag.Origins++
		ox, oy := origin[0], origin[1]
		writesThisOrigin := 0

		for y0 := oy; y0 < oy+v4ServerSize; y0 += v4WindowHeight {
			y1 := minV4(y0+v4WindowHeight-1, oy+v4ServerSize-1)
			for x0 := ox; x0 < ox+v4ServerSize; x0 += v4WindowWidth {
				if !time.Now().Before(sweepDeadline) {
					break
				}
				x1 := minV4(x0+v4WindowWidth-1, ox+v4ServerSize-1)
				requestID++
				frame, err := buildMapFrameV4(serverID, x0, y0, x1, y1, requestID)
				if err != nil {
					return nil, errors.New("PLAYER_SCAN_SYNTHETIC_ENCODE_FAILED")
				}
				writeDeadline := minTimeV4(sweepDeadline, time.Now().Add(v4WriteTimeout))
				if err := conn.SetWriteDeadline(writeDeadline); err != nil {
					return nil, errors.New("PLAYER_SCAN_SYNTHETIC_DEADLINE_FAILED")
				}
				if _, err := conn.Write(frame); err != nil {
					if isTimeoutV4(err) {
						return nil, fmt.Errorf("PLAYER_SCAN_SYNTHETIC_WRITE_TIMEOUT:origin=%d,%d:writes=%d", ox, oy, writesThisOrigin)
					}
					return nil, fmt.Errorf("PLAYER_SCAN_SYNTHETIC_WRITE_FAILED:%T:%v:origin=%d,%d:writes=%d", err, err, ox, oy, writesThisOrigin)
				}
				diag.Requests++
				writesThisOrigin++
				time.Sleep(v4InterWriteDelay)
			}
		}

		readDeadline := minTimeV4(sweepDeadline, time.Now().Add(v4OriginIdle))
		if err := conn.SetReadDeadline(readDeadline); err != nil {
			return nil, errors.New("PLAYER_SCAN_SYNTHETIC_DEADLINE_FAILED")
		}
		for i := 0; i < 600; i++ {
			rb, err := sfs.ReadPacket(conn)
			if err != nil {
				if isTimeoutV4(err) {
					diag.ReadTimeouts++
					break
				}
				return nil, fmt.Errorf("PLAYER_SCAN_SYNTHETIC_READ_FAILED:%T:%v:origin=%d,%d:writes=%d:reads=%d", err, err, ox, oy, writesThisOrigin, i)
			}
			diag.Packets++
			obj, err := sfs.DecodeObject(rb)
			if err != nil {
				diag.DecodeErrors++
				continue
			}

			// V4.3 diagnostics traverse the decoded response in parallel with the
			// production collector. Only aggregate counters are emitted to stderr.
			diag.observe(obj, query, fallbackServer, observedAt, 0, 1000, fallbackServer)

			// Decode the payload itself instead of requiring the server to echo
			// world.get.block as the response command. The V3 collector is strict:
			// only protobuf world-point blobs that decode as player cities and whose
			// pseudo exactly matches the query are accepted.
			collectMapPlayersV3(obj, query, fallbackServer, observedAt, &out, seen, 0, 1000, fallbackServer)
			if len(out) > 0 {
				return out, nil
			}
		}
	}
	return out, nil
}

func buildMapFrameV4(serverID, x0, y0, x1, y1 int, requestID int64) ([]byte, error) {
	params := sfs.NewSFSObject()
	params.PutInt("bigMap", 1)
	params.PutInt("x", int32((x0+x1)/2))
	params.PutInt("y", int32((y0+y1)/2))
	params.PutInt("serverId", int32(serverID))
	params.PutInt("worldId", 0)
	params.PutInt("type", 0)
	params.PutInt("viewLvl", v4ViewLevel)
	params.PutLong("timeStamp", 0)
	params.PutInt("blockSize", v4BlockSize)
	params.PutValue("index", sfs.SFSValue{Type: v4IntArrayTag, Val: blockIndexesV4(x0, y0, x1, y1)})
	params.PutInt("clearUuidSet", 1)
	params.PutInt("leftBottom", int32(y0*v4WorldSize+x0))
	params.PutInt("rightTop", int32(y1*v4WorldSize+x1))
	params.PutLong("_id", requestID)

	ext := sfs.NewSFSObject()
	ext.PutUtfString("c", v3MapCommand)
	ext.PutInt("r", -1)
	ext.PutSFSObject("p", params)

	root := sfs.NewSFSObject()
	root.PutByte("c", 1)
	root.PutShort("a", 13)
	root.PutSFSObject("p", ext)

	body, err := sfs.EncodeObject(root)
	if err != nil {
		return nil, err
	}
	return sfs.EncodePacket(body)
}

func blockIndexesV4(x0, y0, x1, y1 int) []int32 {
	gridWidth := v4WorldSize / v4BlockSize
	bx0, bx1 := x0/v4BlockSize, x1/v4BlockSize
	by0, by1 := y0/v4BlockSize, y1/v4BlockSize
	out := make([]int32, 0, (bx1-bx0+1)*(by1-by0+1))
	for by := by0; by <= by1; by++ {
		for bx := bx0; bx <= bx1; bx++ {
			out = append(out, int32(by*gridWidth+bx))
		}
	}
	return out
}

func isTimeoutV4(err error) bool {
	var ne net.Error
	return errors.As(err, &ne) && ne.Timeout()
}

func minTimeV4(a, b time.Time) time.Time {
	if a.Before(b) {
		return a
	}
	return b
}

func minV4(a, b int) int {
	if a < b {
		return a
	}
	return b
}
