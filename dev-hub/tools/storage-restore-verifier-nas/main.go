package main

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

type Expected struct {
	RowCounts             map[string]int64  `json:"row_counts"`
	BaselineCycle         int64             `json:"baseline_cycle"`
	ObservationsWatermark map[string]any    `json:"observations_watermark"`
	MastersWatermark      map[string]any    `json:"masters_watermark"`
}

type stringList []string

func (s *stringList) String() string {
	return strings.Join(*s, ",")
}

func (s *stringList) Set(value string) error {
	if strings.TrimSpace(value) == "" {
		return errors.New("empty patch path")
	}
	*s = append(*s, value)
	return nil
}

type Result struct {
	Schema                string           `json:"schema"`
	Status                string           `json:"status"`
	ObservedAt            string           `json:"observed_at"`
	Integrity             string           `json:"integrity"`
	Tables                []string         `json:"tables"`
	RowCounts             map[string]int64 `json:"row_counts"`
	BaselineCycle         int64            `json:"baseline_cycle"`
	ObservationsWatermark map[string]any   `json:"observations_watermark"`
	MastersWatermark      map[string]any   `json:"masters_watermark"`
	Errors                []string         `json:"errors"`
	StatementsExecuted    int64            `json:"statements_executed"`
	PatchCount            int              `json:"patch_count"`
}

func main() {
	master := flag.String("master", "", "gzip-compressed SQLite SQL dump")
	restore := flag.String("restore", "", "sandbox SQLite restore path")
	expectedPath := flag.String("expected", "", "expected baseline JSON file")
	expectedB64 := flag.String("expected-b64", "", "base64-encoded expected baseline JSON")
	resultPath := flag.String("result", "", "result JSON path")
	var patches stringList
	flag.Var(&patches, "patch", "gzip-compressed SQLite SQL patch; repeat in chain order")
	flag.Parse()

	if *master == "" || *restore == "" || (*expectedPath == "" && *expectedB64 == "") || *resultPath == "" {
		fail("ARGS_MISSING")
	}
	if *expectedPath != "" && *expectedB64 != "" {
		fail("EXPECTED_SOURCE_AMBIGUOUS")
	}
	if filepath.Clean(*master) == filepath.Clean(*restore) {
		fail("RESTORE_PATH_INVALID")
	}
	for _, patch := range patches {
		if filepath.Clean(patch) == filepath.Clean(*restore) {
			fail("PATCH_PATH_INVALID")
		}
	}

	exp, err := readExpected(*expectedPath, *expectedB64)
	if err != nil {
		fail("EXPECTED_READ_FAILED:" + err.Error())
	}

	if err := os.RemoveAll(*restore); err != nil && !errors.Is(err, os.ErrNotExist) {
		fail("RESTORE_PREP_FAILED:" + err.Error())
	}
	if err := os.MkdirAll(filepath.Dir(*restore), 0700); err != nil {
		fail("RESTORE_DIR_FAILED:" + err.Error())
	}

	res := Result{
		Schema:                "chacha.dev/collector-portable-restore-verifier/v1",
		Status:                "FAILED",
		ObservedAt:            time.Now().UTC().Format(time.RFC3339Nano),
		RowCounts:             map[string]int64{},
		ObservationsWatermark: map[string]any{},
		MastersWatermark:      map[string]any{},
		Errors:                []string{},
		PatchCount:            len(patches),
	}

	statements, err := applyGzipSQL(*master, *restore)
	res.StatementsExecuted = statements
	if err != nil {
		res.Errors = append(res.Errors, "RESTORE_FAILED:"+err.Error())
		writeResult(*resultPath, res)
		os.Exit(2)
	}

	for index, patch := range patches {
		n, patchErr := applyGzipSQL(patch, *restore)
		res.StatementsExecuted += n
		if patchErr != nil {
			res.Errors = append(
				res.Errors,
				fmt.Sprintf("PATCH_FAILED:%d:%s", index+1, patchErr.Error()),
			)
			writeResult(*resultPath, res)
			os.Exit(2)
		}
	}

	if err := verifyDB(*restore, exp, &res); err != nil {
		res.Errors = append(res.Errors, "VERIFY_FAILED:"+err.Error())
		writeResult(*resultPath, res)
		os.Exit(3)
	}

	if len(res.Errors) == 0 {
		res.Status = "PASS"
	}
	writeResult(*resultPath, res)
	if res.Status != "PASS" {
		os.Exit(4)
	}
}

func readExpected(path, encoded string) (Expected, error) {
	var exp Expected
	var b []byte
	var err error
	if encoded != "" {
		b, err = base64.StdEncoding.DecodeString(encoded)
	} else {
		b, err = os.ReadFile(path)
	}
	if err != nil {
		return exp, err
	}
	if err := json.Unmarshal(b, &exp); err != nil {
		return exp, err
	}
	if len(exp.RowCounts) == 0 || exp.BaselineCycle <= 0 {
		return exp, errors.New("expected baseline incomplete")
	}
	return exp, nil
}

