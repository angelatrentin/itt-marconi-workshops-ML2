# Design Document — user-service

## Overview

Il `user-service` è il microservizio di base dell'architettura TechConf. Gestisce
l'anagrafica degli utenti della piattaforma (attendee, speaker, organizer) ed è la
**fonte di verità per l'identità degli utenti**.

A differenza degli altri servizi, `user-service` **non chiama nessun altro servizio**:
non ha dipendenze verso `event-service`, `registration-service` o
`notification-service`. È invece la direzione opposta: gli altri tre servizi chiamano
`user-service` per verificare l'esistenza e il ruolo di un utente prima di creare
registrazioni, inviare notifiche o associare eventi a speaker/organizzatori.

Il servizio espone un'API REST su porta `5001` (configurabile via `PORT`), rispetta i
Platform Standards comuni a tutta la piattaforma e supporta tre backend di persistenza
intercambiabili selezionati tramite la variabile d'ambiente `STORAGE_BACKEND`.

Il contratto OpenAPI ufficiale si trova in:
`contracts/openapi/user-service.yaml`
Quel file è la **fonte di verità** per schemi, codici di stato e formato delle risposte.

---

## Architecture

### Posizione nell'ecosistema TechConf

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT / ALTRI SERVIZI                       │
│                                                                     │
│   event-service ──────────────────────────────────────────────┐    │
│   registration-service ─────────────────────────────────────┐ │    │
│   notification-service ────────────────────────────────────┐│ │    │
│                                                            ││ │    │
│                                                            ▼▼ ▼    │
│                         ┌─────────────────┐                        │
│                         │   user-service  │  :5001                  │
│                         │  (questo doc)   │                        │
│                         └────────┬────────┘                        │
│                                  │                                 │
│                    ┌─────────────┼─────────────┐                   │
│                    ▼             ▼              ▼                   │
│              [memory]         [json]        [sqlite]               │
│             (dict Python)  (file JSON)    (file .db)               │
└─────────────────────────────────────────────────────────────────────┘
```

### Struttura a strati

```
┌──────────────────────────────────────────┐
│             routes.py (HTTP layer)       │  ← Flask, validazione input, HTTP I/O
├──────────────────────────────────────────┤
│            business.py (domain layer)    │  ← regole B01, B02, B03, F01, F02
├──────────────────────────────────────────┤
│  repository.py (persistence interface)   │  ← AbstractUserRepository
├───────────┬──────────────┬───────────────┤
│  Memory   │     JSON     │    SQLite      │  ← implementazioni concrete
└───────────┴──────────────┴───────────────┘
         config.py   main.py
```

La dipendenza scorre sempre verso il basso. `business.py` conosce solo
l'interfaccia `AbstractUserRepository`; non importa mai le implementazioni concrete.
Questo garantisce l'intercambiabilità del backend senza modificare la logica di
dominio (_Requirements: REQ-USR-P03_).

---

## Components and Interfaces

### `config.py` — Configurazione

Unico punto che legge le variabili d'ambiente. Espone una struttura dati (o un oggetto)
con i valori configurati e validati. Viene importato da `main.py` durante il bootstrap.

**Variabili lette:**

| Variabile         | Default   | Vincoli                                      |
|-------------------|-----------|----------------------------------------------|
| `PORT`            | `5001`    | Intero 1–65535                               |
| `STORAGE_BACKEND` | `memory`  | Uno tra `memory`, `json`, `sqlite`           |
| `DATA_DIR`        | `./data`  | Necessario solo per `json` e `sqlite`        |

**Validazione all'avvio** (_Requirements: REQ-USR-P02, REQ-USR-P03_):

- Se `STORAGE_BACKEND` contiene un valore diverso da `memory`, `json`, `sqlite` →
  il processo **termina** con un messaggio di errore che indica il valore non riconosciuto.
- Se `STORAGE_BACKEND` è `json` o `sqlite` e `DATA_DIR` non esiste o non è scrivibile →
  il processo **termina** con un messaggio di errore che indica la directory non utilizzabile.

```python
# Firma concettuale
class Config:
    port: int
    storage_backend: str          # "memory" | "json" | "sqlite"
    data_dir: Path | None         # None se backend è "memory"

