# Requirements Document

## Introduction

Il `user-service` è il microservizio obbligatorio di TechConf che gestisce l'anagrafica degli utenti della piattaforma. Espone le operazioni CRUD sugli utenti (partecipanti, speaker, organizzatori) ed è la fonte di verità per l'identità degli utenti. Viene chiamato da `event-service`, `registration-service` e `notification-service` per verificare l'esistenza e il ruolo degli utenti. Il servizio è accessibile sulla porta 5001, rispetta i Platform Standards comuni a tutta la piattaforma e supporta tre backend di persistenza intercambiabili: `memory`, `json`, `sqlite`.

---

## Glossary

- **User_Service**: il microservizio che implementa l'anagrafica utenti di TechConf, in ascolto sulla porta indicata dalla variabile d'ambiente `PORT` (default 5001).
- **User**: risorsa che rappresenta un utente della piattaforma (attendee, speaker, organizer).
- **Role**: ruolo dell'utente; valori ammessi: `attendee`, `speaker`, `organizer`.
- **UUID**: identificatore unico universale v4, generato dal server, mai accettabile in input.
- **ISO 8601 UTC**: formato data/ora (`YYYY-MM-DDTHH:MM:SSZ`) usato per tutti i timestamp.
- **STORAGE_BACKEND**: variabile d'ambiente che seleziona il backend di persistenza (`memory`, `json`, `sqlite`).
- **DATA_DIR**: directory in cui vengono scritti i file di dati per i backend `json` e `sqlite` (default `./data`).
- **Platform Standards**: l'insieme di regole comuni a tutti i microservizi TechConf definite nel file `.kiro/steering/platform-standards.md`.

---

## Requirements

---

### REQ-USR-F01 — Struttura della risorsa User

**User story:** As a platform consumer, I want every user resource to include a consistent set of fields, so that I can rely on a stable interface regardless of how the data is stored.

#### Criteri di accettazione

1. THE User_Service SHALL rappresentare ogni utente con i seguenti campi obbligatori in output: `id`, `first_name`, `last_name`, `email`, `role`, `created_at`, `updated_at`.
2. THE User_Service SHALL includere il campo opzionale `company` nella risposta, con valore `null` se non fornito.
3. THE User_Service SHALL generare `id` come UUID v4 lato server ad ogni creazione di utente.
4. IF una richiesta di creazione o modifica include il campo `id`, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` (il campo `id` non è mai accettato in input).
5. WHEN un utente viene creato, THE User_Service SHALL valorizzare `created_at` e `updated_at` con il timestamp corrente ISO 8601 UTC; entrambi i campi non sono modificabili dal client nelle richieste successive.
6. IF una richiesta include un campo non previsto dallo schema `UserCreate` o `UserUpdate`, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` (additionalProperties: false).
7. THE User_Service SHALL restituire tutti i campi in formato `snake_case` e in JSON.

---

### REQ-USR-F02 — Valori e vincoli dei campi

**User story:** As a platform administrator, I want field constraints to be enforced consistently, so that data quality is guaranteed across all user records.

#### Criteri di accettazione

