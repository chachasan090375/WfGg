package outbox

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"wfgg-lastwar-mail-outbox-v625/internal/mailcontract"
)

const (
	Version           = "V6.25"
	StatusPreparedDry = "PREPARED_DRY_RUN"
)

type PrepareRequest struct {
	CampaignKey string             `json:"campaignKey"`
	Trigger     string             `json:"trigger"`
	Draft       mailcontract.Draft `json:"draft"`
}

type Item struct {
	ID               string              `json:"id"`
	Version          string              `json:"version"`
	IdempotencyKey   string              `json:"idempotencyKey"`
	CampaignKey      string              `json:"campaignKey"`
	Trigger          string              `json:"trigger"`
	Status           string              `json:"status"`
	DraftHash        string              `json:"draftHash"`
	Draft            mailcontract.Draft  `json:"draft"`
	Preview          mailcontract.DryRun `json:"preview"`
	CreatedAt        string              `json:"createdAt"`
	MutationExecuted bool                `json:"mutationExecuted"`
	NetworkEnabled   bool                `json:"networkEnabled"`
}

type fileData struct {
	Version string `json:"version"`
	Items   []Item `json:"items"`
}

type FileStore struct {
	path string
	now  func() time.Time
	mu   sync.Mutex
}

func NewFileStore(path string) (*FileStore, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, errors.New("outbox path is required")
	}
	return &FileStore{path: path, now: time.Now}, nil
}

func (s *FileStore) SetClockForTest(now func() time.Time) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if now != nil {
		s.now = now
	}
}

func normalizeCampaign(v string) string {
	return strings.TrimSpace(v)
}

func idempotencyKey(campaign, uid string) string {
	h := sha256.Sum256([]byte("wfgg-mail-v625\x00" + campaign + "\x00" + strings.TrimSpace(uid)))
	return hex.EncodeToString(h[:])
}

func draftHash(d mailcontract.Draft) (string, error) {
	b, err := json.Marshal(d)
	if err != nil {
		return "", err
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:]), nil
}

func (s *FileStore) Prepare(req PrepareRequest) (Item, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	req.CampaignKey = normalizeCampaign(req.CampaignKey)
	req.Trigger = strings.TrimSpace(req.Trigger)
	if req.CampaignKey == "" {
		return Item{}, false, errors.New("campaignKey is required for anti-duplicate protection")
	}
	if req.Trigger == "" {
		return Item{}, false, errors.New("trigger is required")
	}
	preview, err := mailcontract.BuildPrivateDryRun(req.Draft)
	if err != nil {
		return Item{}, false, err
	}
	key := idempotencyKey(req.CampaignKey, req.Draft.TargetUID)
	hash, err := draftHash(req.Draft)
	if err != nil {
		return Item{}, false, err
	}

	data, err := s.load()
	if err != nil {
		return Item{}, false, err
	}
	for _, existing := range data.Items {
		if existing.IdempotencyKey != key {
			continue
		}
		if existing.DraftHash != hash {
			return Item{}, false, fmt.Errorf("OUTBOX_IDEMPOTENCY_CONFLICT: campaign=%s targetUid=%s", req.CampaignKey, req.Draft.TargetUID)
		}
		return existing, false, nil
	}

	item := Item{
		ID:               "mail-" + key[:24],
		Version:          Version,
		IdempotencyKey:   key,
		CampaignKey:      req.CampaignKey,
		Trigger:          req.Trigger,
		Status:           StatusPreparedDry,
		DraftHash:        hash,
		Draft:            req.Draft,
		Preview:          preview,
		CreatedAt:        s.now().UTC().Format(time.RFC3339Nano),
		MutationExecuted: false,
		NetworkEnabled:   false,
	}
	data.Items = append(data.Items, item)
	sort.Slice(data.Items, func(i, j int) bool { return data.Items[i].ID < data.Items[j].ID })
	if err := s.save(data); err != nil {
		return Item{}, false, err
	}
	return item, true, nil
}

func (s *FileStore) List() ([]Item, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	data, err := s.load()
	if err != nil {
		return nil, err
	}
	return append([]Item(nil), data.Items...), nil
}

func (s *FileStore) load() (fileData, error) {
	b, err := os.ReadFile(s.path)
	if errors.Is(err, os.ErrNotExist) {
		return fileData{Version: Version, Items: []Item{}}, nil
	}
	if err != nil {
		return fileData{}, err
	}
	var d fileData
	if err := json.Unmarshal(b, &d); err != nil {
		return fileData{}, err
	}
	if d.Version != Version {
		return fileData{}, fmt.Errorf("unsupported outbox version: %q", d.Version)
	}
	if d.Items == nil {
		d.Items = []Item{}
	}
	return d, nil
}

func (s *FileStore) save(d fileData) error {
	d.Version = Version
	dir := filepath.Dir(s.path)
	if err := os.MkdirAll(dir, 0o750); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".outbox-v625-*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	cleanup := func() {
		tmp.Close()
		os.Remove(tmpName)
	}
	enc := json.NewEncoder(tmp)
	enc.SetIndent("", "  ")
	if err := enc.Encode(d); err != nil {
		cleanup()
		return err
	}
	if err := tmp.Sync(); err != nil {
		cleanup()
		return err
	}
	if err := tmp.Close(); err != nil {
		os.Remove(tmpName)
		return err
	}
	if err := os.Chmod(tmpName, 0o600); err != nil {
		os.Remove(tmpName)
		return err
	}
	if err := os.Rename(tmpName, s.path); err != nil {
		os.Remove(tmpName)
		return err
	}
	return nil
}