def load_config() -> Config: ...  # legge os.environ, valida, termina in caso di errore
```

---

### `repository.py` — Persistenza

Definisce l'interfaccia `AbstractUserRepository` e le tre implementazioni concrete.
La scelta dell'implementazione avviene **una sola volta** in `main.py` in base al
valore di `STORAGE_BACKEND`; nessun altro modulo sa quale implementazione è in uso.

#### Interfaccia `AbstractUserRepository`

```python
class AbstractUserRepository(ABC):

    def create(self, user_data: dict) -> dict:
        """Persiste un nuovo utente. Restituisce il dizionario utente completo."""

    def get_by_id(self, user_id: str) -> dict | None:
        """Recupera utente per UUID. None se non esiste."""

    def get_by_email(self, email: str) -> dict | None:
        """Recupera utente per email (già normalizzata). None se non esiste."""

    def list_users(
        self,
        role: str | None,
        email: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        """
        Restituisce (items, total).
        items: lista utenti per la pagina richiesta dopo aver applicato i filtri.
        total: conteggio totale degli utenti che soddisfano i filtri (su tutte le pagine).
        """

    def update(self, user_id: str, fields: dict) -> dict | None:
        """
        Aggiorna i campi forniti. Restituisce l'utente aggiornato, None se non esiste.
        Gestisce sia il PUT (sostituzione completa) sia il PATCH (aggiornamento parziale).
        """

    def delete(self, user_id: str) -> bool:
        """Elimina utente. True se eliminato, False se non trovato."""
```

#### Implementazione `MemoryUserRepository`

- I dati vivono in un dizionario Python `{uuid: user_dict}`.
- Persi al riavvio del processo.
- Adatta per i test unitari: istanza fresca per ogni test.

#### Implementazione `JsonUserRepository`

- Dati serializzati in un file JSON all'interno di `DATA_DIR` (es. `users.json`).
- Se il file non esiste all'avvio, viene creato automaticamente con un array vuoto.
- `DATA_DIR` viene creata automaticamente se non esiste (con `os.makedirs`).
- **Atomicità**: ogni scrittura viene effettuata su un file temporaneo nella stessa
  directory, poi rinominata sul file definitivo (`os.replace`), evitando file
  parzialmente scritti in caso di crash.

#### Implementazione `SqliteUserRepository`

- Dati in un file `.db` dentro `DATA_DIR` (es. `users.db`).
- Schema della tabella:

```sql
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,  -- già in minuscolo
    company     TEXT,
    role        TEXT NOT NULL DEFAULT 'attendee',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

- Usa esclusivamente la libreria standard `sqlite3` (_Requirements: REQ-USR-P03_).
- `DATA_DIR` viene creata automaticamente se non esiste.
- `created_at` e `updated_at` sono stringhe ISO 8601 UTC.

#### Selezione del backend in `main.py`

```python
# Pseudocodice di selezione
repo: AbstractUserRepository
if config.storage_backend == "memory":
    repo = MemoryUserRepository()
elif config.storage_backend == "json":
    repo = JsonUserRepository(config.data_dir)
elif config.storage_backend == "sqlite":
    repo = SqliteUserRepository(config.data_dir)
```

---

### `business.py` — Logica di Dominio

Contiene tutta la logica di business. **Non importa Flask** e non ha conoscenza del
protocollo HTTP. Dipende esclusivamente dall'interfaccia `AbstractUserRepository`.

Il repository viene iniettato all'istanziazione o passato come parametro (dependency
injection), in modo che nei test si possa sostituire con un repository in memoria senza
toccare il codice di business.

#### Funzioni esposte

