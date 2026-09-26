# ChaCha DEV — Voice Gateway V8.1.4

## Objectif

V8.1.4 ajoute une conversation orale bidirectionnelle au canal léger `💬 ChaCha` sans donner la moindre autorité technique au moteur vocal.

Chaîne cible :

Voix utilisateur → Android Speech Recognizer → transcript → canal Conversation → réponse ChaCha → Android TextToSpeech → utilisateur.

Le canal `🛠️ Créer` ne peut jamais être sélectionné automatiquement par la voix.
## Fonctionnement

- le bouton micro active une session vocale et force le canal Conversation ;
- le transcript est envoyé automatiquement, sans étape de copie manuelle ;
- seule la réponse humaine de ChaCha est lue à voix haute ;
- à la fin de la synthèse vocale, Android relance l'écoute pour le tour suivant ;
- toucher le micro pendant la parole de ChaCha arrête immédiatement le TTS puis ouvre l'écoute ;
- le bouton `⏹ Vocal` arrête la session vocale sans déclencher le Stop global de ChaCha DEV.

Le barge-in automatique par VAD, sans toucher l'écran, n'est pas encore activé en V8.1.4.
## Vie privée et Centre Humain

Voice Gateway ne conserve pas l'audio brut. Seul le transcript normal rejoint la timeline de conversation.

La voix n'est jamais utilisée pour déduire automatiquement :
- âge ;
- genre ;
- origine depuis l'accent ;
- identité biométrique ;
- diagnostic émotionnel.

Les signaux émotionnels restent ceux explicitement exprimés dans les mots de l'utilisateur, conformément au Centre Humain V8.1.2.
## Compatibilité Android

La nouvelle application est `0.7.0`, versionCode `7`, protocole shell natif `2`.

`min_shell_protocol_version` reste à `1` : l'ancienne APK continue donc de fonctionner en texte pendant la transition. L'UI détecte simplement l'absence du bridge natif et propose la mise à jour Android pour activer le vocal complet.

La distribution native reste soumise au mécanisme existant : signature épinglée, SHA exact, Guardian, Sentinel, publication atomique, rollback et confirmation d'installation Android par l'utilisateur.

## Gouvernance

Voice Gateway possède un contrat Guardian sans autorité d'exécution, de mutation ou de bascule automatique vers Build. Dépense externe automatique : 0 €.
