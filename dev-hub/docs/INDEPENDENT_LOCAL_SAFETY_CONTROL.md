# Contrôle indépendant Conftest / OPA — preuves locales

Statut : vérificateur local et fixtures uniquement. Aucune qualification ou
autorisation de production. Aucun service serveur ajouté.

## Composants

- `dev-hub/bin/local-safety-evidence.py` collecte des observations de comportement
  du code candidat. Il n’importe pas les tests de ChaCha DEV et ne reprend pas
  leurs constantes de résultats attendus.
- `dev-hub/policy/local-safety.rego` définit les obligations dans un moteur
  distinct, Conftest/OPA : STOP, PRE/POST, absence de replay, inventaire,
  provenance, fraîcheur et scope exclusivement local.
- `dev-hub/tests/test_local_safety_conftest.py` calcule séparément les empreintes
  attendues depuis les fichiers locaux, collecte puis vérifie les preuves,
  et présente des variantes adverses au vrai binaire Conftest.

Le vérificateur évalue les observations, pas un champ `reported_status=PASS`.
Les mutations négatives doivent être refusées avec le code de règle attendu,
pas simplement avec une erreur de compilation ou un crash du moteur.

## Garanties testées

- Les six cas STOP sont présents, uniques et conformes : seul false booléen
  explicite permet l’exécution ; absence, corruption et illisibilité bloquent.
- Les consommateurs centraux utilisent un lecteur qui bloque sur un état absent.
- Les six cas d’étape sont couverts ; PRE/POST partagent la même action ; échec,
  timeout et démarrage impossible tentent POST ; refus PRE ne lance rien ; refus
  POST ne retourne pas de succès ; aucun replay ajouté.
- Inventaire à 100 et élément malformé sont refusés ; 99 éléments valides acceptés.
- La révision de base et les empreintes du code doivent correspondre au dossier
  inspecté. Un arbre modifié est déclaré comme tel, pas comme un nouveau SHA qualifié.
- La preuve date de moins d’une heure, avec tolérance de cinq minutes dans le futur.
- Schéma et scope local obligatoires ; toute autorité de production est refusée.

## Exécution

Utiliser Python 3.12 et un binaire Conftest fourni explicitement, puis :

```sh
python3 -B dev-hub/tests/test_local_safety_conftest.py \
  --conftest /chemin/vers/conftest \
  --output-dir /chemin/hors-du-depot/rapport-local
```

Le contrôleur écrit les preuves, les données de référence, les résultats JSON
Conftest et `report.json` dans ce répertoire. Il refuse un changement des sources
pendant la collecte. Il ne télécharge pas Conftest ni les politiques.

Installation réalisée pour l’essai sur ce Mac, hors dépôt Git :
`/Users/chachasan/ChaChaDEV/tools/conftest/0.71.1/conftest`.
Conftest 0.71.1 embarque OPA 1.21.1. Archive officielle Darwin arm64 vérifiée
par SHA256 et `gh attestation verify`, avec workflow et tag épinglés et runners
self-hosted refusés. Provenance dans `download-provenance.json` à côté du binaire.

## Résultat du 12 octobre 2026

24 évaluations : une preuve locale acceptée et 23 variantes adverses refusées
avec les codes attendus. La politique compte neuf familles de refus.
Les résultats détaillés sont dans
`/Users/chachasan/ChaChaDEV/audits/chacha-dev/2026-10-12/conftest-local/report.json`.

## Limites

L’indépendance porte sur le moteur et les règles d’évaluation, pas sur une
certification externe de l’auteur des preuves. La collecte, le dossier et les
règles sont sur la même machine et restent modifiables par son administrateur.
Les empreintes assurent la correspondance locale, pas l’authenticité d’un export
provenant d’un attaquant. Le passage en production exige signature, provenance,
identité du vérificateur et politiques approuvées séparément.

Les fonctions observées sont isolées par AST pour les fixtures ; Guardian est
simulé et l’exécuteur d’étape remplacé par un enfant de test. Le vérificateur ne
prouve pas l’application réelle de Guardian/Sentinelle, le protocole MCP, le
fonctionnement complet d’un workflow ou le comportement sous arrêt brutal.
Ces points nécessitent des qualifications distinctes ; aucun receipt runtime
authentique n’est fabriqué. Les données de référence sont produites hors des
preuves mais localement, et ne sont pas une racine de confiance cryptographique.

Ce contrôle ne consulte pas le VPS, n’accède pas aux secrets, n’exécute pas
d’action de production, ne lève aucun STOP et n’acquitte aucune remédiation.
Prometheus, Grafana, Obsidian et Antigravity restent inchangés.

Références : [Conftest](https://www.conftest.dev/),
[installation et attestations](https://www.conftest.dev/install/).