```python
def create_user(repo: AbstractUserRepository, data: dict) -> dict:
    """
    Normalizza email in minuscolo, verifica unicità, genera UUID v4,
    imposta role='attendee' se assente, imposta created_at/updated_at.
    Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-F01, REQ-USR-F02
    Solleva EmailAlreadyExists se email già presente (case-insensitive).
    """

def get_user(repo: AbstractUserRepository, user_id: str) -> dict:
    """
    Recupera utente per UUID.
    Requirements: REQ-USR-E03
    Solleva UserNotFound se UUID non esiste.
    """

def list_users(
    repo: AbstractUserRepository,
    role: str | None,
    email: str | None,
    page: int,
    page_size: int,
) -> dict:
    """
    Restituisce il dizionario UserPage con items, page, page_size, total.
    Normalizza email del filtro in minuscolo prima di passarla al repository.
    Requirements: REQ-USR-B03, REQ-USR-E02
    """

def replace_user(repo: AbstractUserRepository, user_id: str, data: dict) -> dict:
    """
    Sostituzione completa: company → None se assente, role → 'attendee' se assente.
    Aggiorna updated_at. Verifica unicità email (self-update non è conflitto).
    Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-E04
    Solleva UserNotFound o EmailAlreadyExists.
    """

def update_user(repo: AbstractUserRepository, user_id: str, data: dict) -> dict:
    """
    Aggiornamento parziale: aggiorna solo i campi forniti.
    Body vuoto {} → restituisce utente invariato (updated_at invariato).
    Verifica unicità email se email è nei campi forniti.
    Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-E05
    Solleva UserNotFound o EmailAlreadyExists.
    """

def delete_user(repo: AbstractUserRepository, user_id: str) -> None:
    """
    Elimina utente per UUID.
    Requirements: REQ-USR-E06
    Solleva UserNotFound se UUID non esiste.
    """
```

#### Eccezioni di dominio

```python
class UserNotFound(Exception): ...
class EmailAlreadyExists(Exception): ...
```

Queste eccezioni vengono catturate da `routes.py` e tradotte negli appropriati codici
HTTP e messaggi di errore.

---

### `routes.py` — Strato HTTP

Gestisce il routing Flask, la **validazione formale dell'input** (tipi, lunghezze,
campi obbligatori, `additionalProperties: false`) e la serializzazione delle risposte.
Delega interamente a `business.py` per la logica di dominio.

#### Responsabilità

1. **Parsing del body**: se il body non è JSON valido → `400 MALFORMED_JSON`.
2. **Validazione strutturale**: campi obbligatori, tipi, lunghezze, enum (`role`),
   formato email, `additionalProperties: false` → `422 VALIDATION_ERROR`.
3. **Validazione del path param `{id}`**: verifica che sia un UUID v4 valido → `422 VALIDATION_ERROR`.
4. **Validazione dei query param**: `page` ≥ 1, `page_size` ∈ [1,100], `role` in enum,
   `email` non vuota → `422 VALIDATION_ERROR`.
5. **Delega a business.py**: chiama la funzione appropriata con i dati già validati.
6. **Traduzione delle eccezioni di dominio** in risposte HTTP (vedi sezione Gestione Errori).
7. **Serializzazione**: costruisce il JSON di risposta conforme agli schemi del contratto
   OpenAPI (`User`, `UserPage`, `Health`, `Error`).
8. **Header `Location`**: aggiunto alla risposta 201 con valore `/api/v1/users/{id}`.
9. **Metodi non previsti**: Flask restituisce 405 automaticamente; `routes.py` configura
   l'handler globale per restituire il formato standard `METHOD_NOT_ALLOWED` e
   l'header `Allow` (_Requirements: REQ-USR-E08_).

#### Routing

| Metodo   | Endpoint                   | Funzione di business chiamata |
|----------|----------------------------|-------------------------------|
| `POST`   | `/api/v1/users`            | `create_user`                 |
| `GET`    | `/api/v1/users`            | `list_users`                  |
| `GET`    | `/api/v1/users/{id}`       | `get_user`                    |
| `PUT`    | `/api/v1/users/{id}`       | `replace_user`                |
| `PATCH`  | `/api/v1/users/{id}`       | `update_user`                 |
| `DELETE` | `/api/v1/users/{id}`       | `delete_user`                 |
| `GET`    | `/health`                  | risposta diretta (no business)|

---

### `main.py` — Entry Point

Bootstrap dell'applicazione: unico punto in cui avvengono l'inizializzazione della
configurazione, la selezione del backend di persistenza e la creazione dell'app Flask.

```
main.py:
  1. config = load_config()           ← legge e valida env vars; termina su errore
  2. repo = seleziona_repository(config)  ← istanzia il repository corretto
  3. app = create_app(repo)           ← crea Flask app, registra blueprint/routes
  4. app.run(host="0.0.0.0", port=config.port)
```

---

## Data Models

### Schema User (risposta)

Conforme a `User` del contratto OpenAPI (_Requirements: REQ-USR-F01_):

