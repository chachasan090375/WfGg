# ChaCha DEV — Checkpoint V7.3 Direct Operator + Android Widget — IN PROGRESS

Date: 2026-09-24
Status: V7.2 ACQUIRED / V7.3 IN PROGRESS

## 1. Baseline acquise à ne pas rejouer

V7.2 Human Interface Gateway est acquise en production.

- Runtime SHA acquis: `d35fb8640145edac392627eebbcc1599e1f2e713`
- Runtime version: `7.2.0`
- Runtime actif:
  `/opt/chacha-dev/platform/releases/20260924T171817Z-d35fb8640145edac392627eebbcc1599e1f2e713`
- Releases physiques: 3
- Timer Intendant: active + enabled
- V7.2 a prouvé en PILOT réel:
  - `Allo` => STATUS via Central Interface Controller
  - INSTRUCTION => orchestration réelle du cerveau central
  - `Go` => nouvelle continuation centrale réelle
  - audit hash-chain PASS
  - Guardian PASS
  - interface technique sans autorité de décision ni mutation
- Ne pas rejouer V7.0/V7.1/V7.2.

## 2. Objectif V7.3

Construire une entrée directe vers ChaCha DEV, sans ChatGPT dans le chemin:

`Android Widget / Direct Web -> Direct Operator -> Functional Translator -> Central Interface Controller -> ChaCha DEV Central Brain`

L'utilisateur ne veut PAS de terminal/Termux comme interface opérationnelle.

UX cible Android:
- widget écran d'accueil ressemblant à une barre de recherche
- texte: “Demander à ChaCha DEV…”
- toucher => mini fenêtre native de saisie
- bouton micro => dictée
- bouton état => équivalent `Allo`
- boutons/actions pour envoyer, Go, Allo, Stop
- aucune logique technique ou décisionnelle dans le widget

## 3. Architecture V7.3 retenue

### Functional Translator satellite
Fichier:
`dev-hub/bin/functional-translator-agent.py`

Responsabilités:
- conserver mot pour mot la demande utilisateur
- la structurer en Functional Intent
- utiliser le `specification-compiler.py` existant
- utiliser le `functional-intent-orchestrator.py` existant
- produire functional contract + functional preplan + interface intent
- aucune autorité d'architecture
- aucune autorité d'exécution
- central-orchestrator obligatoire

### Direct Operator Service
Fichier:
`dev-hub/bin/direct-operator-service.py`

Caractéristiques:
- backend HTTP asynchrone
- bind loopback seulement
- port prévu: 8792
- API commune Web + Android
- POST `/api/v1/intent`
- GET `/api/v1/jobs/<job_id>`
- GET `/api/v1/session`
- cycle asynchrone:
  `QUEUED -> TRANSLATING -> CENTRAL_ORCHESTRATION -> COMPLETE|FAILED`
- `Go / Allo / Stop` normalisés côté service
- réponses enveloppées comme Human Interface Response
- session directe persistante
- aucune décision technique directe

### Direct Web
Fichier:
`dev-hub/direct-operator-ui/index.html`

Surface mobile-first avec:
- champ de saisie libre
- Envoyer
- Go
- Allo
- Stop
- suivi de job asynchrone

### Politique Direct Operator
Fichier:
`dev-hub/config/direct-operator.v1.json`

Principes:
- backend loopback
- accès privé Tailscale
- Funnel public interdit pour cette surface
- identité Tailscale obligatoire
- liste d'utilisateurs autorisés côté runtime
- ChatGPT absent du chemin direct
- central brain obligatoire
- dépense externe automatique = 0

### Service systemd
Fichier:
`dev-hub/systemd/chacha-dev-direct-operator.service`

Le service V7.3 n'est PAS encore installé sur le VPS au moment de ce checkpoint.

## 4. Tailscale

VPS:
- DNS Tailscale: `chachavps.tail3ab05a.ts.net`
- le Funnel existant sur 443 pointe déjà vers Radar et ne doit pas être remplacé.

Choix V7.3:
- Direct Operator doit utiliser une surface Tailscale Serve privée séparée
- HTTPS prévu: `https://chachavps.tail3ab05a.ts.net:8443`
- backend réel reste `127.0.0.1:8792`
- ne pas exposer Direct Operator via le Funnel public existant
- identité Tailscale transmise par Serve utilisée pour l'autorisation
- aucun token opérateur statique dans l'APK/widget

## 5. Android Widget

Module:
`android/chacha-direct-operator-widget`

Déjà présents:
- `settings.gradle.kts`
- `build.gradle.kts`
- `gradle.properties`
- `app/build.gradle.kts`
- `AndroidManifest.xml`
- thème / strings / drawables
- `widget_chacha.xml`
- `activity_operator.xml`
- `chacha_widget_info.xml`
- `ChaChaWidgetProvider.java`
- `OperatorActivity.java`

