package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

// WFGG_RADAR_AUTOPILOT_V6194
//
// Autopilot chains complete targeted Collector cycles and Seed Scout discovery
// without requiring the browser to remain open. The Last War token is captured
// only by the runner goroutine and is never stored in the job, Collector DB,
// logs, or filesystem.
//
// Last War operations remain READ-ONLY. Collector mutation is expected because
// full targeted cycles are intentionally persisted as discovery evidence.
const (
	autopilotVersionV6194                    = "v6.19.4"
	autopilotDefaultFullCyclesV6194          = 3
	autopilotMaxFullCyclesV6194              = 5
	autopilotDefaultMaxClustersV6194         = 5
	autopilotMaxClustersV6194                = 20
	autopilotDefaultPartialRetryLimitV6194   = 5
	autopilotMaxPartialRetryLimitV6194       = 12
	autopilotDefaultFailureLimitV6194        = 3
	autopilotMaxFailureLimitV6194            = 8
	autopilotDefaultScoutLimitV6194          = 8
	autopilotDefaultScoutMaxBatchesV6194     = 20
	autopilotMaxScoutMaxBatchesV6194         = 64
	autopilotDefaultScoutRegionV6194         = 4
	autopilotDefaultScoutMinPlayersV6194     = 20
)

type autopilotStartRequestV6194 struct {
	Token                    string `json:"token"`
	InitialSeed              string `json:"initialSeed,omitempty"`
	FullCyclesPerCluster     int    `json:"fullCyclesPerCluster,omitempty"`
	MaxClusters              int    `json:"maxClusters,omitempty"`
	PartialRetryLimit        int    `json:"partialRetryLimit,omitempty"`
	ConsecutiveFailureLimit  int    `json:"consecutiveFailureLimit,omitempty"`
	ScoutLimit               int    `json:"scoutLimit,omitempty"`
	ScoutMaxBatches          int    `json:"scoutMaxBatches,omitempty"`
	ScoutRegion              *int   `json:"scoutRegion,omitempty"`
	ScoutMinPlayers          int    `json:"scoutMinPlayers,omitempty"`
}

type autopilotCycleResultV6194 struct {
	CycleID          int64  `json:"cycleId,omitempty"`
	Seed             string `json:"seed"`
	Classification   string `json:"classification"`
	RegionsCompleted int    `json:"regionsCompleted"`
	RegionsFailed    int    `json:"regionsFailed"`
	PlayersSeen      int    `json:"playersSeen"`
	ProfilesResolved int    `json:"profilesResolved,omitempty"`
	Error            string `json:"error,omitempty"`
	ObservedAt       string `json:"observedAt"`
}

type autopilotClusterResultV6194 struct {
	Seed             string   `json:"seed"`
	Command          string   `json:"command"`
	FullCycles       int      `json:"fullCycles"`
	PartialCycles    int      `json:"partialCycles"`
	FailedCycles     int      `json:"failedCycles"`
	CycleIDs         []int64  `json:"cycleIds"`
	ConfirmedAt      string   `json:"confirmedAt"`
}