```
{
  "id":         "uuid-v4",
  "first_name": "string (1-50 chars)",
  "last_name":  "string (1-50 chars)",
  "email":      "string email (lowercase)",
  "company":    "string (1-100 chars) | null",
  "role":       "attendee | speaker | organizer",
  "created_at": "2026-10-15T09:30:00Z",
  "updated_at": "2026-10-15T09:30:00Z"
}
```

### Schema UserCreate (input)

Conforme a `UserCreate` del contratto OpenAPI. Campi `id`, `created_at`, `updated_at`
non sono accettati in input (_Requirements: REQ-USR-F01.4_).

```
{
  "first_name": "string (1-50 chars)"  [required],
  "last_name":  "string (1-50 chars)"  [required],
  "email":      "string email"         [required],
  "company":    "string (1-100) | null" [optional],
  "role":       "attendee|speaker|organizer" [optional, default: attendee]
}
```

### Schema UserUpdate (input PATCH)

Tutti i campi opzionali. Conforme a `UserUpdate` del contratto OpenAPI.

### Schema UserPage (risposta lista)

```
{
  "items":     [ ...User... ],
  "page":      1,
  "page_size": 20,
  "total":     57
}
```

`total` è il conteggio su **tutte** le pagine, non solo quella corrente
(_Requirements: REQ-USR-E02_).

### Regola di normalizzazione email

L'email viene convertita in minuscolo (`email.lower()`) in `business.py` prima di
qualsiasi confronto o persistenza (_Requirements: REQ-USR-B02_). Il repository riceve
e restituisce sempre l'email già normalizzata.

---

## Flusso Dati per Endpoint

### POST /api/v1/users

```
Client
  │
  ▼
routes.py
  ├─ Parsing JSON body → 400 se malformato
  ├─ Validazione strutturale (campi obbligatori, tipi, lunghezze, additionalProperties)
  │   → 422 VALIDATION_ERROR se non valido
  │
  ▼
business.create_user(repo, validated_data)
  ├─ email = email.lower()
  ├─ repo.get_by_email(email) → se trovato → raise EmailAlreadyExists
  ├─ id = uuid4()
  ├─ created_at = updated_at = now_iso8601_utc()
  ├─ role = data.get("role", "attendee")
  └─ repo.create(user_dict) → restituisce user_dict completo
  │
  ▼
routes.py
  ├─ Response 201
  ├─ Header Location: /api/v1/users/{id}
  └─ Body: serializza user_dict come JSON (schema User)
```

### GET /api/v1/users

```
Client
  │
  ▼
routes.py
  ├─ Legge query params: page (default 1), page_size (default 20), role, email
  ├─ Valida: page ≥ 1, page_size ∈ [1,100], role in enum, email non vuota
  │   → 422 VALIDATION_ERROR se non valido
  │
  ▼
business.list_users(repo, role, email, page, page_size)
  ├─ email = email.lower() se presente (filtro case-insensitive)
  └─ repo.list_users(role, email, page, page_size) → (items, total)
  │
  ▼
routes.py
  └─ Response 200: {"items": [...], "page": n, "page_size": n, "total": n}
```

### GET /api/v1/users/{id}

```
Client
  │
  ▼
routes.py
  ├─ Valida {id} come UUID v4 → 422 VALIDATION_ERROR se non valido
  │
  ▼
business.get_user(repo, id)
  └─ repo.get_by_id(id) → None → raise UserNotFound
  │
  ▼
routes.py
  └─ Response 200: user_dict serializzato come JSON (schema User)
     oppure 404 NOT_FOUND se UserNotFound catturato
```

### DELETE /api/v1/users/{id}

```
Client
  │
  ▼
routes.py
  ├─ Valida {id} come UUID v4 → 422 VALIDATION_ERROR se non valido
  │
  ▼
business.delete_user(repo, id)
  └─ repo.delete(id) → False → raise UserNotFound
  │
  ▼
routes.py
  └─ Response 204 (no body)
     oppure 404 NOT_FOUND se UserNotFound catturato
```

---

## Gestione della Persistenza

### Dependency Injection e intercambiabilità

Il repository viene istanziato in `main.py` e passato a tutte le funzioni di
`business.py`. Questo schema garantisce che la logica di business non dipenda mai
dall'implementazione concreta, soddisfacendo _Requirements: REQ-USR-P03_.

