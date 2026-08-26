from pathlib import Path
import shutil

root=Path('.')
front=root/'frontend'/'simulator'
front.mkdir(parents=True,exist_ok=True)
for name in ['hero-roster-v15.js','hero-roster-v15.css']:
    shutil.copy2(root/'simulator'/name, front/name)

for path in [root/'simulator'/'index.html',front/'index.html']:
    s=path.read_text(encoding='utf-8')
    for old in ['015-official-icons-rarity-motion','015b-stable-official-icons-motion']:
        s=s.replace(old,'015c-dedicated-portrait-motion')
    css='  <link rel="stylesheet" href="hero-roster-v15.css?v=015c-dedicated-portrait-motion" />\n'
    js='  <script src="hero-roster-v15.js?v=015c-dedicated-portrait-motion"></script>\n'
    if 'hero-roster-v15.css' not in s:
        marker='  <link rel="stylesheet" href="hero-roster-uniform-v14.css?v=014-no-flash-uniform" />\n'
        if marker not in s: raise SystemExit(f'v14 css marker missing in {path}')
        s=s.replace(marker,marker+css,1)
    if 'hero-roster-v15.js' not in s:
        marker='  <script src="hero-roster-uniform-v14.js?v=014-no-flash-uniform"></script>\n'
        if marker not in s: raise SystemExit(f'v14 js marker missing in {path}')
        s=s.replace(marker,marker+js,1)
    path.write_text(s,encoding='utf-8')

(root/'simulator'/'UI_VERSION.txt').write_text('hero-roster-v15c-dedicated-portrait-motion\n',encoding='utf-8')