type autopilotJobV6194 struct {
	ID                      string                          `json:"id"`
	Status                  string                          `json:"status"`
	Phase                   string                          `json:"phase"`
	AutopilotVersion        string                          `json:"autopilotVersion"`
	GameReadonly            bool                            `json:"gameReadonly"`
	GameMutation            bool                            `json:"gameMutation"`
	CollectorMutation       bool                            `json:"collectorMutation"`
	TokenPersisted          bool                            `json:"tokenPersisted"`
	BrowserRequired         bool                            `json:"browserRequired"`
	StopRequested           bool                            `json:"stopRequested"`
	CurrentSeed             string                          `json:"currentSeed,omitempty"`
	CurrentCommand          string                          `json:"currentCommand,omitempty"`
	RequiredFullCycles      int                             `json:"requiredFullCycles"`
	ValidatedCycles         int                             `json:"validatedCycles"`
	PartialCycles           int                             `json:"partialCycles"`
	FailedCycles            int                             `json:"failedCycles"`
	JoinedCycles            int                             `json:"joinedCycles"`
	ConsecutiveFailures     int                             `json:"consecutiveFailures"`
	PartialRetryLimit       int                             `json:"partialRetryLimit"`
	ConsecutiveFailureLimit int                             `json:"consecutiveFailureLimit"`
	MaxClusters             int                             `json:"maxClusters"`
	ConfirmedClusters       int                             `json:"confirmedClusters"`
	CurrentChildJobID       string                          `json:"currentChildJobId,omitempty"`
	CurrentScoutJobID       string                          `json:"currentScoutJobId,omitempty"`
	ScoutLimit              int                             `json:"scoutLimit"`
	ScoutMaxBatches         int                             `json:"scoutMaxBatches"`
	ScoutRegion             int                             `json:"scoutRegion"`
	ScoutMinPlayers         int                             `json:"scoutMinPlayers"`
	ScoutBatch              int                             `json:"scoutBatch"`
	ScoutOffset             int                             `json:"scoutOffset"`
	LastCycle               *autopilotCycleResultV6194     `json:"lastCycle,omitempty"`
	History                 []autopilotClusterResultV6194   `json:"history"`
	LastError               string                          `json:"lastError,omitempty"`
	StartedAt               string                          `json:"startedAt"`
	UpdatedAt               string                          `json:"updatedAt"`
	FinishedAt              string                          `json:"finishedAt,omitempty"`
}

type autopilotStoreV6194 struct {
	mu   sync.RWMutex
	jobs map[string]*autopilotJobV6194
}

var radarAutopilotJobsV6194 = &autopilotStoreV6194{jobs: map[string]*autopilotJobV6194{}}

func newAutopilotJobIDV6194() string {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err == nil {
		return hex.EncodeToString(b)
	}
	return strconv.FormatInt(time.Now().UnixNano(), 36)
}

func cloneAutopilotJobV6194(src *autopilotJobV6194) autopilotJobV6194 {
	if src == nil {
		return autopilotJobV6194{}
	}
	out := *src
	out.History = append([]autopilotClusterResultV6194(nil), src.History...)
	for i := range out.History {
		out.History[i].CycleIDs = append([]int64(nil), src.History[i].CycleIDs...)
	}
	if src.LastCycle != nil {
		x := *src.LastCycle
		out.LastCycle = &x
	}
	return out
}

