# ChaCha DEV — Human Conversation Architecture V8.1.0

## Audit de départ

ChaCha DEV possède déjà :
- un Direct Operator privé derrière identité Tailscale ;
- un agent conversation-interface-agent qui reformule les receipts du cerveau central sans modifier les décisions ;
- une persistance du dernier échange ;
- une synchronisation live de la dernière réponse ;
- une dictée Android via RecognizerIntent.

Les lacunes observées sont :
- pas de véritable historique multi-tours exposé à l'interface ;
- UI structurée autour du dernier couple demande/réponse ;
- pas de profil conversationnel humain explicite ;
- pas de contexte culturel/régional structuré ;
- pas de moteur d'attention aux signaux émotionnels explicites ;
- pas de provider conversationnel générique ;
- pas de synthèse vocale, turn-taking, VAD ni barge-in ;
- pas encore de mémoire conversationnelle résumée à long terme.

## Architecture cible

### 1. Conversation Surface
Fil continu de bulles utilisateur / ChaCha, synchronisé en direct, avec détails techniques secondaires.

### 2. Conversation Session Store
Historique multi-tours privé par opérateur autorisé. Les tours visibles contiennent le texte utile et les statuts, pas les profils démographiques.

### 3. Human Context & Affect Engine
Contexte utilisateur volontaire : prénom préféré, tutoiement/vouvoiement, genre déclaré facultatif, tranche d'âge facultative, langues, contextes culturels, contextes régionaux, registre, directivité, verbosité, humour et préférences vocales.

Règle : aucun de ces attributs n'est inféré à partir du nom, de la voix, de l'accent ou de la localisation.

Les signaux d'interaction sont éphémères et reposent uniquement sur ce que l'utilisateur exprime explicitement : urgence, frustration, enthousiasme, incertitude et besoin de réassurance.

Aucun diagnostic psychologique et aucun profil émotionnel permanent.

### 4. Dialogue Orchestrator
Future couche de génération conversationnelle naturelle. Elle pourra utiliser un modèle interchangeable, mais n'aura aucune autorité technique.

Entrées : décision du cerveau central, fil récent, résumé conversationnel, profil explicite, signaux d'interaction et contexte projet.
Sortie : formulation conversationnelle uniquement.

Le contenu technique, les statuts, les approvals et les décisions centrales restent immuables.

### 5. Conversation Memory
Trois niveaux séparés : court terme (derniers tours), préférence durable (profil explicite), contexte métier/projet (mémoire centrale ChaCha DEV).

### 6. Voice Gateway
Évolution prévue : STT Android natif existant, TTS à ajouter, détection de fin de parole, mode mains libres, interruption/barge-in et préférences de voix volontaires.
Aucune inférence biométrique ou démographique depuis la voix.

### 7. Privacy & Governance
- profils par opérateur : mode 0600 ;
- répertoires privés : mode 0700 ;
- contexte humain de tour : éphémère ;
- aucune copie de l'âge/genre dans la timeline ;
- aucune autorité technique pour la couche humaine ;
- aucun coût externe automatique.

## V8.1.0 — tranche fondation

Implémenté :
- timeline multi-tours privée ;
- endpoint /api/v1/conversation ;
- profil humain explicite par opérateur ;
- endpoints GET/POST /api/v1/human-profile ;
- Human Context & Affect Engine ;
- détection de signaux explicitement exprimés ;
- fil conversationnel en bulles ;
- panneau de personnalisation facultatif ;
- fallback last_response pendant migration ;
- préparation des contrats voix ;
- coût automatique 0 €.

Non implémenté à ce stade : provider LLM conversationnel, synthèse vocale, dialogue vocal continu, barge-in et mémoire conversationnelle résumée longue durée.

## Principe de conception

Le système doit apprendre à mieux parler avec une personne, pas prétendre deviner qui elle est.

La personnalisation culturelle sert à mieux choisir le registre, les exemples, le rythme et le style. Elle ne doit jamais devenir un ensemble de stéréotypes ni influencer les décisions techniques du cerveau central.
