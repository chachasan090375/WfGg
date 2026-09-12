package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"wfgg-radar-connector/internal/protocol"
)

type collectorSearchRequest struct {
	Token string `json:"token"`
	Query string `json:"query"`
}

type collectorJob struct {
	ID          string         `json:"id"`
	Query       string         `json:"query"`
	Status      string         `json:"status"`
	Phase       string         `json:"phase"`
	Region      int            `json:"region"`
	Regions     int            `json:"regions"`
	CycleID     int64          `json:"cycleId,omitempty"`
	Joined      bool           `json:"joined"`
	PlayersSeen int            `json:"playersSeen"`
	Candidates int            `json:"candidates"`
	Enriched    int            `json:"enriched"`
	Player      map[string]any `json:"player,omitempty"`
	Error       string         `json:"error,omitempty"`
	StartedAt   string         `json:"startedAt"`
	UpdatedAt   string         `json:"updatedAt"`
	FinishedAt  string         `json:"finishedAt,omitempty"`
}

type collectorJobStore struct {
	mu   sync.RWMutex
	jobs map[string]*collectorJob
}

var radarCollectorJobs = &collectorJobStore{jobs: map[string]*collectorJob{}}

func utcNow() string { return time.Now().UTC().Format(time.RFC3339Nano) }

func newJobID() string {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err != nil {
		return strconv.FormatInt(time.Now().UnixNano(), 36)
	}
	return hex.EncodeToString(b)
}

func cloneJob(j *collectorJob) collectorJob {
	if j == nil {
		return collectorJob{}
	}
	out := *j
	if j.Player != nil {
		out.Player = make(map[string]any, len(j.Player))
		for k, v := range j.Player {
			out.Player[k] = v
		}
	}
	return out
}

func (s *collectorJobStore) add(query string) *collectorJob {
	now := utcNow()
	j := &collectorJob{ID: newJobID(), Query: query, Status: "QUEUED", Phase: "QUEUED", Regions: 9, StartedAt: now, UpdatedAt: now}
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.jobs) >= 128 {
		var oldestID string
		var oldest string
		for id, old := range s.jobs {
			if old.Status == "RUNNING" || old.Status == "QUEUED" {
				continue
			}
			if oldestID == "" || old.UpdatedAt < oldest {
				oldestID, oldest = id, old.UpdatedAt
			}
		}
		if oldestID != "" {
			delete(s.jobs, oldestID)
		}
	}
	s.jobs[j.ID] = j
	return j
}

func (s *collectorJobStore) update(id string, fn func(*collectorJob)) collectorJob {
	s.mu.Lock()
	defer s.mu.Unlock()
	j := s.jobs[id]
	if j == nil {
		return collectorJob{}
	}
	fn(j)
	j.UpdatedAt = utcNow()
	return cloneJob(j)
}

func (s *collectorJobStore) get(id string) (collectorJob, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	j := s.jobs[id]
	if j == nil {
		return collectorJob{}, false
	}
	return cloneJob(j), true
}

func (s *server) collectorSearchStart(w http.ResponseWriter, r *http.Request, body []byte) {
	var input collectorSearchRequest
	if err := decodeJSON(body, &input); err != nil || len(strings.TrimSpace(input.Token)) < 8 || strings.TrimSpace(input.Query) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "TOKEN_AND_QUERY_REQUIRED"})
		return
	}
	input.Query = strings.TrimSpace(input.Query)
	if len(input.Query) > 128 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PLAYER_QUERY_INVALID"})
		return
	}
	j := radarCollectorJobs.add(input.Query)
	// The token is captured only by this goroutine. It is never copied into the
	// job store, logs, Collector DB, or any persistent VPS file.
	go s.runCollectorSearch(j.ID, input.Token, input.Query)
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": cloneJob(j)})
}

func (s *server) collectorSearchStatus(w http.ResponseWriter, r *http.Request, _ []byte) {
	id := strings.TrimSpace(r.URL.Query().Get("id"))
	if id == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "JOB_ID_REQUIRED"})
		return
	}
	j, ok := radarCollectorJobs.get(id)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "JOB_NOT_FOUND"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "job": j})
}