Architecture widget:
- AppWidget léger
- widget non éditable directement (limitation Android AppWidget/RemoteViews)
- clic sur la barre => petite Activity de saisie
- support micro/dictée
- appel HTTPS privé vers Direct Operator
- aucune clé secrète embarquée

Build Android:
- AGP 9.4.0
- compileSdk 36
- targetSdk 36
- minSdk 26
- Java 17
- applicationId: `com.wfgg.chachadev.operator`

Workflow:
`.github/workflows/dev-hub-v730-android-widget-build.yml`

## 6. Qualification / release V7.3

Branche canonique en cours:
`dev-hub-v730-direct-operator-android-widget`

SHA de travail au moment du checkpoint, avant commit documentaire:
`44a62264fb3eb75a58fda2153bf2855b4ee04eb0`

Message:
`fix(dev-hub): deploy Guardian D1 budget timer transactionally in V7.3`

Autres éléments déjà présents:
- `dev-hub/tests/test_v730_direct_operator.py`
- `dev-hub/bin/install-v730-direct-operator-android-widget.sh`
- `dev-hub/config/v730-release-gates.v1.json`
- `.github/workflows/dev-hub-v730-direct-operator-qualification.yml`
- `.github/workflows/dev-hub-v730-guardian-runtime-deploy.yml`

État CI au moment du checkpoint sur `44a62264...`:
- V7.3 Direct Operator qualification: SUCCESS
- V7 Guardian coverage sync: SUCCESS
- Sentinel technical assurance: IN_PROGRESS
- V7.3 Guardian runtime deploy: IN_PROGRESS
- V7.3 Android Operator Widget build: IN_PROGRESS
- V7 platform qualification: IN_PROGRESS

IMPORTANT:
- ne pas considérer V7.3 acquise tant que tous les gates exact-SHA ne sont pas PASS et que le PILOT VPS réel n'est pas PASS.
- ne pas installer Direct Operator tant que les gates exact-SHA ne sont pas verts.
- ne pas exposer le backend publiquement.

## 7. État VPS au checkpoint

Runtime réel:
- version: `7.2.0`
- revision: `d35fb8640145edac392627eebbcc1599e1f2e713`
- release count: 3
- `chacha-dev-intendant-hygiene.timer`: active + enabled
- `chacha-dev-direct-operator.service`: inactive / not-found

Donc:
- V7.2 est la seule baseline runtime acquise.
- V7.3 n'a encore aucune activation production sur VPS.

## 8. Prochaine séquence exacte

1. Reprendre la branche V7.3 et vérifier sa tête réelle; ne pas supposer qu'elle est encore `44a62264...`.
2. Vérifier tous les workflows exact-SHA:
   - V7.3 Direct Operator qualification
   - V7.3 Android Operator Widget build
   - V7.3 Guardian runtime deploy
   - V7 platform qualification
   - Sentinel
   - Guardian coverage sync
3. Si un workflow a échoué, récupérer le finding exact et corriger minimalement.
4. Quand tous les gates sont PASS:
   - anti-double-deployment VPS
   - PILOT install V7.3 transactionnel
   - vérifier Direct Operator loopback 8792
   - installer Tailscale Serve privé 8443 sans modifier le Funnel Radar existant
   - créer/valider la liste d'identités Tailscale autorisées
   - PILOT réel Direct Operator:
     - instruction fonctionnelle
     - Functional Translator
     - Central Brain receipt
     - Allo
     - Go
     - Stop hors-bande
   - vérifier aucune décision technique directe dans Direct Operator
   - vérifier aucune clé statique dans Android
   - vérifier 3 releases distinctes
5. Récupérer l'APK issu du workflow Android et le fournir à l'utilisateur.
6. Tester sur le Samsung Galaxy Z Flip 7:
   - installation APK
   - ajout widget écran d'accueil
   - saisie
   - micro
   - Allo
   - Go
   - réponse de ChaCha DEV
7. Seulement après tout cela: déclarer V7.3 ACQUIRED et créer son checkpoint final.

## 9. Règles de reprise

- Ne pas rejouer V7.0, V7.1 ou V7.2.
- V7.2 runtime acquis = `d35fb864...`.
- V7.3 est en cours, pas acquise.
- Continuer depuis la tête réelle de `dev-hub-v730-direct-operator-android-widget`.
- Toujours distinguer SHA runtime acquis et commit documentaire.
- En cas de concurrence sur la branche/runtime: inspecter avant d'écrire ou déployer.
- Le chemin direct V7.3 ne passe pas par ChatGPT.
- Functional Translator = traduction fonctionnelle, jamais exécution/architecture finale.
- Central Brain = décision/orchestration.
- Guardian / Bastion / Council / Run Controller restent les autorités existantes.
- Aucun nouveau “cerveau parallèle”.
