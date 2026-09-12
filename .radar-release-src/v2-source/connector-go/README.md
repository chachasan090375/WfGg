# WfGg Radar Connector Gateway V0.4 LAB — Native Template

Service autonome séparé de WfGg Portal et de Train. Cette version remplace le chemin de reconnexion générique du V0.3 par le mécanisme **Phase 5 native-template** retrouvé dans le Master V3.

## Principe Phase 5 repris à l'identique

Le probe charge un Login natif provenant d'un PCAP du compte de test et conserve tous ses champs. Il ne régénère que les six champs dynamiques :

`_id`, `cmdBaseTime`, `SecurityCode`, `OneCode`, `CoreV`, `psh`.

Il ouvre ensuite un seul socket TCP vers le serveur observé dans cette capture, envoie exactement un Login SFS2X puis lit uniquement :

1. la réponse du Login ;
2. le push `init`.

Aucune commande de gameplay, aucun `collect`, aucun `interactive` et aucun scan World/Map ne sont activés dans V0.4.

## Sécurité

- navigateur -> Radar : session Radar ;
- Radar -> Gateway : HMAC-SHA256 + timestamp + nonce anti-rejeu ;
- token Last War : reçu uniquement par le Gateway, écrit dans un répertoire temporaire `0700` / fichier `0600`, détruit après le round-trip ;
- le PCAP de référence est un **secret LAB** : il doit être monté au runtime et ne doit jamais être commité ni intégré à l'image ;
- ni token, ni DeviceID, ni ShumeiBoxId ne sont renvoyés dans les observations ;
- seules des preuves `OBSERVED` expurgées sont transmises à Oracle.

## Mode live V0.4

Variables :

- `RADAR_CONNECTOR_SHARED_KEY` : secret HMAC interne, >= 32 caractères ;
- `LASTWAR_SESSION_CONTEXT_JSON` : `zone`, `gameUid`, `deviceId`, `shumeiBoxId`, `iosMode`, éventuellement `ip/port`, **sans accessToken** ;
- `LASTWAR_NATIVE_CAPTURE` : chemin absolu vers le PCAP/PCAPNG natif monté en lecture seule ;
- `LASTWAR_NATIVE_TEMPLATE_BIN` : facultatif, `/radar-native-template` par défaut dans l'image ;
- `LASTWAR_CLIENT_TIMEOUT_SECONDS` : 10..120, 45 par défaut.

Lorsque `LASTWAR_NATIVE_CAPTURE` est présent, ce mode est prioritaire et le health annonce :

`native-template-readonly-v1`

Le vieux mode `LASTWAR_CLIENT_BIN -list-buildings` reste uniquement comme fallback LAB si aucun capture native-template n'est configuré.

## Résultat

Le snapshot V0.4 expose notamment : Login OK/non OK, nombre de champs natifs copiés, nombre de champs dynamiques régénérés, réception de `init`, nombre de champs `init`, comptes `userHero`, `building_new`, `science_new`, liste des clés de premier niveau et pseudo lorsqu'il est effectivement observé.

La source de provenance est : `wfgg/master-v3/phase5-native-template`.
