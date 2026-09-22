package outbox

import (
	"bufio"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"

	"wfgg-lastwar-messenger-v624/internal/mailcontract"
)

type State string

const (
	StateDraft     State = "DRAFT"
	StateQueued    State = "QUEUED"
	StateCancelled State = "CANCELLED"
)

type Record struct {
	Version        string             `json:"version"`
	ID             string             `json:"id"`
	State          State              `json:"state"`
	IdempotencyKey string             `json:"idempotencyKey"`
	Draft          mailcontract.Draft `json:"draft"`
	DryRun         mailcontract.DryRun `json:"dryRun"`
	CreatedAt      time.Time          `json:"createdAt"`
	UpdatedAt      time.Time          `json:"updatedAt"`
	Revision       int64              `json:"revision"`
}

type Store struct {
	path string
	mu   sync.Mutex
}

func Open(path string) (*Store, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, errors.New("outbox ledger path is required")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("create outbox directory: %w", err)
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, fmt.Errorf("open outbox ledger: %w", err)
	}
	if err := f.Close(); err != nil {
		return nil, fmt.Errorf("close outbox ledger: %w", err)
	}
	return &Store{path: path}, nil
}

func (s *Store) Path() string { return s.path }

func (s *Store) CreateOrReuse(d mailcontract.Draft, now time.Time) (Record, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	dry, err := mailcontract.BuildPrivateSameServerDryRun(d)
	if err != nil {
		return Record{}, false, err
	}
	key := idempotencyKey(d)
	records, _, err := s.loadLocked()
	if err != nil {
		return Record{}, false, err
	}
	for _, r := range records {
		if r.IdempotencyKey == key && (r.State == StateDraft || r.State == StateQueued) {
			return r, true, nil
		}
	}
	id, err := newID()
	if err != nil {
		return Record{}, false, err
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	r := Record{
		Version: "V6.24",
		ID: id,
		State: StateDraft,
		IdempotencyKey: key,
		Draft: d,
		DryRun: dry,
		CreatedAt: now.UTC(),
		UpdatedAt: now.UTC(),
		Revision: 1,
	}
	if err := s.appendLocked(r); err != nil {
		return Record{}, false, err
	}
	return r, false, nil
}

func (s *Store) Queue(id string, now time.Time) (Record, error) {
	return s.transition(id, StateQueued, now)
}

func (s *Store) Cancel(id string, now time.Time) (Record, error) {
	return s.transition(id, StateCancelled, now)
}

func (s *Store) transition(id string, target State, now time.Time) (Record, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	records, _, err := s.loadLocked()
	if err != nil {
		return Record{}, err
	}
	r, ok := records[id]
	if !ok {
		return Record{}, fmt.Errorf("outbox message %q not found", id)
	}
	switch target {
	case StateQueued:
		if r.State == StateQueued {
			return r, nil
		}
		if r.State != StateDraft {
			return Record{}, fmt.Errorf("cannot queue message in state %s", r.State)
		}
	case StateCancelled:
		if r.State == StateCancelled {
			return r, nil
		}
		if r.State != StateDraft && r.State != StateQueued {
			return Record{}, fmt.Errorf("cannot cancel message in state %s", r.State)
		}
	default:
		return Record{}, fmt.Errorf("unsupported dry-run transition %s", target)
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	r.State = target
	r.UpdatedAt = now.UTC()
	r.Revision++
	if err := s.appendLocked(r); err != nil {
		return Record{}, err
	}
	return r, nil
}

func (s *Store) Get(id string) (Record, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	records, _, err := s.loadLocked()
	if err != nil {
		return Record{}, false, err
	}
	r, ok := records[id]
	return r, ok, nil
}

func (s *Store) List() ([]Record, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	records, _, err := s.loadLocked()
	if err != nil {
		return nil, err
	}
	out := make([]Record, 0, len(records))
	for _, r := range records {
		out = append(out, r)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].CreatedAt.Equal(out[j].CreatedAt) {
			return out[i].ID < out[j].ID
		}
		return out[i].CreatedAt.Before(out[j].CreatedAt)
	})
	return out, nil
}

func (s *Store) History(id string) ([]Record, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, history, err := s.loadLocked()
	if err != nil {
		return nil, err
	}
	out := append([]Record(nil), history[id]...)
	sort.Slice(out, func(i, j int) bool { return out[i].Revision < out[j].Revision })
	return out, nil
}

func idempotencyKey(d mailcontract.Draft) string {
	h := sha256.New()
	io.WriteString(h, "wfgg-v624-mail|")
	io.WriteString(h, strings.TrimSpace(d.TargetUID))
	io.WriteString(h, "|")
	io.WriteString(h, strings.TrimSpace(d.TargetName))
	io.WriteString(h, "|")
	io.WriteString(h, d.Title)
	io.WriteString(h, "|")
	io.WriteString(h, d.Contents)
	io.WriteString(h, fmt.Sprintf("|%d|%d", d.SenderServer, d.TargetServer))
	return hex.EncodeToString(h.Sum(nil))
}

func newID() (string, error) {
	var b [12]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", fmt.Errorf("generate outbox id: %w", err)
	}
	return hex.EncodeToString(b[:]), nil
}

func (s *Store) loadLocked() (map[string]Record, map[string][]Record, error) {
	f, err := os.OpenFile(s.path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, nil, fmt.Errorf("open outbox ledger: %w", err)
	}
	defer f.Close()
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_SH); err != nil {
		return nil, nil, fmt.Errorf("lock outbox ledger: %w", err)
	}
	defer syscall.Flock(int(f.Fd()), syscall.LOCK_UN)

	latest := map[string]Record{}
	history := map[string][]Record{}
	sc := bufio.NewScanner(f)
	buf := make([]byte, 0, 64*1024)
	sc.Buffer(buf, 2*1024*1024)
	line := 0
	for sc.Scan() {
		line++
		if len(strings.TrimSpace(sc.Text())) == 0 {
			continue
		}
		var r Record
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			return nil, nil, fmt.Errorf("decode outbox ledger line %d: %w", line, err)
		}
		if r.ID == "" || r.Revision <= 0 {
			return nil, nil, fmt.Errorf("invalid outbox ledger line %d", line)
		}
		prev, ok := latest[r.ID]
		if ok && r.Revision <= prev.Revision {
			return nil, nil, fmt.Errorf("non-monotonic revision for %s", r.ID)
		}
		latest[r.ID] = r
		history[r.ID] = append(history[r.ID], r)
	}
	if err := sc.Err(); err != nil {
		return nil, nil, fmt.Errorf("scan outbox ledger: %w", err)
	}
	return latest, history, nil
}

func (s *Store) appendLocked(r Record) error {
	f, err := os.OpenFile(s.path, os.O_CREATE|os.O_RDWR|os.O_APPEND, 0o600)
	if err != nil {
		return fmt.Errorf("open outbox ledger for append: %w", err)
	}
	defer f.Close()
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX); err != nil {
		return fmt.Errorf("lock outbox ledger for append: %w", err)
	}
	defer syscall.Flock(int(f.Fd()), syscall.LOCK_UN)
	b, err := json.Marshal(r)
	if err != nil {
		return fmt.Errorf("encode outbox record: %w", err)
	}
	if _, err := f.Write(append(b, '\n')); err != nil {
		return fmt.Errorf("append outbox record: %w", err)
	}
	if err := f.Sync(); err != nil {
		return fmt.Errorf("sync outbox ledger: %w", err)
	}
	return nil
}
