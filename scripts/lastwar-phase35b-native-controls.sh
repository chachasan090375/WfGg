#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT="$ROOT/frontend/lab/local-assets/lastwar-kit-v1"
CAT="$KIT/catalog.json"
DEST="$ROOT/frontend/lab/master-assets-v2/ui"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR branche" >&2; exit 1; }
mkdir -p "$DEST"
python - "$KIT" "$CAT" "$DEST" <<'PY'
from pathlib import Path
import json,os,re,shutil,sys
kit=Path(sys.argv[1]); rows=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')).get('extractedAssets',[]); dest=Path(sys.argv[3])
marker='/lab/local-assets/lastwar-kit-v1/'
def stem(s):return re.sub(r'\.(png|jpg|jpeg|webp|tga)$','',os.path.basename(str(s or '')).lower())
def source(r):
 p=str(r.get('localPath') or '')
 if marker not in p:return None
 x=kit/p.split(marker,1)[1]
 return x if x.is_file() else None
def cp(name,out):
 c=[r for r in rows if stem(r.get('name'))==stem(name) and source(r)]
 if not c: print('MISS',name); return
 r=max(c,key=lambda x:(x.get('objectType')=='Sprite',int(x.get('width') or 0)*int(x.get('height') or 0)))
 shutil.copy2(source(r),dest/out); print('OK',name,'->',out)
for name,out in [
 ('zxl_zhuzai_biandui_tianjia','add.png'),
 ('cfm_yingxiong_biandui_tubiao_1','squad-control-1.png'),
 ('cfm_yingxiong_biandui_tubiao_2','squad-control-2.png'),
 ('cfm_yingxiong_biandui_tubiao_3','squad-control-3.png'),
 ('cfm_yingxiong_biandui_tubiao_4','squad-control-4.png'),
 ('lrb_wurenji_xinpian_icon','drone-chip-icon.png'),
 ('fu_juexing_xiaosuozi','lock.png'),
]:cp(name,out)
PY
git add -f frontend/lab/master-assets-v2/ui
if ! git diff --cached --quiet -- frontend/lab/master-assets-v2/ui; then git commit -m "lab: add exact native formation controls"; fi
git push origin "$BRANCH"
