from pathlib import Path

portal = Path('frontend/portal-invitations-v1.js')
text = portal.read_text(encoding='utf-8')
old = """const thankBlocks=[
  `Un grand merci à ${THANKED_OFFICERS.join(', ')} pour leur travail et leur implication dans la mise en place du projet.`,
  `Merci tout particulièrement à ${THANKED_OFFICERS.join(', ')}, qui ont participé au travail du bureau autour de ce projet.`,
  `Ce lancement doit aussi beaucoup au travail de ${THANKED_OFFICERS.join(', ')} : merci à eux pour le temps et l'énergie consacrés au projet.`,
  `Je tiens à remercier ${THANKED_OFFICERS.join(', ')} pour leur contribution au travail mené par le bureau sur cette plateforme.`
];"""
new = """const thankBlocks=[
  `Un grand merci à ${THANKED_OFFICERS.join(', ')} pour leur travail et leur implication dans la mise en place du projet, ainsi que pour leur investissement durant toute l'Inter-Saison.`,
  `Merci tout particulièrement à ${THANKED_OFFICERS.join(', ')}, qui ont participé au travail du bureau autour de ce projet et pour leur investissement durant toute l'Inter-Saison.`,
  `Ce lancement doit aussi beaucoup au travail de ${THANKED_OFFICERS.join(', ')} : merci à eux pour le temps et l'énergie consacrés au projet et pour leur investissement durant toute l'Inter-Saison.`,
  `Je tiens à remercier ${THANKED_OFFICERS.join(', ')} pour leur contribution au travail mené par le bureau sur cette plateforme et pour leur investissement durant toute l'Inter-Saison.`
];"""
if old not in text:
    raise SystemExit('thankBlocks source block not found')
portal.write_text(text.replace(old, new, 1), encoding='utf-8')

index = Path('frontend/index.html')
text = index.read_text(encoding='utf-8')
old_key = 'portal-invitations-v1.js?v=001'
new_key = 'portal-invitations-v1.js?v=002-interseason-thanks'
if old_key not in text:
    raise SystemExit('index invitations cache key not found')
index.write_text(text.replace(old_key, new_key), encoding='utf-8')

qa = Path('.github/qa/portal-invitations-recette.mjs')
text = qa.read_text(encoding='utf-8')
needle = "  assert.ok(r4.includes('https://wfgg.pages.dev/'));\n"
insert = needle + "  assert.ok(r4.includes(\"investissement durant toute l'Inter-Saison\"));\n"
if needle not in text:
    raise SystemExit('QA insertion point not found')
qa.write_text(text.replace(needle, insert, 1), encoding='utf-8')

prod = Path('.github/workflows/production-recette.yml')
text = prod.read_text(encoding='utf-8')
if old_key not in text:
    raise SystemExit('production workflow cache key not found')
text = text.replace(old_key, new_key)
needle = "          grep -q 'https://wfgg.pages.dev/' frontend/portal-invitations-v1.js\n"
insert = needle + "          grep -Fq \"investissement durant toute l'Inter-Saison\" frontend/portal-invitations-v1.js\n"
if needle not in text:
    raise SystemExit('production source assertion insertion point not found')
text = text.replace(needle, insert, 1)
needle2 = "          grep -Fq 'https://wfgg.pages.dev/' /tmp/invitations.js\n"
insert2 = needle2 + "          grep -Fq \"investissement durant toute l'Inter-Saison\" /tmp/invitations.js\n"
if needle2 not in text:
    raise SystemExit('production live assertion insertion point not found')
text = text.replace(needle2, insert2, 1)
prod.write_text(text, encoding='utf-8')

print('WFGG_INVITATIONS_THANKS_INTERSEASON_V21=PATCHED')