func (s *server) runCollectorSearch(jobID, token, query string) {
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Minute)
	defer cancel()
	fail := func(code string) {
		radarCollectorJobs.update(jobID, func(j *collectorJob) {
			j.Status = "FAILED"
			j.Phase = "FAILED"
			j.Error = code
			j.FinishedAt = utcNow()
		})
	}

	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status = "RUNNING"; j.Phase = "STARTING" })
	cycle, joined, err := collectorStartCycle(ctx, query)
	if err != nil {
		fail("COLLECTOR_CYCLE_START_FAILED")
		return
	}
	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.CycleID = cycle.ID; j.Joined = joined })

	if joined {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "WAITING_FOR_CYCLE" })
		if err := waitCollectorCycle(ctx, cycle.ID); err != nil {
			fail("COLLECTOR_JOINED_CYCLE_FAILED")
			return
		}
		// A joined SEARCH did not own the running cycle. Refresh its own target
		// after that cycle, without attaching to the already completed cycle.
		if err := s.refreshSearchTarget(ctx, token, query, 0, jobID); err != nil && !errors.Is(err, errPlayerNotFound) {
			fail("COLLECTOR_TARGET_REFRESH_FAILED")
			return
		}
		player, _ := collectorGetPlayer(ctx, query)
		completeCollectorJob(jobID, player)
		return
	}

	regionScanner, ok := s.game.(protocol.RegionScanner)
	if !ok {
		_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "REGION_SCANNER_UNAVAILABLE")
		fail("REGION_SCANNER_UNAVAILABLE")
		return
	}

	for region := 0; region < 9; region++ {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "MAP"; j.Region = region + 1 })
		players, err := regionScanner.ScanPlayerRegion(ctx, token, "*", region)
		if err != nil {
			_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_REGION_FAILED")
			fail("MAP_REGION_FAILED")
			return
		}
		accepted, err := collectorIngest(ctx, players, cycle.ID)
		if err != nil {
			_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_INGEST_FAILED")
			fail("MAP_INGEST_FAILED")
			return
		}
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.PlayersSeen += accepted })
	}

	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "ENRICHING"; j.Region = 9 })
	uids, err := collectorChangedUIDs(ctx, cycle.ID)
	if err != nil {
		_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "DELTA_READ_FAILED")
		fail("DELTA_READ_FAILED")
		return
	}
	if target, err := collectorGetPlayer(ctx, query); err == nil {
		if uid := stringField(target, "game_uid", "gameUid"); uid != "" {
			uids = appendUnique(uids, uid)
		}
	}
	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Candidates = len(uids) })

	if len(uids) > 0 {
		profileScanner, ok := s.game.(protocol.ProfileScanner)
		if !ok {
			_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "PROFILE_SCANNER_UNAVAILABLE")
			fail("PROFILE_SCANNER_UNAVAILABLE")
			return
		}
		for start := 0; start < len(uids); start += 50 {
			end := start + 50
			if end > len(uids) { end = len(uids) }
			players, err := profileScanner.ScanProfiles(ctx, token, uids[start:end])
			if err != nil {
				_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "PROFILE_BATCH_FAILED")
				fail("PROFILE_BATCH_FAILED")
				return
			}
			accepted, err := collectorIngest(ctx, players, cycle.ID)
			if err != nil {
				_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "PROFILE_INGEST_FAILED")
				fail("PROFILE_INGEST_FAILED")
				return
			}
			radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Enriched += accepted })
		}
	}

	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })
	if err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", ""); err != nil {
		fail("COLLECTOR_CYCLE_FINISH_FAILED")
		return
	}
	player, _ := collectorGetPlayer(ctx, query)
	completeCollectorJob(jobID, player)
}

var errPlayerNotFound = errors.New("COLLECTOR_PLAYER_NOT_FOUND")

func (s *server) refreshSearchTarget(ctx context.Context, token, query string, cycleID int64, jobID string) error {
	player, err := collectorGetPlayer(ctx, query)
	if err != nil { return errPlayerNotFound }
	uid := stringField(player, "game_uid", "gameUid")
	if uid == "" { return errPlayerNotFound }
	profileScanner, ok := s.game.(protocol.ProfileScanner)
	if !ok { return errors.New("PROFILE_SCANNER_UNAVAILABLE") }
	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "ENRICHING"; j.Candidates = 1 })
	players, err := profileScanner.ScanProfiles(ctx, token, []string{uid})
	if err != nil { return err }
	accepted, err := collectorIngest(ctx, players, cycleID)
	if err != nil { return err }
	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Enriched += accepted })
	return nil
}

func completeCollectorJob(jobID string, player map[string]any) {
	radarCollectorJobs.update(jobID, func(j *collectorJob) {
		j.Status = "SUCCESS"
		j.Phase = "DONE"
		j.Player = player
		j.Error = ""
		j.FinishedAt = utcNow()
	})
}

type collectorCycle struct { ID int64 `json:"id"`; Status string `json:"status"` }

type collectorClientResponse struct {
	OK      bool             `json:"ok"`
	Joined  bool             `json:"joined"`
	Cycle   collectorCycle   `json:"cycle"`
	Changes []map[string]any `json:"changes"`
	Player  map[string]any   `json:"player"`
	Accepted int             `json:"accepted"`
}

