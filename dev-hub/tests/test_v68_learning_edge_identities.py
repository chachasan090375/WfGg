#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
P=ROOT/"dev-hub/bin/learning-identity-provisioner.py"
CFG=json.load(open(ROOT/"dev-hub/config/learning-edge.v1.json",encoding="utf-8"))
D=json.load(open(ROOT/"dev-hub/evidence/technology-watch-learning-edge-v68.json",encoding="utf-8"))
assert CFG["scope"]=="PLATFORM_GLOBAL"
assert CFG["app_specific"] is False
assert CFG["selected_provider"]["id"]=="cloudflare-tunnel"
assert CFG["security"]["central_ingress_remains_loopback_only"] is True
assert CFG["economics"]["automatic_external_spend_eur"]==0
assert D["selected"]=="cloudflare-tunnel" and D["automatic_external_spend_eur"]==0
with tempfile.TemporaryDirectory(prefix="chacha-v68-id-") as td:
    td=Path(td);reg=td/"keys.json";bundles=td/"bundles"
    cmd=["python3",str(P),"--registry",str(reg),"provision","--project-id","app-generic","--deployment-id","prod-1","--source-scope","all-learning-capable-components","--endpoint","https://learning.example.test","--bundle-dir",str(bundles)]
    out=json.loads(subprocess.check_output(cmd,text=True))
    assert out["status"]=="PROVISIONED";assert out["secret_revealed"] is False
    env=Path(out["bundle_path"]);pub=Path(out["public_identity_path"])
    assert oct(env.stat().st_mode & 0o777)=="0o600"
    txt=env.read_text();assert "CHACHA_LEARNING_UPLINK_SECRET=" in txt
    public_identity=json.load(open(pub,encoding="utf-8"))
    assert "secret" not in public_identity
    assert public_identity["credential_material_in_this_file"] is False
    secret_line=[line for line in txt.splitlines() if line.startswith("CHACHA_LEARNING_UPLINK_SECRET=")][0]
    secret_value=secret_line.split("=",1)[1]
    assert secret_value not in pub.read_text(encoding="utf-8")
    stat=json.loads(subprocess.check_output(["python3",str(P),"--registry",str(reg),"status"],text=True))
    assert stat["secret_values_exposed"] is False
    key=out["key_id"]
    rev=json.loads(subprocess.check_output(["python3",str(P),"--registry",str(reg),"revoke","--key-id",key,"--reason","test"],text=True))
    assert rev["status"]=="REVOKED"
    x=json.load(open(reg));assert x["keys"][key]["status"]=="REVOKED"
print("CHACHA_DEV_V68_IDENTITY_PROVISIONING=PASS")
print("CHACHA_DEV_V68_SECRET_NON_DISCLOSURE=PASS")
print("CHACHA_DEV_V68_KEY_REVOCATION=PASS")
print("CHACHA_DEV_V68_ZERO_SPEND_EDGE_SELECTION=PASS")
