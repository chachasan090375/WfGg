#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/scripts/lastwar-formation-lua-trace-viewer-build-v1.sh"
IDX="$ROOT/frontend/lab/master-assets-v2/meta/lwscripts-luac-index-v1.json"
MANIFEST="$ROOT/frontend/lab/formation-lua-trace-viewer-data/manifest.json"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$BASE" ]] || fail "builder v1 absent"
bash "$BASE"
[[ -s "$MANIFEST" ]] || fail "manifest absent"
if [[ ! -s "$IDX" ]]; then
  printf 'FORMATION_LUA_TRACE_VIEWER_V2_NO_LUAC_INDEX\n'
  exit 0
fi
python - "$MANIFEST" "$IDX" <<'PY'
from pathlib import Path
from collections import defaultdict,deque
import json,sys
manifest,idxp=map(Path,sys.argv[1:])
m=json.loads(manifest.read_text('utf-8')); idx=json.loads(idxp.read_text('utf-8'))
nodes={n['id']:n for n in m.get('nodes',[])}
edges=list(m.get('edges',[])); evidence=list(m.get('evidence',[])); scripts=list(m.get('scripts',[]))

def add_node(nid,label,kind='lua',**extra):
    if nid in nodes:
        nodes[nid].update({k:v for k,v in extra.items() if v not in (None,'',[],{})});return
    n={'id':nid,'label':label,'kind':kind};n.update(extra);nodes[nid]=n

def add_edge(src,dst,relation,proof,confidence,text,source):
    if src not in nodes or dst not in nodes:return
    for e in edges:
        if e.get('source')==src and e.get('target')==dst and e.get('relation')==relation:return
    eid=f'e{len(edges)+1}'; evid=f'ev{len(evidence)+1}'
    edges.append({'id':eid,'source':src,'target':dst,'relation':relation,'proof':proof,'confidence':confidence,'sourceFile':source,'evidenceId':evid})
    evidence.append({'id':evid,'edgeId':eid,'text':text,'source':source})

anchor_targets={
 'UIHeroPVPFormationPanel':'ui:UIHeroPVPFormationPanel','FormationRT':'ui:FormationRT','FormationBg':'ui:FormationBg',
 'SlotAreas':'ui:SlotAreas','HeroInfoBars':'ui:HeroInfoBars','RenderTexture':'render:RenderTexture',
 'targetTexture':'code:Camera.set_targetTexture','RawImage':'code:RawImage.set_texture','Camera':'render:Camera',
 'A_Hero_Audie_01':'asset:Murphy','Murphy':'asset:Murphy','Audie':'asset:Murphy'
}
added=0
for r in idx.get('relevant',[]):
    hits=r.get('anchorHits') or []
    # Keep graph compact: exact anchors + highest scoring runtime candidates only.
    if not hits and int(r.get('score') or 0)<55:continue
    off=int(r.get('offset') or 0); nid=f'lua-bytecode:{off}'
    label=r.get('moduleGuess') or f'Lua chunk @{off}'
    add_node(nid,label,'lua',subtype='compiled-bytecode',offset=off,size=r.get('size'),version=r.get('version'),anchorHits=hits,keywordHits=r.get('keywordHits') or [],stringConstants=r.get('strings') or [],score=r.get('score') or 0,source='LWScripts.data')
    added+=1
    # Proven container-to-chunk relationship: validated canonical Lua header in LWScripts.data.
    if 'code:LWLuaFile.LoadFile' in nodes:
        add_edge('code:LWLuaFile.LoadFile',nid,'provides compiled Lua chunk','validated LUAC header','high',f"Validated Lua {r.get('version')} chunk in LWScripts.data at offset {off}, size {r.get('size')}",'lwscripts-luac-index-v1')
    for h in hits:
        target=anchor_targets.get(h)
        if target and target in nodes:
            add_edge(nid,target,'contains exact string constant','compiled Lua constant','exact',f"Compiled Lua chunk at offset {off} contains exact string constant {h!r}.",'lwscripts-luac-index-v1')
    scripts.append({'id':nid,'name':label,'source':'LWScripts.data','compiled':True,'offset':off,'bytes':r.get('size'),'hits':[{'anchor':x} for x in hits],'strings':r.get('strings') or []})

# Recompute undirected shortest FormationRT ↔ Murphy using only visible/proven edges.
adj=defaultdict(set)
for e in edges:
    a,b=e.get('source'),e.get('target')
    if a in nodes and b in nodes:adj[a].add(b);adj[b].add(a)
def shortest(a,b):
    q=deque([a]);prev={a:None}
    while q:
        x=q.popleft()
        if x==b:break
        for y in adj.get(x,()):
            if y not in prev:prev[y]=x;q.append(y)
    if b not in prev:return []
    out=[];x=b
    while x is not None:out.append(x);x=prev[x]
    return out[::-1]
path=shortest('ui:FormationRT','asset:Murphy')
for n in nodes.values():
    deg=len(adj.get(n['id'],()))
    text=(str(n.get('label',''))+' '+str(n.get('source',''))).lower()
    rel=sum(1 for k in ('formation','hero','murphy','audie','render','camera','lua') if k in text)
    n['degree']=deg;n['score']=max(int(n.get('score') or 0),deg*3+rel*8)
m['nodes']=sorted(nodes.values(),key=lambda n:(-int(n.get('score') or 0),n.get('kind',''),n.get('label','')))
m['edges']=edges;m['evidence']=evidence;m['scripts']=scripts
m['shortestFormationMurphyPath']=path
m.setdefault('summary',{})['nodes']=len(nodes);m['summary']['edges']=len(edges);m['summary']['evidence']=len(evidence);m['summary']['scripts']=len(scripts)
m['summary']['compiledLuaChunks']=idx.get('summary',{}).get('validChunks',0);m['summary']['compiledLuaGraphNodes']=added
m['summary']['shortestFormationMurphyHops']=len(path)-1 if path else None
m.setdefault('generatedFrom',{})['luacIndex']=str(idxp)
m.setdefault('guardrails',{})['compiledLuaExactStringEvidence']=True
manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_LUA_TRACE_VIEWER_V2_READY compiledChunks={m['summary']['compiledLuaChunks']} graphLuaNodes={added} nodes={len(nodes)} edges={len(edges)}")
if path:print('PATH='+' -> '.join(nodes[x]['label'] for x in path))
else:print('PATH=NONE_YET_REVIEW_COMPILED_LUA_CANDIDATES')
PY
