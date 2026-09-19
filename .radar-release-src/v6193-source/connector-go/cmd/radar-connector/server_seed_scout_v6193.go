package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"wfgg-radar-connector/internal/protocol"
)

// WFGG_RADAR_SEED_SCOUT_V6193
//
// Seed Scout is deliberately separate from Collector cycles. It performs one
// read-only map-region observation per candidate server and keeps only aggregate
// server counts in memory. It never calls collectorStartCycle, collectorIngest,
// profile enrichment, or any Last War mutation command.
const (
	seedScoutVersionV6193           = "v6.19.3"
	seedScoutDefaultLimitV6193      = 8
	seedScoutMaxLimitV6193          = 20
	seedScoutDefaultRegionV6193     = 4
	seedScoutDefaultMinPlayersV6193 = 20
	seedScoutRegularServerMaxV6193  = 7999
)

type seedScoutStartRequestV6193 struct {
	Token            string `json:"token"`
	Limit            int    `json:"limit,omitempty"`
	Region           *int   `json:"region,omitempty"`
	MinTargetPlayers int    `json:"minTargetPlayers,omitempty"`
}

type seedScoutServerCountV6193 struct {
	ServerID string `json:"serverId"`
	Players  int    `json:"players"`
}

type seedScoutAttemptV6193 struct {
	CandidateServer string                      `json:"candidateServer"`
	Status          string                      `json:"status"`
	PlayersDecoded  int                         `json:"playersDecoded"`
	TargetPlayers   int                         `json:"targetPlayers"`
	ObservedServers []seedScoutServerCountV6193 `json:"observedServers"`
	NovelServers    []seedScoutServerCountV6193 `json:"novelServers"`
	Requests        int                         `json:"requests,omitempty"`
	Packets         int                         `json:"packets,omitempty"`
	Error           string                      `json:"error,omitempty"`
}

type seedScoutRecommendationV6193 struct {
	ServerID string `json:"serverId"`
	Command  string `json:"command"`
	Players  int    `json:"players"`
	Reason   string `json:"reason"`
}

type seedScoutJobV6193 struct {
	ID                  string                        `json:"id"`
	Status              string                        `json:"status"`
	Phase               string                        `json:"phase"`
	ScoutVersion        string                        `json:"scoutVersion"`
	Readonly            bool                          `json:"readonly"`
	CollectorMutation   bool                          `json:"collectorMutation"`
	CyclesCreated       int                           `json:"cyclesCreated"`
	ProfilesEnriched    int                           `json:"profilesEnriched"`
	RegionsPerCandidate int                           `json:"regionsPerCandidate"`
	Region              int                           `json:"region"`
	MinTargetPlayers    int                           `json:"minTargetPlayers"`
	KnownServerCount    int                           `json:"knownServerCount"`
	Candidates          []string                      `json:"candidates"`
	CandidateIndex      int                           `json:"candidateIndex"`
	Attempts            []seedScoutAttemptV6193       `json:"attempts"`
	RecommendedSeed     *seedScoutRecommendationV6193 `json:"recommendedSeed,omitempty"`
	StartedAt           string                        `json:"startedAt"`
	UpdatedAt           string                        `json:"updatedAt"`
	FinishedAt          string                        `json:"finishedAt,omitempty"`
}

type seedScoutStoreV6193 struct {
	mu   sync.RWMutex
	jobs map[string]*seedScoutJobV6193
}

var radarSeedScoutJobsV6193 = &seedScoutStoreV6193{jobs: map[string]*seedScoutJobV6193{}}

func newSeedScoutJobIDV6193() string {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err == nil {
		return hex.EncodeToString(b)
	}
	return strconv.FormatInt(time.Now().UnixNano(), 36)
}

func cloneSeedScoutJobV6193(src *seedScoutJobV6193) seedScoutJobV6193 {
	if src == nil {
		return seedScoutJobV6193{}
	}
	out := *src
	out.Candidates = append([]string(nil), src.Candidates...)
	out.Attempts = append([]seedScoutAttemptV6193(nil), src.Attempts...)
	for i := range out.Attempts {
		out.Attempts[i].ObservedServers = append([]seedScoutServerCountV6193(nil), src.Attempts[i].ObservedServers...)
		out.Attempts[i].NovelServers = append([]seedScoutServerCountV6193(nil), src.Attempts[i].NovelServers...)
	}
	if src.RecommendedSeed != nil {
		x := *src.RecommendedSeed
		out.RecommendedSeed = &x
	}
	return out
}

