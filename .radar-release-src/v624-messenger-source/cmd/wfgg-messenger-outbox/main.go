package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"wfgg-lastwar-messenger-v624/internal/mailcontract"
	"wfgg-lastwar-messenger-v624/internal/outbox"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("wfgg-messenger-outbox", flag.ContinueOnError)
	fs.SetOutput(stderr)
	ledger := fs.String("ledger", os.Getenv("WFGG_MESSENGER_OUTBOX_LEDGER"), "append-only outbox ledger path")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if strings.TrimSpace(*ledger) == "" {
		fmt.Fprintln(stderr, "WFGG_MESSENGER_OUTBOX_LEDGER or -ledger is required")
		return 2
	}
	if fs.NArg() < 1 {
		fmt.Fprintln(stderr, "command required: create|queue|cancel|show|history|list")
		return 2
	}
	store, err := outbox.Open(*ledger)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}

	switch fs.Arg(0) {
	case "create":
		var d mailcontract.Draft
		dec := json.NewDecoder(io.LimitReader(stdin, 64*1024))
		dec.DisallowUnknownFields()
		if err := dec.Decode(&d); err != nil {
			fmt.Fprintln(stderr, "decode draft:", err)
			return 2
		}
		r, reused, err := store.CreateOrReuse(d, time.Now().UTC())
		if err != nil {
			fmt.Fprintln(stderr, err)
			return 1
		}
		return writeJSON(stdout, struct {
			Record outbox.Record `json:"record"`
			Reused bool          `json:"reused"`
		}{r, reused})
	case "queue":
		if fs.NArg() != 2 { fmt.Fprintln(stderr, "queue requires message id"); return 2 }
		r, err := store.Queue(fs.Arg(1), time.Now().UTC())
		if err != nil { fmt.Fprintln(stderr, err); return 1 }
		return writeJSON(stdout, r)
	case "cancel":
		if fs.NArg() != 2 { fmt.Fprintln(stderr, "cancel requires message id"); return 2 }
		r, err := store.Cancel(fs.Arg(1), time.Now().UTC())
		if err != nil { fmt.Fprintln(stderr, err); return 1 }
		return writeJSON(stdout, r)
	case "show":
		if fs.NArg() != 2 { fmt.Fprintln(stderr, "show requires message id"); return 2 }
		r, ok, err := store.Get(fs.Arg(1))
		if err != nil { fmt.Fprintln(stderr, err); return 1 }
		if !ok { fmt.Fprintln(stderr, "message not found"); return 3 }
		return writeJSON(stdout, r)
	case "history":
		if fs.NArg() != 2 { fmt.Fprintln(stderr, "history requires message id"); return 2 }
		r, err := store.History(fs.Arg(1))
		if err != nil { fmt.Fprintln(stderr, err); return 1 }
		return writeJSON(stdout, r)
	case "list":
		r, err := store.List()
		if err != nil { fmt.Fprintln(stderr, err); return 1 }
		return writeJSON(stdout, r)
	default:
		fmt.Fprintf(stderr, "unknown command %q\n", fs.Arg(0))
		return 2
	}
}

func writeJSON(w io.Writer, v any) int {
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		return 1
	}
	return 0
}
