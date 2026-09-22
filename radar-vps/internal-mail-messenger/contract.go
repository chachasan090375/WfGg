package messenger

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
)

const (
	Version         = "v6.25.0"
	CommandMailSend = "mail.send"
	MailSelfSend    = int32(21)
	MaxTitleBytes   = 50
	MaxContentBytes = 2000
)

var (
	ErrTargetRequired        = errors.New("MAIL_TARGET_UID_REQUIRED_V625")
	ErrRecipientNameRequired = errors.New("MAIL_RECIPIENT_NAME_REQUIRED_V625")
	ErrTitleRequired         = errors.New("MAIL_TITLE_REQUIRED_V625")
	ErrContentRequired       = errors.New("MAIL_CONTENT_REQUIRED_V625")
	ErrTitleTooLong          = errors.New("MAIL_TITLE_TOO_LONG_V625")
	ErrContentTooLong        = errors.New("MAIL_CONTENT_TOO_LONG_V625")
	ErrMailTypeInvalid       = errors.New("MAIL_TYPE_INVALID_V625")
	ErrSendTimeInvalid       = errors.New("MAIL_SEND_TIME_INVALID_V625")
	ErrCampaignRequired      = errors.New("MAIL_CAMPAIGN_REQUIRED_V625")
)

type PlayerMailRequest struct {
	CampaignKey   string `json:"campaignKey"`
	RecipientName string `json:"recipientName"`
	TargetUID     string `json:"targetUid"`
	Title         string `json:"title"`
	Contents      string `json:"contents"`
	SendLocalTime int64  `json:"sendLocalTime"`
	Type          int32  `json:"type"`
}

type WireField struct {
	Name    string `json:"name"`
	SFSType string `json:"sfsType"`
	Value   any    `json:"value"`
}

func NewPlayerMail(campaignKey, recipientName, targetUID, title, contents string, sendLocalTime int64) PlayerMailRequest {
	return PlayerMailRequest{
		CampaignKey: campaignKey, RecipientName: recipientName, TargetUID: targetUID,
		Title: title, Contents: contents, SendLocalTime: sendLocalTime, Type: MailSelfSend,
	}
}

func (r PlayerMailRequest) Validate() error {
	if strings.TrimSpace(r.CampaignKey) == "" {
		return ErrCampaignRequired
	}
	if strings.TrimSpace(r.TargetUID) == "" {
		return ErrTargetRequired
	}
	if strings.TrimSpace(r.RecipientName) == "" {
		return ErrRecipientNameRequired
	}
	if r.Title == "" {
		return ErrTitleRequired
	}
	if r.Contents == "" {
		return ErrContentRequired
	}
	// The official Lua UI uses string.len, so these are UTF-8 byte limits.
	if len(r.Title) > MaxTitleBytes {
		return ErrTitleTooLong
	}
	if len(r.Contents) > MaxContentBytes {
		return ErrContentTooLong
	}
	if r.Type != MailSelfSend {
		return ErrMailTypeInvalid
	}
	if r.SendLocalTime <= 0 {
		return ErrSendTimeInvalid
	}
	return nil
}

func (r PlayerMailRequest) WireContract() ([]WireField, error) {
	if err := r.Validate(); err != nil {
		return nil, err
	}
	return []WireField{
		{Name: "name", SFSType: "UtfString", Value: r.RecipientName},
		{Name: "title", SFSType: "UtfString", Value: r.Title},
		{Name: "contents", SFSType: "UtfString", Value: r.Contents},
		{Name: "allianceId", SFSType: "UtfString", Value: ""},
		{Name: "targetUid", SFSType: "UtfString", Value: r.TargetUID},
		{Name: "sendLocalTime", SFSType: "Long", Value: r.SendLocalTime},
		{Name: "type", SFSType: "Int", Value: r.Type},
	}, nil
}

func IdempotencyKey(campaignKey, targetUID string) (string, error) {
	campaignKey = strings.TrimSpace(campaignKey)
	targetUID = strings.TrimSpace(targetUID)
	if campaignKey == "" {
		return "", ErrCampaignRequired
	}
	if targetUID == "" {
		return "", ErrTargetRequired
	}
	sum := sha256.Sum256([]byte(campaignKey + "\x00" + targetUID))
	return hex.EncodeToString(sum[:]), nil
}
