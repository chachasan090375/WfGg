package main

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"context"
	"database/sql"
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
}

func main() {
	master := flag.String("master", "", "gzip-compressed SQLite SQL dump")
	restore := flag.String("restore", "", "sandbox SQLite restore path")
	expectedPath := flag.String("expected", "", "expected baseline JSON")
	resultPath := flag.String("result", "", "result JSON path")
	flag.Parse()

	if *master == "" || *restore == "" || *expectedPath == "" || *resultPath == "" {
		fail("ARGS_MISSING")
	}
	if filepath.Clean(*master) == filepath.Clean(*restore) {
		fail("RESTORE_PATH_INVALID")
	}

	exp, err := readExpected(*expectedPath)
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
	}

	statements, err := restoreDump(*master, *restore)
	res.StatementsExecuted = statements
	if err != nil {
		res.Errors = append(res.Errors, "RESTORE_FAILED:"+err.Error())
		writeResult(*resultPath, res)
		os.Exit(2)
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

func readExpected(path string) (Expected, error) {
	var exp Expected
	b, err := os.ReadFile(path)
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

func restoreDump(master, restore string) (int64, error) {
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

		if len(frag) > 0 && frag[len(frag)-1] == ';' && terminalSemicolonOutsideSQL(stmt.Bytes()) {
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

func terminalSemicolonOutsideSQL(b []byte) bool {
	inSingle, inDouble, inBacktick, inBracket := false, false, false, false
	lineComment, blockComment := false, false
	candidateOutside := false

	for i := 0; i < len(b); i++ {
		c := b[i]
		var next byte
		if i+1 < len(b) {
			next = b[i+1]
		}

		if lineComment {
			if c == '\n' {
				lineComment = false
			}
			continue
		}
		if blockComment {
			if c == '*' && next == '/' {
				blockComment = false
				i++
			}
			continue
		}
		if inSingle {
			if c == '\'' {
				if next == '\'' {
					i++
				} else {
					inSingle = false
				}
			}
			continue
		}
		if inDouble {
			if c == '"' {
				if next == '"' {
					i++
				} else {
					inDouble = false
				}
			}
			continue
		}
		if inBacktick {
			if c == '`' {
				if next == '`' {
					i++
				} else {
					inBacktick = false
				}
			}
			continue
		}
		if inBracket {
			if c == ']' {
				inBracket = false
			}
			continue
		}

		if c == '-' && next == '-' {
			lineComment = true
			i++
			continue
		}
		if c == '/' && next == '*' {
			blockComment = true
			i++
			continue
		}
		switch c {
		case '\'':
			inSingle = true
		case '"':
			inDouble = true
		case '`':
			inBacktick = true
		case '[':
			inBracket = true
		case ';':
			candidateOutside = (i == len(b)-1)
		}
	}
	return candidateOutside && !inSingle && !inDouble && !inBacktick && !inBracket && !lineComment && !blockComment
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
