package messenger

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func validRequest() PlayerMailRequest {
	return NewPlayerMail("recruitment-fr-v1", "Player", "7568966261000065", "Bonjour", "Message", time.Now().UnixMilli())
}

func TestPlayerMailExactContractV625(t *testing.T) {
	r := validRequest()
	fields, err := r.WireContract()
	if err != nil { t.Fatal(err) }
	want := []struct{name, typ string}{
		{"name","UtfString"},{"title","UtfString"},{"contents","UtfString"},
		{"allianceId","UtfString"},{"targetUid","UtfString"},
		{"sendLocalTime","Long"},{"type","Int"},
	}
	if len(fields) != len(want) { t.Fatalf("fields=%#v", fields) }
	for i := range want {
		if fields[i].Name != want[i].name || fields[i].SFSType != want[i].typ {
			t.Fatalf("field %d=%#v want=%#v", i, fields[i], want[i])
		}
	}
	if r.Type != 21 { t.Fatalf("type=%d", r.Type) }
	if fields[3].Value != "" { t.Fatalf("allianceId must be empty for 1:1: %#v", fields[3]) }
}

func TestOfficialUILimitsV625(t *testing.T) {
	r := validRequest()
	r.Title = strings.Repeat("x", 50)
	r.Contents = strings.Repeat("y", 2000)
	if err := r.Validate(); err != nil { t.Fatal(err) }
	r.Title += "x"
	if !errors.Is(r.Validate(), ErrTitleTooLong) { t.Fatalf("expected title limit") }
	r = validRequest()
	r.Contents = strings.Repeat("y", 2001)
	if !errors.Is(r.Validate(), ErrContentTooLong) { t.Fatalf("expected content limit") }
}

func TestOfficialUIRequiresTitleAndContentV625(t *testing.T) {
	r := validRequest(); r.Title=""
	if !errors.Is(r.Validate(), ErrTitleRequired) { t.Fatal("empty title must block") }
	r=validRequest(); r.Contents=""
	if !errors.Is(r.Validate(), ErrContentRequired) { t.Fatal("empty content must block") }
}

func TestIdempotencyPerCampaignAndTargetV625(t *testing.T) {
	a,_:=IdempotencyKey("campaign-a","123")
	b,_:=IdempotencyKey("campaign-a","123")
	c,_:=IdempotencyKey("campaign-b","123")
	if a=="" || a!=b || a==c { t.Fatalf("a=%q b=%q c=%q",a,b,c) }
}

func TestNoAllianceOrPresidentTypeV625(t *testing.T) {
	r:=validRequest(); r.Type=20
	if !errors.Is(r.Validate(),ErrMailTypeInvalid){t.Fatal("alliance mail must be blocked")}
	r.Type=45
	if !errors.Is(r.Validate(),ErrMailTypeInvalid){t.Fatal("president mail must be blocked")}
}
