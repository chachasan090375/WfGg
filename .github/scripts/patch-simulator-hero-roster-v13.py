from pathlib import Path

# Mirror V13 into Cloudflare bundle.
for filename in ('hero-roster-uniform-v13.js','hero-roster-uniform-v13.css'):
    Path('frontend/simulator', filename).write_text(Path('simulator', filename).read_text(encoding='utf-8'), encoding='utf-8')

css13='  <link rel="stylesheet" href="hero-roster-uniform-v13.css?v=013-uniform-motion" />\n'
js13='  <script src="hero-roster-uniform-v13.js?v=013-uniform-motion"></script>\n'
for name in ('simulator/index.html','frontend/simulator/index.html'):
    p=Path(name);s=p.read_text(encoding='utf-8')
    if 'hero-roster-uniform-v13.css' not in s:
        marker='  <link rel="stylesheet" href="hero-roster-polish-v12.css?v=012-roster-polish" />\n'
        if marker not in s: raise SystemExit(f'V12 CSS marker missing in {name}')
        s=s.replace(marker,marker+css13,1)
    if 'hero-roster-uniform-v13.js' not in s:
        marker='  <script src="hero-roster-polish-v12.js?v=012-roster-polish"></script>\n'
        if marker not in s: raise SystemExit(f'V12 JS marker missing in {name}')
        s=s.replace(marker,marker+js13,1)
    p.write_text(s,encoding='utf-8')

Path('simulator/UI_VERSION.txt').write_text(
    'HERO_UX_V13\nUniform per-hero crop / all 31 heroes animate once per shuffled cycle / full rest gap / no frame blink\n2026-08-26\n',
    encoding='utf-8'
)