func applyGzipSQL(master, restore string) (int64, error) {
	f, err := os.Open(master)
	if err != nil {
		return 0, err
	}
	defer f.Close()

	gz, err := gzip.NewReader(f)
	if err != nil {
		return 0, err
	}
	defer gz.Close()

	db, err := sql.Open("sqlite", restore)
	if err != nil {
		return 0, err
	}
	defer db.Close()

	ctx := context.Background()
	conn, err := db.Conn(ctx)
	if err != nil {
		return 0, err
	}
	defer conn.Close()

	if _, err := conn.ExecContext(ctx, "PRAGMA journal_mode=OFF;"); err != nil {
		return 0, err
	}
	if _, err := conn.ExecContext(ctx, "PRAGMA synchronous=OFF;"); err != nil {
		return 0, err
	}
	if _, err := conn.ExecContext(ctx, "PRAGMA temp_store=MEMORY;"); err != nil {
		return 0, err
	}

	r := bufio.NewReaderSize(gz, 1024*1024)
	var stmt bytes.Buffer
	var count int64

	for {
		frag, readErr := r.ReadBytes(';')
		if len(frag) > 0 {
			if stmt.Len()+len(frag) > 64*1024*1024 {
				return count, errors.New("statement exceeds 64 MiB")
			}
			stmt.Write(frag)
		}

		if len(frag) > 0 && frag[len(frag)-1] == ';' && statementCompleteSQL(stmt.Bytes()) {
			sqlText := strings.TrimSpace(stmt.String())
			stmt.Reset()
			if sqlText != "" {
				if _, err := conn.ExecContext(ctx, sqlText); err != nil {
					return count, fmt.Errorf("statement %d: %w", count+1, err)
				}
				count++
			}
		}

		if readErr != nil {
			if errors.Is(readErr, io.EOF) {
				break
			}
			return count, readErr
		}
	}

	if strings.TrimSpace(stmt.String()) != "" {
		return count, errors.New("trailing incomplete SQL")
	}
	return count, nil
}

func statementCompleteSQL(b []byte) bool {
	if len(b) == 0 || b[len(b)-1] != ';' {
		return false
	}

	type token struct {
		word string
		pos  int
	}
	var tokens []token

	inSingle, inDouble, inBacktick, inBracket := false, false, false, false
	lineComment, blockComment := false, false
	wordStart := -1

	flushWord := func(i int) {
		if wordStart >= 0 {
			tokens = append(tokens, token{
				word: strings.ToUpper(string(b[wordStart:i])),
				pos:  wordStart,
			})
			wordStart = -1
		}
	}

	for i := 0; i < len(b); i++ {
		ch := b[i]
		var next byte
		if i+1 < len(b) {
			next = b[i+1]
		}

		if lineComment {
			if ch == '\n' {
				lineComment = false
			}
			continue
		}
		if blockComment {
			if ch == '*' && next == '/' {
				blockComment = false
				i++
			}
			continue
		}
		if inSingle {
			if ch == '\'' {
				if next == '\'' {
					i++
				} else {
					inSingle = false
				}
			}
			continue
		}
		if inDouble {
			if ch == '"' {
				if next == '"' {
					i++
				} else {
					inDouble = false
				}
			}
			continue
		}
		if inBacktick {
			if ch == '`' {
				if next == '`' {
					i++
				} else {
					inBacktick = false
				}
			}
			continue
		}
		if inBracket {
			if ch == ']' {
				inBracket = false
			}
			continue
		}

		if ch == '-' && next == '-' {
			flushWord(i)
			lineComment = true
			i++
			continue
		}
		if ch == '/' && next == '*' {
			flushWord(i)
			blockComment = true
			i++
			continue
		}

		switch ch {
		case '\'':
			flushWord(i)
			inSingle = true
			continue
		case '"':
			flushWord(i)
			inDouble = true
			continue
		case '`':
			flushWord(i)
			inBacktick = true
			continue
		case '[':
			flushWord(i)
			inBracket = true
			continue
		}

		isWord := (ch >= 'a' && ch <= 'z') ||
			(ch >= 'A' && ch <= 'Z') ||
			(ch >= '0' && ch <= '9') ||
			ch == '_'
		if isWord {
			if wordStart < 0 {
				wordStart = i
			}
		} else {
			flushWord(i)
		}
	}
	flushWord(len(b))

	if inSingle || inDouble || inBacktick || inBracket || blockComment {
		return false
	}

	// Ordinary SQLite statements are complete at a terminal semicolon.
	// CREATE TRIGGER is the important exception: its body contains internal
	// semicolons between statements and is complete only at the outer END;.
	isTrigger := false
	if len(tokens) >= 2 && tokens[0].word == "CREATE" {
		if tokens[1].word == "TRIGGER" {
			isTrigger = true
		} else if len(tokens) >= 3 &&
			(tokens[1].word == "TEMP" || tokens[1].word == "TEMPORARY") &&
			tokens[2].word == "TRIGGER" {
			isTrigger = true
		}
	}
	if !isTrigger {
		return true
	}

	bodyStarted := false
	caseDepth := 0
	outerEndSeen := false
	for _, t := range tokens {
		switch t.word {
		case "BEGIN":
			if !bodyStarted {
				bodyStarted = true
			}
		case "CASE":
			if bodyStarted {
				caseDepth++
			}
		case "END":
			if bodyStarted {
				if caseDepth > 0 {
					caseDepth--
				} else {
					outerEndSeen = true
				}
			}
		default:
			if bodyStarted && outerEndSeen {
				// Any SQL token after the outer END means that END belonged
				// to something else; keep accumulating until a later END;.
				outerEndSeen = false
			}
		}
	}
	return bodyStarted && caseDepth == 0 && outerEndSeen
}

