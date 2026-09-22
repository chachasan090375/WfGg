package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"

	mailer "wfgg/radar-mailer"
)

func main() {
	version := flag.Bool("version", false, "print version")
	dryRun := flag.Bool("dry-run", false, "print V6.25/V6.26 safety state")
	listen := flag.String("listen", "", "serve the signed V6.26 Outbox API (example: 127.0.0.1:8788)")
	outbox := flag.String("outbox", "", "override the Outbox JSONL path")
	flag.Parse()

	if *version {
		fmt.Println(mailer.BridgeVersion)
		return
	}
	if *dryRun {
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{
			"version":          mailer.BridgeVersion,
			"command":          mailer.LastWarCommand,
			"mailTypeSelf":     mailer.MailTypeSelf,
			"lastwarWrite":     false,
			"lastwarMutation":  false,
			"tokenPersistence": false,
			"outboxOnly":       true,
			"signedOutboxAPI":  true,
		})
		return
	}
	if *listen != "" {
		path := *outbox
		if path == "" {
			path = mailer.DefaultOutboxPath
		}
		key := os.Getenv("RADAR_MAILER_SHARED_KEY")
		handler, err := mailer.NewHTTPHandler(&mailer.Store{Path: path}, key)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		fmt.Fprintf(os.Stderr, "radar-mailer %s listening on %s · OUTBOX_DRY_RUN · Last War write disabled\n", mailer.BridgeVersion, *listen)
		if err := http.ListenAndServe(*listen, handler); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	fmt.Fprintln(os.Stderr, "V6.26 is outbox dry-run only; use --listen, --dry-run or --version")
	os.Exit(2)
}
