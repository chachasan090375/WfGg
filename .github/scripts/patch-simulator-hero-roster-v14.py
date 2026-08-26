from pathlib import Path

for root in (Path('simulator'), Path('frontend/simulator')):
    if root.name == 'simulator' and root.parent.name == 'frontend':
        pass

# Mirror V14 assets into the Cloudflare-served frontend bundle.
Path('frontend/simulator/hero-roster-uniform-v14.js').write_text(Path('simulator/hero-roster-uniform-v14.js').read_text(encoding='utf-8'), encoding='utf-8')
Path('frontend/simulator/hero-roster-uniform-v14.css').write_text(Path('simulator/hero-roster-uniform-v14.css').read_text(encoding='utf-8'), encoding='utf-8')

css_old='  <link rel="stylesheet" href="hero-roster-uniform-v13.css?v=013-uniform-motion" />\n'
css_new=css_old+'  <link rel="stylesheet" href="hero-roster-uniform-v14.css?v=014-no-flash-uniform" />\n'
js_old='  <script src="hero-roster-uniform-v13.js?v=013-uniform-motion"></script>\n'
js_new=js_old+'  <script src="hero-roster-uniform-v14.js?v=014-no-flash-uniform"></script>\n'

for p in (Path('simulator/index.html'), Path('frontend/simulator/index.html')):
    s=p.read_text(encoding='utf-8')
    if 'hero-roster-uniform-v14.css?v=014-no-flash-uniform' not in s:
        if css_old not in s: raise SystemExit(f'V13 CSS marker missing in {p}')
        s=s.replace(css_old,css_new,1)
    if 'hero-roster-uniform-v14.js?v=014-no-flash-uniform' not in s:
        if js_old not in s: raise SystemExit(f'V13 JS marker missing in {p}')
        s=s.replace(js_old,js_new,1)
    p.write_text(s,encoding='utf-8')

Path('simulator/UI_VERSION.txt').write_text('14.0.0-hero-roster-no-flash-uniform\n',encoding='utf-8')