1. IF `first_name` è assente, stringa vuota, o supera 50 caratteri, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` indicando il campo non valido.
2. IF `last_name` è assente, stringa vuota, o supera 50 caratteri, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` indicando il campo non valido.
3. IF `email` è assente o non rispetta il formato email valido (come definito dallo schema OpenAPI `format: email`), THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` indicando il campo non valido.
4. IF `company` è presente e non è `null` e non è una stringa di lunghezza compresa tra 1 e 100 caratteri, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` indicando il campo non valido.
5. IF `role` è presente e il suo valore non è uno tra `attendee`, `speaker`, `organizer`, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` indicando il campo non valido.
6. WHEN il campo `role` non è presente in una richiesta di **creazione**, THE User_Service SHALL impostare il valore di default `attendee`.
7. WHEN uno o più campi obbligatori (`first_name`, `last_name`, `email`) sono assenti nella richiesta, THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR` indicando il/i campo/i mancanti.
8. WHEN un campo non rispetta i vincoli di tipo, lunghezza o formato, THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`; la risposta SHOULD indicare quali campi specifici hanno violato i vincoli.

---

### REQ-USR-B01 — Univocità dell'email (case-insensitive)

**User story:** As a platform administrator, I want email addresses to be unique regardless of case, so that the same person cannot register twice with different capitalizations.

#### Criteri di accettazione

1. IF viene richiesta la creazione di un utente con un'email che, convertita in minuscolo, corrisponde all'email (già in minuscolo) di un utente esistente, THEN THE User_Service SHALL rispondere 409 con codice di errore `EMAIL_ALREADY_EXISTS`.
2. IF viene richiesta la modifica (PUT o PATCH) dell'email di un utente con un'email che, convertita in minuscolo, corrisponde all'email di un **altro** utente esistente, THEN THE User_Service SHALL rispondere 409 con codice di errore `EMAIL_ALREADY_EXISTS`.
3. IF viene richiesta la modifica (PUT o PATCH) dell'email di un utente con la stessa email già assegnata a quell'utente (self-update), THEN THE User_Service SHALL accettare la richiesta senza errore.
4. THE User_Service SHALL eseguire il confronto di unicità normalizzando entrambe le email in minuscolo, in modo che `user@example.com`, `User@Example.com` e `USER@EXAMPLE.COM` siano considerati identici.
5. WHEN la risposta di errore 409 viene restituita, THE User_Service SHALL includere il codice `EMAIL_ALREADY_EXISTS` nel campo `error.code` del body JSON.

_Test di riferimento: IT-U03_

---

### REQ-USR-B02 — Normalizzazione dell'email in minuscolo

**User story:** As a platform consumer, I want emails to be stored in lowercase, so that lookups and comparisons are consistent.

#### Criteri di accettazione

1. WHEN viene ricevuta una richiesta di creazione utente (POST) contenente un campo `email`, THE User_Service SHALL convertire il valore di `email` interamente in minuscolo prima di persistere la risorsa.
2. WHEN viene ricevuta una richiesta di modifica utente (PUT o PATCH) contenente un campo `email`, THE User_Service SHALL convertire il valore di `email` interamente in minuscolo prima di persistere la risorsa.
3. THE User_Service SHALL restituire il campo `email` sempre in minuscolo in qualsiasi risposta contenente la risorsa User, indipendentemente dal valore originale fornito dal client.

---

### REQ-USR-B03 — Filtri della lista utenti

**User story:** As a service consumer, I want to filter users by role and email, so that I can efficiently find specific subsets of users.

#### Criteri di accettazione

1. WHEN il parametro `role` è presente nella query string, THE User_Service SHALL restituire solo gli utenti con il ruolo esattamente corrispondente al valore fornito.
2. WHEN il parametro `email` è presente nella query string, THE User_Service SHALL restituire solo gli utenti la cui email corrisponde esattamente al valore fornito con confronto case-insensitive (normalizzazione in minuscolo su entrambi i lati).
3. WHEN entrambi i parametri `role` ed `email` sono presenti, THE User_Service SHALL applicare entrambi i filtri in combinazione (AND logico): vengono restituiti solo gli utenti che soddisfano entrambi.
4. WHEN nessun filtro è presente, THE User_Service SHALL restituire tutti gli utenti paginati.
5. IF il valore del parametro `role` non è uno tra `attendee`, `speaker`, `organizer`, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`.
6. IF il parametro `role` o `email` è presente con una stringa vuota (`""`), THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`.

_Test di riferimento: IT-U05_

---

### REQ-USR-E01 — Creazione utente (POST /api/v1/users)

**User story:** As a client application, I want to create a new user by posting valid data, so that the user is registered in the platform and immediately retrievable.

#### Criteri di accettazione

1. WHEN viene inviata una richiesta POST a `/api/v1/users` con un body JSON valido contenente i campi obbligatori, THE User_Service SHALL creare l'utente e rispondere 201.
2. WHEN la creazione ha successo, THE User_Service SHALL includere nella risposta 201 l'header `Location` con il valore `/api/v1/users/{id}` dell'utente appena creato.
3. WHEN la creazione ha successo, THE User_Service SHALL restituire nel body la rappresentazione completa dell'utente creato conforme allo schema `User` del contratto OpenAPI, con tutti i campi obbligatori presenti.
4. IF il body della richiesta è JSON malformato (non parsabile), THEN THE User_Service SHALL rispondere 400 con codice di errore `MALFORMED_JSON` nel formato standard degli errori.
5. IF un campo obbligatorio (`first_name`, `last_name`, `email`) è assente, o un campo non rispetta i vincoli di tipo, lunghezza o formato, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`.
6. IF l'email fornita è già presente nel sistema (confronto case-insensitive), THEN THE User_Service SHALL rispondere 409 con codice di errore `EMAIL_ALREADY_EXISTS`.
7. WHEN la creazione ha successo e il campo `role` non è stato fornito, THE User_Service SHALL restituire `"role": "attendee"` nella rappresentazione dell'utente creato.
8. WHEN la creazione ha successo, THE User_Service SHALL restituire l'email nel body in minuscolo, indipendentemente dalle maiuscole fornite in input.

