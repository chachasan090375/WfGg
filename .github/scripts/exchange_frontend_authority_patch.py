from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')

# Force a new Train JS document/cache generation for the exchange fix.
s=s.replace('wfgg_bridge=v13','wfgg_bridge=v14')
s=s.replace("'wfgg_fresh','v13'","'wfgg_fresh','v14'")

seed_old="""              currentUserId:meId,
              messageVariant:localVariants,"""
seed_new="""              currentUserId:meId,
              __serverSchedule:Array.isArray(data.schedule)?data.schedule:[],
              messageVariant:localVariants,"""
if seed_old not in s:
    raise SystemExit('snapshot seed target not found')
s=s.replace(seed_old,seed_new,1)

anchor="    let rewritten = source.split(legacyOrigin).join('');\n"
if anchor not in s:
    raise SystemExit('app rewrite anchor not found')
block=r'''

    /* WFGG_TRAIN_SERVER_SCHEDULE_V1
       La Bourse doit valider exactement le même planning que le backend.
       Le snapshot renvoie désormais le planning autoritatif; on l'attache à
       l'état local et schedule() l'utilise au lieu de recalculer une variante
       historique dans le navigateur.
    */
    {
      const applySnapshotTail = "        refreshRoster();\n        const serverLang=state.languages?.[state.currentUserId];";
      const applySnapshotTailFixed = "        state.__serverSchedule=Array.isArray(snap.schedule)?snap.schedule:[];\n        refreshRoster();\n        const serverLang=state.languages?.[state.currentUserId];";
      rewritten = rewritten.replace(applySnapshotTail, applySnapshotTailFixed);

      const scheduleLegacy = "    function schedule() { return generateSchedule(); }";
      const scheduleServer = "    function schedule() { return Array.isArray(state.__serverSchedule) && state.__serverSchedule.length ? state.__serverSchedule : generateSchedule(); }";
      rewritten = rewritten.replace(scheduleLegacy, scheduleServer);
    }

    /* WFGG_TRAIN_MUTATE_REFRESH_GUARD_V1
       Une mutation n'est annoncée comme réussie que si le snapshot serveur a
       pu être relu. Cela évite le faux positif 'Annonce publiée' avec un écran
       resté sur un état local périmé.
    */
    {
      const mutateRefresh = "            await syncSnapshot({ render: true, quiet: true });";
      const mutateRefreshGuard = "            const refreshed = await syncSnapshot({ render: true, quiet: true });\n            if (!refreshed) throw new Error('Modification enregistrée mais synchronisation impossible');";
      rewritten = rewritten.replace(mutateRefresh, mutateRefreshGuard);
    }

    /* WFGG_TRAIN_EXCHANGE_ORPHAN_FALLBACK_V1
       Une annonce ouverte ne doit jamais disparaître silencieusement lorsque
       son auteur n'est plus résolu dans le roster courant.
    */
    {
      const orphanLegacy = "            const p = byId[x.fromId];\n            if (!p)\n                return '';";
      const orphanFallback = "            const p = byId[x.fromId] || {id:x.fromId,pseudo:'Joueur indisponible',rank:'',avatar:'assets/icon-192.png',active:false};";
      rewritten = rewritten.replace(orphanLegacy, orphanFallback);
    }
'''
s=s.replace(anchor,anchor+block,1)

p.write_text(s,encoding='utf-8')
print('WFGG_EXCHANGE_FRONTEND_AUTHORITY_PATCH=OK')