func (s *autopilotStoreV6194) add(job *autopilotJobV6194) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.jobs) >= 32 {
		var oldestID, oldest string
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

func (s *autopilotStoreV6194) update(id string, fn func(*autopilotJobV6194)) (autopilotJobV6194, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[id]
	if job == nil {
		return autopilotJobV6194{}, false
	}
	fn(job)
	job.UpdatedAt = utcNow()
	return cloneAutopilotJobV6194(job), true
}

func (s *autopilotStoreV6194) get(id string) (autopilotJobV6194, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	job := s.jobs[id]
	if job == nil {
		return autopilotJobV6194{}, false
	}
	return cloneAutopilotJobV6194(job), true
}

func normalizeAutopilotSeedV6194(value string) (string, bool) {
	v := strings.TrimSpace(value)
	if v == "" {
		return "", true
	}
	if len(v) >= len("@federated:") && strings.EqualFold(v[:len("@federated:")], "@federated:") {
		v = strings.TrimSpace(v[len("@federated:"):])
	}
	if len(v) >= 3 && strings.EqualFold(v[:3], "APS") {
		v = strings.TrimSpace(v[3:])
	}
	n, err := strconv.Atoi(v)
	if err != nil || n <= 0 || n > 999999 {
		return "", false
	}
	return strconv.Itoa(n), true
}

func classifyAutopilotCycleV6194(job collectorJob) string {
	if job.Status != "SUCCESS" {
		return "FAILED"
	}
	if job.Joined {
		return "JOINED"
	}
	if job.RegionsCompleted == 9 && job.RegionsFailed == 0 {
		return "FULL"
	}
	return "PARTIAL"
}

func autopilotIsAuthFailureV6194(job collectorJob) bool {
	joined := strings.ToUpper(strings.Join([]string{
		job.Error, job.FailureCategory, job.FailureCode, job.FailureCause, job.AuthState,
	}, " "))
	return strings.Contains(joined, "AUTH")
}

func autopilotStoppedV6194(id string) bool {
	job, ok := radarAutopilotJobsV6194.get(id)
	return ok && job.StopRequested
}

func autopilotFailV6194(id, phase, errCode string) {
	radarAutopilotJobsV6194.update(id, func(job *autopilotJobV6194) {
		job.Status = "FAILED"
		job.Phase = phase
		job.LastError = errCode
		job.CurrentChildJobID = ""
		job.CurrentScoutJobID = ""
		job.FinishedAt = utcNow()
	})
}

func autopilotCompleteV6194(id, phase string) {
	radarAutopilotJobsV6194.update(id, func(job *autopilotJobV6194) {
		job.Status = "SUCCESS"
		job.Phase = phase
		job.CurrentChildJobID = ""
		job.CurrentScoutJobID = ""
		job.FinishedAt = utcNow()
	})
}

func (s *server) autopilotScoutNextSeedV6194(ctx context.Context, jobID, token string) (*seedScoutRecommendationV6193, string) {
	job, ok := radarAutopilotJobsV6194.get(jobID)
	if !ok {
		return nil, "AUTOPILOT_JOB_NOT_FOUND"
	}
	dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
	if dbPath == "" {
		dbPath = "/opt/wfgg-collector/data/collector.db"
	}

	offset := 0
	for batch := 1; batch <= job.ScoutMaxBatches; batch++ {
		if ctx.Err() != nil {
			return nil, "AUTOPILOT_TIMEOUT"
		}
		if autopilotStoppedV6194(jobID) {
			return nil, "AUTOPILOT_STOP_REQUESTED"
		}

		censusCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
		census, err := runServerCensusV612(censusCtx, dbPath)
		cancel()
		if err != nil {
			return nil, "AUTOPILOT_SCOUT_CENSUS_UNAVAILABLE"
		}
		candidates := seedScoutCandidateWindowV6193(census, offset, job.ScoutLimit)
		if len(candidates) == 0 {
			return nil, "AUTOPILOT_SCOUT_NO_CANDIDATES"
		}
		now := utcNow()
		scout := &seedScoutJobV6193{
			ID:                  newSeedScoutJobIDV6193(),
			Status:              "QUEUED",
			Phase:               "QUEUED",
			ScoutVersion:        seedScoutVersionV6193,
			Readonly:            true,
			CollectorMutation:   false,
			CyclesCreated:       0,
			ProfilesEnriched:    0,
			RegionsPerCandidate: 1,
			Region:              job.ScoutRegion,
			MinTargetPlayers:    job.ScoutMinPlayers,
			Offset:              offset,
			NextOffset:          offset + len(candidates),
			KnownServerCount:    len(census.Servers),
			Candidates:          candidates,
			Attempts:            []seedScoutAttemptV6193{},
			StartedAt:           now,
			UpdatedAt:           now,
		}
		radarSeedScoutJobsV6193.add(scout)
		radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
			a.Phase = "SCOUTING"
			a.ScoutBatch = batch
			a.ScoutOffset = offset
			a.CurrentScoutJobID = scout.ID
		})
		s.runSeedScoutV6193(scout.ID, token, census)
		finalScout, ok := radarSeedScoutJobsV6193.get(scout.ID)
		radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
			a.CurrentScoutJobID = ""
		})
		if !ok {
			return nil, "AUTOPILOT_SCOUT_JOB_LOST"
		}
		if finalScout.Status == "FAILED" {
			if finalScout.Phase == "AUTH_FAILED" {
				return nil, "AUTOPILOT_AUTH_FAILED"
			}
			return nil, "AUTOPILOT_SCOUT_FAILED:" + finalScout.Phase
		}
		if finalScout.RecommendedSeed != nil {
			rec := *finalScout.RecommendedSeed
			return &rec, ""
		}
		offset = finalScout.NextOffset
	}
	return nil, "AUTOPILOT_SCOUT_BATCH_LIMIT"
}

