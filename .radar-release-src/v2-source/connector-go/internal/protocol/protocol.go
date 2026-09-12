package protocol

import (
	"context"
	"errors"
)

type Identity struct {
	GameUID   string `json:"gameUid"`
	Pseudo    string `json:"pseudo"`
	ServerID  string `json:"serverId,omitempty"`
	ZoneID    string `json:"zoneId,omitempty"`
	GameBuild string `json:"gameBuild,omitempty"`
}

type Player struct {
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

// Observation is a non-secret scalar observed during a real server round-trip.
// Status is deliberately explicit so Oracle cannot confuse OBSERVED values with
// inferred/calculated values later in the pipeline.
type Observation struct {
	Path       string `json:"path"`
	Value      any    `json:"value"`
	Source     string `json:"source"`
	Status     string `json:"status"`
	ObservedAt string `json:"observedAt"`
}

type SessionMeta struct {
	ZoneID           string `json:"zoneId,omitempty"`
	ServerID         string `json:"serverId,omitempty"`
	ResolvedAddress  string `json:"resolvedAddress,omitempty"`
	Redirected       bool   `json:"redirected"`
	TranscriptSHA256 string `json:"transcriptSha256,omitempty"`
}

type Snapshot struct {
	Identity     *Identity     `json:"identity,omitempty"`
	Session      SessionMeta   `json:"session"`
	Observations []Observation `json:"observations"`
	Readonly     bool          `json:"readonly"`
	Source       string        `json:"source"`
}

type Client interface {
	Authenticate(ctx context.Context, token string) (Identity, error)
	Snapshot(ctx context.Context, token string) (Snapshot, error)
	ScanPlayer(ctx context.Context, token, query string) ([]Player, error)
	Mode() string
}

// RegionScanner is implemented by the native V4 adapter. It is optional so the
// legacy read-only client remains valid. Region 0..8 maps to the same 3x3
// WFGG_COLLECTOR_ORIGIN_INDEX grid already validated by Collector V4.
type RegionScanner interface {
	ScanPlayerRegion(ctx context.Context, token, query string, region int) ([]Player, error)
}

// ProfileScanner exposes the V4 @profile:uid,... fast path without changing the
// public legacy ScanPlayer contract (whose query length is intentionally small).
type ProfileScanner interface {
	ScanProfiles(ctx context.Context, token string, uids []string) ([]Player, error)
}

type NotConfigured struct{}

func (NotConfigured) Authenticate(context.Context, string) (Identity, error) {
	return Identity{}, errors.New("LASTWAR_PROTOCOL_NOT_CONFIGURED")
}
func (NotConfigured) Snapshot(context.Context, string) (Snapshot, error) {
	return Snapshot{}, errors.New("LASTWAR_PROTOCOL_NOT_CONFIGURED")
}
func (NotConfigured) ScanPlayer(context.Context, string, string) ([]Player, error) {
	return nil, errors.New("LASTWAR_PROTOCOL_NOT_CONFIGURED")
}
func (NotConfigured) Mode() string { return "not-configured" }