_Test di riferimento: IT-U01, IT-U02, IT-U03, IT-U08_

---

### REQ-USR-E02 — Lista utenti (GET /api/v1/users)

**User story:** As a service consumer, I want to retrieve a paginated list of users with optional filters, so that I can browse or search the user registry efficiently.

#### Criteri di accettazione

1. WHEN viene inviata una richiesta GET a `/api/v1/users` senza parametri, THE User_Service SHALL rispondere 200 con la lista paginata di tutti gli utenti usando i valori di default (`page=1`, `page_size=20`).
2. WHEN vengono forniti i parametri `page` e `page_size`, THE User_Service SHALL rispondere 200 con la pagina richiesta conforme allo schema `UserPage`, applicando la dimensione specificata.
3. THE User_Service SHALL restituire la risposta di lista nel formato `{"items": [...], "page": <n>, "page_size": <n>, "total": <n>}` conforme allo schema `UserPage`; il campo `total` rappresenta il numero di utenti corrispondenti ai filtri attivi su tutte le pagine.
4. IF `page_size` supera 100, o `page` è inferiore a 1, o `page_size` è inferiore a 1, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`.
5. WHEN i filtri `role` e/o `email` sono presenti, THE User_Service SHALL applicarli come descritto in REQ-USR-B03.
6. WHEN `page` è superiore all'ultima pagina disponibile dati i filtri e la dimensione, THE User_Service SHALL rispondere 200 con `items` vuoto (`[]`) e i campi `page`, `page_size`, `total` corretti.

_Test di riferimento: IT-U05_

---

### REQ-USR-E03 — Lettura utente per ID (GET /api/v1/users/{id})

**User story:** As a service consumer, I want to retrieve a specific user by their UUID, so that I can verify user existence and access their details.

#### Criteri di accettazione

1. WHEN viene inviata una richiesta GET a `/api/v1/users/{id}` con un UUID esistente, THE User_Service SHALL rispondere 200 con la rappresentazione completa dell'utente conforme allo schema `User`; il campo `id` nella risposta deve essere uguale all'UUID presente nel path.
2. IF l'UUID fornito nel path è sintatticamente valido ma non corrisponde ad alcun utente, THEN THE User_Service SHALL rispondere 404 con codice di errore `NOT_FOUND`.
3. IF il valore `{id}` nel path non è un UUID v4 valido (formato non conforme a `uuid`), THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`.

_Test di riferimento: IT-U04_

---

### REQ-USR-E04 — Sostituzione completa utente (PUT /api/v1/users/{id})

**User story:** As a client application, I want to replace all fields of an existing user in one operation, so that I can keep the user record up to date.

#### Criteri di accettazione

