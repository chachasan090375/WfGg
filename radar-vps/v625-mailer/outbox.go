package mailer

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"unicode/utf8"
)

const (
	Version          = "v6.25.0"
	LastWarCommand   = "mail.send"
	MailTypeSelf     = 21
	MaxTitleBytes    = 50
	MaxContentBytes  = 2000
	DefaultOutboxPath = "/opt/wfgg-radar/data/mail-outbox-v625.jsonl"
)

var ErrLastWarWriteDisabled = errors.New("LASTWAR_MAIL_WRITE_DISABLED_V625")

type DraftRequest struct {
	CampaignID string `json:"campaignId"`
	TargetUID  string `json:"targetUid"`
	TargetName string `json:"targetName"`
	Title      string `json:"title"`
	Contents   string `json:"contents"`
}

type WirePayload struct {
	Name          string `json:"name"`
	Title         string `json:"title"`
	Contents      string `json:"contents"`
	AllianceID    string `json:"allianceId"`
	TargetUID     string `json:"targetUid"`
	SendLocalTime int64  `json:"sendLocalTime"`
	Type          int    `json:"type"`
	ServerID      *int   `json:"serverId,omitempty"`
}

type OutboxRecord struct {
	ID                 string       `json:"id"`
	State              string       `json:"state"`
	CampaignID         string       `json:"campaignId"`
	TargetUID          string       `json:"targetUid"`
	TargetName         string       `json:"targetName"`
	Title              string       `json:"title"`
	Contents           string       `json:"contents"`
	Command            string       `json:"command"`
	Type               int          `json:"type"`
	RequiresServerTime bool         `json:"requiresServerTime"`
	LastWarMutation    bool         `json:"lastwarMutation"`
	TokenPersisted     bool         `json:"tokenPersisted"`
	WireTemplate       WirePayload  `json:"wireTemplate"`
}

type QueueResult struct {
	Record    OutboxRecord `json:"record"`
	Duplicate bool         `json:"duplicate"`
}

type Store struct {
	Path string
	mu   sync.Mutex
}

func ValidateDraft(d DraftRequest) error {
	d.CampaignID = strings.TrimSpace(d.CampaignID)
	d.TargetUID = strings.TrimSpace(d.TargetUID)
	d.TargetName = strings.TrimSpace(d.TargetName)
	if d.CampaignID == "" {
		return errors.New("MAIL_CAMPAIGN_REQUIRED_V625")
	}
	if d.TargetUID == "" || len(d.TargetUID) > 64 || strings.IndexFunc(d.TargetUID, func(r rune) bool { return r <= ' ' }) >= 0 {
		return errors.New("MAIL_TARGET_UID_INVALID_V625")
	}
	if d.TargetName == "" || len([]byte(d.TargetName)) > 256 || !utf8.ValidString(d.TargetName) {
		return errors.New("MAIL_TARGET_NAME_INVALID_V625")
	}
	if strings.TrimSpace(d.Title) == "" || len([]byte(d.Title)) > MaxTitleBytes || !utf8.ValidString(d.Title) {
		return errors.New("MAIL_TITLE_INVALID_V625")
	}
	if strings.TrimSpace(d.Contents) == "" || len([]byte(d.Contents)) > MaxContentBytes || !utf8.ValidString(d.Contents) {
		return errors.New("MAIL_CONTENT_INVALID_V625")
	}
	return nil
}

func BuildSelfPayload(d DraftRequest, serverTime int64) (WirePayload, error) {
	if err := ValidateDraft(d); err != nil {
		return WirePayload{}, err
	}
	if serverTime <= 0 {
		return WirePayload{}, errors.New("MAIL_SERVER_TIME_REQUIRED_V625")
	}
	return WirePayload{
		Name:          strings.TrimSpace(d.TargetName),
		Title:         d.Title,
		Contents:      d.Contents,
		AllianceID:    "",
		TargetUID:     strings.TrimSpace(d.TargetUID),
		SendLocalTime: serverTime,
		Type:          MailTypeSelf,
		ServerID:      nil,
	}, nil
}

