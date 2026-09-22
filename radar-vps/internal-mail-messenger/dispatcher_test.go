package messenger

import (
	"errors"
	"testing"
	"time"
)

func TestDisabledIsDefaultAndCannotMutateV625(t *testing.T) {
	mode, err := ParseMode("")
	if err != nil || mode != ModeDisabled {
		t.Fatalf("mode=%q err=%v", mode, err)
	}
	entry, err := Prepare(mode, validRequest(), time.Unix(1, 0))
	if err != nil {
		t.Fatal(err)
	}
	if entry.State != StateBlocked || entry.LastWarMutation || entry.GameConnection != "NONE" {
		t.Fatalf("entry=%#v", entry)
	}
}

func TestDryRunPreparesButNeverConnectsV625(t *testing.T) {
	entry, err := Prepare(ModeDryRun, validRequest(), time.Unix(1, 0))
	if err != nil {
		t.Fatal(err)
	}
	if entry.State != StateDryRunReady || entry.LastWarMutation || entry.GameConnection != "NONE" {
		t.Fatalf("entry=%#v", entry)
	}
}

func TestLiveModeIsImpossibleV625(t *testing.T) {
	_, err := ParseMode("ENABLED")
	if !errors.Is(err, ErrLiveModeForbidden) {
		t.Fatalf("err=%v", err)
	}
}
