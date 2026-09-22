#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, struct, subprocess
from pathlib import Path

COUNT_TERMS = (
    "totalnum","totalcount","playernum","playercount","rolenum","rolecount",
    "usernum","usercount","membernum","membercount","onlinenum","onlinecount",
    "register","registered","population","ranknum","rankcount","maxrank",
    "totalplayer","totalrole","totaluser","allnum",
)

def patch_unluac(root: Path) -> None:
    p=root/"src/unluac/parse/LHeaderType.java"
    s=p.read_text()
    old='    if(format != 0) {\n      throw new IllegalStateException("The input chunk reports a non-standard lua format: " + format);\n    }'
    new='    if(format != 0 && format != 1) {\n      throw new IllegalStateException("The input chunk reports an unsupported lua format: " + format);\n    }'
    if old not in s:
        raise SystemExit("V625_UNLUAC_FORMAT_ANCHOR_MISSING")
    s=s.replace(old,new,1)
    old2='    parse_size_t_size(buffer, header, s);\n    parse_instruction_size(buffer, header, s);\n    parse_integer_size(buffer, header, s);'
    new2='    parse_size_t_size(buffer, header, s);\n    if(s.format != 1) {\n      parse_instruction_size(buffer, header, s);\n    }\n    parse_integer_size(buffer, header, s);'
    if old2 not in s:
        raise SystemExit("V625_UNLUAC_INSTRUCTION_ANCHOR_MISSING")
    p.write_text(s)
    print("V625_UNLUAC_PATCHED=YES")

def read7(data: bytes, off: int):
    value=0; shift=0
    for _ in range(5):
        x=data[off]; off+=1
        value |= (x & 0x7f) << shift
        if not x & 0x80:
            return value,off
        shift += 7
    raise ValueError("bad 7bit")

def extract_candidates(pack: Path, out: Path) -> list[dict]:
    data=pack.read_bytes()
    if data[:4] != b"LWLF":
        raise SystemExit("V625_LWLF_MAGIC_INVALID")
    _,_,count=struct.unpack_from("<III",data,4)
    pos=16
    out.mkdir(parents=True,exist_ok=True)
    picked=[]
    for i in range(count):
        n,pos=read7(data,pos)
        name=data[pos:pos+n].decode("utf-8","replace"); pos+=n
        size=struct.unpack_from("<I",data,pos)[0]; pos+=4
        chunk=data[pos:pos+size]; pos+=size
        low=name.lower()
        raw=chunk.decode("latin1","ignore").lower()
        has_count=any(x in raw for x in COUNT_TERMS)
        target=(
            "seasonserverdetail" in low
            or ("server" in low and ("detail" in low or "info" in low) and has_count)
            or ("net/msgs/" in low and "server" in low and has_count)
            or ("playerdata" in low and has_count)
        )
        if target:
            fn=f"{i:05d}_"+name.replace("/","_")
            (out/fn).write_bytes(chunk)
            picked.append({"index":i,"name":name,"file":fn,"size":size})
    Path("/tmp/v625-picked.json").write_text(json.dumps(picked,indent=2))
    print(f"V625_ENTRY_COUNT={count}")
    print(f"V625_POP_MODULE_COUNT={len(picked)}")
    for x in picked:
        print("V625_POP_MODULE="+x["name"])
    return picked

def decompile(jar: Path, src: Path, out: Path) -> None:
    out.mkdir(parents=True,exist_ok=True)
    for p in sorted(src.glob("*.luac")):
        dst=out/(p.stem+".lua")
        err=out/(p.stem+".err")
        cp=subprocess.run(["java","-jar",str(jar),str(p)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        dst.write_bytes(cp.stdout)
        err.write_bytes(cp.stderr)
        print(("V625_DECOMPILE_OK=" if cp.returncode==0 else "V625_DECOMPILE_FAIL=")+p.stem)

def analyze(src: Path) -> None:
    report=[]
    for p in sorted(src.glob("*.lua")):
        s=p.read_text(errors="replace")
        low=s.lower()
        terms=[x for x in COUNT_TERMS if x in low]
        if not terms:
            continue
        lines=s.splitlines()
        selected=[]
        for i,line in enumerate(lines):
            ll=line.lower()
            if any(x in ll for x in terms+["serverid","cmd =","message","rank","oncreate","handleresponse"]):
                selected.extend(lines[max(0,i-5):min(len(lines),i+9)])
        dedup=[]
        for x in selected:
            if x not in dedup: dedup.append(x)
        report.append({"file":p.name,"terms":terms,"evidence":dedup[:240]})
    Path("/tmp/v625-population-evidence.json").write_text(json.dumps(report,indent=2))
    print(f"V625_EVIDENCE_MODULES={len(report)}")
    for r in report:
        print("===== "+r["file"]+" =====")
        print("V625_TERMS="+",".join(r["terms"]))
        for x in r["evidence"][:160]:
            print(x[:300])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--patch-unluac")
    ap.add_argument("--pack")
    ap.add_argument("--jar")
    args=ap.parse_args()
    if args.patch_unluac:
        patch_unluac(Path(args.patch_unluac)); return
    if not (args.pack and args.jar):
        raise SystemExit("--pack and --jar required")
    src=Path("/tmp/v625-pop")
    dec=Path("/tmp/v625-decompiled")
    extract_candidates(Path(args.pack),src)
    decompile(Path(args.jar),src,dec)
    analyze(dec)
    print("V625_LASTWAR_CONNECTION=NONE")
    print("V625_LASTWAR_MUTATION=NO")
    print("V625_GAME_SCAN_EXECUTED=NO")

if __name__=="__main__":
    main()