func (s *server) runAutopilotV6194(jobID, token string) {
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Hour)
	defer cancel()
	radarAutopilotJobsV6194.update(jobID, func(job *autopilotJobV6194) {
		job.Status = "RUNNING"
		job.Phase = "STARTING"
	})

	for {
		if ctx.Err() != nil {
			autopilotFailV6194(jobID, "TIMEOUT", "AUTOPILOT_TIMEOUT")
			return
		}
		if autopilotStoppedV6194(jobID) {
			autopilotCompleteV6194(jobID, "STOPPED")
			return
		}
		job, ok := radarAutopilotJobsV6194.get(jobID)
		if !ok {
			return
		}
		if job.ConfirmedClusters >= job.MaxClusters {
			autopilotCompleteV6194(jobID, "MAX_CLUSTERS_REACHED")
			return
		}

		if strings.TrimSpace(job.CurrentSeed) == "" {
			rec, errCode := s.autopilotScoutNextSeedV6194(ctx, jobID, token)
			if errCode != "" {
				if errCode == "AUTOPILOT_STOP_REQUESTED" {
					autopilotCompleteV6194(jobID, "STOPPED")
				} else if errCode == "AUTOPILOT_SCOUT_NO_CANDIDATES" || errCode == "AUTOPILOT_SCOUT_BATCH_LIMIT" {
					autopilotCompleteV6194(jobID, "NO_MORE_SEED")
				} else {
					autopilotFailV6194(jobID, "SCOUT_FAILED", errCode)
				}
				return
			}
			radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
				a.CurrentSeed = rec.ServerID
				a.CurrentCommand = rec.Command
				a.ValidatedCycles = 0
				a.PartialCycles = 0
				a.FailedCycles = 0
				a.JoinedCycles = 0
				a.ConsecutiveFailures = 0
				a.ScoutBatch = 0
				a.ScoutOffset = 0
				a.Phase = "COLLECTING"
			})
			continue
		}

		job, _ = radarAutopilotJobsV6194.get(jobID)
		command := "@federated:" + job.CurrentSeed
		child := radarCollectorJobs.add(command)
		radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
			a.Phase = "COLLECTING"
			a.CurrentCommand = command
			a.CurrentChildJobID = child.ID
		})
		s.runCollectorSearch(child.ID, token, command)
		final, found := radarCollectorJobs.get(child.ID)
		if !found {
			autopilotFailV6194(jobID, "COLLECTOR_FAILED", "AUTOPILOT_CHILD_JOB_LOST")
			return
		}
		classification := classifyAutopilotCycleV6194(final)
		cycleResult := &autopilotCycleResultV6194{
			CycleID:          final.CycleID,
			Seed:             job.CurrentSeed,
			Classification:   classification,
			RegionsCompleted: final.RegionsCompleted,
			RegionsFailed:    final.RegionsFailed,
			PlayersSeen:      final.PlayersSeen,
			Error:            final.Error,
			ObservedAt:       utcNow(),
		}
		if final.ProfileStats.Status != "" {
			cycleResult.ProfilesResolved = final.ProfileStats.ProfilesResolved
		}

		radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
			a.CurrentChildJobID = ""
			a.LastCycle = cycleResult
			switch classification {
			case "FULL":
				a.ValidatedCycles++
				a.ConsecutiveFailures = 0
				a.Phase = "CYCLE_FULL"
			case "PARTIAL":
				a.PartialCycles++
				a.ConsecutiveFailures = 0
				a.Phase = "CYCLE_PARTIAL_RETRY"
			case "JOINED":
				a.JoinedCycles++
				a.ConsecutiveFailures = 0
				a.Phase = "CYCLE_JOINED_RETRY"
			default:
				a.FailedCycles++
				a.ConsecutiveFailures++
				a.Phase = "CYCLE_FAILED_RETRY"
				a.LastError = final.Error
			}
		})

		if classification == "FAILED" && autopilotIsAuthFailureV6194(final) {
			autopilotFailV6194(jobID, "AUTH_FAILED", "AUTOPILOT_AUTH_FAILED")
			return
		}
		job, _ = radarAutopilotJobsV6194.get(jobID)
		if job.ConsecutiveFailures >= job.ConsecutiveFailureLimit {
			autopilotFailV6194(jobID, "FAILURE_LIMIT", "AUTOPILOT_CONSECUTIVE_FAILURE_LIMIT")
			return
		}
		if job.PartialCycles >= job.PartialRetryLimit && job.ValidatedCycles < job.RequiredFullCycles {
			autopilotFailV6194(jobID, "PARTIAL_RETRY_LIMIT", "AUTOPILOT_PARTIAL_RETRY_LIMIT")
			return
		}
		if job.ValidatedCycles < job.RequiredFullCycles {
			if autopilotStoppedV6194(jobID) {
				autopilotCompleteV6194(jobID, "STOPPED")
				return
			}
			time.Sleep(1200 * time.Millisecond)
			continue
		}

		cycleIDs := []int64{}
		// The current run intentionally uses fresh 9/9 evidence only. Historical
		// pre-Autopilot cycles are not silently counted because older partial
		// cycles did not persist region-completeness metadata in the Collector.
		if job.LastCycle != nil && job.LastCycle.Classification == "FULL" && job.LastCycle.CycleID > 0 {
			cycleIDs = append(cycleIDs, job.LastCycle.CycleID)
		}
		radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
			a.ConfirmedClusters++
			a.History = append(a.History, autopilotClusterResultV6194{
				Seed:          a.CurrentSeed,
				Command:       "@federated:" + a.CurrentSeed,
				FullCycles:    a.ValidatedCycles,
				PartialCycles: a.PartialCycles,
				FailedCycles:  a.FailedCycles,
				CycleIDs:      cycleIDs,
				ConfirmedAt:   utcNow(),
			})
			a.Phase = "CLUSTER_CONFIRMED"
			a.CurrentSeed = ""
			a.CurrentCommand = ""
			a.ValidatedCycles = 0
			a.PartialCycles = 0
			a.FailedCycles = 0
			a.JoinedCycles = 0
			a.ConsecutiveFailures = 0
			a.ScoutBatch = 0
			a.ScoutOffset = 0
		})
		time.Sleep(1200 * time.Millisecond)
	}
}

