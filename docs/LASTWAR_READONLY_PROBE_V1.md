# WfGg — Last War read-only probe v1

Statut : **laboratoire uniquement** sur `portal-auth-lastwar-lab-v1`. Rien de ce document ne doit être fusionné dans `main` tant que le protocole, les données réellement utiles et le modèle de consentement ne sont pas validés.

## Pourquoi ce probe

Le formulaire Last War actuel du portail Preview ne fait qu'enregistrer une déclaration UID/serveur en `PENDING`. C'est volontairement insuffisant pour apprendre ce que Last War fournit réellement.

Le probe v1 sert à refaire le flux Last War réel, localement sur l'appareil de l'utilisateur, puis à produire une **copie expurgée** du message de compte retourné par Last War. Cette copie permet d'inventorier les champs exploitables sans envoyer les secrets de reconnexion au navigateur, à GitHub ou à la D1 WfGg.

## Flux validé

Le flux protocolaire utilisé est :

1. bootstrap GSL et création d'une identité de laboratoire locale ;
2. connexion SFS2X ;
3. `account.login.send.verify.code` avec l'adresse e-mail du titulaire ;
4. saisie du code à 6 chiffres reçu par e-mail ;
5. `account.login.new` avec le code ;
6. réception de `push.account.login.new` ;
7. lecture de `gameUid`, du nom du rôle et de `accountArr` ;
8. persistance locale du `loginKey` uniquement pour une reconnexion ultérieure du même laboratoire.

Le code reçu par e-mail n'est jamais persisté.

## Ce qui est sensible

Le message de compte peut contenir des valeurs de reconnexion. Elles ne doivent pas être copiées dans WfGg en clair.

Le script `scripts/lastwar-termux-probe.sh` applique un patch **uniquement dans une copie locale** du client protocolaire public. Après `push.account.login.new`, il appelle le formateur récursif `StringRedacted()` de ce client avant d'écrire le snapshot. Ce formateur masque les clés sensibles même lorsqu'elles apparaissent dans des objets imbriqués de `accountArr`.

Le `loginKey` brut reste dans le HOME privé du probe Termux avec des permissions restrictives. Sa valeur n'est ni affichée, ni incluse dans le snapshot, ni envoyée à GitHub/D1.

## Source protocolaire épinglée

Le probe construit une copie du projet public Apache-2.0 :

- dépôt : `ljagiello/lastwar-client`
- commit : `ee5f64de160a8051c2f9f98189b75038dd225a0a`

L'épinglage empêche une mise à jour amont non examinée de modifier silencieusement le comportement du probe.

## Lancer sous Termux

Depuis un clone WfGg positionné sur `portal-auth-lastwar-lab-v1` :

```bash
git pull
bash scripts/lastwar-termux-probe.sh
```

Prérequis : `git`, `go`, `awk`, `mkfifo`, `grep`. Si `go` n'est pas installé dans Termux, installer les paquets nécessaires avant le premier lancement.

Le script demande l'e-mail et le code à 6 chiffres en **saisie masquée**, donc ils ne sont pas inscrits dans l'historique shell.

Le client est exécuté avec `-list-buildings`, une opération de lecture. Le probe n'utilise pas `-collect` et n'envoie pas de commandes d'automatisation de jeu.

## Fichiers locaux

Répertoire privé : `~/.wfgg-lastwar-probe/`

- `home/` : identité et secret de reconnexion locaux du laboratoire ;
- `probe.log` : journal du client, avec redaction amont ;
- `WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt` : snapshot à analyser ;
- `lastwar-client` : binaire construit localement.

Si l'accès stockage Termux est déjà activé, une copie du snapshot est déposée dans `Téléchargements/WFGG_LASTWAR_ACCOUNT_SNAPSHOT_REDACTED.txt` pour pouvoir la joindre facilement à une conversation.

## Réinitialisation volontaire

Le script réutilise un snapshot déjà produit et ne redemande pas un code inutilement. Pour repartir avec une identité de laboratoire neuve :

```bash
WFGG_PROBE_RESET=1 bash scripts/lastwar-termux-probe.sh
```

Cette commande supprime uniquement l'état local sous `~/.wfgg-lastwar-probe/home/`.

## Étape suivante

Après réception d'un snapshot expurgé réel :

1. inventorier les champs de `accountArr` et du compte ;
2. séparer identifiants stables, données de profil, alliance, serveur et données de session ;
3. décider ce qui est utile à WfGg et ce qui doit être ignoré ;
4. construire un broker de lecture qui garde les secrets hors du navigateur ;
5. seulement ensuite envisager le passage `PENDING -> VERIFIED` et l'authentification WfGg par Last War.