```
main.py ──instanzia──► MemoryUserRepository
                      │  oppure
                      ├──► JsonUserRepository(data_dir)
                      │  oppure
                      └──► SqliteUserRepository(data_dir)
                              │
                              ▼  (tutti implementano AbstractUserRepository)
business.py ◄──riceve per DI── repo
```

### Backend `memory`

- Struttura: `dict` Python `{uuid_str: user_dict}`.
- Operazioni O(n) per le liste/filtri (accettabile per il contesto d'esame).
- Nessuna dipendenza da file system.

### Backend `json`

- File: `{DATA_DIR}/users.json`
- Formato: array JSON di oggetti user.
- Creazione automatica: se il file non esiste → `[]`.
- Creazione automatica di `DATA_DIR`: `os.makedirs(data_dir, exist_ok=True)`.
- **Scrittura atomica**: scrittura su `users.json.tmp`, poi `os.replace("users.json.tmp", "users.json")`.
- Ogni operazione di scrittura rilegge il file, modifica in memoria, riscrive.

### Backend `sqlite`

- File: `{DATA_DIR}/users.db`
- Creazione automatica della tabella `users` con `CREATE TABLE IF NOT EXISTS`.
- Creazione automatica di `DATA_DIR`: `os.makedirs(data_dir, exist_ok=True)`.
- Uso esclusivo di `sqlite3` dalla libreria standard.
- La normalizzazione dell'email è già applicata prima di arrivare al repository;
  il campo `email` nella tabella è sempre in minuscolo.

### Avvio fallito

Se `STORAGE_BACKEND` è invalido o `DATA_DIR` è inaccessibile, il processo chiama
`sys.exit(1)` con un messaggio di errore leggibile su stderr, prima di avviare Flask
(_Requirements: REQ-USR-P02, REQ-USR-P03_).

---

## Riferimento al Contratto OpenAPI

Il file `contracts/openapi/user-service.yaml` è la **fonte di verità** per:
- Schemi di input (`UserCreate`, `UserUpdate`)
- Schemi di output (`User`, `UserPage`, `Health`, `Error`)
- Codici di stato HTTP previsti per ogni operazione
- Parametri di query e path

`routes.py` serializza le risposte in modo che siano conformi agli schemi del contratto.
I test di contratto usano `contracts/validator.py` con `assert_matches_contract` per
verificare automaticamente la conformità.

### Codici di errore esatti

| Codice HTTP | `error.code`            | Scenario                                              |
|-------------|-------------------------|-------------------------------------------------------|
| `400`       | `MALFORMED_JSON`        | Body non parsabile come JSON                         |
| `404`       | `NOT_FOUND`             | UUID non trovato (GET, PUT, PATCH, DELETE)            |
| `405`       | `METHOD_NOT_ALLOWED`    | Metodo HTTP non supportato sull'endpoint              |
| `409`       | `EMAIL_ALREADY_EXISTS`  | Email già usata da un altro utente                    |
| `422`       | `VALIDATION_ERROR`      | Campi mancanti, invalidi, tipi errati, id in input   |

---

## Correctness Properties

*Una proprietà è una caratteristica o comportamento che deve essere vera per tutte le
esecuzioni valide del sistema — essenzialmente, una dichiarazione formale su cosa il
sistema deve fare. Le proprietà fanno da ponte tra specifiche leggibili dall'uomo e
garanzie di correttezza verificabili automaticamente.*

### Property 1: Round-trip creazione/lettura

**Validates: Requirements REQ-USR-E01, REQ-USR-E03, REQ-USR-F01**

*Per qualsiasi* insieme valido di dati utente, un utente creato con POST deve essere
recuperabile tramite GET per lo stesso `id`, e la rappresentazione restituita deve
contenere tutti i campi obbligatori (`id`, `first_name`, `last_name`, `email`, `role`,
`created_at`, `updated_at`).

---

### Property 2: Normalizzazione email invariante

**Validates: Requirements REQ-USR-B02**

*Per qualsiasi* email fornita in input (con combinazione arbitraria di maiuscole e
minuscole), l'email restituita dal servizio in qualsiasi risposta contenente la risorsa
User deve essere uguale alla versione interamente in minuscolo dell'email originale.

---

### Property 3: Unicità email globale (case-insensitive)

**Validates: Requirements REQ-USR-B01**

*Per qualsiasi* insieme di utenti presenti nel sistema, non possono mai esistere due
utenti con la stessa email normalizzata in minuscolo. Qualsiasi tentativo di creare o
modificare un utente con un'email che — normalizzata — coincide con quella di un altro
utente deve restituire `409 EMAIL_ALREADY_EXISTS`.

---

### Property 4: UUID v4 generato lato server

**Validates: Requirements REQ-USR-F01.3, REQ-USR-F01.4**

*Per qualsiasi* creazione di utente valida, l'`id` restituito nella risposta deve
essere un UUID v4 sintatticamente valido, unico tra tutti gli utenti nel sistema e
diverso da qualsiasi `id` eventualmente fornito nel body della richiesta (che deve
essere rifiutato con 422).

---

### Property 5: Consistenza paginazione

**Validates: Requirements REQ-USR-E02**

*Per qualsiasi* dataset di utenti e qualsiasi `page_size` valido, la somma del numero
di elementi in tutte le pagine restituite deve essere uguale al valore del campo
`total` presente in ogni risposta di lista.

---

### Property 6: Filtro per role

**Validates: Requirements REQ-USR-B03.1**

*Per qualsiasi* lista di utenti nel sistema e qualsiasi `role` valido usato come
parametro di filtro, tutti gli utenti presenti nella risposta devono avere
esattamente quel `role` e nessun utente con `role` diverso deve essere incluso.

---

### Property 7: Eliminazione rende l'id irraggiungibile

**Validates: Requirements REQ-USR-E06**

*Per qualsiasi* utente eliminato con DELETE, qualsiasi operazione successiva
(GET, PUT, PATCH, DELETE) sullo stesso `id` deve restituire `404 NOT_FOUND`.

---

### Property 8: Intercambiabilità backend

**Validates: Requirements REQ-USR-P03**

*Per qualsiasi* sequenza di operazioni CRUD (creazione, lettura, aggiornamento,
cancellazione) eseguita sugli stessi dati, il risultato osservabile deve essere
identico indipendentemente dal backend di persistenza scelto (`memory`, `json`,
`sqlite`).

---

## Error Handling

### Mappa completa status HTTP → scenario

| Status | Codice errore           | Scenario                                                         | Requisito             |
|--------|-------------------------|------------------------------------------------------------------|-----------------------|
| `400`  | `MALFORMED_JSON`        | Body della richiesta non è JSON valido (non parsabile)           | REQ-USR-E01.4, E04.4, E05.7 |
| `404`  | `NOT_FOUND`             | UUID nel path non corrisponde ad alcun utente                    | REQ-USR-E03.2, E04.3, E05.5, E06.2 |
| `405`  | `METHOD_NOT_ALLOWED`    | Metodo HTTP non supportato sull'endpoint invocato                | REQ-USR-E08           |
| `409`  | `EMAIL_ALREADY_EXISTS`  | Email già usata da un altro utente (case-insensitive)            | REQ-USR-B01, E01.6, E04.6, E05.8 |
| `422`  | `VALIDATION_ERROR`      | Campo obbligatorio assente, tipo errato, lunghezza fuori range   | REQ-USR-F02, E01.5    |
| `422`  | `VALIDATION_ERROR`      | Campo `id` presente nel body di input                            | REQ-USR-F01.4         |
| `422`  | `VALIDATION_ERROR`      | Campo non previsto dallo schema (`additionalProperties: false`)  | REQ-USR-F01.6         |
| `422`  | `VALIDATION_ERROR`      | Valore `{id}` nel path non è un UUID v4 valido                   | REQ-USR-E03.3         |
| `422`  | `VALIDATION_ERROR`      | Parametro `role` non valido nella query string                   | REQ-USR-B03.5         |
| `422`  | `VALIDATION_ERROR`      | Parametro `role` o `email` è stringa vuota nella query string    | REQ-USR-B03.6         |
| `422`  | `VALIDATION_ERROR`      | `page < 1`, `page_size < 1` o `page_size > 100`                  | REQ-USR-E02.4         |

### Formato di risposta di errore

Tutti gli errori, senza eccezione, vengono restituiti nel formato standard
(_Requirements: REQ-USR-P01_):

```json
{
  "error": {
    "code": "UPPER_SNAKE",
    "message": "Descrizione leggibile dell'errore.",
    "details": { }
  }
}
```

Il campo `details` è opzionale; se presente può contenere informazioni sui campi
specifici che hanno causato l'errore (utile per `VALIDATION_ERROR`).

### Gestione 405 METHOD_NOT_ALLOWED

Flask gestisce automaticamente il 405 quando un metodo non è registrato su un
endpoint. `routes.py` registra un handler globale per `MethodNotAllowed` che:
1. Restituisce il corpo nel formato standard con `code: "METHOD_NOT_ALLOWED"`.
2. Include l'header `Allow` con i metodi consentiti.

### Health check indipendente dal backend

`GET /health` risponde sempre `200 {"status": "ok", "service": "user-service"}`,
indipendentemente dallo stato del backend di persistenza (_Requirements: REQ-USR-E07_).
Verifica solo che il processo HTTP sia attivo e risponda.

---

## Testing Strategy

### Struttura della cartella test

```
services/user-service/
├── app/
│   ├── routes.py
│   ├── business.py
│   ├── repository.py
│   ├── config.py
│   └── main.py
├── tests/
│   ├── unit/
│   │   ├── test_business.py          ← test logica di dominio
│   │   ├── test_repository_memory.py ← test backend memory
│   │   ├── test_repository_json.py   ← test backend json (tmp_path)
│   │   ├── test_repository_sqlite.py ← test backend sqlite (tmp_path)
│   │   └── test_config.py            ← test lettura variabili env
│   ├── integration/
│   │   └── test_user_api.py          ← test HTTP con Flask test client
│   └── contract/
│       └── test_user_contract.py     ← test contratto con assert_matches_contract
├── requirements.txt
└── pytest.ini
```

### Unit test

- **`test_business.py`**: instanzia `MemoryUserRepository` e chiama direttamente le
  funzioni di `business.py`. Testa le regole B01, B02, B03, F01, F02 con esempi
  specifici e casi limite.
- **`test_repository_*.py`**: verifica ogni implementazione del repository in
  isolamento. Per `json` e `sqlite` usa la fixture `tmp_path` di pytest per creare
  directory temporanee pulite per ogni test.
- **`test_config.py`**: usa `monkeypatch` di pytest per impostare variabili
  d'ambiente e verifica i valori di default e la terminazione su valori invalidi.

### Test HTTP (integration con Flask test client)

`test_user_api.py` usa il test client Flask (nessun server reale). Ogni test
riceve una fresh app con backend `memory`. Copre tutti gli endpoint con i casi
previsti dai requisiti, inclusi i codici di errore.

Marker pytest per tracciabilità:

```python
@pytest.mark.req("REQ-USR-B01")
def test_email_uniqueness_case_insensitive(): ...
```

### Test di contratto

`test_user_contract.py` usa `contracts/validator.py` con `assert_matches_contract`
per verificare che ogni risposta dell'API sia conforme agli schemi del contratto
OpenAPI:

```python
from contracts.validator import assert_matches_contract

def test_create_user_contract(client):
    response = client.post("/api/v1/users", json={...})
    assert_matches_contract("user-service", "POST", "/api/v1/users", response)
```

Ogni endpoint (POST, GET lista, GET per id, PUT, PATCH, DELETE, health) ha un test
di contratto corrispondente.

### Property-Based Testing (PBT)

Libreria: **`hypothesis`** (da aggiungere a `requirements.txt` nei test).

Ogni proprietà formale identificata nella sezione Correctness Properties viene
implementata come un singolo test hypothesis. Configurazione minima: 100 esempi
per proprietà (default hypothesis).

Tag di tracciabilità richiesto come commento su ogni test:

```python
# Feature: user-service, Property 2: normalizzazione email invariante
@given(email=emails())
@settings(max_examples=100)
def test_email_normalization(client, email): ...
```

Le strategie hypothesis generate (`st.text`, `st.emails()`, `st.sampled_from(...)`)
coprono:
- Email con varianti di case arbitrarie
- `first_name` e `last_name` con lunghezze da 1 a 50 caratteri
- `role` campionato da `["attendee", "speaker", "organizer"]`
- `page` e `page_size` negli intervalli validi
- UUID v4 generati con `uuid.uuid4()`

### Coverage

Obiettivo: **≥ 80%** misurato con `pytest-cov`.

```bash
pytest services/user-service/tests/ --cov=services/user-service/app \
       --cov-report=term-missing -q
```

### Dipendenze test (`requirements.txt` del servizio)

```
pytest
pytest-cov
responses
hypothesis
```
