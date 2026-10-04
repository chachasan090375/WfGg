#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,html,json,os,subprocess
from pathlib import Path
from typing import Any

def load(p:Path,default=None):
    try:
        x=json.loads(p.read_text(encoding='utf-8')); return x
    except Exception:return {} if default is None else default

def esc(x): return html.escape(str(x if x is not None else ''))
def short(x,n=12): return str(x or '')[:n]
def status(path:Path):
    try:return path.read_text(encoding='utf-8').strip()
    except Exception:return 'UNKNOWN'
def service(unit:str)->str:
    try:
        p=subprocess.run(['systemctl','is-active',unit],capture_output=True,text=True,timeout=5)
        return p.stdout.strip().upper() if p.stdout.strip() else 'UNKNOWN'
    except Exception:return 'UNKNOWN'
def git_value(repo:Path,args:list[str])->str:
    try:return subprocess.check_output(['git','-C',str(repo),*args],text=True,timeout=8).strip()
    except Exception:return ''

def svg_box(x,y,w,h,title,body='',fill='#221d2e',stroke='#6d55a3'):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/><text x="{x+w/2}" y="{y+24}" text-anchor="middle" fill="#fff" font-size="15" font-weight="700">{esc(title)}</text><text x="{x+w/2}" y="{y+46}" text-anchor="middle" fill="#cfc6d9" font-size="11">{esc(body)}</text>'
def arrow(x1,y1,x2,y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9587b8" stroke-width="2" marker-end="url(#a)"/>'
def svg(title,w,h,body):
    return f'''<figure><figcaption>{esc(title)}</figcaption><svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}"><defs><marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#9587b8"/></marker></defs>{body}</svg></figure>'''

def map_level0():
    b='';
    b+=svg_box(30,90,160,70,'Cédric / Android','Cockpit + voix + validation')
    b+=svg_box(245,90,175,70,'Tailscale privé','HTTPS :8443 / identité')
    b+=svg_box(480,70,210,110,'ChaChaVPS','Cerveau central + runtime')
    b+=svg_box(755,20,180,70,'GitHub','Source + CI + preuves')
    b+=svg_box(755,105,180,70,'Cloudflare','Pages / Workers / D1 miroir')
    b+=svg_box(755,190,180,70,'ChaChaNas / QNAP','Mémoire + archives + lab')
    b+=arrow(190,125,245,125)+arrow(420,125,480,125)+arrow(690,100,755,55)+arrow(690,125,755,140)+arrow(690,155,755,225)
    return svg('Cartographie L0 - écosystème physique et services',970,290,b)
def map_level1():
    b='';
    b+=svg_box(350,20,250,72,'Direct Operator','Conversation / BUILD / cockpit')
    b+=svg_box(350,125,250,80,'Cerveau central','Central Orchestrator + Project Control')
    b+=svg_box(35,245,190,78,'Intelligence','Veilles + Dark + Truth + mémoire')
    b+=svg_box(255,245,190,78,'Conception','Feasibility + Solution Graph')
    b+=svg_box(475,245,190,78,'Exécution','Scheduler + Run Controller')
    b+=svg_box(695,245,190,78,'Foundries','Branch + Agent + Capability')
    b+=svg_box(35,370,190,78,'Guardian','Conformité fonctionnelle')
    b+=svg_box(255,370,190,78,'Sentinelle','Assurance technique')
    b+=svg_box(475,370,190,78,'Bastion / Intendant','Sécurité + ressources')
    b+=svg_box(695,370,190,78,'État souverain','SQLite local + NAS + D1')
    b+=arrow(475,92,475,125)+arrow(475,205,130,245)+arrow(475,205,350,245)+arrow(475,205,570,245)+arrow(475,205,790,245)
    for x in [130,350,570,790]: b+=arrow(x,323,x,370)
    return svg('Cartographie L1 - architecture logique du VPS',920,480,b)
def map_improvement():
    b=''; xs=[25,185,345,505,665,825]; titles=['Tech Watch','Dark Intel','Truth','Guardian/Sentinel','Runtime/Intendant','Mémoire/UX'];
    for x,t in zip(xs,titles): b+=svg_box(x,20,135,62,t,'signal + preuve')+arrow(x+67,82,475,140)
    b+=svg_box(365,140,220,84,'Improvement Intelligence','normalise • corrèle • valeur')
    b+=arrow(475,224,475,275)
    b+=svg_box(365,275,220,75,'Logicien + Council','falsification + arbitrage')
    b+=arrow(475,350,475,400)
    b+=svg_box(365,400,220,75,'Cerveau central','handoff unique')
    b+=arrow(365,438,220,520)+arrow(585,438,730,520)
    b+=svg_box(120,520,200,75,'Creation Runtime / Foundries','construit en shadow')
    b+=svg_box(630,520,200,75,'Update Center','trains qualifiés + valeur')
    b+=arrow(320,557,630,557)
    b+=arrow(730,595,730,650)
    b+=svg_box(630,650,200,75,'Gate humain','Mise en production')
    return svg('Cartographie L2 - intelligence d’amélioration fédérée',990,755,b)
def map_promotion():
    stages=[('Signal','preuve'),('Valeur','gain global'),('Build','shadow'),('CI','exact-SHA'),('Staging','PREPARE'),('Humain','ACTIVATE'),('Vérif','cycles/rollback'),('Livre blanc','refresh')]
    b=''
    for i,(a,c) in enumerate(stages):
        x=15+i*120;b+=svg_box(x,55,105,62,a,c)
        if i<len(stages)-1:b+=arrow(x+105,86,x+120,86)
    return svg('Cartographie L3 - cycle d’une amélioration jusqu’à la documentation',985,160,b)
def map_data():
    b='';
    b+=svg_box(30,40,180,70,'SQLite local','autorité runtime')
    b+=svg_box(300,40,180,70,'NAS QNAP','snapshots create-only')
    b+=svg_box(570,40,180,70,'D1 Cloudflare','miroir/fallback stale')
    b+=svg_box(300,165,180,70,'Evidence Ledger','SHA / receipts / CI')
    b+=svg_box(300,290,180,70,'CCR + UMG','inventaire + naissance')
    b+=arrow(210,75,300,75)+arrow(480,75,570,75)+arrow(120,110,300,190)+arrow(660,110,480,190)+arrow(390,235,390,290)
    return svg('Cartographie L4 - plan d’état, preuves et gouvernance',780,400,b)

def table(headers,rows):
    h='<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'
    for r in rows:h+='<tr>'+''.join('<td>'+str(x)+'</td>' for x in r)+'</tr>'
    return h+'</tbody></table>'

def generate(repo:Path,runtime:Path,outroot:Path)->dict[str,Any]:
    cfg=repo/'dev-hub/config'; ev=repo/'dev-hub/evidence'
    roadmap=load(cfg/'master-roadmap.v1.json'); direct=load(cfg/'direct-operator.v1.json'); nas=load(cfg/'nas-readback-adapter.v1.json')
    factory=load(cfg/'autonomous-improvement-factory.v1.json'); intel=load(cfg/'improvement-intelligence-fabric.v1.json'); business=load(cfg/'business-valuation-model.v1.json')
    market=load(ev/'market-competitive-baseline-2026-10-04.json'); authority=load(runtime/'sovereign-state/authority.json')
    current=Path('/opt/chacha-dev/platform/current').resolve() if Path('/opt/chacha-dev/platform/current').exists() else None
    current_rev=status(current/'.revision') if current else 'UNKNOWN'; candidate_rev=git_value(repo,['rev-parse','HEAD']); tree=git_value(repo,['rev-parse','HEAD^{tree}'])
    releases=[]
    rr=Path('/opt/chacha-dev/platform/releases')
    if rr.is_dir():
        for p in sorted(rr.iterdir()):
            if p.is_dir() and (p/'.revision').is_file(): releases.append({'path':str(p),'revision':status(p/'.revision'),'active':bool(current and p.resolve()==current)})
    services={u:service(u) for u in ['chacha-dev-direct-operator.service','chacha-dev-sovereign-guardian.service','chacha-dev-sovereign-sentinel.service','chacha-dev-sovereign-assurance-exchange.service','chacha-dev-sovereign-learning-relay.service']}
    generated=datetime.datetime.now(datetime.timezone.utc).isoformat()
    workstreams=roadmap.get('workstreams') or []
    comp_rows=[]
    for c in market.get('competitors') or []:
        comp_rows.append([f"<strong>{esc(c.get('name'))}</strong><br><small>{esc(c.get('category'))}</small>",'<br>'.join('• '+esc(x) for x in c.get('strengths_vs_chacha') or []),'<br>'.join('• '+esc(x) for x in c.get('chacha_potential_advantages') or []),'<br>'.join(f'<a href="{esc(u)}">source</a>' for u in c.get('source_urls') or [])])
    ws_rows=[[f"<strong>{esc(w.get('id'))}</strong>",esc(w.get('priority')),esc(w.get('state')),'<br>'.join('• '+esc(x) for x in (w.get('includes') or []))] for w in workstreams]
    val_rows=[[esc(v.get('stage')),esc(v.get('conditions')),esc(v.get('indicative_range_eur')),esc(v.get('method'))] for v in business.get('valuation_scenarios') or []]
    rel_rows=[[esc(r['revision'][:12]),'ACTIVE' if r['active'] else 'RETAINED',esc(Path(r['path']).name)] for r in releases]
    source_strategy='<br>'.join(f"{i+1}. {esc(x)}" for i,x in enumerate(factory.get('implementation_strategy_order') or []))
    html_doc=f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ChaCha DEV - Livre blanc vivant</title>
<style>
:root{{--bg:#111016;--card:#1a1821;--line:#373140;--ink:#f4eef7;--muted:#bbb0c4;--vio:#8b6bc8;--vio2:#5e477f;--mint:#91e3c5;--amber:#f3cb78}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}}main{{max-width:1180px;margin:auto;padding:34px 22px 80px}}h1{{font-size:44px;margin:.1em 0}}h2{{margin-top:45px;border-bottom:1px solid var(--line);padding-bottom:8px}}h3{{color:#d8c7ef;margin-top:28px}}.lead{{font-size:19px;color:#d4cadb;max-width:900px}}.tag{{display:inline-block;padding:5px 9px;border:1px solid var(--vio2);border-radius:99px;margin:3px;background:#211a2c}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}}.k{{font-size:11px;color:#a89caf;text-transform:uppercase;letter-spacing:.08em}}.v{{font-size:18px;font-weight:800;margin-top:5px}}figure{{margin:24px 0;background:#15131b;border:1px solid var(--line);border-radius:18px;padding:14px;overflow:auto}}figcaption{{font-weight:800;margin:2px 0 10px;color:#d7c9ee}}svg{{width:100%;min-width:760px;height:auto}}table{{border-collapse:collapse;width:100%;background:#16141c}}th,td{{border:1px solid #3b3544;padding:9px;vertical-align:top;text-align:left}}th{{background:#241e30}}small,.muted{{color:var(--muted)}}a{{color:#bca9ff}}.ok{{color:var(--mint)}}.warn{{color:var(--amber)}}.callout{{border-left:4px solid var(--vio);padding:10px 14px;background:#1b1723;border-radius:7px}}code{{background:#211d27;padding:2px 5px;border-radius:5px}}@media print{{body{{background:#fff;color:#111}}.card,figure,table{{background:#fff;color:#111}}a{{color:#333}}}}
</style></head><body><main>
<div class="tag">Livre blanc vivant</div><div class="tag">Généré {esc(generated)}</div><div class="tag">0 € dépense externe automatique</div>
<h1>ChaCha DEV</h1><p class="lead">Architecture fonctionnelle et technique, Factory autonome d’amélioration, gouvernance, positionnement concurrentiel, business plan et scénarios de valorisation.</p>
<div class="callout"><strong>Lecture des états :</strong> ce document sépare l’état runtime observé, la configuration déclarée et la cible roadmap. Une configuration historique ne prévaut jamais sur une preuve runtime plus récente.</div>
<h2>1. Résumé exécutif</h2><p>ChaCha DEV est une plateforme de création logicielle autonome gouvernée : elle transforme une intention fonctionnelle en architecture, plan d’exécution, artefacts et releases, tout en séparant l’autorité de construction, les contrôles indépendants et la décision humaine de production. Son objectif n’est pas d’accumuler des agents ou des nouveautés, mais d’exécuter une <strong>Factory autonome</strong> qui améliore sa capacité globale lorsque l’avantage est prouvé.</p>
<p>Le différenciateur recherché est la combinaison : orchestration multi-agents, spécialisation récursive, faisabilité infrastructure avant conception, état souverain local, Guardian/Sentinelle externes au cerveau central, UMG/CCR pour tout composant, priorité au zéro-coût, preuve exact-SHA, rollback, et désormais Improvement Intelligence fédérée.</p>
<h2>2. État réel observé</h2><div class="grid">
<div class="card"><div class="k">Production active</div><div class="v">{esc(short(current_rev))}</div><small>{esc(current)}</small></div>
<div class="card"><div class="k">Branche analysée</div><div class="v">{esc(short(candidate_rev))}</div><small>tree {esc(short(tree))}</small></div>
<div class="card"><div class="k">État souverain</div><div class="v">{esc(authority.get('mode','UNKNOWN'))}</div><small>Guardian/Sentinel/Assurance/Learning Relay locaux</small></div>
<div class="card"><div class="k">Direct Operator</div><div class="v">{esc(services['chacha-dev-direct-operator.service'])}</div><small>{esc(direct.get('transport',{}).get('expected_url',''))}</small></div>
</div><h3>Releases physiques</h3>{table(['Révision','État','Release'],rel_rows)}
<h3>Services cœur</h3>{table(['Service','État'],[[esc(k),f'<span class="ok">{esc(v)}</span>' if v=='ACTIVE' else esc(v)] for k,v in services.items()])}
<h2>3. Cartographies multi-niveaux</h2>{map_level0()}{map_level1()}{map_improvement()}{map_promotion()}{map_data()}
<h2>4. Architecture fonctionnelle</h2><p>Le parcours nominal sépare cinq responsabilités : <strong>comprendre</strong> la demande, <strong>concevoir</strong> une solution compatible avec les ressources réelles, <strong>construire</strong> en espaces shadow gouvernés, <strong>assurer</strong> indépendamment le résultat, puis <strong>promouvoir</strong> uniquement sur décision humaine explicite.</p>
<div class="grid"><div class="card"><b>Direct Operator</b><p>Surface Android/web privée. Deux canaux : conversation sans mutation et BUILD gouverné.</p></div><div class="card"><b>Cerveau central</b><p>Orchestration, arbitrage, Project Control, décisions d’architecture et handoffs.</p></div><div class="card"><b>Creation Runtime</b><p>Feasibility Auditor, Solution Composer, graphes, planification parallèle, Foundries.</p></div><div class="card"><b>Assurance externe</b><p>Guardian, Sentinelle, Bastion et Intendant ne sont pas des exécutants du cerveau central.</p></div></div>
<h2>5. Improvement Intelligence - progression collective des agents</h2><p>Technology Watch n’est plus la seule porte d’entrée de l’amélioration. Les agents de renseignement, d’assurance, d’exploitation, de mémoire et d’expérience publient des signaux indépendants vers <code>Improvement Intelligence Fabric</code>. Le Fabric déduplique, maintient les contradictions, vérifie la provenance, calcule la valeur globale et transmet uniquement les axes utiles au cerveau central.</p>
<p><strong>Sources autorisées :</strong> {', '.join(esc(x) for x in intel.get('authorized_sources') or [])}.</p><p><strong>Ordre d’implémentation :</strong><br>{source_strategy}</p>
<p>Le code open source peut être réutilisé si la licence, la provenance, les obligations d’attribution/copy-left/brevets et la SBOM sont compatibles. À défaut, ChaCha reconstruit le mécanisme. Un plugin ou connecteur externe est un fallback, pas le chemin normal.</p>
<h2>6. Catalogue des workstreams</h2>{table(['Workstream','Priorité','État','Composants / fonctions'],ws_rows)}
<h2>7. Gouvernance et sécurité</h2><ul><li>Guardian : conformité fonctionnelle et limites d’action.</li><li>Sentinelle : assurance technique exact-SHA.</li><li>Bastion : sécurité et confinement.</li><li>Intendant : coût, capacité, hygiène et rétention.</li><li>CCR : inventaire canonique ; UMG : naissance/activation/retrait des composants.</li><li>STOP : autorité d’urgence globale.</li><li>Production : aucun changement implicite ; humain requis.</li></ul>
<h2>8. Infrastructure</h2><div class="grid"><div class="card"><b>VPS</b><p>Plan de contrôle actif, Direct Operator, orchestration, exécution, SQLite souverain et services cœur.</p></div><div class="card"><b>NAS / QNAP</b><p>Racine déclarée : {esc(nas.get('nas',{}).get('root'))}. Mémoire, snapshots immuables/readback, artefacts lourds et Virtual OS Lab.</p></div><div class="card"><b>GitHub</b><p>Source, branches, exact-SHA CI, preuves et historique.</p></div><div class="card"><b>Cloudflare</b><p>Pages/Workers ; D1 conservé comme miroir/fallback non prioritaire après souveraineté locale.</p></div></div>
<h2>9. Concurrence et inspirations</h2><p>Les comparaisons ci-dessous servent à identifier des mécanismes à benchmarker, pas à copier des affirmations marketing. Une force concurrente ne devient une brique ChaCha qu’après mesure locale et gate de valeur.</p>{table(['Produit','Forces observées','Avantages potentiels ChaCha','Sources'],comp_rows)}
<h2>10. Avantages et limites actuelles</h2><div class="grid"><div class="card"><b>Avantages</b><ul><li>Gouvernance indépendante du cerveau central.</li><li>État local souverain et coût externe automatique nul.</li><li>Architecture model/provider-agnostic visée.</li><li>Traçabilité exacte SHA/tree/rollback.</li><li>Factory d’amélioration value-gated.</li><li>Infrastructure feasibility avant composition.</li></ul></div><div class="card"><b>Limites / dettes</b><ul><li>Remote MCP propriétaire non encore matérialisé en runtime.</li><li>Native Local non actif.</li><li>HA non encore qualifié sur la production courante.</li><li>Plusieurs fabrications restent shadow avant promotion.</li><li>Validation commerciale externe encore à construire.</li><li>Le cockpit Update Center/Livre blanc doit passer par la chaîne de release avant d’être actif.</li></ul></div></div>
<h2>11. Business plan</h2><p><strong>Positionnement :</strong> {esc(business.get('business_model',{}).get('positioning'))}</p><h3>Segments</h3><p>{' • '.join(esc(x) for x in business.get('business_model',{}).get('segments') or [])}</p><h3>Options de revenus</h3>{table(['Offre','Modèle','Prix indicatif','Rôle'],[[esc(x.get('id')),esc(x.get('model')),esc(x.get('indicative_monthly_eur') or x.get('indicative_annual_eur')),esc(x.get('purpose'))] for x in business.get('business_model',{}).get('revenue_options') or []])}
<p>Le go-to-market recommandé commence par des pilotes externes instrumentés : coût par tâche réussie, autonomie réelle, temps humain économisé, rollback/incident rate, coût modèle/compute, et reproductibilité d’installation. La valorisation devient crédible quand ces métriques se transforment en adoption puis en ARR.</p>
<h2>12. Scénarios de valorisation</h2><div class="callout">Ces montants sont des scénarios de travail, pas une expertise financière indépendante.</div>{table(['Stade','Conditions','Fourchette indicative','Méthode'],val_rows)}
<p>Comparables directionnels publics : Factory a annoncé $200M levés à $5B de valorisation le 15 septembre 2026 ; Cognition a annoncé plus de $2B à $48B le 8 septembre 2026 ; Replit a annoncé $400M à $9B le 11 mars 2026. Ces chiffres illustrent l’appétit du marché pour l’automatisation logicielle, mais ne sont pas des comparables de valorisation directe tant que ChaCha DEV n’a pas de traction externe mesurée.</p>
<h2>13. Roadmap et critères de création</h2><p>La prochaine évolution ne doit pas être « ajouter une fonctionnalité », mais fermer un écart mesuré de la Factory. Le gate d’entrée exige : provenance, valeur globale ≥ {esc(intel.get('utility_gate',{}).get('minimum_global_value_score'))}/100, fit architectural, dette de maintenance acceptable, falsification Logicien, Architecture Council, stratégie reuse/licence, qualification et rollback.</p>
<h2>14. Provenance</h2><p>Ce document a été généré depuis la révision <code>{esc(candidate_rev)}</code> / tree <code>{esc(tree)}</code>, les états runtime sous <code>{esc(runtime)}</code>, les configurations du dépôt et le baseline concurrentiel daté {esc(market.get('as_of'))}. Les états runtime observés sont prioritaires lorsqu’ils contredisent un fichier historique.</p>
<p class="muted">ChaCha DEV - livre blanc vivant - {esc(generated)}</p></main></body></html>'''
    outroot.mkdir(parents=True,exist_ok=True); (outroot/'index.html').write_text(html_doc,encoding='utf-8')
    snapshot={'schema':'chacha.dev/living-whitepaper-snapshot/v1','status':'PASS','generated_at':generated,'production_revision':current_rev,'source_revision':candidate_rev,'source_tree':tree,'state_authority':authority.get('mode'),'services':services,'release_count':len(releases),'competitive_baseline_as_of':market.get('as_of'),'automatic_external_spend_eur':0}
    (outroot/'metadata.json').write_text(json.dumps(snapshot,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return snapshot

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--runtime-root',type=Path,default=Path('/opt/chacha-dev/runtime'));ap.add_argument('--output-root',type=Path);a=ap.parse_args()
    repo=a.repo_root.resolve(); runtime=a.runtime_root.resolve(); cfg=load(repo/'dev-hub/config/living-whitepaper.v1.json'); out=(a.output_root or Path(cfg.get('runtime_output_root') or runtime/'whitepaper/current')).resolve()
    snap=generate(repo,runtime,out); print(json.dumps(snap,ensure_ascii=False));print('CHACHA_DEV_LIVING_WHITEPAPER=PASS');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
if __name__=='__main__':main()