func (s *seedScoutStoreV6193) add(job *seedScoutJobV6193) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.jobs) >= 64 {
		var oldestID string
		var oldest string
		for id, item := range s.jobs {
			if item.Status == "RUNNING" || item.Status == "QUEUED" {
				continue
			}
			if oldestID == "" || item.UpdatedAt < oldest {
				oldestID, oldest = id, item.UpdatedAt
			}
		}
		if oldestID != "" {
			delete(s.jobs, oldestID)
		}
	}
	s.jobs[job.ID] = job
}

func (s *seedScoutStoreV6193) update(id string, fn func(*seedScoutJobV6193)) (seedScoutJobV6193, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[id]
	if job == nil {
		return seedScoutJobV6193{}, false
	}
	fn(job)
	job.UpdatedAt = utcNow()
	out := cloneSeedScoutJobV6193(job)
	return out, true
}

func (s *seedScoutStoreV6193) get(id string) (seedScoutJobV6193, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	job := s.jobs[id]
	if job == nil {
		return seedScoutJobV6193{}, false
	}
	return cloneSeedScoutJobV6193(job), true
}

func seedScoutKnownV6193(census serverCensusPayloadV612) map[string]bool {
	known := map[string]bool{}
	for _, row := range census.Servers {
		sid := strings.TrimSpace(row.ServerID)
		if sid != "" {
			known[sid] = true
		}
	}
	return known
}

func seedScoutRegularKnownIntsV6193(census serverCensusPayloadV612) []int {
	seen := map[int]bool{}
	out := []int{}
	for _, row := range census.Servers {
		n, err := strconv.Atoi(strings.TrimSpace(row.ServerID))
		if err != nil || n <= 0 || n > seedScoutRegularServerMaxV6193 || seen[n] {
			continue
		}
		seen[n] = true
		out = append(out, n)
	}
	sort.Ints(out)
	return out
}

func seedScoutNearestDistanceV6193(value int, known []int) int {
	best := int(^uint(0) >> 1)
	for _, n := range known {
		d := n - value
		if d < 0 {
			d = -d
		}
		if d < best {
			best = d
		}
	}
	return best
}

// Numeric proximity orders probes only; it never infers cluster membership.
func seedScoutCandidateSequenceV6193(census serverCensusPayloadV612, limit int) []string {
	if limit <= 0 {
		limit = seedScoutDefaultLimitV6193
	}
	if limit > seedScoutMaxLimitV6193 {
		limit = seedScoutMaxLimitV6193
	}
	knownInts := seedScoutRegularKnownIntsV6193(census)
	if len(knownInts) == 0 {
		return nil
	}
	known := map[int]bool{}
	for _, n := range knownInts {
		known[n] = true
	}
	minID, maxID := knownInts[0], knownInts[len(knownInts)-1]

	gaps := []int{}
	for n := minID; n <= maxID; n++ {
		if !known[n] {
			gaps = append(gaps, n)
		}
	}
	sort.Slice(gaps, func(i, j int) bool {
		di := seedScoutNearestDistanceV6193(gaps[i], knownInts)
		dj := seedScoutNearestDistanceV6193(gaps[j], knownInts)
		if di != dj {
			return di < dj
		}
		return gaps[i] < gaps[j]
	})

	out := make([]string, 0, limit)
	add := func(n int) {
		if len(out) >= limit || n <= 0 || n > seedScoutRegularServerMaxV6193 || known[n] {
			return
		}
		id := strconv.Itoa(n)
		for _, existing := range out {
			if existing == id {
				return
			}
		}
		out = append(out, id)
	}
	for _, n := range gaps {
		add(n)
		if len(out) >= limit {
			return out
		}
	}
	for step := 1; len(out) < limit && step <= seedScoutRegularServerMaxV6193; step++ {
		add(maxID + step)
		add(minID - step)
	}
	return out
}