func verifyDB(path string, exp Expected, res *Result) error {
	db, err := sql.Open("sqlite", "file:"+path+"?mode=ro")
	if err != nil {
		return err
	}
	defer db.Close()

	if err := db.QueryRow("PRAGMA integrity_check;").Scan(&res.Integrity); err != nil {
		return err
	}
	if res.Integrity != "ok" {
		res.Errors = append(res.Errors, "SQLITE_INTEGRITY_FAILED")
	}

	rows, err := db.Query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
	if err != nil {
		return err
	}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return err
		}
		res.Tables = append(res.Tables, name)
	}
	rows.Close()

	expectedTables := make([]string, 0, len(exp.RowCounts))
	for table := range exp.RowCounts {
		expectedTables = append(expectedTables, table)
	}
	sort.Strings(expectedTables)
	if !equalStrings(res.Tables, expectedTables) {
		res.Errors = append(res.Errors, "TABLE_SET_MISMATCH")
	}

	for _, table := range expectedTables {
		var n int64
		q := fmt.Sprintf("SELECT COUNT(*) FROM %s", quoteIdent(table))
		if err := db.QueryRow(q).Scan(&n); err != nil {
			return err
		}
		res.RowCounts[table] = n
		if n != exp.RowCounts[table] {
			res.Errors = append(res.Errors, "ROW_COUNT_MISMATCH:"+table)
		}
	}

	if err := db.QueryRow("SELECT COALESCE(MAX(id),0) FROM cycles").Scan(&res.BaselineCycle); err != nil {
		return err
	}
	if res.BaselineCycle != exp.BaselineCycle {
		res.Errors = append(res.Errors, "BASELINE_CYCLE_MISMATCH")
	}

	var obsAt string
	var obsID int64
	if err := db.QueryRow("SELECT observed_at,id FROM observations ORDER BY observed_at DESC,id DESC LIMIT 1").Scan(&obsAt, &obsID); err != nil {
		return err
	}
	res.ObservationsWatermark = map[string]any{"observed_at": obsAt, "id": obsID}
	if obsAt != asString(exp.ObservationsWatermark["observed_at"]) || obsID != asInt64(exp.ObservationsWatermark["id"]) {
		res.Errors = append(res.Errors, "OBSERVATIONS_WATERMARK_MISMATCH")
	}

	var masterAt string
	var masterID int64
	if err := db.QueryRow("SELECT created_at,id FROM masters ORDER BY created_at DESC,id DESC LIMIT 1").Scan(&masterAt, &masterID); err != nil {
		return err
	}
	res.MastersWatermark = map[string]any{"created_at": masterAt, "id": masterID}
	if masterAt != asString(exp.MastersWatermark["created_at"]) || masterID != asInt64(exp.MastersWatermark["id"]) {
		res.Errors = append(res.Errors, "MASTERS_WATERMARK_MISMATCH")
	}
	return nil
}

func quoteIdent(s string) string {
	return `"` + strings.ReplaceAll(s, `"`, `""`) + `"`
}

func asString(v any) string {
	switch x := v.(type) {
	case string:
		return x
	default:
		return fmt.Sprint(v)
	}
}

func asInt64(v any) int64 {
	switch x := v.(type) {
	case float64:
		return int64(x)
	case int:
		return int64(x)
	case int64:
		return x
	case json.Number:
		n, _ := x.Int64()
		return n
	default:
		var n int64
		fmt.Sscan(fmt.Sprint(v), &n)
		return n
	}
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func writeResult(path string, res Result) {
	b, _ := json.MarshalIndent(res, "", "  ")
	_ = os.WriteFile(path, append(b, '\n'), 0600)
}

func fail(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	os.Exit(1)
}
