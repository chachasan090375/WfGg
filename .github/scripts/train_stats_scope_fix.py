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

# Replace global/player KPIs in the Train statistics landing with Train-only KPIs.
replacements={
"          <div><span>🗓️</span><small>Actions sur 7 jours</small><strong>${s.actions7||0}</strong></div>":
"          <div><span>🚂</span><small>Trains historiques</small><strong>${adminAnalyticsCache.manualHistory?.eventCount||0}</strong></div>",
"          <div><span>👥</span><small>Joueurs actifs</small><strong>${s.activeMembers||0}</strong></div>":
"          <div><span>⚖️</span><small>Écart Conducteur A</small><strong>${adminAnalyticsCache.rotation30?.spread?.officer??0}</strong></div>",
"          <div><span>🔄</span><small>Échanges ouverts</small><strong>${s.openExchanges||0}</strong></div>":
"          <div><span>⭐</span><small>Écart VIP</small><strong>${adminAnalyticsCache.rotation30?.spread?.vip??0}</strong></div>",
}
for old,new in replacements.items():
    s=s.replace(old,new,1)

if s==original:
    print('TRAIN_STATS_SCOPE=ALREADY_APPLIED')
else:
    p.write_text(s,encoding='utf-8')
    print('TRAIN_STATS_SCOPE=OK')
