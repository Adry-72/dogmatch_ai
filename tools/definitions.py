"""OpenAI function-calling tool schemas per il DogMatch AI Orchestrator."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_dogs_semantic",
            "description": (
                "Cerca cani compatibili nella piattaforma usando similarità semantica "
                "su carattere e caratteristiche. Usalo quando l'utente cerca un compagno "
                "per il suo cane o chiede raccomandazioni di match. "
                "Estrai SEMPRE parametri semantici dalle richieste vaghe: "
                "'non irruento' → query='mite, calmo, tranquillo'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Descrizione semantica del carattere cercato, es: 'calmo, equilibrato, bassa energia'",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Filtri opzionali aggiuntivi",
                        "properties": {
                            "taglia": {
                                "type": "string",
                                "enum": ["Piccola", "Media", "Grande", "Gigante"],
                            },
                            "sesso": {"type": "string", "enum": ["M", "F"]},
                            "razza": {"type": "string"},
                            "eta_max": {"type": "integer"},
                            "disponibile_riproduzione": {"type": "boolean"},
                        },
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_user_profile",
            "description": (
                "Analizza in dettaglio il profilo di un utente per diagnosticare "
                "problemi di match o suggerire miglioramenti concreti. "
                "Usalo quando l'utente è frustrato o dichiara di non trovare match."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "UUID dell'utente da analizzare",
                    }
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_knowledge_base_info",
            "description": (
                "Recupera informazioni ufficiali su salute canina, test sanitari, "
                "leggi italiane sui cani e politiche DogMatch. "
                "Usalo per domande su vaccinazioni, accoppiamento, normative, "
                "comportamento, razze, aree cani."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": (
                            "Argomento da cercare, es: 'vaccinazioni', 'accoppiamento', "
                            "'politiche', 'comportamento', 'razze', 'leggi', 'aree cani', 'profilo'"
                        ),
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": (
                "Modifica un campo del profilo utente. "
                "Usalo SOLO su richiesta ESPLICITA e confermata dall'utente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "UUID dell'utente",
                    },
                    "field": {
                        "type": "string",
                        "enum": ["bio", "provincia", "regione", "telefono"],
                        "description": "Campo del profilo da aggiornare",
                    },
                    "value": {
                        "type": "string",
                        "description": "Nuovo valore per il campo",
                    },
                },
                "required": ["user_id", "field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Salva un fatto importante sull'utente per ricordarlo nelle sessioni future. "
                "Usalo quando l'utente rivela informazioni durature e rilevanti: "
                "nome del cane, razza cercata, obiettivo (riproduzione/compagnia), "
                "preferenze di match, intolleranze, provincia di interesse. "
                "NON usarlo per informazioni temporanee o già presenti nel profilo DB."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chiave": {
                        "type": "string",
                        "description": (
                            "Identificatore breve e normalizzato del fatto, "
                            "es: 'nome_cane', 'obiettivo', 'razza_preferita', 'provincia_preferita'"
                        ),
                    },
                    "valore": {
                        "type": "string",
                        "description": "Valore del fatto da ricordare",
                    },
                },
                "required": ["chiave", "valore"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_reminder",
            "description": (
                "Salva un promemoria di contenuto da aggiornare per l'utente. "
                "Usalo quando l'utente dice 'devo aggiornare X', 'ricordami di cambiare Y', "
                "o quando noti contenuti incompleti (foto mancante, bio vuota, scheda sanitaria incompleta). "
                "Il promemoria verrà mostrato nelle sessioni future finché non viene completato."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Identificatore breve del promemoria, es: 'foto_profilo', 'bio_cane', 'scheda_sanitaria'",
                    },
                    "testo": {
                        "type": "string",
                        "description": "Descrizione chiara di cosa aggiornare, es: 'Aggiungere foto profilo', 'Completare la bio del cane Rex'",
                    },
                },
                "required": ["id", "testo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_reminder",
            "description": (
                "Rimuove un promemoria completato. "
                "Usalo quando l'utente conferma di aver effettuato l'aggiornamento richiesto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "ID del promemoria da rimuovere, stesso usato in save_reminder",
                    },
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Cerca informazioni aggiornate sul web usando Tavily. "
                "Usalo per domande su: salute canina (sintomi, malattie, farmaci), "
                "addestramento, alimentazione, leggi italiane sui cani, notizie recenti, "
                "eventi cinofili, o qualsiasi argomento non coperto dalla knowledge base. "
                "Preferisci sempre get_knowledge_base_info per argomenti DogMatch; "
                "usa search_web quando la KB non ha la risposta o l'informazione potrebbe essere aggiornata."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termine di ricerca chiaro e specifico in italiano o inglese, es: 'displasia anca cane sintomi', 'legge microchip cani Italia 2024'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_stats",
            "description": (
                "Mostra le statistiche di attività dell'utente su DogMatch: "
                "match attivi, messaggi non letti, like ricevuti in attesa, like inviati. "
                "Usalo quando l'utente chiede 'quanti match ho', 'ho messaggi', "
                "'qualcuno ha messo like', 'come va la mia attività', 'ho richieste in attesa'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": (
                "Mostra gli slot orari liberi nelle aree cani certificate DogMatch per una data. "
                "Usalo quando l'utente vuole prenotare un'area cani o chiede disponibilità."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "Data nel formato YYYY-MM-DD, es: '2025-06-10'",
                    },
                    "area_id": {
                        "type": "integer",
                        "description": "ID dell'area specifica (opzionale). Se omesso mostra tutte le aree.",
                    },
                },
                "required": ["data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_area_slot",
            "description": (
                "Prenota uno slot da 1 ora in un'area cani certificata DogMatch. "
                "Usalo SOLO dopo aver mostrato la disponibilità con get_available_slots "
                "e ottenuto conferma esplicita dall'utente su area, data e orario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "area_id": {
                        "type": "integer",
                        "description": "ID dell'area cani da prenotare",
                    },
                    "data_ora": {
                        "type": "string",
                        "description": "Data e ora nel formato 'YYYY-MM-DD HH:MM', es: '2025-06-10 10:00'",
                    },
                },
                "required": ["area_id", "data_ora"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_bookings",
            "description": (
                "Mostra le prenotazioni attive dell'utente nelle aree cani. "
                "Usalo quando l'utente chiede le sue prenotazioni o vuole vedere i codici."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": (
                "Cancella una prenotazione tramite codice (formato DM-XXXXXXXX). "
                "Usalo quando l'utente vuole cancellare una prenotazione e fornisce il codice."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codice": {
                        "type": "string",
                        "description": "Codice prenotazione nel formato DM-XXXXXXXX",
                    },
                },
                "required": ["codice"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "moderation_flag",
            "description": (
                "Segnala contenuti inappropriati, richieste non etiche o pratiche "
                "contrarie alle politiche DogMatch."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Contenuto da segnalare",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Motivo della segnalazione",
                    },
                },
                "required": ["content", "reason"],
            },
        },
    },
]
