from pathlib import Path

# Correct the real client tab labels in the V10 layer itself.
for root in ('simulator','frontend/simulator'):
    p=Path(root)/'hero-ux-v10.js'
    s=p.read_text(encoding='utf-8')
    s=s.replace("const labels={attributes:'Attributs',grade:'Compétences',wall:'Étoiles',weapon:'Arme'};","const labels={attributes:'Attributs',grade:'Compétences',wall:'Grade',weapon:'Armes exclusives'};")
    p.write_text(s,encoding='utf-8')

# Mirror V11 Grade / Wall and V12 roster polish into the Cloudflare bundle.
for filename in ('hero-grade-wall-v11.js','hero-grade-wall-v11.css','hero-roster-polish-v12.js','hero-roster-polish-v12.css'):
    Path('frontend/simulator',filename).write_text(Path('simulator',filename).read_text(encoding='utf-8'),encoding='utf-8')

css11='  <link rel="stylesheet" href="hero-grade-wall-v11.css?v=011-grade-wall" />\n'
js11='  <script src="hero-grade-wall-v11.js?v=011-grade-wall"></script>\n'
css12='  <link rel="stylesheet" href="hero-roster-polish-v12.css?v=012-roster-polish" />\n'
js12='  <script src="hero-roster-polish-v12.js?v=012-roster-polish"></script>\n'
for name in ('simulator/index.html','frontend/simulator/index.html'):
    p=Path(name);s=p.read_text(encoding='utf-8')
    if 'hero-grade-wall-v11.css' not in s:
        marker='  <link rel="stylesheet" href="hero-ux-v10.css?v=010-roster-sheet-graphic" />\n'
        if marker not in s: raise SystemExit(f'V10 CSS marker missing in {name}')
        s=s.replace(marker,marker+css11,1)
    if 'hero-roster-polish-v12.css' not in s:
        marker=css11 if css11 in s else '  <link rel="stylesheet" href="hero-grade-wall-v11.css?v=011-grade-wall" />\n'
        if marker not in s: raise SystemExit(f'V11 CSS marker missing in {name}')
        s=s.replace(marker,marker+css12,1)
    if 'hero-grade-wall-v11.js' not in s:
        marker='  <script src="hero-ux-v10.js?v=010-roster-sheet-graphic"></script>\n'
        if marker not in s: raise SystemExit(f'V10 JS marker missing in {name}')
        s=s.replace(marker,marker+js11,1)
    if 'hero-roster-polish-v12.js' not in s:
        marker=js11 if js11 in s else '  <script src="hero-grade-wall-v11.js?v=011-grade-wall"></script>\n'
        if marker not in s: raise SystemExit(f'V11 JS marker missing in {name}')
        s=s.replace(marker,marker+js12,1)
    p.write_text(s,encoding='utf-8')

Path('simulator/UI_VERSION.txt').write_text(
    'HERO_UX_V12\nGrade + Wall of Honor / fixed top language selector / aligned portraits / HQ Tesla Adam / soft live character motion / FR Skyler\n2026-08-26\n',
    encoding='utf-8'
)
