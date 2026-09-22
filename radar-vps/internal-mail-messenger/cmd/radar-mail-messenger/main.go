package main

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	messenger "github.com/chachasan090375/WfGg/radar-vps/internal-mail-messenger"
)

type output struct {
	OK      bool                  `json:"ok"`
	Version string                `json:"version"`
	Mode    messenger.Mode        `json:"mode,omitempty"`
	Entry   *messenger.OutboxEntry `json:"entry,omitempty"`
	Error   string                `json:"error,omitempty"`
}

func main() {
	mode, err := messenger.ParseMode(os.Getenv("WFGG_MAIL_MESSENGER_MODE"))
	if err != nil {
		emit(output{OK:false, Version:messenger.Version, Error:err.Error()})
		os.Exit(2)
	}
	var req messenger.PlayerMailRequest
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		emit(output{OK:false, Version:messenger.Version, Mode:mode, Error:"MAIL_REQUEST_JSON_INVALID_V625"})
		os.Exit(2)
	}
	entry, err := messenger.Prepare(mode, req, time.Now())
	if err != nil {
		emit(output{OK:false, Version:messenger.Version, Mode:mode, Error:err.Error()})
		os.Exit(2)
	}
	emit(output{OK:true, Version:messenger.Version, Mode:mode, Entry:&entry})
}

func emit(v output) {
	b, err := json.Marshal(v)
	if err != nil {
		fmt.Println(`{"ok":false,"error":"MAIL_OUTPUT_JSON_FAILED_V625"}`)
		return
	}
	fmt.Println(string(b))
}
