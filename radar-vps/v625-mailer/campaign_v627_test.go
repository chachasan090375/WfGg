package mailer

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strconv"
	"testing"
	"time"
)

func signedBatchRequestV627(t *testing.T, body []byte, ts int64, nonce string) *http.Request {
	t.Helper()
	const path = "/v1/outbox/queue-batch"
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(body))
	sum := sha256.Sum256(body)
	canonical := http.MethodPost + "\n" + path + "\n" + strconv.FormatInt(ts, 10) + "\n" + nonce + "\n" + hex.EncodeToString(sum[:])
	mac := hmac.New(sha256.New, []byte(testMailerKeyV626))
	_, _ = mac.Write([]byte(canonical))
	req.Header.Set("content-type", "application/json")
	req.Header.Set("X-Radar-Timestamp", strconv.FormatInt(ts, 10))
	req.Header.Set("X-Radar-Nonce", nonce)
	req.Header.Set("X-Radar-Signature", hex.EncodeToString(mac.Sum(nil)))
	return req
}

func campaignFixtureV627() CampaignRequestV627 {
	return CampaignRequestV627{
		CampaignID: "recruitment-fr-v1",
		Title:      "WfGg",
		Contents:   "Message de test.",
		Targets: []CampaignTargetV627{
			{TargetUID: "100001", TargetName: "Alpha"},
			{TargetUID: "100002", TargetName: "Bravo"},
		},
	}
}

func TestV627BatchQueuesAndDeduplicates(t *testing.T) {
	path := filepath.Join(t.TempDir(), "outbox.jsonl")
	now := time.Unix(1770000000, 0)
	server := &HTTPServer{store: &Store{Path: path}, secret: []byte(testMailerKeyV626), now: func() time.Time { return now }, nonces: map[string]int64{}}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/outbox/queue-batch", server.queueBatchV627)

	body, _ := json.Marshal(campaignFixtureV627())
	first := httptest.NewRecorder()
	mux.ServeHTTP(first, signedBatchRequestV627(t, body, now.Unix(), "nonce-v627-00000001"))
	if first.Code != http.StatusAccepted {
		t.Fatalf("first status=%d body=%s", first.Code, first.Body.String())
	}
	var got struct {
		Queued           int  `json:"queued"`
		Duplicates       int  `json:"duplicates"`
		LastWarWrite     bool `json:"lastwarWrite"`
		LastWarMutation  bool `json:"lastwarMutation"`
		MailSendExecuted bool `json:"mailSendExecuted"`
	}
	if err := json.Unmarshal(first.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if got.Queued != 2 || got.Duplicates != 0 || got.LastWarWrite || got.LastWarMutation || got.MailSendExecuted {
		t.Fatalf("first=%#v", got)
	}

	second := httptest.NewRecorder()
	mux.ServeHTTP(second, signedBatchRequestV627(t, body, now.Unix(), "nonce-v627-00000002"))
	if second.Code != http.StatusAccepted {
		t.Fatalf("second status=%d body=%s", second.Code, second.Body.String())
	}
	if err := json.Unmarshal(second.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if got.Queued != 0 || got.Duplicates != 2 {
		t.Fatalf("second=%#v", got)
	}
}

func TestV627BatchRejectsMoreThan25BeforeWriting(t *testing.T) {
	input := campaignFixtureV627()
	input.Targets = nil
	for i := 0; i < MaxCampaignTargets+1; i++ {
		input.Targets = append(input.Targets, CampaignTargetV627{
			TargetUID:  strconv.Itoa(200000 + i),
			TargetName: "Candidate",
		})
	}
	if _, err := validateCampaignV627(input); err == nil || err.Error() != "MAIL_CAMPAIGN_TARGET_COUNT_INVALID_V627" {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestV627BatchRejectsDuplicateTarget(t *testing.T) {
	input := campaignFixtureV627()
	input.Targets[1].TargetUID = input.Targets[0].TargetUID
	if _, err := validateCampaignV627(input); err == nil || err.Error() != "MAIL_CAMPAIGN_DUPLICATE_TARGET_V627" {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestV627BatchInheritsByteLimits(t *testing.T) {
	input := campaignFixtureV627()
	input.Title = string(bytes.Repeat([]byte("a"), 51))
	if _, err := validateCampaignV627(input); err == nil || err.Error() != "MAIL_TITLE_INVALID_V625" {
		t.Fatalf("unexpected error: %v", err)
	}
}