func seedScoutAggregateV6193(players []protocol.Player, known map[string]bool) ([]seedScoutServerCountV6193, []seedScoutServerCountV6193) {
	counts := map[string]int{}
	for _, player := range players {
		sid := strings.TrimSpace(player.ServerID)
		if sid == "" {
			continue
		}
		counts[sid]++
	}
	rows := make([]seedScoutServerCountV6193, 0, len(counts))
	novel := make([]seedScoutServerCountV6193, 0, len(counts))
	for sid, count := range counts {
		row := seedScoutServerCountV6193{ServerID: sid, Players: count}
		rows = append(rows, row)
		if !known[sid] {
			novel = append(novel, row)
		}
	}
	sortRows := func(items []seedScoutServerCountV6193) {
		sort.Slice(items, func(i, j int) bool {
			if items[i].Players != items[j].Players {
				return items[i].Players > items[j].Players
			}
			ni, ei := strconv.Atoi(items[i].ServerID)
			nj, ej := strconv.Atoi(items[j].ServerID)
			if ei == nil && ej == nil && ni != nj {
				return ni < nj
			}
			return items[i].ServerID < items[j].ServerID
		})
	}
	sortRows(rows)
	sortRows(novel)
	return rows, novel
}

func seedScoutRecommendationV6193(candidate string, observed, novel []seedScoutServerCountV6193, minPlayers int) *seedScoutRecommendationV6193 {
	for _, row := range observed {
		if row.ServerID == candidate && row.Players >= minPlayers {
			return &seedScoutRecommendationV6193{
				ServerID: candidate,
				Command:  "@federated:" + candidate,
				Players:  row.Players,
				Reason:   "target_server_observed_in_single_region",
			}
		}
	}
	if len(novel) > 0 && novel[0].Players >= minPlayers {
		return &seedScoutRecommendationV6193{
			ServerID: novel[0].ServerID,
			Command:  "@federated:" + novel[0].ServerID,
			Players:  novel[0].Players,
			Reason:   "novel_server_observed_in_single_region",
		}
	}
	return nil
}

func (s *server) runSeedScoutV6193(jobID, token string, census serverCensusPayloadV612) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	scanner, ok := s.game.(protocol.FederatedRegionDiagnosticScanner)
	if !ok {
		radarSeedScoutJobsV6193.update(jobID, func(job *seedScoutJobV6193) {
			job.Status = "FAILED"
			job.Phase = "SCANNER_UNAVAILABLE"
			job.FinishedAt = utcNow()
		})
		return
	}
	known := seedScoutKnownV6193(census)
	job, ok := radarSeedScoutJobsV6193.get(jobID)
	if !ok {
		return
	}
	radarSeedScoutJobsV6193.update(jobID, func(j *seedScoutJobV6193) {
		j.Status = "RUNNING"
		j.Phase = "SCOUTING"
	})

	for idx, candidate := range job.Candidates {
		if ctx.Err() != nil {
			radarSeedScoutJobsV6193.update(jobID, func(j *seedScoutJobV6193) {
				j.Status = "FAILED"
				j.Phase = "TIMEOUT"
				j.FinishedAt = utcNow()
			})
			return
		}
		radarSeedScoutJobsV6193.update(jobID, func(j *seedScoutJobV6193) {
			j.CandidateIndex = idx + 1
			j.Phase = "SCOUTING"
		})

		players, diag, err := scanner.ScanPlayerRegionDiagnosticOnServer(ctx, token, "*", job.Region, candidate)
		attempt := seedScoutAttemptV6193{
			CandidateServer: candidate,
			Status:          "OBSERVED",
			PlayersDecoded:  len(players),
			Requests:        diag.Requests,
			Packets:         diag.Packets,
		}
		if err != nil {
			attempt.Status = "ERROR"
			attempt.Error = err.Error()
			radarSeedScoutJobsV6193.update(jobID, func(j *seedScoutJobV6193) {
				j.Attempts = append(j.Attempts, attempt)
			})
			if strings.Contains(err.Error(), "AUTH_REJECTED") {
				radarSeedScoutJobsV6193.update(jobID, func(j *seedScoutJobV6193) {
					j.Status = "FAILED"
					j.Phase = "AUTH_FAILED"
					j.FinishedAt = utcNow()
				})
				return
			}
			continue
		}

		observed, novel := seedScoutAggregateV6193(players, known)
		attempt.ObservedServers = observed
		attempt.NovelServers = novel
		for _, row := range observed {
			if row.ServerID == candidate {
				attempt.TargetPlayers = row.Players
				break
			}
		}
		if len(observed) == 0 {
			attempt.Status = "EMPTY"
		}
		recommendation := seedScoutRecommendationV6193(candidate, observed, novel, job.MinTargetPlayers)
		radarSeedScoutJobsV6193.update(jobID, func(j *seedScoutJobV6193) {
			j.Attempts = append(j.Attempts, attempt)
			if recommendation != nil {
				j.RecommendedSeed = recommendation
				j.Status = "SUCCESS"
				j.Phase = "FOUND"
				j.FinishedAt = utcNow()
			}
		})
		if recommendation != nil {
			return
		}
	}

	radarSeedScoutJobsV6193.update(jobID, func(j *seedScoutJobV6193) {
		j.Status = "SUCCESS"
		j.Phase = "EXHAUSTED"
		j.FinishedAt = utcNow()
	})
}

