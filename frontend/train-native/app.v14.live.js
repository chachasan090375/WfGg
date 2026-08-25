(() => {
    'use strict';
    let BASE_ROSTER = (() => { try {
        return JSON.parse(localStorage.getItem('wfgg_train_roster_cache')) || window.WFGG_ROSTER || [];
    }
    catch (e) {
        return window.WFGG_ROSTER || [];
    } })();
    const STORAGE = 'wfgg_train_v13';
    const LEGACY_KEYS = ['wfgg_train_v1'];

    const API_BASE = '';
    const ROSTER_CACHE_KEY = 'wfgg_train_roster_cache';
    let syncTimer = null;
    let presenceTimer = null;
    let syncing = false;
    let adminPresence = {count:0,online:[],thresholdSeconds:90};
    let presenceListOpen = false;
    let publicGameLinks = [];
    const DEFAULT_STATE = {
        currentUserId: null,
        settings: {
            anchorDate: '2026-08-10',
            trainTime: '20:00',
            officersFirst: true,
            reminderDayBefore: true,
            reminder30: true,
            rotationRanks: {
                officer: ['R5', 'R4'],
                r3driver: ['R3'],
                vip: ['R3', 'R2', 'R1']
            }
        },
        unavailable: {},
        outRotation: [],
        overrides: {},
        exchanges: [],
        alertsEnabled: {},
        languages: {},
        gameLinks: [],
        playerEdits: {},
        addedPlayers: [],
        removedPlayers: [],
        rotationOrder: { officer: [], r3driver: [], r3vip: [] },
        messageVariant: { weekly: 0, daily: 0, driver: 0, vip: 0 }
    };
    let state = loadState();
    let ROSTER = [];
    let byId = {};
    let deferredInstall = null;
    function isStandaloneApp() {
        return window.matchMedia('(display-mode: standalone)').matches
            || window.matchMedia('(display-mode: fullscreen)').matches
            || window.navigator.standalone === true
            || document.referrer.startsWith('android-app://');
    }
    function updateInstallVisibility() {
        const installed = isStandaloneApp();
        document.querySelectorAll('.install-login-btn, .portal-install-btn').forEach(el => el.classList.toggle('hidden', installed));
        const topInstall = document.getElementById('installBtn');
        if (topInstall) topInstall.classList.toggle('hidden', installed);
    }
    let weekOffset = 0;
    let currentAdminSection = null;
    let DIRECTORY = [];
    let adminAnalyticsCache = null;
    let analyticsFilter = 'all';
    let analyticsSearch = '';
    let analyticsCurrentSub = null;
    let analyticsRotationDays = 30;
    let analyticsRotationPool = 'officer';
    let analyticsRotationSort = 'count-desc';
    let analyticsActivitySort = 'total-desc';
    let analyticsSettingsFilter = 'all';
    let analyticsHistorySort = 'newest';
    let gameLinksDraft = null;

    const LANG_KEY='wfgg_train_lang';
    const SUPPORTED_LANGS=['fr','en','it','es'];
    const LOCALES={fr:'fr-FR',en:'en-GB',it:'it-IT',es:'es-ES'};
    const UI_TRANSLATIONS={"Train de l’alliance":{"en":"Alliance Train","it":"Treno dell’alleanza","es":"Tren de la alianza"},"Consulte tes passages, ton planning, tes alertes et tes échanges.":{"en":"Check your turns, schedule, alerts and swaps.","it":"Consulta i tuoi turni, il calendario, gli avvisi e gli scambi.","es":"Consulta tus turnos, calendario, alertas e intercambios."},"Ton pseudo":{"en":"Your nickname","it":"Il tuo nickname","es":"Tu apodo"},"Commence à saisir ton pseudo":{"en":"Start typing your nickname","it":"Inizia a digitare il tuo nickname","es":"Empieza a escribir tu apodo"},"Code R4 / R5":{"en":"R4 / R5 code","it":"Codice R4 / R5","es":"Código R4 / R5"},"6 chiffres":{"en":"6 digits","it":"6 cifre","es":"6 dígitos"},"Entrer dans WfGg Train":{"en":"Enter WfGg Train","it":"Entra in WfGg Train","es":"Entrar en WfGg Train"},"R3/R2/R1 : le pseudo suffit pour entrer":{"en":"R3/R2/R1: nickname only","it":"R3/R2/R1: basta il nickname","es":"R3/R2/R1: basta el apodo"},"Installer l’application":{"en":"Install the app","it":"Installa l’app","es":"Instalar la aplicación"},"Moi":{"en":"Me","it":"Io","es":"Yo"},"Planning":{"en":"Schedule","it":"Calendario","es":"Calendario"},"Échanges":{"en":"Swaps","it":"Scambi","es":"Intercambios"},"Alertes":{"en":"Alerts","it":"Avvisi","es":"Alertas"},"Admin":{"en":"Admin","it":"Admin","es":"Admin"},"Synchronisation":{"en":"Sync","it":"Sincronizzazione","es":"Sincronización"},"Synchronisation…":{"en":"Syncing…","it":"Sincronizzazione…","es":"Sincronizando…"},"Hors connexion":{"en":"Offline","it":"Offline","es":"Sin conexión"},"Synchronisé":{"en":"Synced","it":"Sincronizzato","es":"Sincronizado"},"Disponible":{"en":"Available","it":"Disponibile","es":"Disponible"},"Hors rotation":{"en":"Out of rotation","it":"Fuori rotazione","es":"Fuera de rotación"},"Actif":{"en":"Active","it":"Attivo","es":"Activo"},"Ton prochain train":{"en":"Your next train","it":"Il tuo prossimo treno","es":"Tu próximo tren"},"Tes prochains passages":{"en":"Your upcoming turns","it":"I tuoi prossimi turni","es":"Tus próximos turnos"},"Mon statut":{"en":"My status","it":"Il mio stato","es":"Mi estado"},"Touche une carte":{"en":"Tap a card","it":"Tocca una scheda","es":"Toca una tarjeta"},"Profil":{"en":"Profile","it":"Profilo","es":"Perfil"},"Pseudo & profil":{"en":"Nickname & profile","it":"Nickname e profilo","es":"Apodo y perfil"},"Gérer les rappels":{"en":"Manage reminders","it":"Gestisci promemoria","es":"Gestionar recordatorios"},"Indisponibilités":{"en":"Unavailability","it":"Indisponibilità","es":"Indisponibilidades"},"Voir / corriger":{"en":"View / edit","it":"Vedi / correggi","es":"Ver / corregir"},"Rotation":{"en":"Rotation","it":"Rotazione","es":"Rotación"},"Gérer mon statut":{"en":"Manage my status","it":"Gestisci il mio stato","es":"Gestionar mi estado"},"Modifier mon profil":{"en":"Edit my profile","it":"Modifica il mio profilo","es":"Editar mi perfil"},"Modifier mon pseudo / ma photo":{"en":"Edit nickname / photo","it":"Modifica nickname / foto","es":"Editar apodo / foto"},"Aucun passage prévu pour ton rang actuel ou ta rotation.":{"en":"No turn scheduled for your current rank or rotation.","it":"Nessun turno previsto per il tuo grado o la tua rotazione attuale.","es":"No hay turnos previstos para tu rango o rotación actual."},"Aucun autre passage à venir.":{"en":"No other upcoming turns.","it":"Nessun altro turno in arrivo.","es":"No hay otros turnos próximos."},"Aujourd’hui":{"en":"Today","it":"Oggi","es":"Hoy"},"Demain":{"en":"Tomorrow","it":"Domani","es":"Mañana"},"Calendrier":{"en":"Calendar","it":"Calendario","es":"Calendario"},"Échanger ma place":{"en":"Swap my slot","it":"Scambia il mio posto","es":"Intercambiar mi plaza"},"Indisponible":{"en":"Unavailable","it":"Indisponibile","es":"No disponible"},"CONDUCTEUR":{"en":"DRIVER","it":"CONDUCENTE","es":"CONDUCTOR"},"Conducteur":{"en":"Driver","it":"Conducente","es":"Conductor"},"VIP":{"en":"VIP","it":"VIP","es":"VIP"},"Planning hebdomadaire":{"en":"Weekly schedule","it":"Calendario settimanale","es":"Calendario semanal"},"À définir":{"en":"To be assigned","it":"Da definire","es":"Por definir"},"Bourse aux échanges":{"en":"Swap marketplace","it":"Borsa degli scambi","es":"Mercado de intercambios"},"Annonces ouvertes":{"en":"Open requests","it":"Richieste aperte","es":"Solicitudes abiertas"},"Mes demandes":{"en":"My requests","it":"Le mie richieste","es":"Mis solicitudes"},"Aucune annonce ouverte pour le moment.":{"en":"No open swap requests right now.","it":"Nessuna richiesta di scambio aperta al momento.","es":"No hay solicitudes de intercambio abiertas por ahora."},"Aucune demande publiée.":{"en":"No request published.","it":"Nessuna richiesta pubblicata.","es":"No hay solicitudes publicadas."},"OUVERT":{"en":"OPEN","it":"APERTO","es":"ABIERTO"},"Retirer mon annonce":{"en":"Remove my request","it":"Ritira la mia richiesta","es":"Retirar mi solicitud"},"Je propose une de mes dates":{"en":"Offer one of my dates","it":"Propongo una delle mie date","es":"Propongo una de mis fechas"},"Échanger":{"en":"Swap","it":"Scambia","es":"Intercambiar"},"Choisir ta date":{"en":"Choose your date","it":"Scegli la tua data","es":"Elige tu fecha"},"Aucune date compatible":{"en":"No compatible date","it":"Nessuna data compatibile","es":"No hay fecha compatible"},"Publier ma demande":{"en":"Publish my request","it":"Pubblica la mia richiesta","es":"Publicar mi solicitud"},"Publier un échange":{"en":"Publish a swap","it":"Pubblica uno scambio","es":"Publicar un intercambio"},"Pas maintenant":{"en":"Not now","it":"Non ora","es":"Ahora no"},"Annonce publiée":{"en":"Request published","it":"Richiesta pubblicata","es":"Solicitud publicada"},"Annonce retirée":{"en":"Request removed","it":"Richiesta ritirata","es":"Solicitud retirada"},"Échange effectué":{"en":"Swap completed","it":"Scambio effettuato","es":"Intercambio realizado"},"Une annonce existe déjà pour cette date":{"en":"A request already exists for this date","it":"Esiste già una richiesta per questa data","es":"Ya existe una solicitud para esta fecha"},"Tu ne choisis personne : les joueurs compatibles verront l’annonce et proposeront eux-mêmes leur date.":{"en":"You do not choose a player: compatible members will see the request and offer their own date.","it":"Non scegli tu il giocatore: i membri compatibili vedranno la richiesta e proporranno la propria data.","es":"No eliges a nadie: los jugadores compatibles verán la solicitud y propondrán su propia fecha."},"Alertes & calendrier":{"en":"Alerts & calendar","it":"Avvisi e calendario","es":"Alertas y calendario"},"Rappels personnels":{"en":"Personal reminders","it":"Promemoria personali","es":"Recordatorios personales"},"J-1 puis 30 minutes avant le départ.":{"en":"1 day before, then 30 minutes before departure.","it":"1 giorno prima, poi 30 minuti prima della partenza.","es":"1 día antes y luego 30 minutos antes de la salida."},"Ajouter mes passages au calendrier":{"en":"Add my turns to calendar","it":"Aggiungi i miei turni al calendario","es":"Añadir mis turnos al calendario"},"Ajouter mes prochains passages":{"en":"Add my upcoming turns","it":"Aggiungi i miei prossimi turni","es":"Añadir mis próximos turnos"},"Alertes activées":{"en":"Alerts enabled","it":"Avvisi attivati","es":"Alertas activadas"},"Alertes désactivées":{"en":"Alerts disabled","it":"Avvisi disattivati","es":"Alertas desactivadas"},"Événement calendrier créé":{"en":"Calendar event created","it":"Evento calendario creato","es":"Evento de calendario creado"},"Calendrier créé":{"en":"Calendar created","it":"Calendario creato","es":"Calendario creado"},"Aucun passage à ajouter":{"en":"No turn to add","it":"Nessun turno da aggiungere","es":"No hay turnos que añadir"},"Photo de profil":{"en":"Profile picture","it":"Foto profilo","es":"Foto de perfil"},"Photo actuelle":{"en":"Current picture","it":"Foto attuale","es":"Foto actual"},"Pseudo":{"en":"Nickname","it":"Nickname","es":"Apodo"},"Rang":{"en":"Rank","it":"Grado","es":"Rango"},"Code personnel":{"en":"Personal code","it":"Codice personale","es":"Código personal"},"Demandé uniquement pour enregistrer le profil":{"en":"Required only to save profile changes","it":"Richiesto solo per salvare le modifiche al profilo","es":"Solo se solicita para guardar cambios del perfil"},"Ce code n’est pas nécessaire pour ouvrir l’application.":{"en":"This code is not required to open the app.","it":"Questo codice non serve per aprire l’app.","es":"Este código no es necesario para abrir la aplicación."},"Enregistrer":{"en":"Save","it":"Salva","es":"Guardar"},"Changer mon code":{"en":"Change my code","it":"Cambia il mio codice","es":"Cambiar mi código"},"Tu ne peux pas modifier ton rang. Seuls les R4/R5 peuvent le faire.":{"en":"You cannot change your rank. Only R4/R5 can do that.","it":"Non puoi modificare il tuo grado. Solo R4/R5 possono farlo.","es":"No puedes cambiar tu rango. Solo R4/R5 pueden hacerlo."},"Langue de l’interface":{"en":"Interface language","it":"Lingua dell’interfaccia","es":"Idioma de la interfaz"},"Le changement de langue est immédiat et ne demande pas de code.":{"en":"Language changes immediately and does not require a code.","it":"Il cambio di lingua è immediato e non richiede un codice.","es":"El cambio de idioma es inmediato y no requiere código."},"Langue modifiée":{"en":"Language updated","it":"Lingua aggiornata","es":"Idioma actualizado"},"Mes indisponibilités":{"en":"My unavailability","it":"Le mie indisponibilità","es":"Mis indisponibilidades"},"Aucune indisponibilité enregistrée.":{"en":"No unavailability recorded.","it":"Nessuna indisponibilità registrata.","es":"No hay indisponibilidades registradas."},"Retirer":{"en":"Remove","it":"Rimuovi","es":"Quitar"},"Indisponibilité retirée":{"en":"Unavailability removed","it":"Indisponibilità rimossa","es":"Indisponibilidad eliminada"},"Indisponibilité enregistrée":{"en":"Unavailability saved","it":"Indisponibilità registrata","es":"Indisponibilidad registrada"},"Statut":{"en":"Status","it":"Stato","es":"Estado"},"Reprendre la rotation":{"en":"Resume rotation","it":"Riprendi la rotazione","es":"Reanudar rotación"},"Me retirer de la rotation":{"en":"Leave rotation","it":"Esci dalla rotazione","es":"Salir de la rotación"},"Tu es maintenant hors rotation":{"en":"You are now out of rotation","it":"Ora sei fuori rotazione","es":"Ahora estás fuera de rotación"},"Rotation réactivée":{"en":"Rotation resumed","it":"Rotazione riattivata","es":"Rotación reactivada"},"Administration":{"en":"Administration","it":"Amministrazione","es":"Administración"},"Messages & notifications":{"en":"Messages & notifications","it":"Messaggi e notifiche","es":"Mensajes y notificaciones"},"Planning du lundi, annonce du jour, Conducteur et VIP":{"en":"Monday schedule, daily announcement, Driver and VIP","it":"Calendario del lunedì, annuncio del giorno, Conducente e VIP","es":"Calendario del lunes, anuncio diario, Conductor y VIP"},"Paramètres du train":{"en":"Train settings","it":"Impostazioni del treno","es":"Ajustes del tren"},"Heure, ancrage et alternance des Conducteurs":{"en":"Time, anchor date and driver alternation","it":"Orario, data di riferimento e alternanza conducenti","es":"Hora, fecha de referencia y alternancia de conductores"},"Joueurs de l’alliance":{"en":"Alliance members","it":"Giocatori dell’alleanza","es":"Jugadores de la alianza"},"Ajouter, corriger pseudo/photo/rang ou supprimer":{"en":"Add, edit nickname/photo/rank or remove","it":"Aggiungi, modifica nickname/foto/grado o elimina","es":"Añadir, editar apodo/foto/rango o eliminar"},"Codes & accès":{"en":"Codes & access","it":"Codici e accessi","es":"Códigos y acceso"},"R4/R5, nouveaux codes et sécurité des sessions":{"en":"R4/R5, new codes and session security","it":"R4/R5, nuovi codici e sicurezza delle sessioni","es":"R4/R5, nuevos códigos y seguridad de sesiones"},"Rotations":{"en":"Rotations","it":"Rotazioni","es":"Rotaciones"},"Choisir les rangs autorisés et l’ordre de priorité":{"en":"Choose eligible ranks and priority order","it":"Scegli i gradi ammessi e l’ordine di priorità","es":"Elegir rangos permitidos y orden de prioridad"},"Planning manuel":{"en":"Manual schedule","it":"Calendario manuale","es":"Calendario manual"},"Corriger exceptionnellement une journée":{"en":"Manually adjust a specific day","it":"Correggi eccezionalmente una giornata","es":"Ajustar manualmente un día"},"Contrôle d’équité":{"en":"Fairness check","it":"Controllo equità","es":"Control de equidad"},"Comparer le nombre de passages par rotation":{"en":"Compare number of turns per rotation","it":"Confronta il numero di turni per rotazione","es":"Comparar número de turnos por rotación"},"Membres":{"en":"Members","it":"Membri","es":"Miembros"},"Prêts à copier":{"en":"Ready to copy","it":"Pronti da copiare","es":"Listos para copiar"},"Date de référence":{"en":"Reference date","it":"Data di riferimento","es":"Fecha de referencia"},"Lundi · Planning semaine":{"en":"Monday · Weekly schedule","it":"Lunedì · Calendario settimanale","es":"Lunes · Calendario semanal"},"Annonce du jour":{"en":"Daily announcement","it":"Annuncio del giorno","es":"Anuncio del día"},"Message privé":{"en":"Private message","it":"Messaggio privato","es":"Mensaje privado"},"Autre message":{"en":"Another message","it":"Altro messaggio","es":"Otro mensaje"},"Copier":{"en":"Copy","it":"Copia","es":"Copiar"},"Message copié":{"en":"Message copied","it":"Messaggio copiato","es":"Mensaje copiado"},"Le texte reste modifiable avant copie.":{"en":"The text can still be edited before copying.","it":"Il testo può essere modificato prima della copia.","es":"El texto se puede editar antes de copiarlo."},"Heure du train":{"en":"Train time","it":"Orario del treno","es":"Hora del tren"},"Date d’ancrage":{"en":"Anchor date","it":"Data di riferimento","es":"Fecha de anclaje"},"Premier Conducteur":{"en":"First Driver","it":"Primo Conducente","es":"Primer Conductor"},"Enregistrer & régénérer":{"en":"Save & regenerate","it":"Salva e rigenera","es":"Guardar y regenerar"},"Configuration avancée":{"en":"Advanced settings","it":"Configurazione avanzata","es":"Configuración avanzada"},"Rangs autorisés":{"en":"Eligible ranks","it":"Gradi ammessi","es":"Rangos permitidos"},"Ordre de priorité":{"en":"Priority order","it":"Ordine di priorità","es":"Orden de prioridad"},"Enregistrer les rangs autorisés":{"en":"Save eligible ranks","it":"Salva i gradi ammessi","es":"Guardar rangos permitidos"},"Objectif":{"en":"Target","it":"Obiettivo","es":"Objetivo"},"Semaine en cours":{"en":"Current week","it":"Settimana corrente","es":"Semana actual"},"Automatique":{"en":"Automatic","it":"Automatico","es":"Automático"},"Aucun Conducteur":{"en":"No Driver","it":"Nessun Conducente","es":"Sin Conductor"},"Aucun VIP":{"en":"No VIP","it":"Nessun VIP","es":"Sin VIP"},"Journée modifiée":{"en":"Day updated","it":"Giornata modificata","es":"Día actualizado"},"Retour au planning automatique":{"en":"Back to automatic schedule","it":"Ritorno al calendario automatico","es":"Volver al calendario automático"},"Ajouter un joueur":{"en":"Add member","it":"Aggiungi giocatore","es":"Añadir jugador"},"Modifier le joueur":{"en":"Edit member","it":"Modifica giocatore","es":"Editar jugador"},"Profil actif":{"en":"Active profile","it":"Profilo attivo","es":"Perfil activo"},"Nouveau code":{"en":"New code","it":"Nuovo codice","es":"Nuevo código"},"Supprimer":{"en":"Delete","it":"Elimina","es":"Eliminar"},"Pseudo obligatoire":{"en":"Nickname required","it":"Nickname obbligatorio","es":"Apodo obligatorio"},"Impossible de lire la photo":{"en":"Unable to read the picture","it":"Impossibile leggere la foto","es":"No se puede leer la foto"},"Profil corrigé":{"en":"Profile updated","it":"Profilo aggiornato","es":"Perfil actualizado"},"Profil mis à jour":{"en":"Profile updated","it":"Profilo aggiornato","es":"Perfil actualizado"},"Joueur ajouté":{"en":"Player added","it":"Giocatore aggiunto","es":"Jugador añadido"},"Nouveau membre":{"en":"New member","it":"Nuovo membro","es":"Nuevo miembro"},"Accès R4 / R5":{"en":"R4 / R5 access","it":"Accesso R4 / R5","es":"Acceso R4 / R5"},"Sécurité des comptes":{"en":"Account security","it":"Sicurezza degli account","es":"Seguridad de las cuentas"},"Codes générés pendant cette session":{"en":"Codes generated during this session","it":"Codici generati durante questa sessione","es":"Códigos generados durante esta sesión"},"Aucun nouveau code généré pendant cette session.":{"en":"No new code generated during this session.","it":"Nessun nuovo codice generato durante questa sessione.","es":"No se ha generado ningún código nuevo durante esta sesión."},"Télécharger CSV":{"en":"Download CSV","it":"Scarica CSV","es":"Descargar CSV"},"Effacer la liste":{"en":"Clear list","it":"Cancella elenco","es":"Borrar lista"},"Aucun nouveau code à exporter":{"en":"No new code to export","it":"Nessun nuovo codice da esportare","es":"No hay códigos nuevos para exportar"},"CSV des nouveaux codes téléchargé":{"en":"New-code CSV downloaded","it":"CSV dei nuovi codici scaricato","es":"CSV de nuevos códigos descargado"},"Liste temporaire effacée":{"en":"Temporary list cleared","it":"Elenco temporaneo cancellato","es":"Lista temporal borrada"},"Code actuel":{"en":"Current code","it":"Codice attuale","es":"Código actual"},"Nouveau code (6 chiffres)":{"en":"New code (6 digits)","it":"Nuovo codice (6 cifre)","es":"Nuevo código (6 dígitos)"},"Code personnel modifié":{"en":"Personal code changed","it":"Codice personale modificato","es":"Código personal modificado"},"Réseau indisponible":{"en":"Network unavailable","it":"Rete non disponibile","es":"Red no disponible"},"Session expirée":{"en":"Session expired","it":"Sessione scaduta","es":"Sesión caducada"},"Copié":{"en":"Copied","it":"Copiato","es":"Copiado"},"Copie impossible":{"en":"Copy failed","it":"Copia non riuscita","es":"No se pudo copiar"},"Modification enregistrée":{"en":"Change saved","it":"Modifica salvata","es":"Cambio guardado"},"Retour":{"en":"Back","it":"Indietro","es":"Volver"},"Statistiques du train":{"en":"Statistics & history","it":"Statistiche e cronologia","es":"Estadísticas e historial"},"Rotations, équité et historique des passages":{"en":"Rotations, player activity and change log","it":"Rotazioni, attività dei giocatori e registro modifiche","es":"Rotaciones, actividad de jugadores e historial de cambios"},"Aide au jeu":{"en":"Game help","it":"Aiuto di gioco","es":"Ayuda del juego"},"Guides et sites utiles pour l’alliance":{"en":"Guides and useful alliance sites","it":"Guide e siti utili per l’alleanza","es":"Guías y sitios útiles para la alianza"},"Guide Saison 6":{"en":"Season 6 Guide","it":"Guida Stagione 6","es":"Guía Temporada 6"},"Guide complet WfGg en français et italien":{"en":"Complete WfGg guide in French and Italian","it":"Guida completa WfGg in francese e italiano","es":"Guía completa WfGg en francés e italiano"},"Ouvrir le guide":{"en":"Open guide","it":"Apri la guida","es":"Abrir la guía"},"Ressources utiles":{"en":"Useful resources","it":"Risorse utili","es":"Recursos útiles"},"Liens supplémentaires":{"en":"Additional links","it":"Link aggiuntivi","es":"Enlaces adicionales"},"Ajouter un lien":{"en":"Add a link","it":"Aggiungi un link","es":"Añadir un enlace"},"Enregistrer les liens":{"en":"Save links","it":"Salva i link","es":"Guardar enlaces"},"Titre":{"en":"Title","it":"Titolo","es":"Título"},"Adresse https://…":{"en":"https:// address…","it":"Indirizzo https://…","es":"Dirección https://…"},"Icône":{"en":"Icon","it":"Icona","es":"Icono"},"Visible":{"en":"Visible","it":"Visibile","es":"Visible"},"Supprimer ce lien":{"en":"Delete this link","it":"Elimina questo link","es":"Eliminar este enlace"},"Liens mis à jour":{"en":"Links updated","it":"Link aggiornati","es":"Enlaces actualizados"},"Aucun lien supplémentaire.":{"en":"No additional links.","it":"Nessun link aggiuntivo.","es":"No hay enlaces adicionales."},"Tableau de contrôle":{"en":"Control dashboard","it":"Pannello di controllo","es":"Panel de control"},"Actions sur 7 jours":{"en":"Actions in 7 days","it":"Azioni in 7 giorni","es":"Acciones en 7 días"},"Actions sur 30 jours":{"en":"Actions in 30 days","it":"Azioni in 30 giorni","es":"Acciones en 30 días"},"Joueurs actifs":{"en":"Active players","it":"Giocatori attivi","es":"Jugadores activos"},"Échanges ouverts":{"en":"Open swaps","it":"Scambi aperti","es":"Intercambios abiertos"},"Statistiques des rotations":{"en":"Rotation statistics","it":"Statistiche delle rotazioni","es":"Estadísticas de rotaciones"},"30 prochains jours":{"en":"Next 30 days","it":"Prossimi 30 giorni","es":"Próximos 30 días"},"90 prochains jours":{"en":"Next 90 days","it":"Prossimi 90 giorni","es":"Próximos 90 días"},"Conducteur A":{"en":"Driver A","it":"Conducente A","es":"Conductor A"},"Conducteur B":{"en":"Driver B","it":"Conducente B","es":"Conductor B"},"Écart":{"en":"Spread","it":"Scarto","es":"Diferencia"},"Activité par joueur":{"en":"Activity by player","it":"Attività per giocatore","es":"Actividad por jugador"},"30 derniers jours":{"en":"Last 30 days","it":"Ultimi 30 giorni","es":"Últimos 30 días"},"Aucune modification sur cette période.":{"en":"No changes during this period.","it":"Nessuna modifica in questo periodo.","es":"No hay cambios en este período."},"Historique des changements":{"en":"Change history","it":"Cronologia modifiche","es":"Historial de cambios"},"Tous":{"en":"All","it":"Tutti","es":"Todos"},"Joueurs":{"en":"Players","it":"Giocatori","es":"Jugadores"},"Paramètres":{"en":"Settings","it":"Impostazioni","es":"Ajustes"},"Sécurité":{"en":"Security","it":"Sicurezza","es":"Seguridad"},"Rechercher un joueur…":{"en":"Search a player…","it":"Cerca un giocatore…","es":"Buscar un jugador…"},"Actualiser":{"en":"Refresh","it":"Aggiorna","es":"Actualizar"},"Profil modifié":{"en":"Profile updated","it":"Profilo modificato","es":"Perfil modificado"},"Préférences joueur":{"en":"Player preferences","it":"Preferenze giocatore","es":"Preferencias del jugador"},"Échange publié":{"en":"Swap published","it":"Scambio pubblicato","es":"Intercambio publicado"},"Échange retiré":{"en":"Swap removed","it":"Scambio ritirato","es":"Intercambio retirado"},"Échange accepté":{"en":"Swap accepted","it":"Scambio accettato","es":"Intercambio aceptado"},"Paramètres du train modifiés":{"en":"Train settings changed","it":"Impostazioni del treno modificate","es":"Ajustes del tren modificados"},"Rangs des rotations modifiés":{"en":"Rotation ranks changed","it":"Gradi delle rotazioni modificati","es":"Rangos de rotación modificados"},"Ordre de rotation modifié":{"en":"Rotation order changed","it":"Ordine di rotazione modificato","es":"Orden de rotación modificado"},"Planning manuel modifié":{"en":"Manual schedule changed","it":"Calendario manuale modificato","es":"Calendario manual modificado"},"Joueur modifié":{"en":"Player updated","it":"Giocatore modificato","es":"Jugador modificado"},"Joueur supprimé":{"en":"Player removed","it":"Giocatore eliminato","es":"Jugador eliminado"},"Rotation d’un joueur modifiée":{"en":"Player rotation changed","it":"Rotazione giocatore modificata","es":"Rotación de jugador modificada"},"Code joueur réinitialisé":{"en":"Player code reset","it":"Codice giocatore reimpostato","es":"Código de jugador restablecido"},"Liens d’aide modifiés":{"en":"Help links changed","it":"Link di aiuto modificati","es":"Enlaces de ayuda modificados"},"Connexion":{"en":"Login","it":"Accesso","es":"Inicio de sesión"},"Changements de paramètres":{"en":"Settings changes","it":"Modifiche impostazioni","es":"Cambios de ajustes"},"Le journal indique qui a effectué chaque action. Les détails sont conservés côté serveur.":{"en":"The log shows who performed each action. Details are stored server-side.","it":"Il registro mostra chi ha eseguito ogni azione. I dettagli sono conservati lato server.","es":"El historial muestra quién realizó cada acción. Los detalles se guardan en el servidor."},"Les nouveaux journaux V1.3 enregistrent davantage de détails ; les anciennes entrées restent disponibles avec les informations qui existaient déjà.":{"en":"New V1.3 logs record more detail; older entries remain available with the information previously stored.","it":"I nuovi log V1.3 registrano più dettagli; le vecchie voci restano disponibili con le informazioni già presenti.","es":"Los nuevos registros V1.3 guardan más detalles; las entradas antiguas siguen disponibles con la información existente."},"Aide":{"en":"Help","it":"Aiuto","es":"Ayuda"},"Gestion des liens d’aide":{"en":"Manage help links","it":"Gestione link di aiuto","es":"Gestionar enlaces de ayuda"},"Ajouter et organiser les ressources visibles par tous":{"en":"Add and organize resources visible to everyone","it":"Aggiungi e organizza le risorse visibili a tutti","es":"Añade y organiza recursos visibles para todos"},"Vue d’ensemble":{"en":"Overview","it":"Panoramica","es":"Resumen"},"Les chiffres essentiels en un coup d’œil":{"en":"Key figures at a glance","it":"I dati essenziali a colpo d’occhio","es":"Las cifras clave de un vistazo"},"Répartition Conducteur A, Conducteur B et VIP":{"en":"Driver A, Driver B and VIP distribution","it":"Distribuzione Conducente A, Conducente B e VIP","es":"Distribución Conductor A, Conductor B y VIP"},"Activité joueurs":{"en":"Player activity","it":"Attività giocatori","es":"Actividad de jugadores"},"Qui modifie quoi et à quelle fréquence":{"en":"Who changes what and how often","it":"Chi modifica cosa e con quale frequenza","es":"Quién cambia qué y con qué frecuencia"},"Paramétrage":{"en":"Configuration","it":"Configurazione","es":"Configuración"},"Historique des réglages et actions administratives":{"en":"Settings and admin action history","it":"Cronologia impostazioni e azioni amministrative","es":"Historial de ajustes y acciones administrativas"},"Historique complet":{"en":"Full history","it":"Cronologia completa","es":"Historial completo"},"Filtrer, rechercher et contrôler les changements":{"en":"Filter, search and review changes","it":"Filtra, cerca e controlla le modifiche","es":"Filtrar, buscar y controlar los cambios"},"Retour aux statistiques":{"en":"Back to statistics","it":"Torna alle statistiche","es":"Volver a estadísticas"},"Plus de passages":{"en":"Most turns","it":"Più turni","es":"Más turnos"},"Moins de passages":{"en":"Fewest turns","it":"Meno turni","es":"Menos turnos"},"Pseudo A-Z":{"en":"Nickname A-Z","it":"Nickname A-Z","es":"Apodo A-Z"},"Plus actifs":{"en":"Most active","it":"Più attivi","es":"Más activos"},"Moins actifs":{"en":"Least active","it":"Meno attivi","es":"Menos activos"},"Nombre d’actions":{"en":"Number of actions","it":"Numero di azioni","es":"Número de acciones"},"Train":{"en":"Train","it":"Treno","es":"Tren"},"Liens d’aide":{"en":"Help links","it":"Link di aiuto","es":"Enlaces de ayuda"},"Plus récents":{"en":"Newest","it":"Più recenti","es":"Más recientes"},"Plus anciens":{"en":"Oldest","it":"Più vecchi","es":"Más antiguos"},"Toutes les actions":{"en":"All actions","it":"Tutte le azioni","es":"Todas las acciones"},"Aucune ressource supplémentaire pour le moment.":{"en":"No additional resource yet.","it":"Nessuna risorsa aggiuntiva per il momento.","es":"No hay recursos adicionales por ahora."},"Ressources de l’alliance":{"en":"Alliance resources","it":"Risorse dell’alleanza","es":"Recursos de la alianza"},"Ouvre un guide ou un outil en touchant son icône.":{"en":"Open a guide or tool by tapping its icon.","it":"Apri una guida o uno strumento toccando la sua icona.","es":"Abre una guía o herramienta tocando su icono."},"actions":{"en":"actions","it":"azioni","es":"acciones"},"passages":{"en":"turns","it":"turni","es":"turnos"},"Bienvenue chez WfGg":{"en":"Welcome to WfGg","it":"Benvenuto in WfGg","es":"Bienvenido a WfGg"},"Choisis ton espace.":{"en":"Choose your space.","it":"Scegli il tuo spazio.","es":"Elige tu espacio."},"Planning, rotations, échanges et alertes":{"en":"Schedule, rotations, swaps and alerts","it":"Calendario, rotazioni, scambi e avvisi","es":"Calendario, rotaciones, intercambios y alertas"},"Guide WfGg · Last War":{"en":"WfGg Guide · Last War","it":"Guida WfGg · Last War","es":"Guía WfGg · Last War"},"Page d’accueil":{"en":"Home portal","it":"Pagina iniziale","es":"Página de inicio"},"Configuration du portail WfGg":{"en":"WfGg portal settings","it":"Impostazioni del portale WfGg","es":"Configuración del portal WfGg"},"Préparer les futurs réglages de la page de garde":{"en":"Prepare future portal settings","it":"Prepara le future impostazioni della pagina iniziale","es":"Preparar los futuros ajustes de la portada"},"Ce module servira à faire évoluer progressivement la page d’accueil. Pour le moment, le portail propose le Train et l’Aide au jeu.":{"en":"This module will be used to evolve the home portal progressively. For now, the portal offers the Train and the Season 6 Guide.","it":"Questo modulo servirà a far evolvere progressivamente la pagina iniziale. Per ora, il portale propone il Treno e la Guida Stagione 6.","es":"Este módulo servirá para hacer evolucionar progresivamente la página de inicio. Por ahora, el portal ofrece el Tren y la Guía de la Temporada 6."},"Entrées actuelles":{"en":"Current entries","it":"Voci attuali","es":"Entradas actuales"},"Page de garde WfGg":{"en":"WfGg home portal","it":"Pagina iniziale WfGg","es":"Portada WfGg"},"Retour au portail":{"en":"Back to portal","it":"Torna al portale","es":"Volver al portal"},"Guides, documents et outils WfGg":{"en":"WfGg guides, documents and tools","it":"Guide, documenti e strumenti WfGg","es":"Guías, documentos y herramientas WfGg"},"Choisis une ressource.":{"en":"Choose a resource.","it":"Scegli una risorsa.","es":"Elige un recurso."},"joueur connecté":{"en":"player online","it":"giocatore online","es":"jugador conectado"},"joueurs connectés":{"en":"players online","it":"giocatori online","es":"jugadores conectados"},"Connectés maintenant":{"en":"Online now","it":"Connessi ora","es":"Conectados ahora"},"Aucun autre joueur connecté pour le moment.":{"en":"No other player online right now.","it":"Nessun altro giocatore connesso al momento.","es":"No hay otros jugadores conectados ahora."},"activité récente":{"en":"recent activity","it":"attività recente","es":"actividad reciente"},"Gestion des ressources d’aide":{"en":"Manage help resources","it":"Gestione risorse di aiuto","es":"Gestionar recursos de ayuda"},"Dernière connexion":{"en":"Last seen","it":"Ultimo accesso","es":"Última conexión"},"En ligne maintenant":{"en":"Online now","it":"Online adesso","es":"En línea ahora"},"Aucune connexion enregistrée":{"en":"No recorded activity","it":"Nessun accesso registrato","es":"Sin conexión registrada"},"Accueil WfGg":{"en":"WfGg home","it":"Home WfGg","es":"Inicio WfGg"},"Accueil du guide":{"en":"Guide home","it":"Home della guida","es":"Inicio de la guía"},"Ajouter une indisponibilité":{"en":"Add unavailability","it":"Aggiungi indisponibilità","es":"Añadir indisponibilidad"},"Choisis le type d’indisponibilité":{"en":"Choose the type of unavailability","it":"Scegli il tipo di indisponibilità","es":"Elige el tipo de indisponibilidad"},"Une journée":{"en":"One day","it":"Un giorno","es":"Un día"},"Ce jour de passage":{"en":"This scheduled day","it":"Questo giorno di turno","es":"Este día de turno"},"Indisponible uniquement pour cette date":{"en":"Unavailable only on this date","it":"Indisponibile solo in questa data","es":"No disponible solo en esta fecha"},"Une période":{"en":"A period","it":"Un periodo","es":"Un período"},"Vacances, déplacement, pause du train…":{"en":"Holiday, travel, train break…","it":"Vacanze, viaggio, pausa dal treno…","es":"Vacaciones, viaje, pausa del tren…"},"Choisir une journée":{"en":"Choose a day","it":"Scegli un giorno","es":"Elegir un día"},"Choisir une période":{"en":"Choose a period","it":"Scegli un periodo","es":"Elegir un período"},"Date":{"en":"Date","it":"Data","es":"Fecha"},"Du":{"en":"From","it":"Dal","es":"Desde"},"Au":{"en":"To","it":"Al","es":"Hasta"},"Enregistrer cette journée":{"en":"Save this day","it":"Salva questo giorno","es":"Guardar este día"},"Enregistrer la période":{"en":"Save period","it":"Salva il periodo","es":"Guardar período"},"Retirer la période":{"en":"Remove period","it":"Rimuovi periodo","es":"Quitar período"},"Période enregistrée":{"en":"Period saved","it":"Periodo salvato","es":"Período guardado"},"La date de fin doit être après la date de début.":{"en":"The end date must be on or after the start date.","it":"La data di fine deve essere uguale o successiva alla data di inizio.","es":"La fecha final debe ser igual o posterior a la fecha inicial."},"Choisis les deux dates.":{"en":"Choose both dates.","it":"Scegli entrambe le date.","es":"Elige ambas fechas."},"Période trop longue":{"en":"Period too long","it":"Periodo troppo lungo","es":"Período demasiado largo"},"Maximum : 366 jours par période.":{"en":"Maximum: 366 days per period.","it":"Massimo: 366 giorni per periodo.","es":"Máximo: 366 días por período."},"jours":{"en":"days","it":"giorni","es":"días"},"jour":{"en":"day","it":"giorno","es":"día"},"passages concernés":{"en":"scheduled turns affected","it":"turni interessati","es":"turnos afectados"},"passage concerné":{"en":"scheduled turn affected","it":"turno interessato","es":"turno afectado"},"Indisponibilité supprimée":{"en":"Unavailability removed","it":"Indisponibilità rimossa","es":"Indisponibilidad eliminada"},"Historique du train":{"en":"Train history","it":"Storico del treno","es":"Historial del tren"},"Passages effectués avant l’application":{"en":"Turns completed before the app","it":"Turni effettuati prima dell’app","es":"Turnos realizados antes de la app"},"Historique manuel importé":{"en":"Imported manual history","it":"Storico manuale importato","es":"Historial manual importado"},"Trains compilés":{"en":"Compiled trains","it":"Treni compilati","es":"Trenes compilados"},"Conducteurs":{"en":"Drivers","it":"Conducenti","es":"Conductores"},"Jusqu’au":{"en":"Through","it":"Fino al","es":"Hasta el"},"Compteurs historiques des membres actuels":{"en":"Historical counts for current members","it":"Conteggi storici dei membri attuali","es":"Contadores históricos de miembros actuales"},"Passages conducteur":{"en":"Driver turns","it":"Turni conducente","es":"Turnos conductor"},"Passages VIP":{"en":"VIP turns","it":"Turni VIP","es":"Turnos VIP"},"Anciens joueurs":{"en":"Former players","it":"Ex giocatori","es":"Antiguos jugadores"},"Conservés uniquement dans l’historique":{"en":"Kept only in history","it":"Conservati solo nello storico","es":"Conservados solo en el historial"},"Corrections de pseudos":{"en":"Nickname corrections","it":"Correzioni nickname","es":"Correcciones de apodos"},"Corrections appliquées automatiquement":{"en":"Automatically applied corrections","it":"Correzioni applicate automaticamente","es":"Correcciones aplicadas automáticamente"},"À vérifier":{"en":"Needs review","it":"Da verificare","es":"Por revisar"},"Membres du fichier absents de l’application":{"en":"Spreadsheet members missing from the app","it":"Membri del file assenti dall’app","es":"Miembros del archivo ausentes de la app"},"Membres de l’application absents du fichier":{"en":"App members missing from the spreadsheet","it":"Membri dell’app assenti dal file","es":"Miembros de la app ausentes del archivo"},"Ancien pseudo":{"en":"Old nickname","it":"Vecchio nickname","es":"Apodo anterior"},"Nouveau pseudo":{"en":"New nickname","it":"Nuovo nickname","es":"Nuevo apodo"},"Dernier passage":{"en":"Last turn","it":"Ultimo turno","es":"Último turno"},"La rotation automatique tient maintenant compte de ces passages.":{"en":"Automatic rotation now takes these turns into account.","it":"La rotazione automatica ora tiene conto di questi turni.","es":"La rotación automática ahora tiene en cuenta estos turnos."},"Source : historique manuel WfGg":{"en":"Source: WfGg manual history","it":"Fonte: storico manuale WfGg","es":"Fuente: historial manual WfGg"}};
    const ORIGINAL_TEXT=new WeakMap();
    const ORIGINAL_ATTR=new WeakMap();
    let applyingLanguage=false;
    let languageObserver=null;

    function currentLanguage(){
        const id=state.currentUserId;
        const lang=(id&&state.languages&&state.languages[id])||localStorage.getItem(LANG_KEY)||'fr';
        return SUPPORTED_LANGS.includes(lang)?lang:'fr';
    }
    function currentLocale(){return LOCALES[currentLanguage()]||'fr-FR';}
    function translateDynamic(s,lang){
        let m;
        if((m=s.match(/^Dans (\d+) jours$/))) return lang==='en'?`In ${m[1]} days`:lang==='it'?`Tra ${m[1]} giorni`:lang==='es'?`En ${m[1]} días`:s;
        if((m=s.match(/^(\d+) affichés$/))) return lang==='en'?`${m[1]} shown`:lang==='it'?`${m[1]} mostrati`:lang==='es'?`${m[1]} mostrados`:s;
        if((m=s.match(/^Train à ([^·]+)(?: · avec (.+))?$/))){
            const withName=m[2];
            if(lang==='en')return `Train at ${m[1].trim()}${withName?` · with ${withName}`:''}`;
            if(lang==='it')return `Treno alle ${m[1].trim()}${withName?` · con ${withName}`:''}`;
            if(lang==='es')return `Tren a las ${m[1].trim()}${withName?` · con ${withName}`:''}`;
        }
        if((m=s.match(/^Variante (\d+) \/ (\d+)$/)))return lang==='en'?`Variant ${m[1]} / ${m[2]}`:lang==='it'?`Variante ${m[1]} / ${m[2]}`:lang==='es'?`Variante ${m[1]} / ${m[2]}`:s;
        if((m=s.match(/^Nouvelle date : (.+)$/)))return lang==='en'?`New date: ${m[1]}`:lang==='it'?`Nuova data: ${m[1]}`:lang==='es'?`Nueva fecha: ${m[1]}`:s;
        if((m=s.match(/^Code personnel de (.+) :$/)))return lang==='en'?`Personal code for ${m[1]}:`:lang==='it'?`Codice personale di ${m[1]}:`:lang==='es'?`Código personal de ${m[1]}:`:s;
        if((m=s.match(/^Quelle date veux-tu échanger avec le (.+) \?$/)))return lang==='en'?`Which date do you want to swap with ${m[1]}?`:lang==='it'?`Quale data vuoi scambiare con ${m[1]}?`:lang==='es'?`¿Qué fecha quieres intercambiar con ${m[1]}?`:s;
        if((m=s.match(/^Publier ton passage du (.+) dans la bourse \?$/)))return lang==='en'?`Publish your ${m[1]} turn on the swap marketplace?`:lang==='it'?`Pubblicare il tuo turno del ${m[1]} nella borsa scambi?`:lang==='es'?`¿Publicar tu turno del ${m[1]} en el mercado de intercambios?`:s;
        return s;
    }
    function translatedString(value,lang=currentLanguage()){
        if(!value||lang==='fr')return value;
        const lead=value.match(/^\s*/)?.[0]||'', trail=value.match(/\s*$/)?.[0]||'';
        let core=value.trim();
        if(!core)return value;
        let prefix='';
        const pm=core.match(/^([^A-Za-zÀ-ÿ0-9]+)(.*)$/);
        if(pm){prefix=pm[1];core=pm[2];}
        const hit=UI_TRANSLATIONS[core];
        let out=hit?.[lang]||translateDynamic(core,lang);
        return lead+prefix+out+trail;
    }
    function translateTextNode(node,lang){
        if(!ORIGINAL_TEXT.has(node))ORIGINAL_TEXT.set(node,node.nodeValue);
        const original=ORIGINAL_TEXT.get(node);
        const next=translatedString(original,lang);
        if(node.nodeValue!==next)node.nodeValue=next;
    }
    function translateElementAttrs(el,lang){
        if(!(el instanceof Element))return;
        let rec=ORIGINAL_ATTR.get(el);
        if(!rec){rec={};ORIGINAL_ATTR.set(el,rec);}
        for(const attr of ['placeholder','title','aria-label']){
            if(!el.hasAttribute(attr))continue;
            if(!(attr in rec))rec[attr]=el.getAttribute(attr);
            const next=translatedString(rec[attr],lang);
            if(el.getAttribute(attr)!==next)el.setAttribute(attr,next);
        }
    }
    function applyLanguage(root=document){
        if(applyingLanguage)return;
        applyingLanguage=true;
        try{
            const lang=currentLanguage();
            document.documentElement.lang=lang;
            const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
            let n;while((n=walker.nextNode()))translateTextNode(n,lang);
            if(root instanceof Element)translateElementAttrs(root,lang);
            if(root.querySelectorAll)root.querySelectorAll('*').forEach(el=>translateElementAttrs(el,lang));
        }finally{applyingLanguage=false;}
    }
    function queueApplyLanguage(){setTimeout(()=>applyLanguage(document),0);}
    function startLanguageObserver(){
        if(languageObserver)return;
        languageObserver=new MutationObserver(muts=>{
            if(applyingLanguage)return;
            queueApplyLanguage();
        });
        languageObserver.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label']});
    }
    async function changeLanguage(lang){
        if(!SUPPORTED_LANGS.includes(lang))return;
        const id=user()?.id,old=currentLanguage();
        localStorage.setItem(LANG_KEY,lang);
        if(id){state.languages=state.languages||{};state.languages[id]=lang;saveState();}
        renderAll();applyLanguage(document);
        try{
            if(id)await api('/api/me/preferences',{method:'PUT',body:JSON.stringify({language:lang})});
            toast('Langue modifiée');
        }catch(e){
            localStorage.setItem(LANG_KEY,old);
            if(id)state.languages[id]=old;
            saveState();renderAll();applyLanguage(document);toast(e.message);
        }
    }

    const ADMIN_CODES_KEY = 'wfgg_train_admin_codes_session';
    function getGeneratedCodes(){
        try{return JSON.parse(sessionStorage.getItem(ADMIN_CODES_KEY)||'[]')}catch(e){return []}
    }
    function rememberGeneratedCode(id,pseudo,rank,pin,reason){
        if(!pin)return;
        const list=getGeneratedCodes().filter(x=>x.id!==id);
        list.push({id,pseudo,rank,pin,reason,createdAt:new Date().toISOString()});
        sessionStorage.setItem(ADMIN_CODES_KEY,JSON.stringify(list));
    }
    function clearGeneratedCodes(){
        if(!confirm('Effacer les codes générés de cette session ? Vérifie d’abord que tu les as copiés ou exportés.'))return;
        sessionStorage.removeItem(ADMIN_CODES_KEY);
        openAdminSection('access');
        toast('Liste temporaire effacée');
    }
    function downloadGeneratedCodesCsv(){
        const list=getGeneratedCodes();
        if(!list.length)return toast('Aucun nouveau code à exporter');
        const q=v=>'"'+String(v??'').replaceAll('"','""')+'"';
        const rows=[['Pseudo','Rang','Code','Motif','Date']];
        list.forEach(x=>{
            const p=byId[x.id];
            rows.push([p?.pseudo||x.pseudo,p?.rank||x.rank,x.pin,x.reason||'',new Date(x.createdAt).toLocaleString(currentLocale())]);
        });
        const csv='\ufeff'+rows.map(r=>r.map(q).join(';')).join('\r\n');
        const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),a=document.createElement('a');
        a.href=URL.createObjectURL(blob);a.download='WfGg-codes-generes-session.csv';
        document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
        toast('CSV des nouveaux codes téléchargé');
    }
    function generatedCodesHtml(){
        const list=getGeneratedCodes();
        if(!list.length)return '<div class="empty compact-empty">Aucun nouveau code généré pendant cette session.</div>';
        return `<div class="access-code-list">${list.map(x=>{
            const p=byId[x.id],pseudo=p?.pseudo||x.pseudo,rank=p?.rank||x.rank;
            return `<div class="access-code-row"><div><b>${esc(pseudo)}</b><small>${rank} · ${esc(x.reason||'Nouveau code')}</small></div><div class="access-pin">${x.pin}</div><button class="icon-mini" onclick="W.copyText('${x.pin}')">📋</button></div>`;
        }).join('')}</div>`;
    }

    const BUILTIN_GAME_LINKS=[{
        id:'season6-guide',icon:'📘',title:'Guide Saison 6',
        description:'Guide complet WfGg en français et italien',
        url:'help/saison6/index.html',builtin:true,enabled:true
    }];
    async function loadPublicGameLinks(){
        try{
            const r=await fetch(API_BASE+'/api/help-links',{cache:'no-store'}).then(x=>x.ok?x.json():Promise.reject());
            publicGameLinks=Array.isArray(r.links)?r.links:[];
        }catch(e){
            publicGameLinks=(state.gameLinks||[]).filter(x=>x&&x.enabled);
        }
        return publicGameLinks;
    }
    function portalHelpLinks(){
        return [...BUILTIN_GAME_LINKS,...publicGameLinks.filter(x=>x&&x.enabled)];
    }
    function renderPortalHelp(){
        const grid=document.getElementById('portalHelpGrid');
        if(!grid)return;
        const links=portalHelpLinks();
        grid.innerHTML=links.map(x=>`<button class="public-help-tile ${x.builtin?'featured':''}" onclick="W.openPortalResource('${esc(x.url)}',${x.builtin?'true':'false'})">
          <span class="public-help-icon">${x.builtin?`<img src="assets/icon-192.png" alt="">`:esc(x.icon||'🔗')}</span>
          <b>${esc(x.title)}</b>
          <small>${esc(x.description||x.url)}</small><i>→</i>
        </button>`).join('')||'<div class="empty">Aucune ressource supplémentaire pour le moment.</div>';
        queueApplyLanguage();
    }
    async function showPortalHelp(){
        document.getElementById('portalView')?.classList.add('hidden');
        document.getElementById('appView')?.classList.add('hidden');
        document.getElementById('portalHelpView')?.classList.remove('hidden');
        await loadPublicGameLinks();
        renderPortalHelp();
        window.scrollTo({top:0,behavior:'smooth'});
    }
    function openPortalResource(url,builtin=false){
        if(builtin){
            location.href='/help/saison6/index.html';
            return;
        }
        if(/^https:\/\//i.test(url))window.open(url,'_blank','noopener,noreferrer');
    }

    function effectiveGameLinks(){
        return [...BUILTIN_GAME_LINKS,...(state.gameLinks||[]).filter(x=>x&&x.enabled)];
    }
    function renderGameHelp(){
        const el=document.getElementById('helpScreen');
        if(!el)return;
        const links=effectiveGameLinks();
        const extras=links.filter(x=>!x.builtin);
        el.innerHTML=`<div class="section-title help-screen-title"><h2>🎓 Aide au jeu</h2><p>Ressources de l’alliance</p></div>
          <p class="help-screen-intro">Ouvre un guide ou un outil en touchant son icône.</p>
          <div class="public-help-grid">
            ${links.map(x=>`<button class="public-help-tile ${x.builtin?'featured':''}" onclick="W.openGameLink('${esc(x.url)}')">
              <span class="public-help-icon">${x.builtin?`<img src="assets/icon-192.png" alt="">`:esc(x.icon||'🔗')}</span>
              <b>${esc(x.title)}</b>
              <small>${esc(x.description||x.url)}</small>
              <i>↗</i>
            </button>`).join('')}
          </div>
          ${extras.length?'':`<div class="help-empty-note">Aucune ressource supplémentaire pour le moment.</div>`}`;
        queueApplyLanguage();
    }
    function openGameHelp(){
        showScreen('helpScreen');
    }
    function openGameLink(url){
        if(!url)return;
        window.open(url,'_blank','noopener,noreferrer');
    }
    function resetGameLinksDraft(){
        gameLinksDraft=(state.gameLinks||[]).map(x=>({...x}));
    }
    function gameLinkRows(){
        if(gameLinksDraft===null)resetGameLinksDraft();
        if(!gameLinksDraft.length)return '<div class="empty compact-empty">Aucun lien supplémentaire.</div>';
        return `<div class="game-link-admin-list">${gameLinksDraft.map((x,i)=>`<div class="game-link-admin-row">
          <div class="game-link-fields">
            <div class="game-link-short"><label class="field-label">Icône</label><input id="gl-icon-${i}" value="${esc(x.icon||'🔗')}" maxlength="16"></div>
            <div><label class="field-label">Titre</label><input id="gl-title-${i}" value="${esc(x.title||'')}"></div>
          </div>
          <label class="field-label">Adresse https://…</label><input id="gl-url-${i}" type="url" value="${esc(x.url||'')}" placeholder="https://…">
          <label class="checkline game-link-visible"><input id="gl-enabled-${i}" type="checkbox" ${x.enabled!==false?'checked':''}><span>Visible</span></label>
          <button class="btn danger small" onclick="W.removeGameLinkDraft(${i})">🗑️ Supprimer ce lien</button>
        </div>`).join('')}</div>`;
    }
    function addGameLinkDraft(){
        if(gameLinksDraft===null)resetGameLinksDraft();
        if(gameLinksDraft.length>=20)return toast('Maximum 20 liens');
        gameLinksDraft.push({id:'link_'+Date.now()+'_'+Math.random().toString(36).slice(2,7),icon:'🔗',title:'',url:'https://',enabled:true});
        openAdminSection('help');
    }
    function removeGameLinkDraft(i){
        if(gameLinksDraft===null)resetGameLinksDraft();
        gameLinksDraft.splice(i,1);openAdminSection('help');
    }
    async function saveGameLinks(){
        if(gameLinksDraft===null)resetGameLinksDraft();
        const links=gameLinksDraft.map((x,i)=>({
            id:x.id,
            icon:(document.getElementById(`gl-icon-${i}`)?.value||'🔗').trim()||'🔗',
            title:(document.getElementById(`gl-title-${i}`)?.value||'').trim(),
            url:(document.getElementById(`gl-url-${i}`)?.value||'').trim(),
            enabled:!!document.getElementById(`gl-enabled-${i}`)?.checked
        }));
        if(links.some(x=>!x.title))return toast('Titre obligatoire');
        if(links.some(x=>!/^https:\/\//i.test(x.url)))return toast('Chaque lien doit commencer par https://');
        try{
            await api('/api/admin/game-links',{method:'PUT',body:JSON.stringify({links})});
            gameLinksDraft=null;
            await syncSnapshot({render:false,quiet:true});
            openAdminSection('help');toast('Liens mis à jour');
        }catch(e){toast(e.message);}
    }
    const AUDIT_LABELS={
      'profile.update':'Profil modifié','preferences.update':'Préférences joueur','pin.change':'Code personnel modifié',
      'exchange.publish':'Échange publié','exchange.cancel':'Échange retiré','exchange.accept':'Échange accepté',
      'admin.settings':'Paramètres du train modifiés','admin.rotation-ranks':'Rangs des rotations modifiés',
      'admin.rotation-order':'Ordre de rotation modifié','admin.override.set':'Planning manuel modifié',
      'admin.override.clear':'Retour au planning automatique','admin.member.add':'Joueur ajouté',
      'admin.member.update':'Joueur modifié','admin.member.delete':'Joueur supprimé',
      'admin.member.preferences':'Rotation d’un joueur modifiée','admin.pin.reset':'Code joueur réinitialisé',
      'admin.game-links':'Liens d’aide modifiés','login':'Connexion','bootstrap':'Initialisation'
    };
    function auditCategory(action){
      if(action.startsWith('exchange.'))return 'exchanges';
      if(action==='profile.update'||action==='preferences.update'||action==='pin.change')return 'players';
      if(action.startsWith('admin.member.')||action==='admin.pin.reset')return 'members';
      if(action.startsWith('admin.settings')||action.startsWith('admin.rotation')||action.startsWith('admin.override')||action==='admin.game-links')return 'settings';
      if(action==='login'||action==='bootstrap')return 'security';
      return 'other';
    }
    function auditLabel(action){return AUDIT_LABELS[action]||action;}
    function auditDetails(e){
      const p=e.payload||{},a=e.action;
      if(a==='profile.update'){
        const rename=p.previousPseudo&&p.pseudo&&p.previousPseudo!==p.pseudo?`${p.previousPseudo} → ${p.pseudo}`:(p.pseudo||'');
        return [rename,p.avatarChanged?'photo modifiée':''].filter(Boolean).join(' · ')||'Profil';
      }
      if(a==='preferences.update'){
        const v=p.values||{},bits=[];
        if('outRotation' in v)bits.push(v.outRotation?'hors rotation':'rotation active');
        if(v.language)bits.push(`langue ${v.language.toUpperCase()}`);
        if(Array.isArray(v.unavailable))bits.push(`${v.unavailable.length} indisponibilité(s)`);
        if('alertsEnabled' in v)bits.push(v.alertsEnabled?'alertes ON':'alertes OFF');
        return bits.join(' · ')||(p.fields||[]).join(', ');
      }
      if(a==='exchange.publish')return `${p.date||''} · ${p.roleKey||''}`;
      if(a==='exchange.accept')return `${p.fromDate||''} ↔ ${p.myDate||''}`;
      if(a==='exchange.cancel')return `#${p.id||''}`;
      if(a==='admin.settings')return p.after?`Train ${p.after.trainTime||''} · ancrage ${p.after.anchorDate||''}`:'Paramètres';
      if(a==='admin.rotation-ranks')return p.after?`A ${p.after.officer?.join('+')||''} · B ${p.after.r3driver?.join('+')||''} · VIP ${p.after.vip?.join('+')||''}`:'Rotations';
      if(a==='admin.rotation-order')return `${p.key||''}`;
      if(a==='admin.override.set')return `${p.date||''} · conducteur ${byId[p.driverId]?.pseudo||p.driverId||'—'} · VIP ${byId[p.vipId]?.pseudo||p.vipId||'—'}`;
      if(a==='admin.override.clear')return p.date||'';
      if(a==='admin.member.add'||a==='admin.member.update')return `${p.pseudo||byId[p.id]?.pseudo||p.id||''}${p.rank?' · '+p.rank:''}`;
      if(a==='admin.member.delete'||a==='admin.member.preferences'||a==='admin.pin.reset')return `${byId[p.id]?.pseudo||p.id||''}`;
      if(a==='admin.game-links')return `${(p.after||[]).length} lien(s)`;
      if(a==='pin.change')return 'Code personnel';
      if(a==='login')return p.mode||'';
      return Object.keys(p).length?JSON.stringify(p):'';
    }
    function rotationStatsList(list){
      if(!list?.length)return '<div class="empty compact-empty">—</div>';
      const max=Math.max(1,...list.map(x=>x.count||0));
      return `<div class="rotation-stats-list">${list.map(x=>`<div class="rotation-stat-row">
        <div><b>${esc(x.pseudo)}</b><small>${x.rank}</small></div>
        <div class="rotation-stat-bar"><span style="width:${Math.max(5,Math.round((x.count/max)*100))}%"></span></div><strong>${x.count}</strong>
      </div>`).join('')}</div>`;
    }
    function analyticsBackButton(){
      return `<button class="admin-back" onclick="W.renderAnalyticsMenu()">← Retour aux statistiques</button>`;
    }
    function analyticsIconMenu(){
      return `<div class="analytics-icon-menu">
        <button class="analytics-icon-card rotations" onclick="W.openAnalyticsSub('rotations')"><span>🔁</span><b>Rotations</b><small>Répartition Conducteur A, Conducteur B et VIP</small><i>→</i></button>
        <button class="analytics-icon-card train-history" onclick="W.openAnalyticsSub('trainhistory')"><span>📚</span><b>Historique du train</b><small>Passages effectués avant l’application</small><i>→</i></button>
      </div>`;
    }
    function renderAnalyticsMenu(){
      if(!adminAnalyticsCache)return openAdminAnalytics();
      analyticsCurrentSub=null;
      const el=document.getElementById('adminScreen'),s=adminAnalyticsCache.summary||{};
      el.innerHTML=`${adminBackButton()}
        <div class="section-title"><h2>📊 Statistiques du train</h2><p>Tableau de contrôle</p></div>
        ${analyticsIconMenu()}
        <div class="analytics-quick-kpis">
          <div><span>🚂</span><small>Trains historiques</small><strong>${adminAnalyticsCache.manualHistory?.eventCount||0}</strong></div>
          <div><span>⚖️</span><small>Écart Conducteur A</small><strong>${adminAnalyticsCache.rotation30?.spread?.officer??0}</strong></div>
          <div><span>⭐</span><small>Écart VIP</small><strong>${adminAnalyticsCache.rotation30?.spread?.vip??0}</strong></div>
          <div><span>✍️</span><small>Planning manuel</small><strong>${s.manualOverrides||0}</strong></div>
        </div>`;
      window.scrollTo({top:0,behavior:'smooth'});queueApplyLanguage();
    }
    function openAnalyticsSub(section){
      if(!adminAnalyticsCache)return openAdminAnalytics();
      analyticsCurrentSub=section;
      if(section==='overview')return renderAnalyticsOverview();
      if(section==='rotations')return renderAnalyticsRotations();
      if(section==='activity')return renderAnalyticsActivity();
      if(section==='settings')return renderAnalyticsSettings();
      if(section==='history')return renderAnalyticsHistoryScreen();
      if(section==='trainhistory')return renderTrainHistory();
    }
    function renderAnalyticsOverview(){
      const d=adminAnalyticsCache,s=d.summary||{},r30=d.rotation30||{};
      const el=document.getElementById('adminScreen');
      el.innerHTML=`${analyticsBackButton()}
        <div class="section-title"><h2>📈 Vue d’ensemble</h2><p>30 derniers jours</p></div>
        <div class="overview-icon-grid">
          <div class="overview-icon-card"><span>7️⃣</span><small>Actions sur 7 jours</small><strong>${s.actions7||0}</strong></div>
          <div class="overview-icon-card"><span>3️⃣0️⃣</span><small>Actions sur 30 jours</small><strong>${s.actions30||0}</strong></div>
          <div class="overview-icon-card"><span>👥</span><small>Joueurs actifs</small><strong>${s.activeMembers||0}</strong></div>
          <div class="overview-icon-card"><span>⏸️</span><small>Hors rotation</small><strong>${s.outRotation||0}</strong></div>
          <div class="overview-icon-card"><span>🚫</span><small>Indisponibilités</small><strong>${s.unavailablePlayers||0}</strong></div>
          <div class="overview-icon-card"><span>🔄</span><small>Échanges ouverts</small><strong>${s.openExchanges||0}</strong></div>
          <div class="overview-icon-card"><span>✍️</span><small>Planning manuel</small><strong>${s.manualOverrides||0}</strong></div>
          <div class="overview-icon-card"><span>⚖️</span><small>Écart VIP</small><strong>${r30.spread?.vip??0}</strong></div>
        </div>
        <button class="btn outline full analytics-refresh" onclick="W.openAdminAnalytics(true)">↻ Actualiser</button>`;
      queueApplyLanguage();window.scrollTo({top:0,behavior:'smooth'});
    }
    function analyticsPlayerCards(list,valueLabel='passages',breakdown=false){
      if(!list?.length)return '<div class="empty">Aucune modification sur cette période.</div>';
      return `<div class="analytics-player-grid">${list.map(x=>{
        const p=byId[x.id]||x;
        const extra=breakdown?`<div class="player-breakdown"><span>👤 ${x.players||0}</span><span>🔄 ${x.exchanges||0}</span><span>👥 ${x.members||0}</span><span>⚙️ ${x.settings||0}</span></div>`:'';
        return `<div class="analytics-player-card">${avatar(p,'xs')}<div class="analytics-player-meta"><b>${esc(x.pseudo||p.pseudo||'—')}</b><small>${x.rank||p.rank||''}</small></div><strong>${x.count??x.total??0}</strong><em>${valueLabel}</em>${extra}</div>`;
      }).join('')}</div>`;
    }
    function sortRotationList(list){
      const a=[...(list||[])];
      if(analyticsRotationSort==='count-asc')a.sort((x,y)=>(x.count||0)-(y.count||0)||x.pseudo.localeCompare(y.pseudo));
      else if(analyticsRotationSort==='alpha')a.sort((x,y)=>x.pseudo.localeCompare(y.pseudo));
      else a.sort((x,y)=>(y.count||0)-(x.count||0)||x.pseudo.localeCompare(y.pseudo));
      return a;
    }
    function setAnalyticsRotationDays(days){analyticsRotationDays=Number(days)||30;renderAnalyticsRotations();}
    function setAnalyticsRotationPool(pool){analyticsRotationPool=pool;renderAnalyticsRotations();}
    function setAnalyticsRotationSort(sort){analyticsRotationSort=sort;renderAnalyticsRotations();}
    function renderAnalyticsRotations(){
      const d=adminAnalyticsCache,rot=analyticsRotationDays===90?d.rotation90:d.rotation30;
      const pools={
        officer:{icon:'🚂',title:'Conducteur A',list:rot?.officer||[],spread:rot?.spread?.officer??0},
        r3driver:{icon:'🚆',title:'Conducteur B',list:rot?.r3driver||[],spread:rot?.spread?.r3driver??0},
        vip:{icon:'⭐',title:'VIP',list:rot?.vip||[],spread:rot?.spread?.vip??0}
      };
      const p=pools[analyticsRotationPool]||pools.officer;
      const list=sortRotationList(p.list);
      const el=document.getElementById('adminScreen');
      el.innerHTML=`${analyticsBackButton()}
        <div class="section-title"><h2>🔁 Rotations</h2><p>${analyticsRotationDays} jours</p></div>
        <div class="analytics-period-switch">
          <button class="chip ${analyticsRotationDays===30?'active':''}" onclick="W.setAnalyticsRotationDays(30)">30 prochains jours</button>
          <button class="chip ${analyticsRotationDays===90?'active':''}" onclick="W.setAnalyticsRotationDays(90)">90 prochains jours</button>
        </div>
        <div class="analytics-group-icons">
          ${Object.entries(pools).map(([key,x])=>`<button class="analytics-group-icon ${analyticsRotationPool===key?'active':''}" onclick="W.setAnalyticsRotationPool('${key}')"><span>${x.icon}</span><b>${x.title}</b><small>Écart ${x.spread}</small></button>`).join('')}
        </div>
        <div class="analytics-sort-row"><label>Trier</label><select onchange="W.setAnalyticsRotationSort(this.value)">
          <option value="count-desc" ${analyticsRotationSort==='count-desc'?'selected':''}>Plus de passages</option>
          <option value="count-asc" ${analyticsRotationSort==='count-asc'?'selected':''}>Moins de passages</option>
          <option value="alpha" ${analyticsRotationSort==='alpha'?'selected':''}>Pseudo A-Z</option>
        </select></div>
        <div class="analytics-selected-title"><span>${p.icon}</span><div><b>${p.title}</b><small>Écart ${p.spread}</small></div></div>
        ${analyticsPlayerCards(list,'passages')}
      `;
      queueApplyLanguage();window.scrollTo({top:0,behavior:'smooth'});
    }
    function sortActivity(list){
      const a=[...(list||[])];
      const q=analyticsSearch.trim().toLowerCase();
      let r=q?a.filter(x=>(x.pseudo||'').toLowerCase().includes(q)):a;
      if(analyticsActivitySort==='total-asc')r.sort((x,y)=>(x.total||0)-(y.total||0)||x.pseudo.localeCompare(y.pseudo));
      else if(analyticsActivitySort==='alpha')r.sort((x,y)=>x.pseudo.localeCompare(y.pseudo));
      else r.sort((x,y)=>(y.total||0)-(x.total||0)||x.pseudo.localeCompare(y.pseudo));
      return r;
    }
    function setAnalyticsActivitySort(sort){analyticsActivitySort=sort;renderAnalyticsActivity();}
    function setAnalyticsSearch(q){analyticsSearch=q; if(analyticsCurrentSub==='activity')renderAnalyticsActivity(); else if(analyticsCurrentSub==='history')renderAnalyticsHistoryScreen();}
    function renderAnalyticsActivity(){
      const list=sortActivity(adminAnalyticsCache.activityByActor||[]);
      const el=document.getElementById('adminScreen');
      el.innerHTML=`${analyticsBackButton()}
        <div class="section-title"><h2>👥 Activité joueurs</h2><p>30 derniers jours</p></div>
        <div class="analytics-toolbar">
          <input class="admin-search" value="${esc(analyticsSearch)}" placeholder="🔎 Rechercher un joueur…" oninput="W.setAnalyticsSearch(this.value)">
          <select onchange="W.setAnalyticsActivitySort(this.value)">
            <option value="total-desc" ${analyticsActivitySort==='total-desc'?'selected':''}>Plus actifs</option>
            <option value="total-asc" ${analyticsActivitySort==='total-asc'?'selected':''}>Moins actifs</option>
            <option value="alpha" ${analyticsActivitySort==='alpha'?'selected':''}>Pseudo A-Z</option>
          </select>
        </div>
        ${analyticsPlayerCards(list,'actions',true)}`;
      queueApplyLanguage();window.scrollTo({top:0,behavior:'smooth'});
    }
    function settingsCategory(action){
      if(action==='admin.settings')return 'train';
      if(action==='admin.rotation-ranks'||action==='admin.rotation-order')return 'rotations';
      if(action.startsWith('admin.override'))return 'planning';
      if(action.startsWith('admin.member.')||action==='admin.pin.reset')return 'members';
      if(action==='admin.game-links')return 'help';
      return 'other';
    }
    function setAnalyticsSettingsFilter(filter){analyticsSettingsFilter=filter;renderAnalyticsSettings();}
    function renderAnalyticsSettings(){
      const groups=[
        ['all','📚','Toutes les actions'],
        ['train','🚂','Train'],
        ['rotations','🔁','Rotations'],
        ['planning','✍️','Planning'],
        ['members','👥','Membres'],
        ['help','🎓','Liens d’aide']
      ];
      let entries=(adminAnalyticsCache.entries||[]).filter(e=>['settings','members'].includes(auditCategory(e.action)));
      if(analyticsSettingsFilter!=='all')entries=entries.filter(e=>settingsCategory(e.action)===analyticsSettingsFilter);
      const el=document.getElementById('adminScreen');
      el.innerHTML=`${analyticsBackButton()}
        <div class="section-title"><h2>⚙️ Paramétrage</h2><p>Historique administratif</p></div>
        <div class="analytics-group-icons compact">${groups.map(g=>`<button class="analytics-group-icon ${analyticsSettingsFilter===g[0]?'active':''}" onclick="W.setAnalyticsSettingsFilter('${g[0]}')"><span>${g[1]}</span><b>${g[2]}</b></button>`).join('')}</div>
        <div class="analytics-event-grid">${entries.slice(0,120).map(e=>analyticsEventCard(e)).join('')||'<div class="empty">Aucune modification sur cette période.</div>'}</div>`;
      queueApplyLanguage();window.scrollTo({top:0,behavior:'smooth'});
    }
    function analyticsEventCard(e){
      const icons={players:'👤',exchanges:'🔄',members:'👥',settings:'⚙️',security:'🔐',other:'📝'};
      return `<div class="analytics-event-card"><span class="event-icon">${icons[auditCategory(e.action)]||'📝'}</span><div><div class="event-head"><b>${esc(e.actor||'Système')}</b><small>${e.actor_rank||''}</small></div><strong>${auditLabel(e.action)}</strong><p>${esc(auditDetails(e))}</p><time>${new Date(e.created_at).toLocaleString(currentLocale())}</time></div></div>`;
    }
    function setAnalyticsFilter(filter){analyticsFilter=filter;renderAnalyticsHistoryScreen();}
    function setAnalyticsHistorySort(sort){analyticsHistorySort=sort;renderAnalyticsHistoryScreen();}
    function renderAnalyticsHistoryScreen(){
      const filters=[
        ['all','📚','Tous'],['players','👤','Joueurs'],['exchanges','🔄','Échanges'],
        ['members','👥','Admin joueurs'],['settings','⚙️','Paramètres'],['security','🔐','Sécurité']
      ];
      let entries=[...(adminAnalyticsCache.entries||[])];
      if(analyticsFilter!=='all')entries=entries.filter(e=>auditCategory(e.action)===analyticsFilter);
      const q=analyticsSearch.trim().toLowerCase();
      if(q)entries=entries.filter(e=>(e.actor||'Système').toLowerCase().includes(q)||auditDetails(e).toLowerCase().includes(q)||auditLabel(e.action).toLowerCase().includes(q));
      entries.sort((a,b)=>analyticsHistorySort==='oldest'?new Date(a.created_at)-new Date(b.created_at):new Date(b.created_at)-new Date(a.created_at));
      const el=document.getElementById('adminScreen');
      el.innerHTML=`${analyticsBackButton()}
        <div class="section-title"><h2>🧾 Historique complet</h2><p>${entries.length} actions</p></div>
        <div class="analytics-group-icons compact history-groups">${filters.map(g=>`<button class="analytics-group-icon ${analyticsFilter===g[0]?'active':''}" onclick="W.setAnalyticsFilter('${g[0]}')"><span>${g[1]}</span><b>${g[2]}</b></button>`).join('')}</div>
        <div class="analytics-toolbar">
          <input class="admin-search" value="${esc(analyticsSearch)}" placeholder="🔎 Rechercher un joueur…" oninput="W.setAnalyticsSearch(this.value)">
          <select onchange="W.setAnalyticsHistorySort(this.value)">
            <option value="newest" ${analyticsHistorySort==='newest'?'selected':''}>Plus récents</option>
            <option value="oldest" ${analyticsHistorySort==='oldest'?'selected':''}>Plus anciens</option>
          </select>
        </div>
        <div class="analytics-event-grid">${entries.slice(0,250).map(e=>analyticsEventCard(e)).join('')||'<div class="empty">Aucune modification sur cette période.</div>'}</div>
        <div class="warning">Les nouveaux journaux V1.3 enregistrent davantage de détails ; les anciennes entrées restent disponibles avec les informations qui existaient déjà.</div>`;
      queueApplyLanguage();window.scrollTo({top:0,behavior:'smooth'});
    }
    function historyDate(ds){
      if(!ds)return '—';
      try{return new Date(ds+'T12:00:00').toLocaleDateString(currentLocale(),{day:'2-digit',month:'2-digit',year:'numeric'});}catch(e){return ds;}
    }
    function historyCountCards(list,role){
      const key=role==='driver'?'driver':'vip',lastKey=role==='driver'?'driverLast':'vipLast';
      const rows=[...(list||[])].sort((a,b)=>(b[key]||0)-(a[key]||0)||a.pseudo.localeCompare(b.pseudo));
      return `<div class="history-count-grid">${rows.map(x=>`<div class="history-count-card">
        ${avatar(byId[x.id]||x,'xs')}
        <div><b>${esc(x.pseudo)}</b><small>${x.rank||''} · Dernier passage : ${historyDate(x[lastKey])}</small></div>
        <strong>${x[key]||0}</strong>
      </div>`).join('')}</div>`;
    }
    function renderTrainHistory(){
      const d=adminAnalyticsCache||{},h=d.manualHistory||{},active=d.historyActive||[];
      const former=h.former||[],applied=h.correctionsApplied||[],reviews=h.reviewSuggestions||{},missing=h.missingReference||[],extra=h.extraApp||[];
      const el=document.getElementById('adminScreen');
      el.innerHTML=`${analyticsBackButton()}
        <div class="section-title"><h2>📚 Historique du train</h2><p>Historique manuel importé</p></div>
        <div class="history-import-kpis">
          <div><span>🚂</span><small>Trains compilés</small><strong>${h.eventCount||0}</strong></div>
          <div><span>🚆</span><small>Conducteurs</small><strong>${h.eventCount||0}</strong></div>
          <div><span>⭐</span><small>VIP</small><strong>${h.eventCount||0}</strong></div>
          <div><span>📅</span><small>Jusqu’au</small><strong>${historyDate(h.cutoff)}</strong></div>
        </div>
        <div class="success history-import-ok">✅ La rotation automatique tient maintenant compte de ces passages.</div>
        <div class="admin-panel">
          <div class="history-role-switch">
            <button class="chip active" onclick="document.getElementById('historyDriverBox').classList.remove('hidden');document.getElementById('historyVipBox').classList.add('hidden');this.parentNode.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));this.classList.add('active')">🚆 Passages conducteur</button>
            <button class="chip" onclick="document.getElementById('historyVipBox').classList.remove('hidden');document.getElementById('historyDriverBox').classList.add('hidden');this.parentNode.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));this.classList.add('active')">⭐ Passages VIP</button>
          </div>
          <h3>👥 Compteurs historiques des membres actuels</h3>
          <div id="historyDriverBox">${historyCountCards(active,'driver')}</div>
          <div id="historyVipBox" class="hidden">${historyCountCards(active,'vip')}</div>
        </div>
        <div class="admin-panel">
          <h3>🕰️ Anciens joueurs</h3><p class="admin-lead">Conservés uniquement dans l’historique</p>
          ${former.length?`<div class="former-history-list">${former.map(x=>`<div><b>${esc(x.pseudo)}</b><span>🚆 ${x.driver||0} · ⭐ ${x.vip||0}</span></div>`).join('')}</div>`:'<div class="empty">—</div>'}
        </div>
        <div class="admin-panel">
          <h3>🔤 Corrections de pseudos</h3>
          <p class="admin-lead">Corrections appliquées automatiquement</p>
          ${applied.length?`<div class="pseudo-correction-list">${applied.map(x=>`<div><span>${esc(x.old)}</span><i>→</i><b>${esc(x.new)}</b></div>`).join('')}</div>`:'<div class="empty compact-empty">Aucune correction restante à appliquer.</div>'}
          ${Object.keys(reviews).length?`<details class="history-review"><summary>⚠️ À vérifier</summary><div class="pseudo-correction-list review">${Object.entries(reviews).map(([a,b])=>`<div><span>${esc(a)}</span><i>?</i><b>${esc(b)}</b></div>`).join('')}</div></details>`:''}
        </div>
        <div class="admin-panel">
          <h3>🔎 Comparaison avec le fichier de référence</h3>
          <p class="admin-lead">Membres du fichier absents de l’application</p>
          ${missing.length?`<div class="history-name-chips">${missing.map(x=>`<span>${esc(x.pseudo)} · ${x.rank}</span>`).join('')}</div>`:'<div class="success">✅ Aucun</div>'}
          <p class="admin-lead" style="margin-top:14px">Membres de l’application absents du fichier</p>
          ${extra.length?`<div class="history-name-chips warning-chips">${extra.map(x=>`<span>${esc(x.pseudo)} · ${x.rank}</span>`).join('')}</div>`:'<div class="success">✅ Aucun</div>'}
        </div>
        <div class="history-source-note">📄 Source : historique manuel WfGg · ${esc(h.source||'Train Wfgg')}</div>`;
      queueApplyLanguage();window.scrollTo({top:0,behavior:'smooth'});
    }

    async function openAdminAnalytics(force=false){
      if(!isAdmin())return;
      currentAdminSection='analytics';
      analyticsCurrentSub=null;
      const el=document.getElementById('adminScreen');
      el.innerHTML=`${adminBackButton()}<div class="section-title"><h2>📊 Statistiques du train</h2></div><div class="empty">Synchronisation…</div>`;
      try{
        if(force||!adminAnalyticsCache)adminAnalyticsCache=await api('/api/admin/analytics',{method:'GET'});
        renderAnalyticsMenu();
      }catch(e){el.innerHTML=`${adminBackButton()}<div class="empty">${esc(e.message)}</div>`;}
    }

    refreshRoster();
    function cloneDefault() { return JSON.parse(JSON.stringify(DEFAULT_STATE)); }
    function loadState() {
        let raw = localStorage.getItem(STORAGE);
        if (!raw) {
            for (const key of LEGACY_KEYS) {
                if (localStorage.getItem(key)) {
                    raw = localStorage.getItem(key);
                    break;
                }
            }
        }
        let parsed = {};
        try {
            parsed = raw ? JSON.parse(raw) : {};
        }
        catch (e) {
            parsed = {};
        }
        const base = cloneDefault();
        return Object.assign(Object.assign(Object.assign({}, base), parsed), { settings: Object.assign(Object.assign(Object.assign({}, base.settings), (parsed.settings || {})), { rotationRanks: Object.assign(Object.assign({}, base.settings.rotationRanks), ((parsed.settings || {}).rotationRanks || {})) }), unavailable: parsed.unavailable || {}, outRotation: parsed.outRotation || [], overrides: parsed.overrides || {}, exchanges: parsed.exchanges || [], alertsEnabled: parsed.alertsEnabled || {}, languages: parsed.languages || {}, gameLinks: parsed.gameLinks || [], playerEdits: parsed.playerEdits || {}, addedPlayers: parsed.addedPlayers || [], removedPlayers: parsed.removedPlayers || [], rotationOrder: Object.assign(Object.assign({}, base.rotationOrder), (parsed.rotationOrder || {})), messageVariant: Object.assign(Object.assign({}, base.messageVariant), (parsed.messageVariant || {})) });
    }
    function saveState() { localStorage.setItem(STORAGE, JSON.stringify(state)); }
    

    function setSyncStatus(kind = 'ok') {
        const b = document.getElementById('syncBadge');
        if (!b)
            return;
        b.classList.remove('sync-ok', 'sync-work', 'sync-off');
        b.classList.add(kind === 'work' ? 'sync-work' : kind === 'off' ? 'sync-off' : 'sync-ok');
        b.title = kind === 'work' ? 'Synchronisation…' : kind === 'off' ? 'Hors connexion' : 'Synchronisé';
    }
    async function api(path, options = {}) {
        var _a, _b;
        const headers = Object.assign({ 'content-type': 'application/json' }, (options.headers || {}));

        setSyncStatus('work');
        let res;
        try {
            res = await fetch(API_BASE + path, Object.assign(Object.assign({}, options), { headers }));
        }
        catch (e) {
            setSyncStatus('off');
            throw new Error('Réseau indisponible');
        }
        let data = {};
        try {
            data = await res.json();
        }
        catch (e) { }
        if (res.status === 401) {

            state.currentUserId = null;
            saveState();
            setSyncStatus('off');
            (_a = document.getElementById('appView')) === null || _a === void 0 ? void 0 : _a.classList.add('hidden');
            throw new Error(data.error || 'Session expirée');
        }
        if (!res.ok) {
            setSyncStatus('off');
            throw new Error(data.error || `Erreur ${res.status}`);
        }
        setSyncStatus('ok');
        return data;
    }
    function applySnapshot(snap) {
        const localVariants = state.messageVariant || { weekly: 0, daily: 0, driver: 0, vip: 0 };
        BASE_ROSTER = snap.roster || [];
        localStorage.setItem(ROSTER_CACHE_KEY, JSON.stringify(BASE_ROSTER));
        state = Object.assign(Object.assign(Object.assign({}, cloneDefault()), (snap.state || {})), { currentUserId: snap.me.id, messageVariant: localVariants, playerEdits: {}, addedPlayers: [], removedPlayers: [] });
        state.__serverSchedule=Array.isArray(snap.schedule)?snap.schedule:[];
        refreshRoster();
        const serverLang=state.languages?.[state.currentUserId];
        if(SUPPORTED_LANGS.includes(serverLang))localStorage.setItem(LANG_KEY,serverLang);
        saveState();
        queueApplyLanguage();
    }
    async function syncSnapshot({ render = true, quiet = false } = {}) {
        var _a;
        if (syncing)
            return false;
        syncing = true;
        try {
            const snap = await api('/api/snapshot', { method: 'GET' });
            applySnapshot(snap);
            if (render && document.getElementById('appView') && !document.getElementById('appView').classList.contains('hidden')) {
                const active = (_a = document.querySelector('.screen.active')) === null || _a === void 0 ? void 0 : _a.id;
                if (active === 'adminScreen' && currentAdminSection)
                    openAdminSection(currentAdminSection);
                else
                    renderAll();
            }
            return true;
        }
        catch (e) {
            if (!quiet)
                toast(e.message);
            return false;
        }
        finally {
            syncing = false;
        }
    }
    async function mutate(path, options = {}, success = 'Modification enregistrée') {
        try {
            await api(path, options);
            const refreshed = await syncSnapshot({ render: true, quiet: true });
            if (!refreshed) throw new Error('Modification enregistrée mais synchronisation impossible');
            if (success)
                toast(success);
            return true;
        }
        catch (e) {
            toast(e.message);
            return false;
        }
    }
    function ensureRotationRankSettings() {
        state.settings = state.settings || {};
        state.settings.rotationRanks = state.settings.rotationRanks || {};
        if (!Array.isArray(state.settings.rotationRanks.officer) || !state.settings.rotationRanks.officer.length)
            state.settings.rotationRanks.officer = ['R5', 'R4'];
        if (!Array.isArray(state.settings.rotationRanks.r3driver) || !state.settings.rotationRanks.r3driver.length)
            state.settings.rotationRanks.r3driver = ['R3'];
        if (!Array.isArray(state.settings.rotationRanks.vip) || !state.settings.rotationRanks.vip.length)
            state.settings.rotationRanks.vip = ['R3', 'R2', 'R1'];
    }
    function ranksForRotation(key) {
        ensureRotationRankSettings();
        return [...state.settings.rotationRanks[key]];
    }
    function rolePoolLabel(key) {
        const names = { officer: 'Conducteur A', r3driver: 'Conducteur B', vip: 'VIP' };
        return `${names[key]} · ${ranksForRotation(key).join('/')}`;
    }
    function roleKeyLabel(key) {
        if (key === 'vip')
            return rolePoolLabel('vip');
        if (key === 'driver-r3')
            return rolePoolLabel('r3driver');
        return rolePoolLabel('officer');
    }
    function rankCheckHtml(key, label) {
        const selected = new Set(ranksForRotation(key));
        return `<div class="rank-config-block">
    <h4>${label}</h4>
    <div class="rank-toggle-grid">${['R5', 'R4', 'R3', 'R2', 'R1'].map(r => `
      <label class="rank-toggle">
        <input type="checkbox" data-rotation-key="${key}" value="${r}" ${selected.has(r) ? 'checked' : ''}>
        <span>${r}</span>
      </label>`).join('')}
    </div>
  </div>`;
    }
    function refreshRoster() {
        const removed = new Set(state.removedPlayers || []);
        const edits = state.playerEdits || {};
        const base = BASE_ROSTER
            .filter(m => !removed.has(m.id))
            .map(m => (Object.assign(Object.assign({}, m), (edits[m.id] || {}))));
        const added = (state.addedPlayers || []).filter(m => !removed.has(m.id));
        ROSTER = [...base, ...added];
        byId = Object.fromEntries(ROSTER.map(m => [m.id, m]));
        normalizeRotationOrders();
        updateLoginList();
    }
    function normalizeRotationOrders() {
        state.rotationOrder = state.rotationOrder || { officer: [], r3driver: [], r3vip: [] };
        ensureRotationRankSettings();
        const eligible = {
            officer: ROSTER.filter(m => ranksForRotation('officer').includes(m.rank) && m.active).map(m => m.id),
            r3driver: ROSTER.filter(m => ranksForRotation('r3driver').includes(m.rank) && m.active).map(m => m.id),
            r3vip: ROSTER.filter(m => ranksForRotation('vip').includes(m.rank) && m.active).map(m => m.id)
        };
        Object.keys(eligible).forEach(key => {
            const allowed = eligible[key];
            const old = (state.rotationOrder[key] || []).filter(id => allowed.includes(id));
            state.rotationOrder[key] = [...old, ...allowed.filter(id => !old.includes(id))];
        });
    }
    function orderedPool(pool, key) {
        const order = state.rotationOrder[key] || [];
        const pos = Object.fromEntries(order.map((id, i) => [id, i]));
        return pool.slice().sort((a, b) => { var _a, _b; return ((_a = pos[a.id]) !== null && _a !== void 0 ? _a : 9999) - ((_b = pos[b.id]) !== null && _b !== void 0 ? _b : 9999) || a.id.localeCompare(b.id); });
    }
    function updateLoginList() {
        const dl = document.getElementById('memberList');
        if (dl)
            dl.innerHTML = ROSTER.filter(x => x.active).map(x => `<option value="${esc(x.pseudo)}">${x.rank}</option>`).join('');
        const note = document.querySelector('.login-note');
        if (note)
            note.textContent = `Connexion par pseudo • ${ROSTER.filter(x => x.active).length} profils actifs`;
    }
    function user() { return byId[state.currentUserId]; }
    function isAdmin(m = user()) { return !!m && ['R5', 'R4'].includes(m.rank); }
    function canSelfManage(m = user()) { return !!m && ['R5', 'R4', 'R3', 'R2'].includes(m.rank); }
    function isOut(id) { return (state.outRotation || []).includes(id); }
    function isUnavailable(id, date) { return (state.unavailable[id] || []).includes(date); }
    function activePool(ranks) { return ROSTER.filter(m => ranks.includes(m.rank) && m.active && !isOut(m.id)); }
    function esc(s) { return String(s !== null && s !== void 0 ? s : '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m])); }
    function uid() { return 'x' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }
    function avatarSrc(m) {
        const src = (m === null || m === void 0 ? void 0 : m.avatar) || 'assets/icon-192.png';
        return src.startsWith('/api/') ? API_BASE + src : src;
    }
    function avatar(m, cls = 'sm') { return `<img class="avatar ${cls}" src="${esc(avatarSrc(m))}" alt="${esc((m === null || m === void 0 ? void 0 : m.pseudo) || 'joueur')}">`; }
    function rankBadge(r) { return `<span class="rank rank-${r}">${r}</span>`; }
    function dateISO(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
    function parseISO(s) { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }
    function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
    function mondayOf(d) { const x = new Date(d); const day = (x.getDay() + 6) % 7; x.setHours(0, 0, 0, 0); return addDays(x, -day); }
    function fmtDate(d, opt = { weekday: 'long', day: 'numeric', month: 'long' }) { return new Intl.DateTimeFormat(currentLocale(), opt).format(d); }
    function fmtShort(d) { return new Intl.DateTimeFormat(currentLocale(), { weekday: 'short', day: 'numeric', month: 'short' }).format(d); }
    function toast(msg) {
        const t = document.getElementById('toast');
        if (!t)
            return;
        t.textContent = translatedString(msg);
        t.classList.add('show');
        setTimeout(() => t.classList.remove('show'), 2300);
    }
    function pickFair(pool, date, history, exclude = []) {
        const filtered = pool.filter(m => !exclude.includes(m.id) && !isUnavailable(m.id, date));
        if (!filtered.length)
            return null;
        const orderIndex = Object.fromEntries(pool.map((m, i) => [m.id, i]));
        return filtered.slice().sort((a, b) => {
            var _a, _b;
            const ha = history[a.id] || { count: 0, last: '0000-00-00' };
            const hb = history[b.id] || { count: 0, last: '0000-00-00' };
            if (ha.count !== hb.count)
                return ha.count - hb.count;
            const lc = ha.last.localeCompare(hb.last);
            if (lc !== 0)
                return lc;
            return ((_a = orderIndex[a.id]) !== null && _a !== void 0 ? _a : 9999) - ((_b = orderIndex[b.id]) !== null && _b !== void 0 ? _b : 9999);
        })[0];
    }
    function touchHistory(history, m, date) {
        if (!m)
            return;
        history[m.id] = history[m.id] || { count: 0, last: '0000-00-00' };
        history[m.id].count++;
        history[m.id].last = date;
    }
    function generateSchedule(days = 260) {
        const anchor = parseISO(state.settings.anchorDate);
        ensureRotationRankSettings();
        const officers = orderedPool(activePool(ranksForRotation('officer')), 'officer');
        const r3Drivers = orderedPool(activePool(ranksForRotation('r3driver')), 'r3driver');
        const r3Vips = orderedPool(activePool(ranksForRotation('vip')), 'r3vip');
        const officerHistory = {}, r3DriverHistory = {}, vipHistory = {};
        const out = [];
        for (let i = 0; i < days; i++) {
            const d = addDays(anchor, i), ds = dateISO(d);
            const officerDay = state.settings.officersFirst ? i % 2 === 0 : i % 2 === 1;
            const driver = officerDay
                ? pickFair(officers, ds, officerHistory, [])
                : pickFair(r3Drivers, ds, r3DriverHistory, []);
            if (officerDay)
                touchHistory(officerHistory, driver, ds);
            else
                touchHistory(r3DriverHistory, driver, ds);
            // VIP : rotation équitable entre R3, R2 et R1.
            // Pas de règle artificielle J+1 : l'équité de comptage suffit.
            // Seule incompatibilité : un joueur ne peut pas être Conducteur et VIP le même jour.
            const vipExclude = driver ? [driver.id] : [];
            const vip = pickFair(r3Vips, ds, vipHistory, vipExclude);
            touchHistory(vipHistory, vip, ds);
            let item = { date: ds, driverId: (driver === null || driver === void 0 ? void 0 : driver.id) || null, vipId: (vip === null || vip === void 0 ? void 0 : vip.id) || null, driverClass: officerDay ? 'officer' : 'r3' };
            if (state.overrides[ds])
                item = Object.assign(Object.assign({}, item), state.overrides[ds]);
            out.push(item);
        }
        return out;
    }
    function schedule() { return Array.isArray(state.__serverSchedule) && state.__serverSchedule.length ? state.__serverSchedule : generateSchedule(); }
    function findAssignment(date) { return schedule().find(x => x.date === date); }
    function roleKey(item, role) { return role === 'vip' ? 'vip' : (item.driverClass === 'officer' ? 'driver-officer' : 'driver-r3'); }
    function myAssignments(id) {
        var _a;
        if (id === void 0) { id = (_a = user()) === null || _a === void 0 ? void 0 : _a.id; }
        if (!id)
            return [];
        const list = [];
        for (const x of schedule()) {
            if (x.driverId === id)
                list.push(Object.assign(Object.assign({}, x), { role: 'driver', roleKey: roleKey(x, 'driver') }));
            if (x.vipId === id)
                list.push(Object.assign(Object.assign({}, x), { role: 'vip', roleKey: 'vip' }));
        }
        return list;
    }
    function upcomingMine(limit = 8) {
        const today = dateISO(new Date());
        return myAssignments().filter(x => x.date >= today).sort((a, b) => a.date.localeCompare(b.date)).slice(0, limit);
    }
    function nextMine() { return upcomingMine(1)[0] || null; }
    function otherOn(item, role) { return role === 'driver' ? byId[item.vipId] : byId[item.driverId]; }
    function countdown(ds) {
        const d = parseISO(ds), [hh, mm] = state.settings.trainTime.split(':').map(Number);
        d.setHours(hh, mm, 0, 0);
        const diff = d - new Date(), days = Math.ceil(diff / 86400000);
        if (days <= 0)
            return 'Aujourd’hui';
        if (days === 1)
            return 'Demain';
        return `Dans ${days} jours`;
    }
    function renderHome() {
        const m = user(), el = document.getElementById('homeScreen');
        if (!m || !el)
            return;
        const next = nextMine(), mine = upcomingMine(6);
        let nextHtml = '';
        if (next) {
            const d = parseISO(next.date), other = otherOn(next, next.role);
            nextHtml = `<div class="next-card">
      <div class="next-top"><div><div class="role-label">${next.role === 'driver' ? '🚂 CONDUCTEUR' : '⭐ VIP'}</div><div class="next-date">${fmtDate(d)}</div><div class="next-meta">Train à ${state.settings.trainTime}${other ? ` · avec ${esc(other.pseudo)}` : ''}</div></div><span class="countdown">${countdown(next.date)}</span></div>
      <div class="actions home-next-actions">
        <button class="btn gold" onclick="W.addCalendar('${next.date}','${next.role}')">📅 Calendrier</button>
        ${canSelfManage() ? `<button class="btn exchange-btn" onclick="W.openExchange('${next.date}','${next.role}')">🔄 Échanger ma place</button><button class="btn outline" onclick="W.markUnavailable('${next.date}')">🚫 Indisponible</button>` : ''}
      </div>
    </div>`;
        }
        else
            nextHtml = '<div class="empty">Aucun passage prévu pour ton rang actuel ou ta rotation.</div>';
        const upcoming = mine.length ? mine.map(x => `<div class="assignment me">${avatar(m, 'xs')}<div class="who"><b>${fmtShort(parseISO(x.date))}</b><small>${state.settings.trainTime}</small></div><div class="assignment-role">${x.role === 'driver' ? 'CONDUCTEUR' : 'VIP'}</div></div>`).join('') : '<div class="empty">Aucun autre passage à venir.</div>';
        el.innerHTML = `<div class="hero-card"><div class="profile-head">${avatar(m)}<div class="profile-name"><h2>${esc(m.pseudo)}</h2><p>${rankBadge(m.rank)} · ${isOut(m.id) ? 'Hors rotation' : 'Disponible'}</p></div></div><button class="btn outline profile-edit-btn" onclick="W.openSelfProfileEdit()">✏️ Modifier mon profil</button></div>
  <div class="section-title"><h2>Ton prochain train</h2><p>${state.settings.trainTime}</p></div>${nextHtml}
  <div class="section-title"><h2>Tes prochains passages</h2><p>${mine.length} affichés</p></div><div class="day-card">${upcoming}</div>
  <div class="section-title"><h2>Mon statut</h2><p>Touche une carte</p></div>
  <div class="mini-grid status-grid">
    <button type="button" class="stat-card stat-button" onclick="W.openProfileInfo()"><small>👤 Profil</small><strong>${m.rank}</strong><em>Pseudo & profil</em></button>
    <button type="button" class="stat-card stat-button" onclick="W.goAlerts()"><small>🔔 Alertes</small><strong>${state.alertsEnabled[m.id] ? 'ON' : 'OFF'}</strong><em>Gérer les rappels</em></button>
    <button type="button" class="stat-card stat-button" onclick="W.showUnavailable()"><small>🚫 Indisponibilités</small><strong>${(state.unavailable[m.id] || []).length}</strong><em>Voir / corriger</em></button>
    <button type="button" class="stat-card stat-button" onclick="W.showRotationStatus()"><small>🔁 Rotation</small><strong>${isOut(m.id) ? 'PAUSE' : 'ACTIVE'}</strong><em>Gérer mon statut</em></button>
  </div>
  `;
    }
    function renderPlanning() {
        const el = document.getElementById('planningScreen'), m = user();
        if (!el || !m)
            return;
        const base = addDays(mondayOf(new Date()), weekOffset * 7), sched = schedule(), today = dateISO(new Date());
        const days = [0, 1, 2, 3, 4, 5, 6].map(i => addDays(base, i));
        el.innerHTML = `<div class="week-head"><button onclick="W.changeWeek(-1)">‹</button><div class="week-label"><strong>${fmtDate(base, { day: 'numeric', month: 'long' })} — ${fmtDate(addDays(base, 6), { day: 'numeric', month: 'long', year: 'numeric' })}</strong><small>Planning hebdomadaire</small></div><button onclick="W.changeWeek(1)">›</button></div>
  <div class="day-list">${days.map(d => {
            const ds = dateISO(d), x = sched.find(z => z.date === ds), driver = x && byId[x.driverId], vip = x && byId[x.vipId], mine = x && (x.driverId === m.id || x.vipId === m.id);
            return `<article class="day-card ${ds === today ? 'today' : ''} ${mine ? 'mine' : ''}"><div class="day-date"><strong>${fmtDate(d)}</strong><span>${state.settings.trainTime}</span></div>
      ${x ? `<div class="assignment ${x.driverId === m.id ? 'me' : ''}">${driver ? avatar(driver, 'xs') : ''}<div class="who"><b>${driver ? esc(driver.pseudo) : 'À définir'}</b><small>${driver ? driver.rank : ''}</small></div><div class="assignment-role">🚂 CONDUCTEUR</div></div>
      <div class="assignment ${x.vipId === m.id ? 'me' : ''}">${vip ? avatar(vip, 'xs') : ''}<div class="who"><b>${vip ? esc(vip.pseudo) : 'À définir'}</b><small>${vip ? vip.rank : ''}</small></div><div class="assignment-role">⭐ VIP</div></div>
      ${mine ? `<div class="actions" style="margin-top:8px"><button class="btn small gold" onclick="W.addCalendar('${ds}','${x.driverId === m.id ? 'driver' : 'vip'}')">📅 Calendrier</button>${canSelfManage() ? `<button class="btn small outline" onclick="W.openExchange('${ds}','${x.driverId === m.id ? 'driver' : 'vip'}')">🔄 Échanger</button>` : ''}</div>` : ''}` : '<div class="empty">Planning non généré pour cette date.</div>'}</article>`;
        }).join('')}</div>`;
    }
    function renderExchanges() {
        const el = document.getElementById('exchangeScreen'), m = user();
        if (!el || !m)
            return;
        const open = state.exchanges.filter(x => x.status === 'open').sort((a, b) => a.fromDate.localeCompare(b.fromDate));
        const compatible = open.filter(x => x.fromId !== m.id && myAssignments(m.id).some(a => a.roleKey === x.roleKey && a.date !== x.fromDate));
        const badge = document.getElementById('exchangeBadge');
        if (badge) {
            badge.textContent = compatible.length;
            badge.classList.toggle('hidden', !compatible.length);
        }
        const mine = state.exchanges.filter(x => x.fromId === m.id).sort((a, b) => b.created.localeCompare(a.created));
        el.innerHTML = `<div class="section-title"><h2>🔄 Bourse aux échanges</h2><p>${open.length} annonce${open.length > 1 ? 's' : ''}</p></div>
  <div class="warning">Tu publies ton passage sans choisir de joueur. Toute personne ayant une date compatible peut proposer son propre passage.</div>
  <div class="section-title"><h2>Annonces ouvertes</h2></div>
  ${open.length ? open.map(x => {
            const p = byId[x.fromId] || {id:x.fromId,pseudo:'Joueur indisponible',rank:'',avatar:'assets/icon-192.png',active:false};
            const compatibleMine = myAssignments(m.id).filter(a => a.roleKey === x.roleKey && a.date !== x.fromDate);
            return `<div class="request-card"><span class="request-status pending">OUVERT</span><h3 class="request-person">${avatar(p, 'xs')}<span>${esc(p.pseudo)}</span></h3><p>Souhaite échanger le <strong>${fmtShort(parseISO(x.fromDate))}</strong>.</p><p>${x.roleKey === 'vip' ? '⭐ ' + roleKeyLabel(x.roleKey) : '🚂 ' + roleKeyLabel(x.roleKey)}</p>
    ${x.fromId === m.id ? `<button class="btn danger small" onclick="W.cancelMarketExchange('${x.id}')">Retirer mon annonce</button>` : (canSelfManage() && compatibleMine.length) ? `<button class="btn success full" onclick="W.pickMyDateForMarket('${x.id}')">Je propose une de mes dates</button>` : '<span class="request-status">Aucune action disponible</span>'}</div>`;
        }).join('') : '<div class="empty">Aucune annonce ouverte pour le moment.</div>'}
  <div class="section-title"><h2>Mes demandes</h2></div>${mine.length ? mine.map(x => `<div class="request-card"><span class="request-status ${x.status === 'open' ? 'pending' : x.status === 'accepted' ? 'accepted' : ''}">${x.status === 'open' ? 'OUVERT' : x.status === 'accepted' ? 'ÉCHANGÉ' : 'FERMÉ'}</span><h3>${fmtShort(parseISO(x.fromDate))}</h3><p>${x.roleKey === 'vip' ? '⭐ ' + roleKeyLabel(x.roleKey) : '🚂 ' + roleKeyLabel(x.roleKey)}</p>${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}${x.status === 'open' ? `<button class="btn danger small" onclick="W.cancelMarketExchange('${x.id}')">Retirer mon annonce</button>` : ''}</div>`).join('') : '<div class="empty">Aucune demande publiée.</div>'}`;
    }
    function renderAlerts() {
        const el = document.getElementById('alertsScreen'), m = user();
        if (!el || !m)
            return;
        const on = !!state.alertsEnabled[m.id];
        el.innerHTML = `<div class="section-title"><h2>🔔 Alertes & calendrier</h2></div>
  <div class="alert-card"><div class="toggle-row"><div><h3>Rappels personnels</h3><p>J-1 puis 30 minutes avant le départ.</p></div><button class="toggle ${on ? 'on' : ''}" onclick="W.toggleAlerts()"><i></i></button></div></div>
  <div class="alert-card"><h3>📅 Ajouter mes prochains passages</h3><p>Crée les événements à ${state.settings.trainTime}, avec alarmes J-1 et 19h30 si le train reste à 20h.</p><button class="btn gold full" onclick="W.addAllCalendar()">Ajouter mes passages au calendrier</button></div>
  <div class="alert-card"><h3>🕗 Heure du train</h3><p>Heure actuelle : <strong>${state.settings.trainTime}</strong>. Elle est modifiable par les R4/R5.</p></div>`;
    }
    function rotationEquityHtml() {
        ensureRotationRankSettings();
        const today = dateISO(new Date()), future = schedule().filter(x => x.date >= today).slice(0, 180);
        function range(ids, key) {
            const c = Object.fromEntries(ids.map(id => [id, 0]));
            future.forEach(x => { const id = x[key]; if (id in c)
                c[id]++; });
            const v = Object.values(c);
            return v.length ? `${Math.min(...v)} à ${Math.max(...v)}` : '—';
        }
        const a = ranksForRotation('officer'), b = ranksForRotation('r3driver'), v = ranksForRotation('vip');
        return `<div class="mini-grid">
    <div class="stat-card"><small>${rolePoolLabel('officer')}</small><strong>${range(activePool(a).map(x => x.id), 'driverId')}</strong></div>
    <div class="stat-card"><small>${rolePoolLabel('r3driver')}</small><strong>${range(activePool(b).map(x => x.id), 'driverId')}</strong></div>
    <div class="stat-card"><small>${rolePoolLabel('vip')}</small><strong>${range(activePool(v).map(x => x.id), 'vipId')}</strong></div>
    <div class="stat-card"><small>Objectif</small><strong>±1 max</strong></div>
  </div>`;
    }
    function rotationOrderRows(key) {
        normalizeRotationOrders();
        const ids = state.rotationOrder[key] || [];
        return `<div class="rotation-order">${ids.map((id, i) => { const p = byId[id]; if (!p)
            return ''; return `<div class="rotation-row"><span class="rotation-pos">${i + 1}</span>${avatar(p, 'xs')}<div><b>${esc(p.pseudo)}</b><small>${p.rank}</small></div><div class="rotation-buttons"><button class="icon-mini" onclick="W.moveRotation('${key}',${i},-1)" ${i === 0 ? 'disabled' : ''}>↑</button><button class="icon-mini" onclick="W.moveRotation('${key}',${i},1)" ${i === ids.length - 1 ? 'disabled' : ''}>↓</button></div></div>`; }).join('')}</div>`;
    }
    function relativeLastSeen(iso){
        const lang=currentLanguage();
        if(!iso){
            return {online:false,text:{
                fr:'Aucune connexion enregistrée',en:'No recorded activity',
                it:'Nessun accesso registrato',es:'Sin conexión registrada'
            }[lang]||'Aucune connexion enregistrée'};
        }
        const t=new Date(iso).getTime(),delta=Math.max(0,Date.now()-t),sec=Math.floor(delta/1000);
        if(sec<=90){
            return {online:true,text:{fr:'En ligne maintenant',en:'Online now',it:'Online adesso',es:'En línea ahora'}[lang]||'En ligne maintenant'};
        }
        const min=Math.floor(sec/60),hour=Math.floor(min/60),day=Math.floor(hour/24),month=Math.floor(day/30),year=Math.floor(day/365);
        let text;
        if(min<60){
            text=lang==='en'?`${min} min ago`:lang==='it'?`${min} min fa`:lang==='es'?`hace ${min} min`:`il y a ${min} min`;
        }else if(hour<24){
            text=lang==='en'?`${hour} h ago`:lang==='it'?`${hour} h fa`:lang==='es'?`hace ${hour} h`:`il y a ${hour} h`;
        }else if(day<30){
            text=lang==='en'?`${day} day${day>1?'s':''} ago`:lang==='it'?`${day} giorn${day===1?'o':'i'} fa`:lang==='es'?`hace ${day} día${day>1?'s':''}`:`il y a ${day} jour${day>1?'s':''}`;
        }else if(day<365){
            const n=Math.max(1,month);
            text=lang==='en'?`${n} month${n>1?'s':''} ago`:lang==='it'?`${n} mes${n===1?'e':'i'} fa`:lang==='es'?`hace ${n} mes${n>1?'es':''}`:`il y a ${n} mois`;
        }else{
            const n=Math.max(1,year);
            text=lang==='en'?`${n} year${n>1?'s':''} ago`:lang==='it'?`${n} ann${n===1?'o':'i'} fa`:lang==='es'?`hace ${n} año${n>1?'s':''}`:`il y a ${n} an${n>1?'s':''}`;
        }
        return {online:false,text};
    }
    function memberLastSeenLine(p){
        const x=relativeLastSeen(p.lastSeen);
        const label={fr:'Dernière connexion',en:'Last seen',it:'Ultimo accesso',es:'Última conexión'}[currentLanguage()]||'Dernière connexion';
        const exact=p.lastSeen?new Date(p.lastSeen).toLocaleString(currentLocale()):'';
        if(x.online)return `<small class="member-last-seen online" ${exact?`title="${esc(exact)}"`:''}>🟢 ${x.text}</small>`;
        return `<small class="member-last-seen" ${exact?`title="${esc(exact)}"`:''}>🕒 ${label} · ${x.text}</small>`;
    }

    function memberRows(list) {
        return list.map(p => `<div class="member-row">${avatar(p, 'xs')}<div class="member-row-main"><b>${esc(p.pseudo)}</b><small>${rankBadge(p.rank)} · ${p.active ? 'actif' : 'désactivé'} · ${isOut(p.id) ? 'hors rotation' : 'rotation OK'}</small>${memberLastSeenLine(p)}</div><div class="member-admin-actions"><button class="btn small gold" onclick="W.openMemberForm('${p.id}')">✏️ Modifier</button><button class="btn small ${isOut(p.id) ? 'success' : 'outline'}" onclick="W.adminToggleRotation('${p.id}')">${isOut(p.id) ? 'Réactiver' : 'Pause'}</button></div></div>`).join('');
    }
    async function heartbeatPresence(){

        if(document.visibilityState!=='visible')return;
        try{
            await fetch(API_BASE+'/api/presence/heartbeat',{
              method:'POST',keepalive:true,
              headers:{'content-type':'application/json'},
              body:'{}'
            });
        }catch(e){}
        const active=document.querySelector('.screen.active')?.id;
        if(isAdmin() && active==='adminScreen' && currentAdminSection===null)refreshAdminPresence();
    }
    function startPresenceLoop(){
        clearInterval(presenceTimer);presenceTimer=null;
        
        heartbeatPresence();
        presenceTimer=setInterval(heartbeatPresence,30000);
    }
    async function refreshAdminPresence(){
        if(!isAdmin())return;
        try{
            const r=await api('/api/admin/presence',{method:'GET'});
            adminPresence={count:r.count||0,online:r.online||[],thresholdSeconds:r.thresholdSeconds||90};
            renderAdminPresenceBar();
        }catch(e){}
    }
    function presenceAgo(lastSeen){
        const s=Math.max(0,Math.round((Date.now()-new Date(lastSeen).getTime())/1000));
        return s<15?'maintenant':`il y a ${s} s`;
    }
    function presenceBarHtml(){
        const count=adminPresence.count||0;
        return `<div class="admin-presence-wrap">
          <button class="admin-presence-bar" onclick="W.togglePresenceList()">
            <span class="presence-live-dot"></span>
            <div><b>${count} ${count===1?'joueur connecté':'joueurs connectés'}</b><small>activité récente · ${adminPresence.thresholdSeconds||90} s</small></div>
            <i>${presenceListOpen?'⌃':'⌄'}</i>
          </button>
          <div id="adminPresenceList" class="admin-presence-list ${presenceListOpen?'':'hidden'}">
            <div class="presence-list-title">🟢 Connectés maintenant</div>
            ${adminPresence.online?.length?adminPresence.online.map(p=>`<div class="presence-player">${avatar(p,'xs')}<div><b>${esc(p.pseudo)}</b><small>${p.rank} · ${presenceAgo(p.lastSeen)}</small></div></div>`).join(''):'<div class="empty compact-empty">Aucun autre joueur connecté pour le moment.</div>'}
          </div>
        </div>`;
    }
    function renderAdminPresenceBar(){
        const host=document.getElementById('adminPresenceHost');
        if(host)host.innerHTML=presenceBarHtml();
        queueApplyLanguage();
    }
    function togglePresenceList(){
        presenceListOpen=!presenceListOpen;
        renderAdminPresenceBar();
    }

    function renderAdmin() {
        const el = document.getElementById('adminScreen'), m = user();
        if (!el)
            return;
        if (!isAdmin()) {
            el.innerHTML = '<div class="empty">Accès réservé aux R4 et R5.</div>';
            return;
        }
        el.innerHTML = `<div class="section-title"><h2>⚙️ Administration</h2><p>${m.rank}</p></div>
  <div id="adminPresenceHost">${presenceBarHtml()}</div>
  <div class="admin-dashboard">
    <button class="admin-menu-card messages" onclick="W.openAdminSection('messages')">
      <span>💬</span><div><b>Messages & notifications</b><small>Planning du lundi, annonce du jour, Conducteur et VIP</small></div><i>→</i>
    </button>
    <button class="admin-menu-card settings" onclick="W.openAdminSection('settings')">
      <span>🚂</span><div><b>Paramètres du train</b><small>Heure, ancrage et alternance des Conducteurs</small></div><i>→</i>
    </button>
    <button class="admin-menu-card rotations" onclick="W.openAdminSection('rotations')">
      <span>🔁</span><div><b>Rotations</b><small>Choisir les rangs autorisés et l’ordre de priorité</small></div><i>→</i>
    </button>
    <button class="admin-menu-card manual" onclick="W.openAdminSection('manual')">
      <span>✍️</span><div><b>Planning manuel</b><small>Corriger exceptionnellement une journée</small></div><i>→</i>
    </button>
    <button class="admin-menu-card equity" onclick="W.openAdminSection('equity')">
      <span>⚖️</span><div><b>Contrôle d’équité</b><small>Comparer le nombre de passages par rotation</small></div><i>→</i>
    </button>
    <button class="admin-menu-card analytics" onclick="W.openAdminAnalytics()">
      <span>📊</span><div><b>Statistiques du train</b><small>Rotations, équité et historique des passages</small></div><i>→</i>
    </button>
  </div>
  <div class="admin-summary">
    <div><small>Membres</small><strong>${ROSTER.length}</strong></div>
    <div><small>Train</small><strong>${state.settings.trainTime}</strong></div>
    <div><small>VIP</small><strong>${ranksForRotation('vip').join('+')}</strong></div>
  </div>`;
        refreshAdminPresence();
    }
    function renderAll() { renderHome(); renderPlanning(); renderExchanges(); renderAlerts(); renderAdmin(); queueApplyLanguage(); }
    function openModal(html) { const m = document.getElementById('modal'); document.getElementById('modalBody').innerHTML = html; m.classList.remove('hidden'); queueApplyLanguage(); }
    function closeModal() { document.getElementById('modal').classList.add('hidden'); }
    function openSelfProfileEdit() {
        const p = user();
        if (!p)
            return;
        openModal(`<h2>✏️ Modifier mon profil</h2>
    <div class="avatar-edit-preview">${avatar(p)}<span>${esc(p.pseudo)}</span></div>
    <label class="field-label">Pseudo</label>
    <input id="selfPseudoField" value="${esc(p.pseudo)}" placeholder="Ton pseudo">
    <label class="field-label" style="margin-top:10px">Photo de profil</label>
    <input id="selfAvatarField" type="file" accept="image/*">
    <label class="field-label language-label" style="margin-top:12px">🌍 Langue de l’interface</label>
    <select id="selfLanguageField" class="language-select" onchange="W.changeLanguage(this.value)">
      <option value="fr" ${currentLanguage()==='fr'?'selected':''}>🇫🇷 Français</option>
      <option value="it" ${currentLanguage()==='it'?'selected':''}>🇮🇹 Italiano</option>
      <option value="en" ${currentLanguage()==='en'?'selected':''}>🇬🇧 English</option>
      <option value="es" ${currentLanguage()==='es'?'selected':''}>🇪🇸 Español</option>
    </select>
    <p class="language-note">Le changement de langue est immédiat et ne demande pas de code.</p>
    <div class="locked-rank"><span>🔒 Rang</span><strong>${p.rank}</strong><small>Tu ne peux pas modifier ton rang. Seuls les R4/R5 peuvent le faire.</small></div>
    ${isAdmin(p) ? '' : `<label class="field-label" style="margin-top:10px">Code personnel</label><input id="selfPinField" type="password" inputmode="numeric" maxlength="6" autocomplete="current-password" placeholder="Demandé uniquement pour enregistrer le profil"><p class="profile-pin-note">🔐 Ce code n’est pas nécessaire pour ouvrir l’application.</p>`}
    <div class="actions"><button class="btn gold" onclick="W.saveSelfProfile()">💾 Enregistrer</button><button class="btn outline" onclick="W.openChangePin()">🔑 Changer mon code</button></div>`);
    }
    async function saveSelfProfile() {
        var _a, _b, _c, _d;
        const p = user();
        if (!p)
            return;
        const pseudo = (((_a = document.getElementById('selfPseudoField')) === null || _a === void 0 ? void 0 : _a.value) || '').trim();
        if (!pseudo)
            return toast('Pseudo obligatoire');
        const file = (_c = (_b = document.getElementById('selfAvatarField')) === null || _b === void 0 ? void 0 : _b.files) === null || _c === void 0 ? void 0 : _c[0], body = { pseudo };
        if (!isAdmin(p)) {
            const pin = (((_d = document.getElementById('selfPinField')) === null || _d === void 0 ? void 0 : _d.value) || '').trim();
            if (!/^[0-9]{6}$/.test(pin))
                return toast('Entre ton code personnel à 6 chiffres');
            body.pin = pin;
        }
        if (file) {
            try {
                body.avatar = await resizeAvatarFile(file);
            }
            catch (e) {
                return toast('Impossible de lire la photo');
            }
        }
        const ok = await mutate('/api/me', { method: 'PUT', body: JSON.stringify(body) }, 'Profil mis à jour');
        if (ok)
            closeModal();
    }
    function openProfileInfo() {
        const m = user();
        const memberships = [];
        if (ranksForRotation('officer').includes(m.rank))
            memberships.push(rolePoolLabel('officer'));
        if (ranksForRotation('r3driver').includes(m.rank))
            memberships.push(rolePoolLabel('r3driver'));
        if (ranksForRotation('vip').includes(m.rank))
            memberships.push(rolePoolLabel('vip'));
        openModal(`<h2 class="profile-modal-title">${avatar(m)}<span>${esc(m.pseudo)}</span></h2>
    <p>${rankBadge(m.rank)}</p>
    <div class="warning">${memberships.length ? `Rotations automatiques actuelles : ${memberships.join(' · ')}` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>
    <div class="profile-language-current"><span>🌍 Langue de l’interface</span><strong>${({fr:'Français',it:'Italiano',en:'English',es:'Español'})[currentLanguage()]}</strong></div>
    <button class="btn gold full" onclick="W.openSelfProfileEdit()">✏️ Modifier mon pseudo / ma photo</button>
    <div class="locked-rank compact"><span>🔒 Rang ${m.rank}</span><small>Le rang est modifiable uniquement par un R4/R5 depuis l’administration.</small></div>`);
    }
    function goAlerts() { showScreen('alertsScreen'); }
    function unavailabilityText(fr,en,it,es){
        const lang=currentLanguage();
        return lang==='en'?en:lang==='it'?it:lang==='es'?es:fr;
    }
    function unavailableGroups(arr){
        const dates=[...new Set(arr||[])].sort();
        if(!dates.length)return [];
        const groups=[];
        let start=dates[0],prev=dates[0],items=[dates[0]];
        for(let i=1;i<dates.length;i++){
            const cur=dates[i];
            const expected=dateISO(addDays(parseISO(prev),1));
            if(cur===expected){items.push(cur);prev=cur;continue;}
            groups.push({start,end:prev,dates:items});
            start=cur;prev=cur;items=[cur];
        }
        groups.push({start,end:prev,dates:items});
        return groups;
    }
    function showUnavailable() {
        const m=user(), arr=(state.unavailable[m.id]||[]).slice().sort(), groups=unavailableGroups(arr);
        const count=arr.length;
        const summary=count?`<div class="unavailability-count">🚫 <strong>${count}</strong> ${count===1?unavailabilityText('jour indisponible','unavailable day','giorno indisponibile','día no disponible'):unavailabilityText('jours indisponibles','unavailable days','giorni indisponibili','días no disponibles')}</div>`:'';
        const rows=groups.map(g=>{
            const single=g.start===g.end;
            const title=single?fmtDate(parseISO(g.start)):`${fmtDate(parseISO(g.start))} → ${fmtDate(parseISO(g.end))}`;
            const sub=single?unavailabilityText('Une journée','One day','Un giorno','Un día'):`${g.dates.length} ${unavailabilityText('jours','days','giorni','días')}`;
            return `<div class="option option-with-action unavailability-period-row">
              <span>${single?'📅':'🧳'}</span>
              <span><b>${title}</b><small>${sub}</small></span>
              <button class="btn danger small" onclick="W.removeUnavailableRange('${g.start}','${g.end}')">${single?'Retirer':'Retirer la période'}</button>
            </div>`;
        }).join('');
        openModal(`<h2>🚫 Mes indisponibilités</h2>
          <button class="btn gold full unavailability-add" onclick="W.showUnavailableChoice()">＋ Ajouter une indisponibilité</button>
          ${summary}
          ${rows?`<div class="option-list">${rows}</div>`:'<div class="empty">Aucune indisponibilité enregistrée.</div>'}`);
    }
    function showUnavailableChoice(ds=''){
        const dayLabel=ds?fmtDate(parseISO(ds)):'';
        openModal(`<h2>🚫 Choisis le type d’indisponibilité</h2>
          <div class="unavailable-choice-grid">
            <button class="unavailable-choice-card day" onclick="${ds?`W.openUnavailableDayPicker('${ds}')`:`W.openUnavailableDayPicker()`}">
              <span>📅</span>
              <b>${ds?'Ce jour de passage':'Une journée'}</b>
              <small>${ds?`${dayLabel} · Indisponible uniquement pour cette date`:'Choisir une journée'}</small>
              <i>→</i>
            </button>
            <button class="unavailable-choice-card period" onclick="W.openUnavailablePeriod('${ds||''}')">
              <span>🧳</span>
              <b>Une période</b>
              <small>Vacances, déplacement, pause du train…</small>
              <i>→</i>
            </button>
          </div>`);
    }
    function openUnavailableDayPicker(defaultDate=''){
        const min=dateISO(new Date());
        const value=defaultDate||min;
        openModal(`<h2>📅 Choisir une journée</h2>
          <label class="field-label">Date</label>
          <input id="unavailableSingleDate" type="date" min="${min}" value="${value}">
          <button class="btn gold full period-save-btn" onclick="W.saveUnavailableDayFromPicker()">🚫 Enregistrer cette journée</button>`);
    }
    async function saveUnavailableDayFromPicker(){
        const ds=document.getElementById('unavailableSingleDate')?.value;
        if(!ds)return toast(unavailabilityText('Choisis une date.','Choose a date.','Scegli una data.','Elige una fecha.'));
        await saveUnavailableDay(ds);
    }
    function openUnavailablePeriod(defaultStart=''){
        const min=dateISO(new Date());
        const start=(defaultStart&&defaultStart>=min)?defaultStart:min;
        const end=start;
        openModal(`<h2>🧳 Choisir une période</h2>
          <p class="period-help">${unavailabilityText('Indique le premier et le dernier jour où tu ne souhaites pas participer au train.','Select the first and last day you do not want to take part in the train.','Indica il primo e l’ultimo giorno in cui non vuoi partecipare al treno.','Indica el primer y el último día en que no quieres participar en el tren.')}</p>
          <div class="period-date-grid">
            <label><span class="field-label">Du</span><input id="unavailablePeriodStart" type="date" min="${min}" value="${start}" onchange="W.syncUnavailablePeriodMin()"></label>
            <label><span class="field-label">Au</span><input id="unavailablePeriodEnd" type="date" min="${start}" value="${end}"></label>
          </div>
          <div id="unavailablePeriodPreview" class="period-preview"></div>
          <button class="btn gold full period-save-btn" onclick="W.saveUnavailablePeriod()">🚫 Enregistrer la période</button>`);
        syncUnavailablePeriodMin();
    }
    function syncUnavailablePeriodMin(){
        const s=document.getElementById('unavailablePeriodStart'),e=document.getElementById('unavailablePeriodEnd');
        if(!s||!e)return;
        e.min=s.value;
        if(e.value<s.value)e.value=s.value;
        const a=parseISO(s.value),b=parseISO(e.value);
        const days=Math.round((b-a)/86400000)+1;
        const preview=document.getElementById('unavailablePeriodPreview');
        if(preview&&Number.isFinite(days)&&days>0)preview.innerHTML=`🧳 <strong>${days}</strong> ${days===1?unavailabilityText('jour','day','giorno','día'):unavailabilityText('jours','days','giorni','días')}`;
        e.onchange=syncUnavailablePeriodMin;
    }
    function datesBetween(start,end){
        const out=[],a=parseISO(start),b=parseISO(end);
        for(let d=new Date(a);d<=b;d=addDays(d,1))out.push(dateISO(d));
        return out;
    }
    async function saveUnavailablePeriod(){
        const start=document.getElementById('unavailablePeriodStart')?.value;
        const end=document.getElementById('unavailablePeriodEnd')?.value;
        if(!start||!end)return toast(unavailabilityText('Choisis les deux dates.','Choose both dates.','Scegli entrambe le date.','Elige ambas fechas.'));
        if(end<start)return toast(unavailabilityText('La date de fin doit être après la date de début.','The end date must be on or after the start date.','La data di fine deve essere uguale o successiva alla data di inizio.','La fecha final debe ser igual o posterior a la fecha inicial.'));
        const range=datesBetween(start,end);
        if(range.length>366)return toast(unavailabilityText('Maximum : 366 jours par période.','Maximum: 366 days per period.','Massimo: 366 giorni per periodo.','Máximo: 366 días por período.'));
        const m=user();
        const dates=[...new Set([...(state.unavailable[m.id]||[]),...range])].sort();
        const affected=myAssignments(m.id).filter(x=>range.includes(x.date));
        const ok=await mutate('/api/me/preferences',{method:'PUT',body:JSON.stringify({unavailable:dates})},'Période enregistrée');
        if(!ok)return;
        const n=affected.length;
        openModal(`<h2>✅ Période enregistrée</h2>
          <div class="period-success">
            <span>🧳</span>
            <div><b>${fmtDate(parseISO(start))} → ${fmtDate(parseISO(end))}</b>
            <small>${range.length} ${range.length===1?unavailabilityText('jour','day','giorno','día') : unavailabilityText('jours','days','giorni','días')}</small></div>
          </div>
          ${n?`<div class="warning">${n} ${n===1?unavailabilityText('passage concerné','scheduled turn affected','turno interessato','turno afectado'):unavailabilityText('passages concernés','scheduled turns affected','turni interessati','turnos afectados')}.</div>`:''}
          <button class="btn gold full" onclick="W.showUnavailable()">🚫 Mes indisponibilités</button>`);
    }
    async function saveUnavailableDay(ds){
        const m=user();
        if(!canSelfManage())return;
        const dates=[...new Set([...(state.unavailable[m.id]||[]),ds])].sort();
        const ok=await mutate('/api/me/preferences',{method:'PUT',body:JSON.stringify({unavailable:dates})},'Indisponibilité enregistrée');
        if(!ok)return;
        const a=myAssignments(m.id).find(x=>x.date===ds);
        if(a)
            openModal(`<h2>🚫 Indisponibilité enregistrée</h2><p>Tu peux maintenant publier ce passage dans la bourse d’échange.</p><div class="actions"><button class="btn exchange-btn" onclick="W.closeAndOpenExchange('${ds}','${a.role}')">🔄 Publier un échange</button><button class="btn outline" onclick="W.closeModal()">Pas maintenant</button></div>`);
        else showUnavailable();
    }
    async function removeUnavailableRange(start,end){
        const id=user().id;
        const dates=(state.unavailable[id]||[]).filter(x=>x<start||x>end);
        const ok=await mutate('/api/me/preferences',{method:'PUT',body:JSON.stringify({unavailable:dates})},'Indisponibilité supprimée');
        if(ok)showUnavailable();
    }
    async function removeUnavailable(ds){
        return removeUnavailableRange(ds,ds);
    }
    function showRotationStatus() {
        const m = user(), pools = [];
        if (ranksForRotation('officer').includes(m.rank))
            pools.push(rolePoolLabel('officer'));
        if (ranksForRotation('r3driver').includes(m.rank))
            pools.push(rolePoolLabel('r3driver'));
        if (ranksForRotation('vip').includes(m.rank))
            pools.push(rolePoolLabel('vip'));
        openModal(`<h2>🔁 Rotation</h2><p>Statut : <strong>${isOut(m.id) ? 'Hors rotation' : 'Actif'}</strong>.</p>
    <div class="warning">${pools.length ? `Tu participes actuellement à : ${pools.join(' · ')}.` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>
    ${canSelfManage() ? `<button class="btn ${isOut(m.id) ? 'success' : 'outline'} full" onclick="W.toggleRotation();W.showRotationStatus()">${isOut(m.id) ? '✅ Reprendre la rotation' : '⏸ Me retirer de la rotation'}</button>` : ''}`);
    }
    async function toggleRotation() {
        const next = !isOut(user().id);
        await mutate('/api/me/preferences', { method: 'PUT', body: JSON.stringify({ outRotation: next }) }, next ? 'Tu es maintenant hors rotation' : 'Rotation réactivée');
    }
    function markUnavailable(ds) {
        if(!canSelfManage())return;
        showUnavailableChoice(ds||'');
    }
    function closeAndOpenExchange(ds, role) { closeModal(); openExchange(ds, role); }
    function openExchange(ds, role) {
        const item = findAssignment(ds), m = user();
        if (!item || !m)
            return;
        const rk = roleKey(item, role);
        if (state.exchanges.some(x => x.fromId === m.id && x.fromDate === ds && x.roleKey === rk && x.status === 'open'))
            return toast('Une annonce existe déjà pour cette date');
        openModal(`<h2>🔄 Échanger ma place</h2><p>Publier ton passage du <strong>${fmtDate(parseISO(ds))}</strong> dans la bourse ?</p><div class="warning">Tu ne choisis personne : les joueurs compatibles verront l’annonce et proposeront eux-mêmes leur date.</div><button class="btn exchange-btn full" onclick="W.publishMarketExchange('${ds}','${rk}')">Publier ma demande</button>`);
    }
    async function publishMarketExchange(ds, rk) {
        const ok = await mutate('/api/exchanges', { method: 'POST', body: JSON.stringify({ fromDate: ds, roleKey: rk }) }, 'Annonce publiée');
        if (ok)
            closeModal();
    }
    async function cancelMarketExchange(id) {
        await mutate(`/api/exchanges/${encodeURIComponent(id)}`, { method: 'DELETE' }, 'Annonce retirée');
    }
    function pickMyDateForMarket(id) {
        const x = state.exchanges.find(e => e.id === id);
        if (!x || x.status !== 'open' || x.fromId === user().id)
            return;
        const mine = myAssignments().filter(a => a.roleKey === x.roleKey && a.date !== x.fromDate);
        if (!mine.length)
            return toast('Aucune date compatible');
        openModal(`<h2>Choisir ta date</h2><p>Quelle date veux-tu échanger avec le ${fmtShort(parseISO(x.fromDate))} ?</p><div class="option-list">${mine.map(a => `<button class="option" onclick="W.executeMarketSwap('${x.id}','${a.date}')"><span>${a.role === 'vip' ? '⭐' : '🚂'}</span><span><b>${fmtDate(parseISO(a.date))}</b><small>${a.role === 'vip' ? 'VIP' : 'Conducteur'}</small></span></button>`).join('')}</div>`);
    }
    async function executeMarketSwap(id, myDate) {
        const ok = await mutate(`/api/exchanges/${encodeURIComponent(id)}/accept`, { method: 'POST', body: JSON.stringify({ myDate }) }, 'Échange effectué');
        if (ok)
            closeModal();
    }
    function icsEvent(item, role) {
        const m = user(), ds = item.date.replaceAll('-', ''), [hh, mm] = state.settings.trainTime.split(':'), start = `${ds}T${hh}${mm}00`, endH = String((Number(hh) + 1) % 24).padStart(2, '0'), end = `${ds}T${endH}${mm}00`, title = `Train WfGg — ${role === 'driver' ? 'Conducteur' : 'VIP'}`, other = otherOn(item, role);
        return `BEGIN:VEVENT\nUID:${m.id}-${item.date}-${role}@wfgg-train\nDTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z/, 'Z')}\nDTSTART:${start}\nDTEND:${end}\nSUMMARY:${title}\nDESCRIPTION:${other ? `Avec ${other.pseudo}. ` : ''}WfGg Train\nBEGIN:VALARM\nTRIGGER:-P1D\nACTION:DISPLAY\nDESCRIPTION:Demain : ${title}\nEND:VALARM\nBEGIN:VALARM\nTRIGGER:-PT30M\nACTION:DISPLAY\nDESCRIPTION:Dans 30 minutes : ${title}\nEND:VALARM\nEND:VEVENT`;
    }
    function downloadICS(events, filename) { const content = `BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//WfGg//Train//FR\nCALSCALE:GREGORIAN\nMETHOD:PUBLISH\n${events.join('\n')}\nEND:VCALENDAR`; const blob = new Blob([content], { type: 'text/calendar;charset=utf-8' }), a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); }
    function addCalendar(ds, role) { const item = findAssignment(ds); if (item) {
        downloadICS([icsEvent(item, role)], `WfGg-Train-${ds}.ics`);
        toast('Événement calendrier créé');
    } }
    function addAllCalendar() { const ev = upcomingMine(12).map(x => icsEvent(x, x.role)); if (!ev.length)
        return toast('Aucun passage à ajouter'); downloadICS(ev, 'WfGg-Train-mes-passages.ics'); toast('Calendrier créé'); }
    async function toggleAlerts() {
        const id = user().id, next = !state.alertsEnabled[id];
        await mutate('/api/me/preferences', { method: 'PUT', body: JSON.stringify({ alertsEnabled: next }) }, next ? 'Alertes activées' : 'Alertes désactivées');
    }
    function changeWeek(n) { weekOffset += n; renderPlanning(); }
    async function saveAdminSettings() {
        const body = { trainTime: document.getElementById('trainTimeAdmin').value || '20:00', anchorDate: document.getElementById('anchorAdmin').value || state.settings.anchorDate, officersFirst: document.getElementById('parityAdmin').value === 'officer', resetOverrides: true };
        return mutate('/api/admin/settings', { method: 'PUT', body: JSON.stringify(body) }, 'Planning régénéré');
    }
    async function saveDay(ds) {
        const driverId = document.getElementById(`drv-${ds}`).value || null, vipId = document.getElementById(`vip-${ds}`).value || null;
        if (driverId && vipId && driverId === vipId)
            return toast('Conducteur et VIP doivent être différents');
        return mutate(`/api/admin/override/${ds}`, { method: 'PUT', body: JSON.stringify({ driverId, vipId }) }, 'Journée modifiée');
    }
    async function clearDayOverride(ds) {
        return mutate(`/api/admin/override/${ds}`, { method: 'DELETE' }, 'Retour au planning automatique');
    }
    async function adminToggleRotation(id) {
        if (!isAdmin())
            return;
        const next = !isOut(id);
        return mutate(`/api/admin/members/${encodeURIComponent(id)}/preferences`, { method: 'PUT', body: JSON.stringify({ outRotation: next }) }, 'Statut mis à jour');
    }
    function filterMembers(rank, btn) { document.querySelectorAll('#adminScreen .chips .chip').forEach(x => x.classList.remove('active')); if (btn)
        btn.classList.add('active'); document.getElementById('adminMembers').innerHTML = memberRows(rank === 'TOUS' ? ROSTER : ROSTER.filter(x => x.rank === rank)); }
    function searchMembers(q) { const s = (q || '').trim().toLowerCase(); document.getElementById('adminMembers').innerHTML = memberRows(!s ? ROSTER : ROSTER.filter(x => x.pseudo.toLowerCase().includes(s) || x.rank.toLowerCase().includes(s))); }
    function openMemberForm(id = '') {
        if (!isAdmin())
            return;
        const p = id ? byId[id] : null;
        openModal(`<h2>${p ? '✏️ Modifier le joueur' : '＋ Ajouter un joueur'}</h2><input type="hidden" id="memberIdField" value="${p ? p.id : ''}"><label class="field-label">Pseudo</label><input id="memberPseudoField" value="${p ? esc(p.pseudo) : ''}" placeholder="Pseudo exact"><label class="field-label" style="margin-top:10px">Rang</label><select id="memberRankField">${['R5', 'R4', 'R3', 'R2', 'R1'].map(r => `<option ${p && p.rank === r ? 'selected' : ''}>${r}</option>`).join('')}</select><label class="field-label" style="margin-top:10px">Photo de profil</label>${p ? `<div class="avatar-edit-preview">${avatar(p)}<span>Photo actuelle</span></div>` : ''}<input id="memberAvatarField" type="file" accept="image/*"><label class="toggle-row member-active-row"><span>Profil actif</span><input id="memberActiveField" type="checkbox" ${!p || p.active ? 'checked' : ''}></label><div class="actions"><button class="btn gold" onclick="W.saveMemberForm()">💾 Enregistrer</button>${p ? `<button class="btn outline" onclick="W.resetMemberPin('${p.id}')">🔑 Nouveau code</button><button class="btn danger" onclick="W.deleteMember('${p.id}')">🗑 Supprimer</button>` : ''}</div>`);
    }
    async function resizeAvatarFile(file) {
        if (!file)
            return null;
        return await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => { const img = new Image(); img.onload = () => { const c = document.createElement('canvas'); c.width = 160; c.height = 160; const ctx = c.getContext('2d'), scale = Math.max(160 / img.width, 160 / img.height), w = img.width * scale, h = img.height * scale; ctx.drawImage(img, (160 - w) / 2, (160 - h) / 2, w, h); resolve(c.toDataURL('image/jpeg', .78)); }; img.onerror = reject; img.src = reader.result; }; reader.onerror = reject; reader.readAsDataURL(file); });
    }
    async function saveMemberForm() {
        if (!isAdmin())
            return;
        const id = document.getElementById('memberIdField').value || '';
        const existing = id ? byId[id] : null, pseudo = document.getElementById('memberPseudoField').value.trim(), rank = document.getElementById('memberRankField').value, active = document.getElementById('memberActiveField').checked;
        if (!pseudo)
            return toast('Pseudo obligatoire');
        const file = document.getElementById('memberAvatarField').files[0], body = { pseudo, rank, active };
        if (file) {
            try {
                body.avatar = await resizeAvatarFile(file);
            }
            catch (e) {
                return toast('Impossible de lire la photo');
            }
        }
        else if (!existing)
            body.avatar = 'assets/icon-192.png';
        try {
            let result;
            if (existing)
                result = await api(`/api/admin/members/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) });
            else
                result = await api('/api/admin/members', { method: 'POST', body: JSON.stringify(body) });
            if (result.pin)
                rememberGeneratedCode(result.id,pseudo,rank,result.pin,'Nouveau membre');
            const selfSecurityChange=!!(existing&&existing.id===user()?.id&&result.sessionInvalidated);
            if(selfSecurityChange){
                closeModal();

                state.currentUserId=null;saveState();
                document.getElementById('appView')?.classList.add('hidden');
                toast('Ton rang ou ton statut a changé : reconnecte-toi.');
                return;
            }
            await syncSnapshot({ render: true, quiet: true });
            closeModal();
            if (result.pin)
                openModal(`<h2>✅ Joueur ajouté</h2><p>Code personnel de <strong>${esc(pseudo)}</strong> :</p><div class="new-pin">${result.pin}</div><div class="warning">Ce code n’est affiché qu’une fois. Il est aussi disponible temporairement dans Admin → Codes & accès.</div><div class="actions"><button class="btn gold" onclick="W.copyText('${result.pin}')">📋 Copier le code</button><button class="btn outline" onclick="W.closeModal();W.openAdminSection('access')">🔐 Codes & accès</button></div>`);
            else if(result.sessionInvalidated)
                toast('Profil corrigé · sessions du joueur fermées');
            else
                toast('Profil corrigé');
        }
        catch (e) {
            toast(e.message);
        }
    }
    async function deleteMember(id) {
        if (!isAdmin())
            return;
        const p = byId[id];
        if (!p || !confirm(`Supprimer ${p.pseudo} de la liste ?`))
            return;
        const ok = await mutate(`/api/admin/members/${encodeURIComponent(id)}`, { method: 'DELETE' }, 'Joueur supprimé');
        if (ok)
            closeModal();
    }
    function renderRotationOrder(key, btn) { const panel = btn === null || btn === void 0 ? void 0 : btn.closest('.admin-panel'); if (panel)
        panel.querySelectorAll('.chip').forEach(x => x.classList.remove('active')); if (btn)
        btn.classList.add('active'); document.getElementById('rotationOrderList').innerHTML = rotationOrderRows(key); }
    async function moveRotation(key, index, delta) {
        const arr = [...(state.rotationOrder[key] || [])], j = index + delta;
        if (j < 0 || j >= arr.length)
            return;
        [arr[index], arr[j]] = [arr[j], arr[index]];
        const ok = await mutate('/api/admin/rotation-order', { method: 'PUT', body: JSON.stringify({ key, ids: arr }) }, 'Ordre modifié');
        if (ok && document.getElementById('rotationOrderList'))
            document.getElementById('rotationOrderList').innerHTML = rotationOrderRows(key);
    }
    const WEEKLY_MESSAGES = [
        ({ week, time }) => `🚂✨ WfGg TRAIN — Le planning de la semaine est servi !\n\n${week}\n\nDépart habituel : ${time}. Merci à chacun de jeter un œil à son jour avant que le train ne parte sans les wagons 😄. Un empêchement ? La bourse d’échange est là. Unis, forts, solidaires… et ponctuels si possible ! 💪`,
        ({ week, time }) => `📅🚆 Nouvelle semaine, nouveau casting du train WfGg !\n\n${week}\n\nTrain à ${time}. Conducteurs, chauffez la locomotive. VIP, préparez le tapis rouge (enfin… façon de parler 😎). Vérifiez vos dates et signalez vite tout souci pour qu’on garde une organisation fluide.`,
        ({ week, time }) => `📣 WfGg, rassemblement sur le quai ! Voici le planning de la semaine :\n\n${week}\n\n🕗 ${time} pour le départ. Merci aux Conducteurs et VIP de bien noter leur jour. Si la vraie vie décide de nous mettre un boss surprise, publiez votre échange au plus tôt. Ensemble, le train roule mieux !`,
        ({ week, time }) => `🚂 Semaine WfGg : les billets sont distribués !\n\n${week}\n\nDépart à ${time}. Pas besoin de composter, juste de penser à votre passage 😄. Un souci de date ? Bourse d’échange. Une question ? On communique. Une victoire ? On la prend tous ensemble.`,
        ({ week, time }) => `🏆 Planning train de la semaine — WfGg Edition\n\n${week}\n\nHeure habituelle : ${time}. Merci à chacun de vérifier son passage. Conducteur + VIP = duo du jour : prenez contact avant le départ, ça évite les chorégraphies improvisées à 19h59 😅.`,
        ({ week, time }) => `🌴🚆 Le train WfGg traverse la jungle cette semaine avec cet équipage :\n\n${week}\n\nRendez-vous à ${time}. Si vous êtes programmé, gardez la date sous le coude. Si vous ne pouvez pas, prévenez tôt : on préfère un échange bien organisé qu’un sprint olympique au dernier moment !`,
        ({ week, time }) => `⚔️🚂 Ordre de mission de la semaine : faire rouler le train sans perdre un wagon !\n\n${week}\n\nDépart ${time}. Merci à tous de vérifier le planning. Les imprévus sont autorisés, le silence radio beaucoup moins 😄 : utilisez l’indisponibilité ou la bourse d’échange.`,
        ({ week, time }) => `💙💛 WfGg — Unis, forts, solidaires… et cette semaine aussi bien installés dans le train !\n\n${week}\n\n🕗 ${time}. Conducteurs et VIP : notez votre passage et contactez votre binôme le jour J. Tout le monde joue le jeu, tout le monde avance.`,
        ({ week, time }) => `🎟️ Les places de la semaine sont attribuées ! Voici le planning WfGg :\n\n${week}\n\nTrain à ${time}. Merci de vérifier votre nom avant de demander au contrôleur où est votre wagon 😂. En cas d’absence, publiez votre échange le plus tôt possible.`,
        ({ week, time }) => `🚆🔥 Le planning WfGg de la semaine vient d’arriver en gare !\n\n${week}\n\nDépart habituel ${time}. On anticipe, on échange si besoin, on se coordonne et surtout on garde la bonne humeur. Le train est collectif : chacun fait sa petite part, et ça roule !`
    ];
    const DAILY_MESSAGES = [
        ({ date, time, driver, vip }) => `🚂 Aujourd’hui, le train WfGg est entre de bonnes mains : ${driver} au volant et ${vip} en VIP ⭐. Rendez-vous à ${time}. Vous deux, un petit contact avant le départ et hop, ça roule !`,
        ({ date, time, driver, vip }) => `📣 Casting du jour : 🚂 Conducteur ${driver} · ⭐ VIP ${vip}. Train à ${time}. Merci de vous coordonner — la télépathie n’est toujours pas une compétence d’alliance 😄.`,
        ({ date, time, driver, vip }) => `🚆 ${date} : le duo du jour est ${driver} + ${vip}. Départ ${time}. Prenez contact avant, histoire que le train ne découvre pas son équipage au générique de fin 😂.`,
        ({ date, time, driver, vip }) => `⭐🚂 WfGg Train du jour : ${driver} conduit, ${vip} prend la place VIP. ${time} au quai ! Bonne coordination et bon trajet à tous les deux.`,
        ({ date, time, driver, vip }) => `🕗 Tic-tac… train à ${time} ! Aujourd’hui : ${driver} Conducteur, ${vip} VIP. Un petit message entre vous et on évite le fameux “Ah, c’était aujourd’hui ?” 😅`,
        ({ date, time, driver, vip }) => `🎟️ Billets du jour validés : ${driver} 🚂 + ${vip} ⭐. Départ ${time}. Merci à notre duo de se caler avant le passage. WfGg en voiture !`,
        ({ date, time, driver, vip }) => `🌴 Le train traverse la jungle aujourd’hui avec ${driver} aux commandes et ${vip} en VIP. Départ ${time}. Faites connaissance avant, même si c’est juste pour dire “Salut, prêt ?” 😄`,
        ({ date, time, driver, vip }) => `⚡ Alerte locomotive : ${driver} conduit aujourd’hui, accompagné de ${vip} en VIP. ${time}. Coordination recommandée, panique déconseillée 😎.`,
        ({ date, time, driver, vip }) => `🏆 Duo WfGg du jour : ${driver} & ${vip}. Train à ${time}. Vous avez une mission : vous parler avant. Oui, même les héros ont besoin d’un chat 😄.`,
        ({ date, time, driver, vip }) => `🚂 Le quai est prêt : Conducteur ${driver}, VIP ${vip}, départ ${time}. Merci de vous organiser ensemble. Le train aime la ponctualité, mais surtout les équipages qui communiquent !`,
        ({ date, time, driver, vip }) => `📅 Petit rappel qui évite les grands oublis : aujourd’hui ${driver} conduit et ${vip} est VIP. Train ${time}. À vous deux de jouer !`,
        ({ date, time, driver, vip }) => `💪 WfGg, aujourd’hui on compte sur ${driver} 🚂 et ${vip} ⭐. Rendez-vous à ${time}. Un petit ping entre vous avant le départ et la machine est lancée.`,
        ({ date, time, driver, vip }) => `🚆 Service du jour : ${driver} en cabine, ${vip} en VIP. ${time}. Merci de vous synchroniser — même une montre cassée donne l’heure deux fois par jour, nous on vise mieux 😜.`,
        ({ date, time, driver, vip }) => `🎉 Train du jour ! ${driver} prend le volant, ${vip} prend les étoiles. Départ ${time}. Bonne humeur obligatoire, billet non remboursable 😄.`,
        ({ date, time, driver, vip }) => `📣 ${date} : ${driver} + ${vip}, c’est votre tour de faire rouler WfGg. ${time}. Contactez-vous avant et faites-nous ça propre !`,
        ({ date, time, driver, vip }) => `🛤️ La voie est libre pour ${driver} (Conducteur) et ${vip} (VIP). Train à ${time}. Petit échange entre vous avant le départ, gros gain de sérénité après.`,
        ({ date, time, driver, vip }) => `⭐ Le VIP du jour est ${vip}, et son chauffeur de luxe est ${driver} 😂. Départ à ${time}. Merci de vous mettre d’accord avant que la limousine… euh, le train… arrive.`,
        ({ date, time, driver, vip }) => `🚂 Conducteur ${driver}, VIP ${vip} : votre aventure ferroviaire commence aujourd’hui à ${time}. Un message entre vous et vous gagnez +100 en organisation (stat non contractuelle 😄).`,
        ({ date, time, driver, vip }) => `🔥 WfGg Train : aujourd’hui ${driver} et ${vip} montent sur scène. Départ ${time}. Répétez juste une chose avant : “On est bien d’accord pour ce soir ?” 😄`,
        ({ date, time, driver, vip }) => `📢 Attention quai WfGg : le train de ${time} sera conduit par ${driver}, avec ${vip} en VIP. Merci au duo de prendre contact. Les autres peuvent applaudir depuis le quai 👏.`,
        ({ date, time, driver, vip }) => `🏅 Le passage du jour revient à ${driver} 🚂 et ${vip} ⭐. Rendez-vous ${time}. On communique, on s’organise, on gagne du temps — une recette presque trop simple !`,
        ({ date, time, driver, vip }) => `🚆 Aujourd’hui, pas de grève prévue : ${driver} conduit et ${vip} est VIP 😄. Départ ${time}. Un petit message avant et c’est parti !`,
        ({ date, time, driver, vip }) => `🌟 Équipage du jour confirmé : ${driver} + ${vip}. Train ${time}. Merci de vous coordonner pour que WfGg garde sa réputation de compagnie ferroviaire 5 étoiles ⭐⭐⭐⭐⭐.`,
        ({ date, time, driver, vip }) => `🕗 ${time} approche ! ${driver}, la cabine est à toi. ${vip}, le fauteuil VIP aussi. Organisez-vous avant, et que le train soit avec vous 🚂.`,
        ({ date, time, driver, vip }) => `🎯 Mission du jour : faire partir le train à ${time} avec ${driver} en Conducteur et ${vip} en VIP. Objectif secondaire : ne pas découvrir son binôme à 19h59 😂.`,
        ({ date, time, driver, vip }) => `💙💛 WfGg du jour : ${driver} conduit, ${vip} accompagne en VIP. ${time}. Deux joueurs, un train, zéro stress si vous vous contactez avant.`,
        ({ date, time, driver, vip }) => `📣 Le duo ferroviaire du jour est arrivé : ${driver} 🚂 / ${vip} ⭐. Train à ${time}. Bonne coordination et surtout amusez-vous !`,
        ({ date, time, driver, vip }) => `🚂 Aujourd’hui, ${driver} tient le manche… enfin, ce qu’il y a dans un train 😄, et ${vip} est VIP. Départ ${time}. Contact préalable fortement recommandé !`,
        ({ date, time, driver, vip }) => `🏁 Le compte à rebours est lancé : ${driver} + ${vip}, rendez-vous à ${time}. Un petit coucou entre vous avant le train, et WfGg reste sur les rails.`,
        ({ date, time, driver, vip }) => `🥳 Train WfGg du jour : Conducteur ${driver}, VIP ${vip}, départ ${time}. Merci de vous coordonner. Et rappelez-vous : un train bien organisé, c’est un R4 qui dort mieux ce soir 😂.`
    ];
    const DRIVER_MESSAGES = [
        ({ date, time, driver, vip }) => `Salut ${driver} 👋 Tu es Conducteur aujourd’hui à ${time}. Ton VIP est ${vip}. Envoie-lui un petit message avant le départ pour vous organiser — ça évite le speed-dating ferroviaire à 19h59 😄.`,
        ({ date, time, driver, vip }) => `🚂 ${driver}, aujourd’hui c’est toi qui as les clés de la locomotive ! Départ ${time}, VIP ${vip}. Prenez contact avant et bon trajet !`,
        ({ date, time, driver, vip }) => `Petit rappel Conducteur : ${driver}, passage aujourd’hui (${date}) à ${time}. ${vip} sera ton VIP. Un petit “Salut, on se cale ?” et vous êtes déjà à moitié organisés 😉.`,
        ({ date, time, driver, vip }) => `📣 ${driver}, cabine réservée pour toi à ${time}. Ton binôme VIP : ${vip}. Merci de vous coordonner avant le train.`,
        ({ date, time, driver, vip }) => `🏆 Conducteur du jour = ${driver}. VIP = ${vip}. Heure = ${time}. Mission bonus : parler à son binôme avant le départ 😄.`,
        ({ date, time, driver, vip }) => `🚆 Salut ${driver}, le train compte sur toi aujourd’hui à ${time}. ${vip} sera VIP. Mettez-vous d’accord avant, et tout roule. Littéralement.`,
        ({ date, time, driver, vip }) => `⚡ Rappel express pour ${driver} : tu conduis aujourd’hui à ${time}, avec ${vip} comme VIP. Ping ton binôme et bonne route !`,
        ({ date, time, driver, vip }) => `🛤️ ${driver}, ton jour de Conducteur est arrivé. ${time}, avec ${vip} en VIP. Un petit contact entre vous = beaucoup moins d’improvisation ensuite.`,
        ({ date, time, driver, vip }) => `🌟 ${driver}, la locomotive est chaude ! Tu conduis à ${time}. ${vip} est ton VIP. Coordonnez-vous avant et faites-nous un beau passage WfGg.`,
        ({ date, time, driver, vip }) => `🎟️ Billet Conducteur pour ${driver} aujourd’hui. Train ${time}, VIP ${vip}. Pense à le/la contacter — notre appli organise le planning, pas encore la télépathie 😄.`
    ];
    const VIP_MESSAGES = [
        ({ date, time, driver, vip }) => `Salut ${vip} 👋 Tu es VIP aujourd’hui à ${time}. Ton Conducteur est ${driver}. Envoie-lui un petit message avant le départ pour vous organiser — le tapis rouge n’attend pas 😄.`,
        ({ date, time, driver, vip }) => `⭐ ${vip}, place VIP réservée pour toi aujourd’hui ! Train ${time}, Conducteur ${driver}. Prenez contact avant et profitez du voyage.`,
        ({ date, time, driver, vip }) => `Petit rappel VIP : ${vip}, passage aujourd’hui (${date}) à ${time}. ${driver} conduit. Un petit “Salut, on se cale ?” et l’équipage est prêt 😉.`,
        ({ date, time, driver, vip }) => `📣 ${vip}, fauteuil VIP à ${time} ! Ton Conducteur : ${driver}. Merci de vous coordonner avant le train.`,
        ({ date, time, driver, vip }) => `🏆 VIP du jour = ${vip}. Conducteur = ${driver}. Heure = ${time}. Mission bonus : parler à son binôme avant le départ 😄.`,
        ({ date, time, driver, vip }) => `🚆 Salut ${vip}, tu es VIP aujourd’hui à ${time}. ${driver} sera aux commandes. Mettez-vous d’accord avant, et tout roule.`,
        ({ date, time, driver, vip }) => `⚡ Rappel express pour ${vip} : passage VIP aujourd’hui à ${time}, avec ${driver} comme Conducteur. Ping ton binôme et c’est parti !`,
        ({ date, time, driver, vip }) => `🛤️ ${vip}, ton jour de VIP est arrivé. ${time}, Conducteur ${driver}. Un petit contact entre vous = beaucoup moins d’improvisation ensuite.`,
        ({ date, time, driver, vip }) => `🌟 ${vip}, aujourd’hui c’est tapis rouge WfGg ! Tu es VIP à ${time}. ${driver} conduit. Coordonnez-vous avant et bon passage.`,
        ({ date, time, driver, vip }) => `🎟️ Billet VIP pour ${vip} aujourd’hui. Train ${time}, Conducteur ${driver}. Pense à le/la contacter — la première classe commence par une bonne organisation 😄.`
    ];
    const MESSAGE_SETS = { weekly: WEEKLY_MESSAGES, daily: DAILY_MESSAGES, driver: DRIVER_MESSAGES, vip: VIP_MESSAGES };
    function messageContext(type) {
        const input = document.getElementById('messageDateAdmin'), ds = (input === null || input === void 0 ? void 0 : input.value) || dateISO(new Date()), d = parseISO(ds), item = findAssignment(ds), driver = item && byId[item.driverId], vip = item && byId[item.vipId];
        const ctx = { date: fmtDate(d), time: state.settings.trainTime, driver: (driver === null || driver === void 0 ? void 0 : driver.pseudo) || 'À définir', vip: (vip === null || vip === void 0 ? void 0 : vip.pseudo) || 'À définir', week: '' };
        if (type === 'weekly') {
            const mon = mondayOf(d);
            ctx.week = [0, 1, 2, 3, 4, 5, 6].map(i => { const day = addDays(mon, i), x = findAssignment(dateISO(day)), dr = x && byId[x.driverId], vi = x && byId[x.vipId]; return `${fmtShort(day)} — 🚂 ${(dr === null || dr === void 0 ? void 0 : dr.pseudo) || 'À définir'} · ⭐ ${(vi === null || vi === void 0 ? void 0 : vi.pseudo) || 'À définir'}`; }).join('\n');
        }
        return ctx;
    }
    function generateMessage(type) {
        const arr = MESSAGE_SETS[type];
        if (!arr)
            return;
        const idx = (state.messageVariant[type] || 0) % arr.length, text = arr[idx](messageContext(type));
        state.messageVariant[type] = idx;
        saveState();
        const label = type === 'weekly' ? 'Planning du lundi' : type === 'daily' ? 'Annonce du jour' : type === 'driver' ? 'Message Conducteur' : 'Message VIP';
        openModal(`<h2>💬 ${label}</h2><div class="message-counter">Variante ${idx + 1} / ${arr.length}</div><textarea id="generatedMessage" class="message-output">${esc(text)}</textarea><div class="actions"><button class="btn gold" onclick="W.copyGeneratedMessage()">📋 Copier</button><button class="btn outline" onclick="W.nextMessage('${type}')">🔀 Autre message</button></div><p class="message-help">Le texte reste modifiable avant copie.</p>`);
    }
    function nextMessage(type) { const arr = MESSAGE_SETS[type]; state.messageVariant[type] = ((state.messageVariant[type] || 0) + 1) % arr.length; saveState(); closeModal(); generateMessage(type); }
    async function copyGeneratedMessage() { const el = document.getElementById('generatedMessage'); try {
        await navigator.clipboard.writeText(el.value);
        toast('Message copié');
    }
    catch (e) {
        el.select();
        document.execCommand('copy');
        toast('Message copié');
    } }
    async function saveRotationRanks() {
        if (!isAdmin())
            return;
        const rotationRanks = {};
        for (const key of ['officer', 'r3driver', 'vip']) {
            rotationRanks[key] = [...document.querySelectorAll(`input[data-rotation-key="${key}"]:checked`)].map(x => x.value);
            if (!rotationRanks[key].length)
                return toast('Sélectionne au moins un rang dans chaque rotation');
        }
        const ok = await mutate('/api/admin/rotation-ranks', { method: 'PUT', body: JSON.stringify({ rotationRanks }) }, 'Rotations mises à jour');
        if (ok)
            openAdminSection('rotations');
    }
    function adminBackButton() {
        return `<button class="admin-back" onclick="W.renderAdminHome()">← Administration</button>`;
    }
    function renderAdminHome() {
        currentAdminSection = null;
        gameLinksDraft = null;
        renderAdmin();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    function openAdminSection(section) {
        if (!isAdmin())
            return;
        currentAdminSection = section;
        const el = document.getElementById('adminScreen');
        const today = dateISO(new Date());
        if (section === 'messages') {
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>💬 Messages & notifications</h2><p>Prêts à copier</p></div>
      <div class="admin-panel admin-highlight">
        <label class="field-label">Date de référence</label>
        <input type="date" id="messageDateAdmin" value="${today}">
        <p class="admin-lead">10 messages du lundi, 30 annonces quotidiennes, plus les rappels privés Conducteur et VIP.</p>
        <div class="message-grid">
          <button class="message-type monday" onclick="W.generateMessage('weekly')"><span>📅</span><b>Lundi · Planning semaine</b><small>10 messages</small></button>
          <button class="message-type" onclick="W.generateMessage('daily')"><span>📣</span><b>Annonce du jour</b><small>30 messages</small></button>
          <button class="message-type" onclick="W.generateMessage('driver')"><span>🚂</span><b>Conducteur</b><small>Message privé</small></button>
          <button class="message-type" onclick="W.generateMessage('vip')"><span>⭐</span><b>VIP</b><small>Message privé</small></button>
        </div>
      </div>`;
        }
        if (section === 'settings') {
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>🚂 Paramètres du train</h2></div>
      <div class="admin-panel">
        <label class="field-label">Heure du train</label>
        <input type="time" id="trainTimeAdmin" value="${state.settings.trainTime}">
        <label class="field-label" style="margin-top:10px">Date d’ancrage</label>
        <input type="date" id="anchorAdmin" value="${state.settings.anchorDate}">
        <label class="field-label" style="margin-top:10px">Premier Conducteur</label>
        <select id="parityAdmin">
          <option value="officer" ${state.settings.officersFirst ? 'selected' : ''}>R5 / R4</option>
          <option value="r3" ${!state.settings.officersFirst ? 'selected' : ''}>R3</option>
        </select>
        <div class="warning">Le calendrier alterne toujours deux groupes de Conducteurs. Les rangs présents dans les groupes A, B et VIP se configurent dans le sous-menu « Rotations ».</div>
        <button class="btn gold full" onclick="W.saveAdminSettings();W.openAdminSection('settings')">Enregistrer & régénérer</button>
      </div>`;
        }
        if (section === 'players') {
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>👥 Joueurs de l’alliance</h2><p>${ROSTER.length} profils</p></div>
      <div class="admin-panel">
        <button class="btn gold full" onclick="W.openMemberForm()">＋ Ajouter un joueur</button>
        <input id="memberSearchAdmin" class="admin-search" placeholder="🔎 Rechercher un pseudo…" oninput="W.searchMembers(this.value)">
        <div class="chips">${['TOUS', 'R5', 'R4', 'R3', 'R2', 'R1'].map(r => `<button class="chip ${r === 'TOUS' ? 'active' : ''}" onclick="W.filterMembers('${r}',this)">${r}</button>`).join('')}</div>
        <div id="adminMembers" class="member-list">${memberRows(ROSTER)}</div>
      </div>`;
        }
        if (section === 'access') {
            const admins=ROSTER.filter(p=>p.active&&['R5','R4'].includes(p.rank));
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>🔐 Codes & accès</h2><p>Sécurité des comptes</p></div>
      <div class="admin-panel">
        <h3>🛡️ Accès R4 / R5</h3>
        <p class="admin-lead">Les R4/R5 doivent saisir leur code à la connexion. Toute modification de rang ou de statut actif ferme automatiquement toutes les sessions du joueur concerné.</p>
        <div class="access-admin-list">${admins.map(p=>`<div class="access-admin-row">${avatar(p,'xs')}<div><b>${esc(p.pseudo)}</b><small>${p.rank} · accès administrateur</small></div><button class="btn small outline" onclick="W.resetMemberPin('${p.id}')">🔑 Nouveau code</button></div>`).join('')}</div>
      </div>
      <div class="admin-panel">
        <h3>🧾 Codes générés pendant cette session</h3>
        <p class="admin-lead">Seuls les nouveaux codes créés ou réinitialisés ici apparaissent temporairement. Les anciens codes ne peuvent jamais être relus depuis la base.</p>
        ${generatedCodesHtml()}
        <div class="actions access-actions">
          <button class="btn gold" onclick="W.downloadGeneratedCodesCsv()">⬇️ Télécharger CSV</button>
          <button class="btn outline" onclick="W.clearGeneratedCodes()">🧹 Effacer la liste</button>
        </div>
      </div>
      <div class="warning">R3/R2/R1 : pseudo seul pour entrer. Leur code est demandé uniquement pour modifier leur profil. En cas de promotion R4/R5, leurs sessions sont fermées et ils doivent se reconnecter avec leur code.</div>`;
        }
        if (section === 'portal') {
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>🏠 Page d’accueil</h2><p>Configuration du portail WfGg</p></div>
      <div class="admin-panel admin-highlight">
        <h3>🏡 Page de garde WfGg</h3>
        <p class="admin-lead">Ce module servira à faire évoluer progressivement la page d’accueil. Pour le moment, le portail propose le Train et le Guide Saison 6.</p>
        <div class="portal-admin-current">
          <div><span>🚂</span><b>Train de l’alliance</b></div>
          <div><span>🎓</span><b>Aide au jeu</b></div>
        </div>
      </div>
      <div class="warning">Aucun réglage n’est encore appliqué ici : ce sous-menu est prêt pour les prochaines évolutions de la page d’accueil.</div>`;
        }
        if (section === 'analytics') {
            openAdminAnalytics();
            return;
        }
        if (section === 'help') {
            if(gameLinksDraft===null)resetGameLinksDraft();
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>🧰 Gestion des liens d’aide</h2><p>Administration</p></div>
      <div class="admin-panel">
        <h3>📘 Guide Saison 6</h3>
        <p class="admin-lead">Le guide WfGg Saison 6 est intégré directement à l’application et reste toujours la première ressource.</p>
        <button class="btn gold full" onclick="W.openGameLink('help/saison6/index.html')">↗ Ouvrir le guide</button>
      </div>
      <div class="admin-panel">
        <h3>🔗 Liens supplémentaires</h3>
        <p class="admin-lead">Ajoute jusqu’à 20 sites utiles. Ils seront visibles par tous les membres dans « Aide au jeu ».</p>
        ${gameLinkRows()}
        <div class="actions game-link-actions">
          <button class="btn outline" onclick="W.addGameLinkDraft()">＋ Ajouter un lien</button>
          <button class="btn gold" onclick="W.saveGameLinks()">💾 Enregistrer les liens</button>
        </div>
      </div>`;
        }
        if (section === 'rotations') {
            ensureRotationRankSettings();
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>🔁 Rotations</h2><p>Configuration avancée</p></div>

      <div class="admin-panel">
        <h3>🎚️ Rangs autorisés</h3>
        <p class="admin-lead">Choisis librement les rangs qui participent automatiquement à chacun des trois pools. Tu peux par exemple mettre le VIP sur R3 uniquement, ou sur R3+R2+R1.</p>
        ${rankCheckHtml('officer', 'Conducteur A — un jour sur deux')}
        ${rankCheckHtml('r3driver', 'Conducteur B — l’autre jour')}
        ${rankCheckHtml('vip', 'VIP — tous les jours')}
        <div class="warning">Un même rang peut être présent dans plusieurs pools. Un joueur ne pourra toutefois jamais être Conducteur et VIP le même jour.</div>
        <button class="btn gold full" onclick="W.saveRotationRanks()">💾 Enregistrer les rangs autorisés</button>
      </div>

      <div class="admin-panel">
        <h3>↕️ Ordre de priorité</h3>
        <p class="admin-lead">L’équité reste prioritaire. Cet ordre sert seulement à départager les joueurs à égalité de passages.</p>
        <div class="chips rotation-chips">
          <button class="chip active" onclick="W.renderRotationOrder('officer',this)">Conducteur A</button>
          <button class="chip" onclick="W.renderRotationOrder('r3driver',this)">Conducteur B</button>
          <button class="chip" onclick="W.renderRotationOrder('r3vip',this)">VIP</button>
        </div>
        <div id="rotationOrderList">${rotationOrderRows('officer')}</div>
      </div>`;
        }
        if (section === 'manual') {
            const base = mondayOf(new Date());
            const days = [0, 1, 2, 3, 4, 5, 6].map(i => addDays(base, i));
            const sched = schedule(), all = ROSTER.filter(p => p.active);
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>✍️ Planning manuel</h2><p>Semaine en cours</p></div>
      <div class="warning">Un R4/R5 peut exceptionnellement placer n’importe quel joueur actif, y compris un R2 ou un R1, dans un rôle.</div>
      <div class="admin-panel">
      ${days.map(d => {
                const ds = dateISO(d), x = sched.find(s => s.date === ds);
                return `<div class="admin-day"><h4>${fmtShort(d)} · ${state.settings.trainTime}</h4>
          <div class="admin-selects">
            <select id="drv-${ds}"><option value="">— Aucun Conducteur —</option>${all.map(p => `<option value="${p.id}" ${p.id === (x === null || x === void 0 ? void 0 : x.driverId) ? 'selected' : ''}>🚂 ${esc(p.pseudo)} · ${p.rank}</option>`).join('')}</select>
            <select id="vip-${ds}"><option value="">— Aucun VIP —</option>${all.map(p => `<option value="${p.id}" ${p.id === (x === null || x === void 0 ? void 0 : x.vipId) ? 'selected' : ''}>⭐ ${esc(p.pseudo)} · ${p.rank}</option>`).join('')}</select>
          </div>
          <div class="actions" style="margin-top:8px">
            <button class="btn outline small" onclick="W.saveDay('${ds}');W.openAdminSection('manual')">Enregistrer</button>
            <button class="btn danger small" onclick="W.clearDayOverride('${ds}');W.openAdminSection('manual')">Automatique</button>
          </div>
        </div>`;
            }).join('')}
      </div>`;
        }
        if (section === 'equity') {
            el.innerHTML = `${adminBackButton()}
      <div class="section-title"><h2>⚖️ Contrôle d’équité</h2></div>
      <div class="admin-panel">${rotationEquityHtml()}</div>
      <div class="warning">Chaque pool configuré est compté séparément. Pendant un cycle, l’objectif reste un écart maximal d’un passage entre joueurs éligibles.</div>`;
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    function updatePortalLanguage(){
        const lang=currentLanguage();
        document.querySelectorAll('[data-portal-lang]').forEach(b=>b.classList.toggle('active',b.dataset.portalLang===lang));
        applyLanguage(document);
    }
    async function setPortalLanguage(lang){
        await changeLanguage(lang);
        updatePortalLanguage();
    }
    function showPortal(){
        document.getElementById('portalView')?.classList.remove('hidden');
        document.getElementById('portalHelpView')?.classList.add('hidden');
        document.getElementById('appView')?.classList.add('hidden');
        clearInterval(syncTimer); syncTimer=null;
        updatePortalLanguage();
        updateInstallVisibility();
        window.scrollTo({top:0,behavior:'smooth'});
    }
    function showTrainEntry(){
      document.getElementById('portalView')?.classList.add('hidden');
      document.getElementById('portalHelpView')?.classList.add('hidden');

      /* WFGG_PORTAL_ONLY_AUTH_V1 */

      return bootApp();
    }

    function openGuidePortal(){
        const lang=currentLanguage();
        location.href=`/help/saison6/${lang}/index.html`;
    }

    function showScreen(id) {
        if (id === 'adminScreen')
            currentAdminSection = null;
        document.querySelectorAll('.screen').forEach(x => x.classList.toggle('active', x.id === id));
        document.querySelectorAll('.nav-btn').forEach(x => x.classList.toggle('active', x.dataset.screen === id));
        if (id === 'homeScreen')
            renderHome();
        if (id === 'planningScreen')
            renderPlanning();
        if (id === 'exchangeScreen')
            renderExchanges();
        if (id === 'alertsScreen')
            renderAlerts();
        if (id === 'adminScreen')
            renderAdmin();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    function bootApp() {
        const m = user();
        if (!m) {
            state.currentUserId = null;
            saveState();
            return;
        }
        document.getElementById('portalView').classList.add('hidden');
        document.getElementById('portalHelpView')?.classList.add('hidden');
        document.getElementById('appView').classList.remove('hidden');
        document.getElementById('adminNav').classList.toggle('hidden', !isAdmin(m));
        renderAll();
        showScreen('homeScreen');
        clearInterval(syncTimer);
        syncTimer = setInterval(() => syncSnapshot({ render: true, quiet: true }), 20000);
        startPresenceLoop();
    }
    async function init() {
        startLanguageObserver();
        applyLanguage(document);
        var _a;
        refreshRoster();
        { const el = document.getElementById('loginBtn'); if (el) el.onclick = login; }
        document.getElementById('brandHome').onclick = showPortal;
        document.getElementById('portalTrainBtn').onclick = showTrainEntry;
        document.getElementById('portalHelpBtn').onclick = showPortalHelp;
        document.getElementById('portalHelpBack').onclick = showPortal;
        document.getElementById('portalHelpLogo').onclick = showPortal;
        { const el = document.getElementById('loginPortalBack'); if (el) el.onclick = showPortal; }
        document.querySelectorAll('.nav-btn').forEach(b => b.onclick = () => showScreen(b.dataset.screen));
        document.querySelectorAll('[data-close-modal]').forEach(b => b.onclick = closeModal);
        window.addEventListener('beforeinstallprompt', e => {
            e.preventDefault();
            deferredInstall = e;
            updateInstallVisibility();
        });
        window.addEventListener('appinstalled', () => {
            deferredInstall = null;
            updateInstallVisibility();
        });
        const installBtn = document.getElementById('installBtn');
        if (installBtn) installBtn.onclick = async () => {
            if (isStandaloneApp()) {
                updateInstallVisibility();
                return;
            }
            if (deferredInstall) {
                deferredInstall.prompt();
                await deferredInstall.userChoice;
                deferredInstall = null;
                updateInstallVisibility();
            }
            else {
                location.href = '/installer.html';
            }
        };
        updateInstallVisibility();
        document.addEventListener('visibilitychange', () => {
            if(document.visibilityState==='visible'){
                syncSnapshot({render:true,quiet:true});
                startPresenceLoop();
            }
        });
        window.addEventListener('online', () => syncSnapshot({ render: true, quiet: true }));
        window.addEventListener('offline', () => setSyncStatus('off'));
        /* WFGG_TRAIN_PROXY_NO_SERVICE_WORKER_V1 */
        try {
            const d = await api('/api/directory', { method: 'GET' });
            DIRECTORY = d.users || [];
            const dl = document.getElementById('memberList');
            if (dl)
                dl.innerHTML = DIRECTORY.map(x => `<option value="${esc(x.pseudo)}">${x.rank}</option>`).join('');
        }
        catch (e) { }
      const cachedId = state.currentUserId;
      const ok = await syncSnapshot({ render: false, quiet: true });

      if (!ok && cachedId && byId[cachedId]) {
        state.currentUserId = cachedId;
        setSyncStatus('off');
      }

      if (!ok && !(cachedId && byId[cachedId])) {
        state.currentUserId = null;
        saveState();
        setSyncStatus('off');
      }

        try {
            const st = await api('/api/bootstrap/status', { method: 'GET' });
            if (!st.initialized)
                document.querySelector('.login-note').innerHTML = '⚠️ Application à initialiser · ouvre <b>/setup.html</b>';
        }
        catch (e) { }
        /* WFGG_PORTAL_DIRECT_TRAIN_V1
           Sous /train/, l'identité a déjà été synchronisée
           via le bridge du Portail. On ouvre donc Train directement.
        */
        if (location.pathname === '/train' ||
            location.pathname.startsWith('/train/')) {

          if (state.currentUserId && user()) {
            bootApp();
          } else {
            console.warn('WFGG_PORTAL_TRAIN_IDENTITY_MISSING');
            location.replace('/');
          }

        } else {
          showPortal();
        }

        startPresenceLoop();
    }
    async function copyText(text) { try {
        await navigator.clipboard.writeText(text);
        toast('Copié');
    }
    catch (e) {
        toast('Copie impossible');
    } }
    async function resetMemberPin(id) {
        if (!isAdmin())
            return;
        try {
            const r = await api(`/api/admin/members/${encodeURIComponent(id)}/reset-pin`, { method: 'POST', body: '{}' });
            const p=byId[id];
            rememberGeneratedCode(id,p?.pseudo||id,p?.rank||'',r.pin,'Code réinitialisé');
            openModal(`<h2>🔑 Nouveau code</h2><p><strong>${esc(p?.pseudo||'Joueur')}</strong> · ${p?.rank||''}</p><div class="new-pin">${r.pin}</div><div class="warning">L’ancien code est invalide et toutes les sessions du joueur ont été fermées. Pour un R4/R5, ce nouveau code sera obligatoire à la prochaine connexion.</div><div class="actions"><button class="btn gold" onclick="W.copyText('${r.pin}')">📋 Copier</button><button class="btn outline" onclick="W.closeModal();W.openAdminSection('access')">🔐 Codes & accès</button></div>`);
        }
        catch (e) {
            toast(e.message);
        }
    }
    function openChangePin() { openModal(`<h2>🔑 Changer mon code</h2><label class="field-label">Code actuel</label><input id="oldPinField" type="password" inputmode="numeric" maxlength="6"><label class="field-label" style="margin-top:10px">Nouveau code (6 chiffres)</label><input id="newPinField" type="password" inputmode="numeric" maxlength="6"><button class="btn gold full" onclick="W.changeMyPin()">Enregistrer</button>`); }
    async function changeMyPin() { const oldPin = document.getElementById('oldPinField').value, newPin = document.getElementById('newPinField').value; const ok = await mutate('/api/me/pin', { method: 'PUT', body: JSON.stringify({ oldPin, newPin }) }, 'Code personnel modifié'); if (ok)
        closeModal(); }
    window.W = {
        addCalendar, addAllCalendar, toggleAlerts, changeWeek, openExchange, publishMarketExchange, cancelMarketExchange, pickMyDateForMarket, executeMarketSwap, markUnavailable, showUnavailableChoice, openUnavailableDayPicker, saveUnavailableDayFromPicker, openUnavailablePeriod, syncUnavailablePeriodMin, saveUnavailablePeriod, saveUnavailableDay, removeUnavailableRange, removeUnavailable, showUnavailable, toggleRotation, showRotationStatus, openProfileInfo, goAlerts, closeAndOpenExchange, closeModal, saveAdminSettings, saveDay, clearDayOverride, adminToggleRotation, filterMembers, searchMembers, openMemberForm, saveMemberForm, deleteMember, renderRotationOrder, moveRotation, generateMessage, nextMessage, copyGeneratedMessage, openAdminSection, renderAdminHome, openSelfProfileEdit, saveSelfProfile, saveRotationRanks, copyText, resetMemberPin, downloadGeneratedCodesCsv, clearGeneratedCodes, changeLanguage, setPortalLanguage, showPortal, showTrainEntry, showPortalHelp, openPortalResource, togglePresenceList, refreshAdminPresence, openGuidePortal, openGameHelp, openGameLink, addGameLinkDraft, removeGameLinkDraft, saveGameLinks, openAdminAnalytics, renderAnalyticsMenu, openAnalyticsSub, renderTrainHistory, setAnalyticsRotationDays, setAnalyticsRotationPool, setAnalyticsRotationSort, setAnalyticsActivitySort, setAnalyticsSettingsFilter, setAnalyticsFilter, setAnalyticsHistorySort, setAnalyticsSearch, openChangePin, changeMyPin
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
