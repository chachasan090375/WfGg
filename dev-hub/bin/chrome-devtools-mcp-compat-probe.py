#!/usr/bin/env python3
"""Evidence-only Chrome DevTools MCP provider-specific compatibility probe.

Qualifies the upstream v1 MCP initialize handshake at 2025-11-25.
No browser tool is called and no lifecycle state is mutated.
"""
from __future__ import annotations
import argparse, hashlib, json, selectors, subprocess, threading, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/chrome-devtools-mcp-compat-probe/v1'
PROTOCOL='2025-11-25'
EXPECTED_READ={'list_pages','take_snapshot','take_screenshot','list_console_messages','get_console_message','list_network_requests','get_network_request'}
DENIED={'evaluate_script','click','click_at','drag','fill','fill_form','handle_dialog','hover','press_key','type_text','upload_file','navigate_page','new_page','close_page','resize_page','emulate','lighthouse_audit','performance_start_trace','performance_stop_trace','performance_analyze_insight'}

def now(): return datetime.now(timezone.utc).isoformat()
def digest(v: Any) -> str:
    return 'sha256:'+hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

class MCP:
    def __init__(self, argv:list[str], cwd:Path, timeout:float=25):
        self.timeout=timeout
        self.p=subprocess.Popen(argv,cwd=str(cwd),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        assert self.p.stdin and self.p.stdout and self.p.stderr
        self.sel=selectors.DefaultSelector(); self.sel.register(self.p.stdout,selectors.EVENT_READ)
        self.err=[]; threading.Thread(target=self._drain,daemon=True).start()
    def _drain(self):
        assert self.p.stderr
        for line in self.p.stderr:
            s=line.rstrip('\n')
            if s:
                self.err.append(s[:1000]); self.err=self.err[-100:]
    def request(self, id_:str, method:str, params:dict|None=None):
        assert self.p.stdin and self.p.stdout
        self.p.stdin.write(json.dumps({'jsonrpc':'2.0','id':id_,'method':method,'params':params or {}},separators=(',',':'))+'\n'); self.p.stdin.flush()
        deadline=time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            if self.p.poll() is not None: raise RuntimeError(f'MCP_SERVER_EXITED:{self.p.returncode}')
            for _key, _mask in self.sel.select(min(.5,max(.1,deadline-time.monotonic()))):
                line=self.p.stdout.readline()
                if not line: continue
                try: m=json.loads(line)
                except json.JSONDecodeError: continue
                if str(m.get('id'))==str(id_): return m
        raise TimeoutError(method)
    def notify(self, method:str, params:dict|None=None):
        assert self.p.stdin
        self.p.stdin.write(json.dumps({'jsonrpc':'2.0','method':method,'params':params or {}},separators=(',',':'))+'\n'); self.p.stdin.flush()
    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:self.p.kill(); self.p.wait(timeout=5)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--server',required=True,type=Path); ap.add_argument('--workdir',required=True,type=Path); ap.add_argument('--output',required=True,type=Path); ap.add_argument('--package-version',required=True); a=ap.parse_args()
    e={'schema':SCHEMA,'observed_at':now(),'provider':'chrome-devtools-mcp','adapter':'chrome-devtools-mcp-adapter','package':'chrome-devtools-mcp','package_version':a.package_version,'compatibility_mode':'EXPLICIT_PROVIDER_COMPATIBILITY','dev_hub_protocol_baseline':'2026-07-28','requested_protocol':PROTOCOL,'generic_legacy_fallback':False,'browser_launched':False,'browser_downloaded':False,'called_tools':[],'vps_modified':False,'production_target':False,'credentials_used':False,'checks':{},'promotion':{'automatic':False,'eligible_for_compat_pilot':False,'blockers':[]}}
    blockers=[]; c=None
    try:
        c=MCP([str(a.server),'--headless=true','--isolated=true','--no-javascript-evaluation','--no-performance-crux','--no-usage-statistics','--redact-network-headers','--no-source-maps'],a.workdir)
        init=c.request('1','initialize',{'protocolVersion':PROTOCOL,'capabilities':{},'clientInfo':{'name':'chacha-dev-chrome-devtools-compat-probe','version':'1.0.0'}})
        e['checks']['initialize']={'pass':'error' not in init,'error':init.get('error')}
        if 'error' in init: blockers.append('MCP_2025_11_25_INITIALIZE_FAILED'); raise RuntimeError('INITIALIZE_BLOCKED')
        r=init.get('result') or {}; e['negotiated_protocol_version']=r.get('protocolVersion'); e['server_info']=r.get('serverInfo'); e['server_capabilities']=r.get('capabilities')
        if r.get('protocolVersion')!=PROTOCOL: blockers.append('MCP_2025_11_25_NOT_NEGOTIATED'); raise RuntimeError('NEGOTIATION_BLOCKED')
        c.notify('notifications/initialized')
        tools=c.request('2','tools/list',{})
        e['checks']['tools_list']={'pass':'error' not in tools,'error':tools.get('error')}
        if 'error' in tools: blockers.append('TOOLS_LIST_FAILED'); raise RuntimeError('TOOLS_LIST_BLOCKED')
        items=((tools.get('result') or {}).get('tools') or []); names=sorted(str(x.get('name')) for x in items if isinstance(x,dict) and x.get('name'))
        e['tools_exposed']=names; missing=sorted(EXPECTED_READ-set(names)); denied=sorted(DENIED & set(names))
        e['checks']['tool_surface']={'pass':not missing,'tool_count':len(names),'missing_expected_read':missing,'denied_tools_exposed_but_not_authorized':denied}
        if missing: blockers.extend('EXPECTED_READ_TOOL_MISSING:'+x for x in missing)
    except Exception as ex:
        e['probe_exception']=str(ex)
        if not blockers: blockers.append('PROBE_INFRASTRUCTURE_FAILURE')
    finally:
        if c: e['server_stderr_tail']=c.err[-20:]; c.close()
    e['promotion']={'automatic':False,'eligible_for_compat_pilot':not blockers,'blockers':sorted(set(blockers))}
    e['evidence_digest']=digest({k:v for k,v in e.items() if k!='evidence_digest'})
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(e,indent=2,ensure_ascii=False)+'\n')
    print('ELIGIBLE_FOR_COMPAT_PILOT='+('YES' if not blockers else 'NO'))
    for b in sorted(set(blockers)): print('BLOCKER='+b)
    return 0
if __name__=='__main__': raise SystemExit(main())