func collectorBase() string {
	b := strings.TrimRight(strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_URL")), "/")
	if b == "" { b = "http://127.0.0.1:8790" }
	return b
}

func collectorJSON(ctx context.Context, method, path string, payload any, out any) error {
	var body io.Reader
	if payload != nil {
		raw, err := json.Marshal(payload); if err != nil { return err }
		body = bytes.NewReader(raw)
	}
	req, err := http.NewRequestWithContext(ctx, method, collectorBase()+path, body); if err != nil { return err }
	if payload != nil { req.Header.Set("Content-Type", "application/json") }
	client := &http.Client{Timeout: 90 * time.Second}
	resp, err := client.Do(req); if err != nil { return err }
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("collector http %d", resp.StatusCode)
	}
	return json.NewDecoder(io.LimitReader(resp.Body, 8<<20)).Decode(out)
}

func collectorStartCycle(ctx context.Context, query string) (collectorCycle, bool, error) {
	var r collectorClientResponse
	err := collectorJSON(ctx, http.MethodPost, "/cycle/start", map[string]any{"trigger":"SEARCH","query":query}, &r)
	return r.Cycle, r.Joined, err
}

func collectorCycleStatus(ctx context.Context, id int64) (collectorCycle, error) {
	var r collectorClientResponse
	err := collectorJSON(ctx, http.MethodGet, "/cycle/status?id="+strconv.FormatInt(id,10), nil, &r)
	return r.Cycle, err
}

func waitCollectorCycle(ctx context.Context, id int64) error {
	ticker := time.NewTicker(2*time.Second); defer ticker.Stop()
	for {
		cy, err := collectorCycleStatus(ctx,id); if err != nil { return err }
		if cy.Status != "RUNNING" {
			if cy.Status == "SUCCESS" { return nil }
			return errors.New("COLLECTOR_CYCLE_FAILED")
		}
		select { case <-ctx.Done(): return ctx.Err(); case <-ticker.C: }
	}
}

func collectorFinishCycle(ctx context.Context, id int64, status, errorCode string) error {
	var r collectorClientResponse
	return collectorJSON(ctx,http.MethodPost,"/cycle/finish",map[string]any{"cycleId":id,"status":status,"error":errorCode},&r)
}

func collectorIngest(ctx context.Context, players []protocol.Player, cycleID int64) (int,error) {
	total := 0
	for start:=0; start<len(players); start+=250 {
		end:=start+250; if end>len(players){end=len(players)}
		payload:=map[string]any{"players":players[start:end]}
		if cycleID>0 { payload["cycleId"]=cycleID }
		var r collectorClientResponse
		if err:=collectorJSON(ctx,http.MethodPost,"/ingest",payload,&r); err!=nil{return total,err}
		total += r.Accepted
	}
	return total,nil
}

func collectorChangedUIDs(ctx context.Context, cycleID int64) ([]string,error) {
	out:=[]string{}; seen:=map[string]bool{}; offset:=0
	for {
		var r collectorClientResponse
		path:="/cycle/changes?id="+strconv.FormatInt(cycleID,10)+"&limit=1000&offset="+strconv.Itoa(offset)
		if err:=collectorJSON(ctx,http.MethodGet,path,nil,&r); err!=nil{return nil,err}
		if len(r.Changes)==0 { break }
		newOnPage:=0
		for _,ch:=range r.Changes {
			uid:=stringField(ch,"game_uid","gameUid")
			if uid=="" { if a,ok:=ch["after"].(map[string]any);ok{uid=stringField(a,"game_uid","gameUid")} }
			if uid!=""&&!seen[uid]{seen[uid]=true;out=append(out,uid);newOnPage++}
		}
		if len(r.Changes)<1000 { break }
		if newOnPage==0 { return nil,errors.New("COLLECTOR_CHANGES_PAGINATION_REQUIRED") }
		offset += len(r.Changes)
		if offset>10000 { return nil,errors.New("COLLECTOR_CHANGE_LIMIT_EXCEEDED") }
	}
	return out,nil
}

func collectorGetPlayer(ctx context.Context, query string) (map[string]any,error) {
	var r collectorClientResponse
	path:="/player?q="+url.QueryEscape(query)
	if err:=collectorJSON(ctx,http.MethodGet,path,nil,&r);err!=nil{return nil,err}
	if r.Player==nil{return nil,errPlayerNotFound}
	return r.Player,nil
}

func stringField(m map[string]any, keys ...string) string {
	for _,k:=range keys { if v,ok:=m[k];ok { if s,ok:=v.(string);ok{return strings.TrimSpace(s)} } }
	return ""
}

func appendUnique(in []string, value string) []string {
	for _,v:=range in { if v==value{return in} }
	return append(in,value)
}