func draftID(d DraftRequest) string {
	material := strings.Join([]string{
		"v625",
		strings.TrimSpace(d.CampaignID),
		strings.TrimSpace(d.TargetUID),
		d.Title,
		d.Contents,
	}, "\n")
	sum := sha256.Sum256([]byte(material))
	return hex.EncodeToString(sum[:])
}

func makeRecord(d DraftRequest) OutboxRecord {
	return OutboxRecord{
		ID:                 draftID(d),
		State:              "DRY_RUN_READY",
		CampaignID:         strings.TrimSpace(d.CampaignID),
		TargetUID:          strings.TrimSpace(d.TargetUID),
		TargetName:         strings.TrimSpace(d.TargetName),
		Title:              d.Title,
		Contents:           d.Contents,
		Command:            LastWarCommand,
		Type:               MailTypeSelf,
		RequiresServerTime: true,
		LastWarMutation:    false,
		TokenPersisted:     false,
		WireTemplate: WirePayload{
			Name:          strings.TrimSpace(d.TargetName),
			Title:         d.Title,
			Contents:      d.Contents,
			AllianceID:    "",
			TargetUID:     strings.TrimSpace(d.TargetUID),
			SendLocalTime: 0,
			Type:          MailTypeSelf,
			ServerID:      nil,
		},
	}
}

func (s *Store) Queue(d DraftRequest) (QueueResult, error) {
	if err := ValidateDraft(d); err != nil {
		return QueueResult{}, err
	}
	path := s.Path
	if strings.TrimSpace(path) == "" {
		path = DefaultOutboxPath
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return QueueResult{}, fmt.Errorf("MAIL_OUTBOX_DIR_FAILED_V625: %w", err)
	}

	record := makeRecord(d)
	if f, err := os.Open(path); err == nil {
		scanner := bufio.NewScanner(f)
		buf := make([]byte, 64*1024)
		scanner.Buffer(buf, 4*1024*1024)
		for scanner.Scan() {
			var existing OutboxRecord
			if json.Unmarshal(scanner.Bytes(), &existing) == nil && existing.ID == record.ID {
				_ = f.Close()
				return QueueResult{Record: existing, Duplicate: true}, nil
			}
		}
		if err := scanner.Err(); err != nil {
			_ = f.Close()
			return QueueResult{}, fmt.Errorf("MAIL_OUTBOX_READ_FAILED_V625: %w", err)
		}
		_ = f.Close()
	} else if !errors.Is(err, os.ErrNotExist) {
		return QueueResult{}, fmt.Errorf("MAIL_OUTBOX_OPEN_FAILED_V625: %w", err)
	}

	line, err := json.Marshal(record)
	if err != nil {
		return QueueResult{}, fmt.Errorf("MAIL_OUTBOX_ENCODE_FAILED_V625: %w", err)
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return QueueResult{}, fmt.Errorf("MAIL_OUTBOX_WRITE_OPEN_FAILED_V625: %w", err)
	}
	if _, err := f.Write(append(line, '\n')); err != nil {
		_ = f.Close()
		return QueueResult{}, fmt.Errorf("MAIL_OUTBOX_WRITE_FAILED_V625: %w", err)
	}
	if err := f.Close(); err != nil {
		return QueueResult{}, fmt.Errorf("MAIL_OUTBOX_CLOSE_FAILED_V625: %w", err)
	}
	_ = os.Chmod(path, 0o600)
	return QueueResult{Record: record, Duplicate: false}, nil
}

// DispatchLive intentionally has no transport implementation in V6.25.
// The outbox can be qualified without granting Last War write capability.
func DispatchLive(_ OutboxRecord, _ int64) error {
	return ErrLastWarWriteDisabled
}
