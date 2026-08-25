from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
marker='WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V1'
if marker in s:
    print('EXCHANGE_UI_FIX=ALREADY_PRESENT')
    raise SystemExit(0)

anchor='    /* WFGG_TRAIN_INIT_DOM_GUARD_V1'
if anchor not in s:
    raise SystemExit('missing Train init guard anchor')

block=r'''    /* WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V1
       Une annonce ouverte du joueur doit toujours rester visible dans
       « Mes demandes » avec la possibilité de la retirer. Le frontend amont
       affichait le bouton uniquement dans la liste générale des annonces.
    */
    {
      const ownExchangeTail = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}</div>`).join('') : '<div class=\\\"empty\\\">Aucune demande publiée.</div>'}";
      const ownExchangeTailFixed = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}${x.status === 'open' ? `<button class=\\\"btn danger small\\\" onclick=\\\"W.cancelMarketExchange('${x.id}')\\\">Retirer mon annonce</button>` : ''}</div>`).join('') : '<div class=\\\"empty\\\">Aucune demande publiée.</div>'}";
      rewritten = rewritten.replace(ownExchangeTail, ownExchangeTailFixed);
    }

'''
s=s.replace(anchor,block+anchor,1)
s=s.replace('wfgg_bridge=v11','wfgg_bridge=v12')
s=s.replace("wfgg_fresh','v11'","wfgg_fresh','v12'")
p.write_text(s,encoding='utf-8')
print('EXCHANGE_UI_FIX=OK')
