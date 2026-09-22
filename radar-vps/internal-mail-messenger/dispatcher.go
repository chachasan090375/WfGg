package messenger

import (
	"errors"
	"strings"
	"time"
)

type Mode string

const (
	ModeDisabled Mode = "DISABLED"
	ModeDryRun   Mode = "DRY_RUN"
)

var (
	ErrExecutionDisabled = errors.New("MAIL_EXECUTION_DISABLED_V625")
	ErrLiveModeForbidden = errors.New("MAIL_LIVE_MODE_NOT_IMPLEMENTED_V625")
)

type OutboxState string

const (
	StateBlocked     OutboxState = "BLOCKED"
	StateDryRunReady OutboxState = "DRY_RUN_READY"
)

type OutboxEntry struct {
	ID              string            `json:"id"`
	State           OutboxState       `json:"state"`
	Command         string            `json:"command"`
	Request         PlayerMailRequest `json:"request"`
	PreparedAt      string            `json:"preparedAt"`
	LastWarMutation bool              `json:"lastWarMutation"`
	GameConnection  string            `json:"gameConnection"`
	Reason          string            `json:"reason,omitempty"`
}

func ParseMode(raw string) (Mode, error) {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case "", string(ModeDisabled):
		return ModeDisabled, nil
	case string(ModeDryRun):
		return ModeDryRun, nil
	default:
		return "", ErrLiveModeForbidden
	}
}

func Prepare(mode Mode, req PlayerMailRequest, now time.Time) (OutboxEntry, error) {
	if err := req.Validate(); err != nil {
		return OutboxEntry{}, err
	}
	id, err := IdempotencyKey(req.CampaignKey, req.TargetUID)
	if err != nil {
		return OutboxEntry{}, err
	}
	entry := OutboxEntry{
		ID: id, Command: CommandMailSend, Request: req,
		PreparedAt:      now.UTC().Format(time.RFC3339Nano),
		LastWarMutation: false, GameConnection: "NONE",
	}
	switch mode {
	case ModeDisabled:
		entry.State = StateBlocked
		entry.Reason = ErrExecutionDisabled.Error()
		return entry, nil
	case ModeDryRun:
		entry.State = StateDryRunReady
		return entry, nil
	default:
		return OutboxEntry{}, ErrLiveModeForbidden
	}
}