func (s *server) serverAutopilotStartV6194(w http.ResponseWriter, r *http.Request, body []byte) {
	var input autopilotStartRequestV6194
	if err := decodeJSON(body, &input); err != nil || len(strings.TrimSpace(input.Token)) < 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "GAME_TOKEN_REQUIRED"})
		return
	}
	seed, valid := normalizeAutopilotSeedV6194(input.InitialSeed)
	if !valid {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_INITIAL_SEED_INVALID"})
		return
	}
	fullCycles := input.FullCyclesPerCluster
	if fullCycles == 0 {
		fullCycles = autopilotDefaultFullCyclesV6194
	}
	if fullCycles < 1 || fullCycles > autopilotMaxFullCyclesV6194 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_FULL_CYCLES_INVALID"})
		return
	}
	maxClusters := input.MaxClusters
	if maxClusters == 0 {
		maxClusters = autopilotDefaultMaxClustersV6194
	}
	if maxClusters < 1 || maxClusters > autopilotMaxClustersV6194 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_MAX_CLUSTERS_INVALID"})
		return
	}
	partialLimit := input.PartialRetryLimit
	if partialLimit == 0 {
		partialLimit = autopilotDefaultPartialRetryLimitV6194
	}
	if partialLimit < 1 || partialLimit > autopilotMaxPartialRetryLimitV6194 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_PARTIAL_LIMIT_INVALID"})
		return
	}
	failureLimit := input.ConsecutiveFailureLimit
	if failureLimit == 0 {
		failureLimit = autopilotDefaultFailureLimitV6194
	}
	if failureLimit < 1 || failureLimit > autopilotMaxFailureLimitV6194 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_FAILURE_LIMIT_INVALID"})
		return
	}
	scoutLimit := input.ScoutLimit
	if scoutLimit == 0 {
		scoutLimit = autopilotDefaultScoutLimitV6194
	}
	if scoutLimit < 1 || scoutLimit > seedScoutMaxLimitV6193 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_SCOUT_LIMIT_INVALID"})
		return
	}
	scoutMaxBatches := input.ScoutMaxBatches
	if scoutMaxBatches == 0 {
		scoutMaxBatches = autopilotDefaultScoutMaxBatchesV6194
	}
	if scoutMaxBatches < 1 || scoutMaxBatches > autopilotMaxScoutMaxBatchesV6194 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_SCOUT_BATCH_LIMIT_INVALID"})
		return
	}
	scoutRegion := autopilotDefaultScoutRegionV6194
	if input.ScoutRegion != nil {
		scoutRegion = *input.ScoutRegion
	}
	if scoutRegion < 0 || scoutRegion > 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_SCOUT_REGION_INVALID"})
		return
	}
	scoutMinPlayers := input.ScoutMinPlayers
	if scoutMinPlayers == 0 {
		scoutMinPlayers = autopilotDefaultScoutMinPlayersV6194
	}
	if scoutMinPlayers < 1 || scoutMinPlayers > 500 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_SCOUT_MIN_PLAYERS_INVALID"})
		return
	}

	now := utcNow()
	job := &autopilotJobV6194{
		ID:                      newAutopilotJobIDV6194(),
		Status:                  "QUEUED",
		Phase:                   "QUEUED",
		AutopilotVersion:        autopilotVersionV6194,
		GameReadonly:            true,
		GameMutation:            false,
		CollectorMutation:       true,
		TokenPersisted:          false,
		BrowserRequired:         false,
		CurrentSeed:             seed,
		CurrentCommand:          func() string { if seed == "" { return "" }; return "@federated:" + seed }(),
		RequiredFullCycles:      fullCycles,
		PartialRetryLimit:       partialLimit,
		ConsecutiveFailureLimit: failureLimit,
		MaxClusters:             maxClusters,
		ScoutLimit:              scoutLimit,
		ScoutMaxBatches:         scoutMaxBatches,
		ScoutRegion:             scoutRegion,
		ScoutMinPlayers:         scoutMinPlayers,
		History:                 []autopilotClusterResultV6194{},
		StartedAt:               now,
		UpdatedAt:               now,
	}
	radarAutopilotJobsV6194.add(job)
	go s.runAutopilotV6194(job.ID, strings.TrimSpace(input.Token))
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": cloneAutopilotJobV6194(job)})
}