1. WHEN viene inviata una richiesta PUT a `/api/v1/users/{id}` con un body JSON valido, THE User_Service SHALL sostituire i campi modificabili (`first_name`, `last_name`, `email`, `company`, `role`) dell'utente e rispondere 200 con la rappresentazione aggiornata conforme allo schema `User`; se `company` è omesso viene impostato a `null`, se `role` è omesso viene impostato a `attendee`.
2. WHEN la sostituzione ha successo, THE User_Service SHALL aggiornare il campo `updated_at` al timestamp corrente ISO 8601 UTC; `created_at` rimane invariato.
3. IF l'UUID non corrisponde ad alcun utente, THEN THE User_Service SHALL rispondere 404 con codice di errore `NOT_FOUND`.
4. IF il body della richiesta è JSON malformato, THEN THE User_Service SHALL rispondere 400 con codice di errore `MALFORMED_JSON`.
5. IF un campo obbligatorio è assente o non valido, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`.
6. IF la nuova email è già usata da un **altro** utente (confronto case-insensitive), THEN THE User_Service SHALL rispondere 409 con codice di errore `EMAIL_ALREADY_EXISTS`; la stessa email dell'utente che si sta aggiornando non è considerata un conflitto.

_Test di riferimento: IT-U06_

---

### REQ-USR-E05 — Aggiornamento parziale utente (PATCH /api/v1/users/{id})

**User story:** As a client application, I want to update only specific fields of an existing user, so that I can make targeted changes without overwriting unmodified data.

#### Criteri di accettazione

1. WHEN viene inviata una richiesta PATCH a `/api/v1/users/{id}` con un body JSON contenente uno o più campi validi, THE User_Service SHALL aggiornare solo i campi forniti e rispondere 200 con la rappresentazione aggiornata conforme allo schema `User`.
2. WHEN il body PATCH contiene zero campi (oggetto JSON vuoto `{}`), THE User_Service SHALL rispondere 200 con la rappresentazione corrente dell'utente invariata.
3. WHEN l'aggiornamento parziale ha successo e almeno un campo è stato modificato, THE User_Service SHALL aggiornare il campo `updated_at` al timestamp corrente ISO 8601 UTC; `created_at` rimane invariato.
4. THE User_Service SHALL accettare in PATCH zero o più campi tra: `first_name`, `last_name`, `email`, `company`, `role`.
5. IF l'UUID non corrisponde ad alcun utente, THEN THE User_Service SHALL rispondere 404 con codice di errore `NOT_FOUND`.
6. IF un campo fornito non rispetta i vincoli di tipo, lunghezza o formato, THEN THE User_Service SHALL rispondere 422 con codice di errore `VALIDATION_ERROR`.
7. IF il body della richiesta è JSON malformato, THEN THE User_Service SHALL rispondere 400 con codice di errore `MALFORMED_JSON`.
8. IF la nuova email è già usata da un **altro** utente (confronto case-insensitive), THEN THE User_Service SHALL rispondere 409 con codice di errore `EMAIL_ALREADY_EXISTS`.

_Test di riferimento: IT-U06_

---

### REQ-USR-E06 — Cancellazione utente (DELETE /api/v1/users/{id})

**User story:** As a platform administrator, I want to delete a user by their UUID, so that I can remove records that are no longer needed.

#### Criteri di accettazione

1. WHEN viene inviata una richiesta DELETE a `/api/v1/users/{id}` con un UUID esistente, THE User_Service SHALL eliminare l'utente e rispondere 204 senza body.
2. IF l'UUID non corrisponde ad alcun utente (incluso il caso in cui l'utente sia già stato eliminato), THEN THE User_Service SHALL rispondere 404 con codice di errore `NOT_FOUND`.
3. IF un utente è stato eliminato, THEN qualsiasi richiesta su `/api/v1/users/{id}` (GET, PUT, PATCH, DELETE) con lo stesso UUID SHALL restituire 404 con codice di errore `NOT_FOUND`.

_Test di riferimento: IT-U07_

---

### REQ-USR-E07 — Health check (GET /health)

**User story:** As an infrastructure operator, I want a health endpoint to confirm the service is running, so that orchestration and monitoring tools can verify its availability.

#### Criteri di accettazione

1. WHEN viene inviata una richiesta GET a `/health`, THE User_Service SHALL rispondere 200 con il body `{"status": "ok", "service": "user-service"}` conforme allo schema `Health`.
2. IF il backend di persistenza è irraggiungibile o non risponde entro 2 secondi, THEN THE User_Service SHALL comunque rispondere 200 a `GET /health` con il body `{"status": "ok", "service": "user-service"}` (l'health check verifica la vivacità del processo HTTP, non del backend).

_Test di riferimento: IT-U08_

---

### REQ-USR-E08 — Gestione del metodo non previsto

**User story:** As a client developer, I want the service to reject unsupported HTTP methods with a clear error, so that API misuse is immediately evident.

#### Criteri di accettazione

1. WHEN viene invocato un metodo HTTP non previsto su `/api/v1/users` o su `/api/v1/users/{id}` (ad esempio DELETE su `/api/v1/users` o POST su `/api/v1/users/{id}`), THE User_Service SHALL rispondere 405 con un body di errore nel formato standard contenente il codice `METHOD_NOT_ALLOWED`.
2. WHEN il User_Service restituisce 405, THE User_Service SHALL includere nella risposta l'header `Allow` con la lista dei metodi HTTP consentiti sull'endpoint invocato.

---

### REQ-USR-P01 — Formato degli errori

**User story:** As a service consumer, I want all error responses to follow a consistent structure, so that I can handle errors programmatically without inspecting the message text.

#### Criteri di accettazione

1. THE User_Service SHALL restituire tutti gli errori nel formato `{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}` conforme allo schema `Error` del contratto OpenAPI; il campo `details` è opzionale e può essere omesso se non ci sono dettagli aggiuntivi.
2. THE User_Service SHALL utilizzare i seguenti codici di errore esatti: `VALIDATION_ERROR` (422), `NOT_FOUND` (404), `EMAIL_ALREADY_EXISTS` (409), `MALFORMED_JSON` (400), `METHOD_NOT_ALLOWED` (405) secondo quanto definito nei requisiti specifici.
3. IF il body della richiesta è JSON non parsabile, THEN THE User_Service SHALL rispondere 400 con codice di errore `MALFORMED_JSON` nel formato standard.

---

### REQ-USR-P02 — Avvio e configurazione

**User story:** As a platform operator, I want the service to read its configuration from environment variables, so that the same artifact can run in any environment without code changes.

#### Criteri di accettazione

1. WHEN il processo viene avviato, THE User_Service SHALL leggere la porta di ascolto dalla variabile d'ambiente `PORT` e accettare connessioni TCP su quel numero di porta (valore intero compreso tra 1 e 65535).
2. IF la variabile d'ambiente `PORT` è assente all'avvio, THEN THE User_Service SHALL usare la porta 5001.
3. WHEN il processo viene avviato, THE User_Service SHALL leggere il backend di persistenza dalla variabile d'ambiente `STORAGE_BACKEND`; i valori ammessi sono `memory`, `json`, `sqlite`.
4. IF la variabile d'ambiente `STORAGE_BACKEND` è assente all'avvio, THEN THE User_Service SHALL selezionare il backend `memory`.
5. IF la variabile d'ambiente `STORAGE_BACKEND` contiene un valore diverso da `memory`, `json` o `sqlite`, THEN THE User_Service SHALL terminare il processo con un messaggio di errore indicante il valore non riconosciuto.
6. IF `STORAGE_BACKEND` è `json` o `sqlite` e la variabile d'ambiente `DATA_DIR` è assente all'avvio, THEN THE User_Service SHALL usare il percorso `./data` come directory dei file di dati.
7. WHEN il processo viene avviato con il comando dichiarato in `services.yaml` e le variabili d'ambiente impostate dall'esterno, THE User_Service SHALL rispondere 200 a `GET /health` entro 10 secondi dall'avvio del processo.

---

### REQ-USR-P03 — Persistenza multi-backend

**User story:** As a developer, I want to switch storage backends without modifying business logic, so that the service can run in-memory for tests and on disk for production.

#### Criteri di accettazione

1. THE User_Service SHALL supportare il backend `memory`: i dati sono mantenuti in strutture Python e vanno persi al riavvio del processo.
2. WHEN il backend `json` è selezionato, THE User_Service SHALL persistere i dati in un file JSON dentro `DATA_DIR`; IF il file non esiste all'avvio, THEN THE User_Service SHALL crearlo automaticamente.
3. WHEN il backend `sqlite` è selezionato, THE User_Service SHALL persistere i dati in un file `.db` dentro `DATA_DIR`, usando esclusivamente la libreria standard `sqlite3`.
4. IF il backend è `json` o `sqlite` e `DATA_DIR` non è scrivibile o non esiste, THEN THE User_Service SHALL terminare il processo all'avvio con un messaggio di errore che indica la directory non utilizzabile.
5. THE User_Service SHALL garantire che il cambio di `STORAGE_BACKEND` non richieda alcuna modifica alla logica di business; la selezione del backend avviene una sola volta all'avvio tramite il valore di `STORAGE_BACKEND`.
6. THE User_Service SHALL usare esclusivamente librerie standard Python per la persistenza (`json`, `sqlite3`): nessun DBMS esterno è ammesso.
