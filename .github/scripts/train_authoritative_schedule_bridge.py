from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
marker='WFGG_TRAIN_AUTHORITATIVE_SCHEDULE_V1'
if marker in s:
    print('TRAIN_AUTHORITATIVE_SCHEDULE=ALREADY_APPLIED')
    raise SystemExit(0)

anchors=[
    '    /* WFGG_TRAIN_STATS_SCOPE_V1',
    '    /* WFGG_TRAIN_INIT_DOM_GUARD_V1',
    '    /* WFGG_TRAIN_DANGLING_TOKEN_FIX_V1'
]
anchor=next((a for a in anchors if a in s),None)
if not anchor:
    raise SystemExit('no app.js rewrite anchor found')

block=r'''    /* WFGG_TRAIN_AUTHORITATIVE_SCHEDULE_V1
       Le planning calculé par le Worker est la source unique de vérité.
       Le frontend ne doit plus recalculer un planning différent de celui
       utilisé par les validations de la bourse d'échange.
    */
    rewritten = rewritten.replace(
      "        const localVariants = state.messageVariant || { weekly: 0, daily: 0, driver: 0, vip: 0 };",
      "        const localVariants = state.messageVariant || { weekly: 0, daily: 0, driver: 0, vip: 0 };\n        window.__WFGG_SERVER_SCHEDULE__ = Array.isArray(snap.schedule) ? snap.schedule : [];"
    );
    rewritten = rewritten.replace(
      "    function schedule() { return generateSchedule(); }",
      "    function schedule() { const authoritative = window.__WFGG_SERVER_SCHEDULE__; return Array.isArray(authoritative) && authoritative.length ? authoritative : generateSchedule(); }"
    );

'''
s=s.replace(anchor,block+anchor,1)

# Seed the authoritative schedule as soon as the Portal probe succeeds, before
# the historical Train application performs its first render.
probe_old="""              const meId=String(data?.me?.id||'');
              const roster=Array.isArray(data?.roster)?data.roster:[];"""
probe_new="""              const meId=String(data?.me?.id||'');
              const roster=Array.isArray(data?.roster)?data.roster:[];
              window.__WFGG_SERVER_SCHEDULE__=Array.isArray(data?.schedule)?data.schedule:[];"""
if probe_old in s:
    s=s.replace(probe_old,probe_new,1)
else:
    print('warning: probe seed anchor not found; applySnapshot remains authoritative')

s=s.replace('wfgg_bridge=v13','wfgg_bridge=v14')
s=s.replace("wfgg_fresh','v13'","wfgg_fresh','v14'")
p.write_text(s,encoding='utf-8')
print('TRAIN_AUTHORITATIVE_SCHEDULE=OK')