func (s *server) serverAutopilotStatusV6194(w http.ResponseWriter, r *http.Request, _ []byte) {
	id := strings.TrimSpace(r.URL.Query().Get("id"))
	if id == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_JOB_ID_REQUIRED"})
		return
	}
	job, ok := radarAutopilotJobsV6194.get(id)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "AUTOPILOT_JOB_NOT_FOUND"})
		return
	}
	response := map[string]any{"ok": true, "job": job}
	if job.CurrentChildJobID != "" {
		if child, found := radarCollectorJobs.get(job.CurrentChildJobID); found {
			response["currentCycleJob"] = child
		}
	}
	if job.CurrentScoutJobID != "" {
		if scout, found := radarSeedScoutJobsV6193.get(job.CurrentScoutJobID); found {
			response["currentScoutJob"] = scout
		}
	}
	writeJSON(w, http.StatusOK, response)
}

func (s *server) serverAutopilotStopV6194(w http.ResponseWriter, r *http.Request, body []byte) {
	var input struct {
		ID string `json:"id"`
	}
	if err := decodeJSON(body, &input); err != nil || strings.TrimSpace(input.ID) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "AUTOPILOT_JOB_ID_REQUIRED"})
		return
	}
	job, ok := radarAutopilotJobsV6194.update(strings.TrimSpace(input.ID), func(job *autopilotJobV6194) {
		job.StopRequested = true
		if job.Status == "RUNNING" || job.Status == "QUEUED" {
			job.Phase = "STOP_REQUESTED_AFTER_CURRENT_STEP"
		}
	})
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "AUTOPILOT_JOB_NOT_FOUND"})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": job})
}
