package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"wfgg-lastwar-mail-outbox-v625/internal/outbox"
)

func main() {
	var path string
	flag.StringVar(&path, "outbox", "", "path to the V6.25 dry-run outbox JSON file")
	flag.Parse()
	if path == "" {
		path = os.Getenv("WFGG_MAIL_OUTBOX_PATH")
	}
	if path == "" {
		fmt.Fprintln(os.Stderr, "OUTBOX_PATH_REQUIRED")
		os.Exit(2)
	}

	var req outbox.PrepareRequest
	dec := json.NewDecoder(os.Stdin)
	if err := dec.Decode(&req); err != nil {
		fmt.Fprintln(os.Stderr, "OUTBOX_REQUEST_INVALID:", err)
		os.Exit(2)
	}

	store, err := outbox.NewFileStore(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, "OUTBOX_STORE_INVALID:", err)
		os.Exit(2)
	}
	item, created, err := store.Prepare(req)
	if err != nil {
		fmt.Fprintln(os.Stderr, "OUTBOX_PREPARE_FAILED:", err)
		os.Exit(3)
	}
	resp := struct {
		OK      bool        `json:"ok"`
		Created bool        `json:"created"`
		Item    outbox.Item `json:"item"`
	}{OK: true, Created: created, Item: item}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(resp); err != nil {
		fmt.Fprintln(os.Stderr, "OUTBOX_RESPONSE_FAILED:", err)
		os.Exit(4)
	}
}
