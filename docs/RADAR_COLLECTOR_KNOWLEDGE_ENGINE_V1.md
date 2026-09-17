# Radar Collector Knowledge Engine V1

## Mission
Collector est la couche d'observation technique du jeu. Il ne doit pas seulement aspirer des profils joueurs : il doit apprendre les structures, états, événements et mécanismes observables jusqu'au protocole bas niveau, puis transmettre des faits traçables à une couche de connaissance séparée.

## Séparation des responsabilités

1. **Collector / Observation Plane**
   - capture les réponses et structures réellement observées ;
   - identifie commandes, champs, états, coordonnées, entités, effets, erreurs et transitions ;
   - conserve la provenance, la saison/version, le serveur, la région et l'horodatage ;
   - ne transforme jamais une hypothèse en fait.

2. **Knowledge Engine / Rules Plane**
   - relie les observations entre elles ;
   - formalise buffs, debuffs, pourcentages, multiplicateurs, caps, priorités, fenêtres temporelles, règles de saison, règles de serveur et types de zones ;
   - versionne chaque règle et ses preuves.

3. **Application Plane**
   - Radar, simulateurs, guides et futurs agents consomment uniquement les faits/règles exposés par les deux couches précédentes ;
   - les calculs et recommandations restent reproductibles à partir des preuves.

## États de connaissance
Toute règle ou propriété dérivée porte un statut explicite :

- `OBSERVED` : directement vu dans une réponse ou un état du jeu ;
- `INFERRED` : déduit de plusieurs observations mais pas encore confirmé ;
- `CONFIRMED` : reproduit sur plusieurs observations indépendantes ou corroboré par une source canonique ;
- `OBSOLETE` : invalide pour la version/saison courante mais conservé historiquement.

Aucun passage `INFERRED -> CONFIRMED` n'est automatique sans preuve indépendante suffisante.

## Provenance minimale
Chaque observation/règle doit pouvoir référencer :

- `observedAt` ;
- serveur et région/origine ;
- saison/version du jeu si connue ;
- type d'entité ou commande ;
- digest ou identifiant de preuve non sensible ;
- statut de connaissance ;
- première et dernière observation ;
- nombre de reproductions ;
- relations avec les autres règles/observations.

Les tokens, credentials, payloads privés complets et transcriptions sensibles ne sont jamais stockés dans le Knowledge Engine.

## Region learning
Les neuf origines fédérées sont traitées individuellement. Une origine spéciale ou temporairement indisponible ne doit pas annuler les huit autres. Collector doit conserver pour chaque région : succès/échec, nombre d'entités observées, code/cause normalisés et comportement protocolaire. Une région vide est une observation valide ; une erreur de protocole est une observation distincte.

Cette séparation permet notamment de déterminer empiriquement si la région centrale d'une grappe possède des règles différentes (zone de conquête, population différée, entités non-joueurs, protocole distinct) sans l'affirmer avant observation.

## Règles de calcul
Pour les buffs/debuffs et pourcentages, le Knowledge Engine doit conserver la formule sous forme structurée : base, opérateurs, ordre d'application, caps/planchers, conditions, portée et version. Une valeur affichée dans le jeu et une valeur recalculée sont deux preuves distinctes et doivent pouvoir être comparées.

## Principe de sûreté
Collector reste read-only vis-à-vis du jeu. L'apprentissage repose sur observation et requêtes déjà qualifiées en lecture. Aucune action de combat, achat, consommation, mouvement, don, amélioration ou mutation de compte n'est utilisée pour découvrir une règle.

## Premier jalon implémenté
V6.6 matérialise le principe de `Region learning` dans la source canonique : une région de scan défaillante est isolée et journalisée, les autres régions continuent, et les données valides restent utilisables. L'échec global n'est conservé que si aucune des neuf régions n'a pu être traitée avec succès.

Qualification canonique : connecteur, Worker/UI, compilation Go et garde-fous read-only validés sur le HEAD V6.6 avant ouverture de la PR.