package mailcontract

import (
	"errors"
	"fmt"
	"strings"
)

const (
	MailSelfSend     int32 = 21
	MaxTitleBytes          = 50
	MaxContentsBytes       = 2000
)

type Draft struct {
	TargetName    string `json:"targetName"`
	TargetUID     string `json:"targetUid"`
	Title         string `json:"title"`
	Contents      string `json:"contents"`
	SendLocalTime int64  `json:"sendLocalTime"`
	TargetServer  int32  `json:"targetServer,omitempty"`
	SenderServer  int32  `json:"senderServer,omitempty"`
}

type WireField struct {
	Method string `json:"method"`
	Key    string `json:"key"`
	Value  any    `json:"value"`
}

type DryRun struct {
	Version          string      `json:"version"`
	Command          string      `json:"command"`
	MailType         int32       `json:"mailType"`
	Transport        string      `json:"transport"`
	MutationExecuted bool        `json:"mutationExecuted"`
	NetworkEnabled   bool        `json:"networkEnabled"`
	Fields           []WireField `json:"fields"`
}

func ValidatePrivateSameServer(d Draft) error {
	d.TargetName = strings.TrimSpace(d.TargetName)
	d.TargetUID = strings.TrimSpace(d.TargetUID)
	if d.TargetName == "" {
		return errors.New("target name is required")
	}
	if d.TargetUID == "" {
		return errors.New("target uid is required")
	}
	if d.Title == "" {
		return errors.New("title is required")
	}
	if d.Contents == "" {
		return errors.New("contents are required")
	}
	if len([]byte(d.Title)) > MaxTitleBytes {
		return fmt.Errorf("title exceeds client limit: %d > %d bytes", len([]byte(d.Title)), MaxTitleBytes)
	}
	if len([]byte(d.Contents)) > MaxContentsBytes {
		return fmt.Errorf("contents exceed client limit: %d > %d bytes", len([]byte(d.Contents)), MaxContentsBytes)
	}
	if d.SendLocalTime <= 0 {
		return errors.New("sendLocalTime must be a positive server-time value")
	}
	if d.TargetServer > 0 && d.SenderServer > 0 && d.TargetServer != d.SenderServer {
		return errors.New("cross-server private mail is not proven in Last War 1.0.351")
	}
	return nil
}

func BuildPrivateSameServerDryRun(d Draft) (DryRun, error) {
	if err := ValidatePrivateSameServer(d); err != nil {
		return DryRun{}, err
	}
	return DryRun{
		Version:          "V6.24",
		Command:          "mail.send",
		MailType:         MailSelfSend,
		Transport:        "SFS",
		MutationExecuted: false,
		NetworkEnabled:   false,
		Fields: []WireField{
			{Method: "PutUtfString", Key: "name", Value: d.TargetName},
			{Method: "PutUtfString", Key: "title", Value: d.Title},
			{Method: "PutUtfString", Key: "contents", Value: d.Contents},
			{Method: "PutUtfString", Key: "allianceId", Value: ""},
			{Method: "PutUtfString", Key: "targetUid", Value: d.TargetUID},
			{Method: "PutLong", Key: "sendLocalTime", Value: d.SendLocalTime},
			{Method: "PutInt", Key: "type", Value: MailSelfSend},
		},
	}, nil
}
