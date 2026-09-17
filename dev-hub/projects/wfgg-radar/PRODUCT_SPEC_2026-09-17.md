# WfGg Radar — Product Specification / Project Control source of truth

Date de référence : 2026-09-17  
Projet : WfGg Radar  
Pilotage : ChaCha DEV HUB V5 / Project Control  
Repository : `chachasan090375/WfGg`  
Branche de production Radar : `radar-production-v1`

## 1. Règle de gouvernance

Ce document est la source de vérité fonctionnelle Radar pour ChaCha DEV.

- Le développement Radar doit être piloté par ChaCha DEV / Project Control.
- Les incidents runtime (VPS, SHA, Sentinel, déploiement) sont des gates d’environnement et ne doivent pas remplacer le backlog fonctionnel.
- Aucun contournement manuel Termux/SSH ne doit devenir le chemin normal de développement.
- Toute mutation production reste soumise à approbation humaine explicite.
- Last War reste strictement READONLY : aucune collecte, attaque, marche, achat, donation, récompense ou autre action de gameplay ne doit être émise.

## 2. État acquis à conserver

### Cartographie et profils

La chaîne réelle carte -> GameUID -> profil a été validée :

- 9/9 régions ;
- environ 21k joueurs/villes observés par cycle ;
- V6.9.7 : 21 688 GameUID uniques observés ;
- V6.9.7 : 21 688 / 21 688 profils résolus ;
- enrichissement natif via `get.user.info.multi`.

Le problème historique de wildcard, de région centrale, de découpage 9 régions et d’enrichissement profil n’est plus le front principal.

### V6.18

Dernier jalon métier acquis : **Radar V6.18 — preserve map fields during profile enrichment**.

But :
- préserver les données issues de la carte quand le profil enrichi est plus pauvre ;
- conserver notamment serveur, alliance, HQ, X/Y et, quand observés, rang/bouclier.

PR de référence : **#158**, fusionnée.

## 3. Priorités fonctionnelles courantes

### P1 — Serveur + coordonnées cliquables

Pour chaque joueur, Radar doit afficher :

- serveur ;
- coordonnées X/Y ;
- coordonnées cliquables permettant de localiser immédiatement le joueur sur la carte Radar.

Le besoin utilisateur est : **je clique sur les coordonnées d’un joueur et je vois où il se trouve**.

Un deep-link natif directement dans Last War n’est pas considéré comme acquis tant qu’il n’est pas prouvé. La navigation interne Radar est le besoin minimum obligatoire.

### P2 — GameUID comme identité canonique

`GameUID` est la clé stable de la base joueur.

Radar doit :

- dédupliquer par GameUID ;
- rattacher les observations successives au même joueur ;
- réinterroger périodiquement les profils ;
- détecter les changements de pseudo ;
- conserver un historique des alias/pseudonymes avec dates d’observation.

Un changement de pseudo ne doit jamais créer artificiellement un nouveau joueur si le GameUID est identique.

### P3 — Recherche joueur rapide

Recherche utilisateur à partir de **3 caractères**.

Résultat rapide / popup minimum :

- avatar/photo si réellement observable ;
- pseudo courant ;
- alliance ;
- serveur ;
- coordonnées.

La fiche détaillée complète est une étape ultérieure ; elle ne doit pas bloquer la recherche rapide.

### P4 — Inventaire READONLY des données joueur

ChaCha DEV doit piloter un inventaire de ce qui est réellement observable sans écriture côté jeu.

Cibles prioritaires :

- bouclier / shield ;
- équipes ;
- héros ;
- troupes ;
- garnison / mur ;
- données PvP observables ;
- puissance ;
- buffs / debuffs ;
- autres attributs de ville ou joueur utiles à Radar.

Chaque champ doit être classé explicitement :

- `OBSERVED` : lu directement dans une réponse ou structure protocolaire ;
- `INFERRED` : déduit à partir de plusieurs observations ;
- `CONFIRMED` : observation répétée/corroborée ;
- `UNKNOWN` : non prouvé.

Ne jamais présenter une valeur calculée ou supposée comme une donnée directement fournie par Last War.

### P5 — Bouclier / Shield

Le bouclier ne doit pas être recherché uniquement dans `get.user.info.multi`.

Piste prioritaire :

- données monde/ville ;
- structures de type `ShieldInfo` ;
- structures de type `WorldPointInfo` ;
- observations carte associées au GameUID / pointId.

L’objectif est de déterminer précisément :

- présence/absence du bouclier ;
- éventuel timestamp d’expiration ;
- provenance du champ ;
- stabilité du champ au fil des observations.

## 4. Architecture fonctionnelle Radar

### Collector

Responsable de l’observation bas niveau :

- protocole ;
- commandes READONLY ;
- réponses ;
- coordonnées ;
- villes/joueurs ;
- états ;
- effets ;
- événements.

### Identity / Player index

Responsable de :

- GameUID canonique ;
- pseudo courant ;
- historique des alias ;
- serveur ;
- alliance ;
- coordonnées ;
- timestamps d’observation ;
- provenance.

### Knowledge Engine

Transforme les observations en connaissances versionnées :

- `OBSERVED`
- `INFERRED`
- `CONFIRMED`
- `OBSOLETE`

### Application Plane

Consomme les données pour :

- recherche joueur ;
- localisation carte ;
- fiches joueur ;
- diagnostics ;
- outils d’analyse futurs.

## 5. Contraintes de sécurité et d’exploitation

- READONLY Last War obligatoire.
- Aucun secret, token Last War, session, payload brut sensible ou clé HMAC dans Git, les artifacts ou les logs.
- Provider result != vérité : Verification Broker requis pour les résultats externes.
- Producer != verifier.
- Planning != execution.
- Run Controller = seul dispatch explicite.
- Production/main interdits sans approbation humaine explicite.
- Les incidents de synchronisation VPS doivent être traités comme `environment/runtime blockers`, pas comme nouveau cahier des charges produit.

## 6. Prochain front produit

Le prochain front produit est :

**V6.19 — Player data / Shield inventory**, tout en finalisant l’exposition serveur + coordonnées cliquables et la persistance GameUID/alias.

Ordre attendu :

1. certifier la persistance serveur + X/Y issue de V6.18 ;
2. exposer les coordonnées cliquables dans Radar ;
3. consolider l’index GameUID + alias ;
4. recherche 3 caractères + popup minimale ;
5. inventorier ShieldInfo / WorldPointInfo et les autres données joueur ;
6. n’implémenter dans l’UI que les champs dont la provenance est prouvée.

## 7. Critère de reprise dans un nouveau chat

Ne pas repartir d’un ancien checkpoint Radar V6.9.x si ce document ou un successeur existe.

Le point de reprise doit être :

**ChaCha DEV Project Control -> WfGg Radar -> dernière evidence vérifiée -> prochain requirement non satisfait.**
