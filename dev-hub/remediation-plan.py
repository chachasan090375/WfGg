#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ROOT = Path('/opt/chacha-dev')

ACTIONS = {
    'product': [
        'Formaliser exigences fonctionnelles/non fonctionnelles et criteres d acceptance.',
        'Relier chaque changement a un besoin produit testable.'
    ],
    'frontend': [
        'Verifier responsive, accessibilite, etats erreur/chargement et PWA si applicable.',
        'Ajouter tests de parcours utilisateur critiques.'
    ],
    'backend': [
        'Verifier validation des entrees, contrats API, erreurs et idempotence.',
        'Ajouter tests unitaires et integration des routes critiques.'
    ],
    'data': [
        'Documenter cycle de vie schema, retention, migrations et restauration.',
        'Tester migrations et rollback sur environnement isole.'
    ],
    'security': [
        'Verifier authn/authz, secrets, CORS, headers et dependances.',
        'Ajouter scan de dependances/securite en CI et traitement des alertes.'
    ],
    'integrations': [
        'Documenter contrats, timeouts, retries, quotas et modes de panne.',
        'Ajouter tests de degradation des integrations externes.'
    ],
    'testing': [
        'Mettre en place tests unitaires rapides pour la logique metier.',
        'Ajouter tests integration API/data puis E2E des parcours critiques.',
        'Executer les tests dans la CI avec seuil minimal et rapport exploitable.'
    ],
    'build': [
        'Rendre build et deploy reproductibles depuis un environnement propre.',
        'Versionner les commandes et verifier les artefacts produits.'
    ],
    'ci_cd': [
        'Ajouter controles CI obligatoires avant production.',
        'Verifier separation recette/production, approbation et rollback.'
    ],
    'observability': [
        'Ajouter health checks, logs structures, metriques et alertes actionnables.',
        'Definir signaux SLO et procedure d investigation.'
    ],
    'performance': [
        'Definir budgets de performance mesurables.',
        'Ajouter tests de charge/web-vitals et strategie cache.'
    ],
    'backup_recovery': [
        'Definir RPO et RTO explicites.',
        'Automatiser sauvegardes des donnees non recreables.',
        'Executer un restore drill isole et conserver la preuve du resultat.'
    ],
    'documentation': [
        'Maintenir architecture, runbook et ADR pour les choix structurants.',
        'Documenter installation, exploitation, incidents et reprise.'
    ],
    'operations': [
        'Completer runbook incident/rollback et gestion couts/quotas.',
        'Tester regulierement les procedures operatoires.'
    ],
}


def priority(status, score):
    if status == 'MISSING':
        return 'P0'
    if status == 'PARTIAL' and score < 50:
        return 'P0'
    if status == 'PARTIAL':
        return 'P1'
    if status == 'OK' and score < 85:
        return 'P2'
    return None


def main():
    ap = argparse.ArgumentParser(prog='architect-remediation')
    ap.add_argument('project')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    p = ROOT / 'audits' / args.project / 'latest.json'
    if not p.exists():
        raise SystemExit(f'AUDIT_NOT_FOUND={p}')
    report = json.loads(p.read_text())
    if int(report.get('files_scanned', 0)) <= 0:
        raise SystemExit('REMEDIATION_REFUSES_EMPTY_AUDIT')

    items = []
    for name, gate in report.get('gates', {}).items():
        status = gate.get('status', 'MISSING')
        score = int(gate.get('score', 0))
        prio = priority(status, score)
        if not prio:
            continue
        actions = []
        for m in gate.get('missing', []):
            actions.append('Corriger preuve manquante: ' + str(m))
        for a in ACTIONS.get(name, []):
            if a not in actions:
                actions.append(a)
        items.append({
            'priority': prio,
            'gate': name,
            'status': status,
            'score': score,
            'actions': actions[:5],
        })

    order = {'P0': 0, 'P1': 1, 'P2': 2}
    items.sort(key=lambda x: (order[x['priority']], x['score'], x['gate']))
    out = {
        'schema': 'chacha.dev/remediation-plan/v1',
        'project': args.project,
        'audit_time': report.get('time'),
        'files_scanned': report.get('files_scanned'),
        'items': items,
    }

    dest = ROOT / 'audits' / args.project / 'remediation-latest.json'
    dest.write_text(json.dumps(out, indent=2) + '\n')

    if args.json:
        print(json.dumps(out, indent=2))
        return

    print('=== CHACHA ARCHITECT REMEDIATION PLAN V4.5 ===')
    print(f'PROJECT={args.project}')
    print(f'FILES_SCANNED={report.get("files_scanned", 0)}')
    print(f'ACTION_GROUPS={len(items)}')
    print()
    for item in items:
        print(f"{item['priority']}  {item['gate'].upper()}  STATUS={item['status']} SCORE={item['score']}")
        for action in item['actions']:
            print(f'    - {action}')
        print()
    if not items:
        print('NO_REMEDIATION_REQUIRED')
    print(f'REMEDIATION_REPORT={dest}')
    print('REMEDIATION_PLAN=OK')


if __name__ == '__main__':
    main()
