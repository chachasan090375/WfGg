package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	mailer "wfgg/radar-mailer"
)

func main() {
	version := flag.Bool("version", false, "print version")
	dryRun := flag.Bool("dry-run", false, "print V6.25 safety state")
	flag.Parse()

	if *version {
		fmt.Println(mailer.Version)
		return
	}
	if *dryRun {
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{
			"version":           mailer.Version,
			"command":           mailer.LastWarCommand,
			"mailTypeSelf":      mailer.MailTypeSelf,
			"lastwarWrite":      false,
			"lastwarMutation":   false,
			"tokenPersistence":  false,
			"outboxOnly":        true,
		})
		return
	}
	fmt.Fprintln(os.Stderr, "V6.25 is dry-run only; use --dry-run or --version")
	os.Exit(2)
}
