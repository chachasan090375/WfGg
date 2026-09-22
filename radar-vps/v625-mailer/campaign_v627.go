package mailer

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strings"
)

const (
	CampaignVersion      = "v6.27.0"
	MaxCampaignTargets   = 25
	MaxCampaignBodyBytes = 65536
)

type CampaignTargetV627 struct {
	TargetUID  string `json:"targetUid"`
	TargetName string `json:"targetName"`
}

type CampaignRequestV627 struct {
	CampaignID string               `json:"campaignId"`
	Title      string               `json:"title"`
	Contents   string               `json:"contents"`
	Targets    []CampaignTargetV627 `json:"targets"`
}

type CampaignResultV627 struct {
	Queued     int            `json:"queued"`
	Duplicates int            `json:"duplicates"`
	Records    []OutboxRecord `json:"records"`
}

type campaignErrorV627 struct{ code string }

func (e *campaignErrorV627) Error() string { return e.code }

func validateCampaignV627(input CampaignRequestV627) ([]DraftRequest, error) {
	if len(input.Targets) < 1 || len(input.Targets) > MaxCampaignTargets {
		return nil, &campaignErrorV627{"MAIL_CAMPAIGN_TARGET_COUNT_INVALID_V627"}
	}
	campaignID := strings.TrimSpace(input.CampaignID)
	if campaignID == "" || len(campaignID) > 128 {
		return nil, &campaignErrorV627{"MAIL_CAMPAIGN_ID_INVALID_V627"}
	}
	seen := map[string]bool{}
	drafts := make([]DraftRequest, 0, len(input.Targets))
	for _, target := range input.Targets {
		uid := strings.TrimSpace(target.TargetUID)
		if seen[uid] {
			return nil, &campaignErrorV627{"MAIL_CAMPAIGN_DUPLICATE_TARGET_V627"}
		}
		seen[uid] = true
		draft := DraftRequest{
			CampaignID: campaignID,
			TargetUID:  uid,
			TargetName: strings.TrimSpace(target.TargetName),
			Title:      input.Title,
			Contents:   input.Contents,
		}
		if err := ValidateDraft(draft); err != nil {
			return nil, err
		}
		drafts = append(drafts, draft)
	}
	return drafts, nil
}

func (s *HTTPServer) queueBatchV627(w http.ResponseWriter, r *http.Request) {
	body, err := readBoundedBodyV627(r, MaxCampaignBodyBytes)
	if err != nil {
		writeHTTPJSON(w, http.StatusRequestEntityTooLarge, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	if err := s.verifySignedRequest(r, body); err != nil {
		writeHTTPJSON(w, http.StatusUnauthorized, map[string]any{"ok": false, "error": err.Error()})
		return
	}

	var input CampaignRequestV627
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&input); err != nil {
		writeHTTPJSON(w, http.StatusBadRequest, map[string]any{"ok": false, "error": "MAIL_CAMPAIGN_REQUEST_INVALID_V627"})
		return
	}
	drafts, err := validateCampaignV627(input)
	if err != nil {
		writeHTTPJSON(w, http.StatusBadRequest, map[string]any{"ok": false, "error": err.Error()})
		return
	}

	result := CampaignResultV627{Records: make([]OutboxRecord, 0, len(drafts))}
	for _, draft := range drafts {
		queued, err := s.store.Queue(draft)
		if err != nil {
			writeHTTPJSON(w, http.StatusInternalServerError, map[string]any{"ok": false, "error": "MAIL_CAMPAIGN_QUEUE_FAILED_V627"})
			return
		}
		if queued.Duplicate {
			result.Duplicates++
		} else {
			result.Queued++
		}
		result.Records = append(result.Records, queued.Record)
	}

	writeHTTPJSON(w, http.StatusAccepted, map[string]any{
		"ok":               true,
		"version":          CampaignVersion,
		"mode":             "CAMPAIGN_AUTOQUEUE_DRY_RUN",
		"queued":           result.Queued,
		"duplicates":       result.Duplicates,
		"records":          result.Records,
		"lastwarWrite":     false,
		"lastwarMutation":  false,
		"mailSendExecuted": false,
		"tokenPersistence": false,
	})
}

func readBoundedBodyV627(r *http.Request, limit int64) ([]byte, error) {
	body, err := io.ReadAll(io.LimitReader(r.Body, limit+1))
	if err != nil {
		return nil, &campaignErrorV627{"MAIL_CAMPAIGN_BODY_READ_FAILED_V627"}
	}
	if int64(len(body)) > limit {
		return nil, &campaignErrorV627{"MAIL_CAMPAIGN_BODY_TOO_LARGE_V627"}
	}
	return body, nil
}