func (s *server) serverSeedScoutStartV6193(w http.ResponseWriter, r *http.Request, body []byte) {
	var input seedScoutStartRequestV6193
	if err := decodeJSON(body, &input); err != nil || len(strings.TrimSpace(input.Token)) < 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "GAME_TOKEN_REQUIRED"})
		return
	}
	limit := input.Limit
	if limit == 0 {
		limit = seedScoutDefaultLimitV6193
	}
	if limit < 1 || limit > seedScoutMaxLimitV6193 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "SEED_SCOUT_LIMIT_INVALID"})
		return
	}
	region := seedScoutDefaultRegionV6193
	if input.Region != nil {
		region = *input.Region
	}
	if region < 0 || region > 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "SEED_SCOUT_REGION_INVALID"})
		return
	}
	minPlayers := input.MinTargetPlayers
	if minPlayers == 0 {
		minPlayers = seedScoutDefaultMinPlayersV6193
	}
	if minPlayers < 1 || minPlayers > 500 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "SEED_SCOUT_MIN_PLAYERS_INVALID"})
		return
	}

	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}
	censusCtx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	census, err := runServerCensusV612(censusCtx, dbPath)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"ok": false, "scoutVersion": seedScoutVersionV6193, "readonly": true,
			"collectorMutation": false, "error": "SEED_SCOUT_CENSUS_UNAVAILABLE",
		})
		return
	}
	candidates := seedScoutCandidateSequenceV6193(census, limit)
	if len(candidates) == 0 {
		writeJSON(w, http.StatusConflict, map[string]any{
			"ok": false, "scoutVersion": seedScoutVersionV6193, "readonly": true,
			"collectorMutation": false, "error": "SEED_SCOUT_NO_CANDIDATES",
		})
		return
	}

	now := utcNow()
	job := &seedScoutJobV6193{
		ID:                  newSeedScoutJobIDV6193(),
		Status:              "QUEUED",
		Phase:               "QUEUED",
		ScoutVersion:        seedScoutVersionV6193,
		Readonly:            true,
		CollectorMutation:   false,
		CyclesCreated:       0,
		ProfilesEnriched:    0,
		RegionsPerCandidate: 1,
		Region:              region,
		MinTargetPlayers:    minPlayers,
		KnownServerCount:    len(census.Servers),
		Candidates:          candidates,
		Attempts:            []seedScoutAttemptV6193{},
		StartedAt:           now,
		UpdatedAt:           now,
	}
	radarSeedScoutJobsV6193.add(job)
	go s.runSeedScoutV6193(job.ID, strings.TrimSpace(input.Token), census)

	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": cloneSeedScoutJobV6193(job)})
}

func (s *server) serverSeedScoutStatusV6193(w http.ResponseWriter, r *http.Request, _ []byte) {
	id := strings.TrimSpace(r.URL.Query().Get("id"))
	if id == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "SEED_SCOUT_JOB_ID_REQUIRED"})
		return
	}
	job, ok := radarSeedScoutJobsV6193.get(id)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "SEED_SCOUT_JOB_NOT_FOUND"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "job": job})
}
