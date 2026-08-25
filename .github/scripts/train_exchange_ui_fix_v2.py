from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
marker='WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V2'
if marker in s:
    print('EXCHANGE_UI_FIX_V2=ALREADY_PRESENT')
    raise SystemExit(0)

anchor='    /* WFGG_TRAIN_INIT_DOM_GUARD_V1'
if anchor not in s:
    raise SystemExit('missing Train init guard anchor')

block=r'''    /* WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V2
       Patch ciblé sur le fragment exact du rendu « Mes demandes ».
       Le V1 incluait trop de contexte et ne correspondait pas au JS upstream.
    */
    {
      const ownOpenTail = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}</div>";
      const ownOpenTailFixed = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}${x.status === 'open' ? `<button class=\"btn danger small\" onclick=\"W.cancelMarketExchange('${x.id}')\">Retirer mon annonce</button>` : ''}</div>";
      rewritten = rewritten.replace(ownOpenTail, ownOpenTailFixed);
    }

'''
s=s.replace(anchor,block+anchor,1)
s=s.replace('wfgg_bridge=v12','wfgg_bridge=v13')
s=s.replace("wfgg_fresh','v12'","wfgg_fresh','v13'")
p.write_text(s,encoding='utf-8')
print('EXCHANGE_UI_FIX_V2=OK')
