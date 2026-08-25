from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
original=s

# Remove the global overview entry from Train analytics navigation.
s=s.replace(
    '(?:activity|settings|history)',
    '(?:overview|activity|settings|history)',
    1,
)

# Runtime rewrite: the upstream app.js still contains global/player KPIs.
# Replace them when the proxied Train JS is served so Train keeps only
# Train-specific indicators.
if 'WFGG_TRAIN_STATS_SCOPE_V1' not in s:
    anchor = '    /* WFGG_TRAIN_INIT_DOM_GUARD_V1'
    block = '''    /* WFGG_TRAIN_STATS_SCOPE_V1
       Les statistiques globales/joueurs sont administrées dans le Portail.
       La page Statistiques du train ne conserve que des indicateurs propres au
       train, aux rotations et à son historique.
    */
    rewritten = rewritten
      .replace(
        "          <div><span>🗓️</span><small>Actions sur 7 jours</small><strong>${s.actions7||0}</strong></div>",
        "          <div><span>🚂</span><small>Trains historiques</small><strong>${adminAnalyticsCache.manualHistory?.eventCount||0}</strong></div>"
      )
      .replace(
        "          <div><span>👥</span><small>Joueurs actifs</small><strong>${s.activeMembers||0}</strong></div>",
        "          <div><span>⚖️</span><small>Écart Conducteur A</small><strong>${adminAnalyticsCache.rotation30?.spread?.officer??0}</strong></div>"
      )
      .replace(
        "          <div><span>🔄</span><small>Échanges ouverts</small><strong>${s.openExchanges||0}</strong></div>",
        "          <div><span>⭐</span><small>Écart VIP</small><strong>${adminAnalyticsCache.rotation30?.spread?.vip??0}</strong></div>"
      );

'''
    if anchor not in s:
        raise SystemExit('missing Train DOM guard anchor')
    s=s.replace(anchor,block+anchor,1)

if s==original:
    print('TRAIN_STATS_SCOPE=ALREADY_APPLIED')
else:
    p.write_text(s,encoding='utf-8')
    print('TRAIN_STATS_SCOPE=OK')
