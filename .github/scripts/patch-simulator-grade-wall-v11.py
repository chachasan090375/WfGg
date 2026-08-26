from pathlib import Path

for root in ('simulator','frontend/simulator'):
    p=Path(root)/'hero-ux-v10.js'
    s=p.read_text(encoding='utf-8')
    s=s.replace("const labels={attributes:'Attributs',grade:'Compétences',wall:'Étoiles',weapon:'Arme'};","const labels={attributes:'Attributs',grade:'Compétences',wall:'Grade',weapon:'Armes exclusives'};")
    p.write_text(s,encoding='utf-8')

Path('frontend/simulator/hero-grade-wall-v11.js').write_text(Path('simulator/hero-grade-wall-v11.js').read_text(encoding='utf-8'),encoding='utf-8')
Path('frontend/simulator/hero-grade-wall-v11.css').write_text(Path('simulator/hero-grade-wall-v11.css').read_text(encoding='utf-8'),encoding='utf-8')

css='  <link rel="stylesheet" href="hero-grade-wall-v11.css?v=011-grade-wall" />\n'
js='  <script src="hero-grade-wall-v11.js?v=011-grade-wall"></script>\n'
for name in ('simulator/index.html','frontend/simulator/index.html'):
    p=Path(name);s=p.read_text(encoding='utf-8')
    if 'hero-grade-wall-v11.css' not in s:
        marker='  <link rel="stylesheet" href="hero-ux-v10.css?v=010-roster-sheet-graphic" />\n'
        if marker not in s: raise SystemExit(f'CSS marker missing in {name}')
        s=s.replace(marker,marker+css,1)
    if 'hero-grade-wall-v11.js' not in s:
        marker='  <script src="hero-ux-v10.js?v=010-roster-sheet-graphic"></script>\n'
        if marker not in s: raise SystemExit(f'JS marker missing in {name}')
        s=s.replace(marker,marker+js,1)
    p.write_text(s,encoding='utf-8')

Path('simulator/UI_VERSION.txt').write_text('HERO_UX_V11\nGrade restored as third tab / 5-star Wall of Honor subpage / per-hero honor data\n2026-08-26\n',encoding='utf-8')
