# Implementation Plan: user-service

## Overview

Il `user-service` è il microservizio di anagrafica utenti della piattaforma TechConf.
Questo piano implementa in modo incrementale la struttura a strati prevista dal design:
setup → persistenza → logica di dominio → endpoint HTTP → test.
Ogni task produce codice committabile e compilabile; i task di test sono opzionali (marcati con `*`) e affiancano immediatamente il codice che verificano.

---

## Tasks

- [x] 1. **Set up project structure and dependencies**
  - Creare le cartelle `services/user-service/app/`, `services/user-service/tests/unit/`, `services/user-service/tests/integration/`, `services/user-service/tests/contract/`
  - Creare `services/user-service/requirements.txt` con le dipendenze runtime (`flask`, `requests`) e di test (`pytest`, `pytest-cov`, `responses`, `hypothesis`)
  - Creare `services/user-service/pytest.ini` con la configurazione minima (testpaths, markers `req`)
  - Creare i file `__init__.py` vuoti nelle cartelle `app/`, `tests/`, `tests/unit/`, `tests/integration/`, `tests/contract/`
  - _Requirements: REQ-USR-P02, REQ-USR-P03_

  - [x] 1.1 Create directory structure and requirements.txt
    - Creare tutte le cartelle e i file `__init__.py`
    - Scrivere `requirements.txt` con versioni pinnate: `flask`, `requests`, `pytest`, `pytest-cov`, `responses`, `hypothesis`
    - Scrivere `pytest.ini` con `testpaths = tests` e registrazione del marker `req`
    - _Requirements: REQ-USR-P02, REQ-USR-P03_

- [x] 2. **Implement config.py**
  - Leggere `PORT` (default `5001`, intero 1–65535), `STORAGE_BACKEND` (default `memory`, valori ammessi: `memory`/`json`/`sqlite`, `sys.exit(1)` su valore non valido), `DATA_DIR` (default `./data`)
  - Esporre la classe `Config` e la funzione `load_config() -> Config`
  - Validazione all'avvio: se `STORAGE_BACKEND` è invalido → messaggio su stderr + `sys.exit(1)`; se `STORAGE_BACKEND` è `json`/`sqlite` e `DATA_DIR` non è scrivibile/esistente → `sys.exit(1)`
  - _Requirements: REQ-USR-P02, REQ-USR-P03_

  - [x] 2.1 Implement config.py with env var reading and validation
    - Scrivere classe `Config` (dataclass o namedtuple) con attributi `port`, `storage_backend`, `data_dir`
    - Scrivere `load_config()` con lettura `os.environ`, conversione tipi, validazione, `sys.exit(1)` sui casi di errore
    - _Requirements: REQ-USR-P02.1–7, REQ-USR-P03.4_

  - [x] 2.2 Write unit tests for config.py
    - Scrivere `tests/unit/test_config.py` con `monkeypatch` per le variabili d'ambiente
    - Verificare valori di default, parsing porta, terminazione su `STORAGE_BACKEND` non valido
    - Aggiungere marker `@pytest.mark.req("REQ-USR-P02")`
    - _Requirements: REQ-USR-P02, REQ-USR-P03_

- [ ] 3. **Implement main.py with /health endpoint and Flask bootstrap**
  - Scrivere `create_app(repo) -> Flask` che registra le routes e il blueprint
  - Implementare `GET /health` → `200 {"status": "ok", "service": "user-service"}` direttamente in `main.py` o in `routes.py`
  - Scrivere il bootstrap: `config = load_config()` → `repo = select_repository(config)` → `app = create_app(repo)` → `app.run(...)`
  - Aggiornare `services.yaml` nella root del progetto con `cwd` e `command` per `user-service` (porta 5001)
  - _Requirements: REQ-USR-E07, REQ-USR-P02_

  - [ ] 3.1 Implement main.py bootstrap and /health route
    - Scrivere `create_app(repo)` con registrazione blueprint
    - Implementare route `GET /health` con risposta `{"status": "ok", "service": "user-service"}`
    - Scrivere logica di selezione repository in `main.py`
    - Compilare voce `user-service` in `services.yaml`
    - _Requirements: REQ-USR-E07.1–2, REQ-USR-P02.7_

- [ ] 4. **Implement AbstractUserRepository and MemoryUserRepository**
  - Definire `AbstractUserRepository(ABC)` in `repository.py` con i metodi astratti: `create`, `get_by_id`, `get_by_email`, `list_users(role, email, page, page_size) → (items, total)`, `update`, `delete`
  - Implementare `MemoryUserRepository` con dizionario Python `{uuid_str: user_dict}`, operazioni O(n) per lista/filtri
  - _Requirements: REQ-USR-P03, REQ-USR-F01_

  - [ ] 4.1 Implement AbstractUserRepository interface and MemoryUserRepository
    - Scrivere `AbstractUserRepository` con ABC e metodi astratti documentati
    - Scrivere `MemoryUserRepository` con `dict` interno, implementare tutti i metodi inclusa paginazione e filtri
    - _Requirements: REQ-USR-P03.1, REQ-USR-P03.5_

  - [ ]* 4.2 Write unit tests for MemoryUserRepository
    - Scrivere `tests/unit/test_repository_memory.py`
    - Testare CRUD completo: `create`, `get_by_id`, `get_by_email`, `list_users` con filtro `role`/`email`, `update`, `delete`
    - Verificare che `get_by_id` ritorni `None` dopo `delete`
    - Aggiungere marker `@pytest.mark.req("REQ-USR-P03")`
    - _Requirements: REQ-USR-P03.1_

- [ ] 5. **Implement JsonUserRepository**
  - Implementare `JsonUserRepository(data_dir: Path)` in `repository.py`
  - File dati: `{DATA_DIR}/users.json`; creazione automatica se assente (array vuoto `[]`)
  - Creazione automatica `DATA_DIR` con `os.makedirs(data_dir, exist_ok=True)`
  - Scrittura atomica: scrivi su `users.json.tmp`, poi `os.replace` sul file definitivo
  - _Requirements: REQ-USR-P03.2_

  - [ ] 5.1 Implement JsonUserRepository with atomic writes
    - Scrivere `JsonUserRepository` che carica il file all'avvio e salva atomicamente ad ogni scrittura
    - Implementare tutti i metodi dell'interfaccia con logica di filtro/paginazione in memoria dopo la lettura
    - _Requirements: REQ-USR-P03.2_

  - [ ]* 5.2 Write unit tests for JsonUserRepository
    - Scrivere `tests/unit/test_repository_json.py` con fixture `tmp_path`
    - Testare stesso CRUD di `MemoryUserRepository`, più: verifica che il file `users.json.tmp` non rimanga dopo una scrittura, verifica che il file venga creato automaticamente
    - _Requirements: REQ-USR-P03.2_

- [ ] 6. **Implement SqliteUserRepository**
  - Implementare `SqliteUserRepository(data_dir: Path)` in `repository.py`
  - File dati: `{DATA_DIR}/users.db`; schema con `CREATE TABLE IF NOT EXISTS users (...)`
  - Usare esclusivamente `sqlite3` dalla libreria standard
  - Creazione automatica `DATA_DIR` con `os.makedirs`
  - Campi: `id TEXT PRIMARY KEY`, `first_name TEXT NOT NULL`, `last_name TEXT NOT NULL`, `email TEXT NOT NULL UNIQUE`, `company TEXT`, `role TEXT NOT NULL DEFAULT 'attendee'`, `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`
  - _Requirements: REQ-USR-P03.3, REQ-USR-P03.6_

  - [ ] 6.1 Implement SqliteUserRepository
    - Scrivere `SqliteUserRepository` con `sqlite3`, `CREATE TABLE IF NOT EXISTS`, implementare tutti i metodi
    - Gestire filtri con `WHERE` clause parametrizzata (no string interpolation)
    - Gestire paginazione con `LIMIT`/`OFFSET`
    - _Requirements: REQ-USR-P03.3, REQ-USR-P03.6_

  - [ ]* 6.2 Write unit tests for SqliteUserRepository
    - Scrivere `tests/unit/test_repository_sqlite.py` con fixture `tmp_path`
    - Testare stesso CRUD di `MemoryUserRepository`, più: verifica che la tabella `users` esista con le colonne attese
    - _Requirements: REQ-USR-P03.3_

- [ ] 7. **Implement business.py — create_user and domain exceptions**
  - Scrivere le eccezioni di dominio `UserNotFound(Exception)` e `EmailAlreadyExists(Exception)`
  - Implementare `create_user(repo, data) -> dict`: normalizza `email.lower()`, verifica unicità con `repo.get_by_email`, genera `uuid.uuid4()`, imposta `role='attendee'` se assente, valorizza `created_at`/`updated_at` con timestamp ISO 8601 UTC
  - `business.py` non deve importare Flask
  - _Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-F01, REQ-USR-F02_

  - [ ] 7.1 Implement create_user and domain exceptions
    - Scrivere eccezioni `UserNotFound`, `EmailAlreadyExists`
    - Scrivere `create_user` con normalizzazione email, unicità, UUID v4, timestamp
    - _Requirements: REQ-USR-B01.1, REQ-USR-B02.1, REQ-USR-F01.3–5, REQ-USR-F02.6_

  - [ ]* 7.2 Write unit tests for create_user
    - In `tests/unit/test_business.py`, usare `MemoryUserRepository` fresco per ogni test
    - Testare: creazione con successo, normalizzazione email (maiuscole → minuscolo), email duplicata → `EmailAlreadyExists`, role default → `attendee`, UUID nel risultato è valido v4
    - `@pytest.mark.req("REQ-USR-B01")`, `@pytest.mark.req("REQ-USR-B02")`
    - _Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-F01_

- [ ] 8. **Implement remaining business.py functions**
  - Implementare `get_user(repo, user_id) -> dict` — `repo.get_by_id` → `None` → raise `UserNotFound`
  - Implementare `list_users(repo, role, email, page, page_size) -> dict` — normalizza email filtro in minuscolo, chiama `repo.list_users`, restituisce dizionario `UserPage`
  - Implementare `replace_user(repo, user_id, data) -> dict` — full replace, `company→None` se assente, `role→attendee` se assente, aggiorna `updated_at`, verifica unicità email (self-update non è conflitto)
  - Implementare `update_user(repo, user_id, data) -> dict` — partial update, body `{}` → restituisce utente invariato (`updated_at` non viene aggiornato), verifica unicità email se email è nei campi
  - Implementare `delete_user(repo, user_id) -> None` — `repo.delete` → `False` → raise `UserNotFound`
  - _Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-B03, REQ-USR-E03, REQ-USR-E04, REQ-USR-E05, REQ-USR-E06_

  - [ ] 8.1 Implement get_user, list_users, replace_user, update_user, delete_user
    - Scrivere tutte e cinque le funzioni in `business.py`
    - Prestare attenzione alla semantica self-update (REQ-USR-B01.3) e al body vuoto in PATCH (REQ-USR-E05.2)
    - _Requirements: REQ-USR-B01.2–4, REQ-USR-B02.2–3, REQ-USR-B03.1–4, REQ-USR-E03, REQ-USR-E04, REQ-USR-E05, REQ-USR-E06_

  - [ ]* 8.2 Write unit tests for get_user, list_users, replace_user, update_user, delete_user
    - Aggiungere test in `tests/unit/test_business.py`
    - Testare: `get_user` con UUID inesistente → `UserNotFound`, `list_users` con filtro `role` e `email` (case-insensitive), `replace_user` self-update non è conflitto, `update_user` body `{}` → `updated_at` invariato, `delete_user` → `UserNotFound` alla seconda chiamata
    - `@pytest.mark.req("REQ-USR-B01")`, `@pytest.mark.req("REQ-USR-B03")`, `@pytest.mark.req("REQ-USR-E05")`
    - _Requirements: REQ-USR-B01.3, REQ-USR-B03, REQ-USR-E05.2, REQ-USR-E06_

- [ ] 9. **Checkpoint — unit tests pass**
  - Eseguire `pytest services/user-service/tests/unit/ -q` e verificare che tutti i test passino.
  - Assicurarsi che tutti i test passino; chiedere all'utente se sorgono domande.

- [ ] 10. **Implement routes.py — POST /api/v1/users**
  - Parsare il body JSON → `400 MALFORMED_JSON` se non parsabile
  - Validare struttura (campi obbligatori: `first_name`, `last_name`, `email`; tipi, lunghezze, formato email, `additionalProperties: false`, rifiuto del campo `id`) → `422 VALIDATION_ERROR`
  - Delegare a `business.create_user`; tradurre `EmailAlreadyExists` → `409 EMAIL_ALREADY_EXISTS`
  - Risposta `201` + header `Location: /api/v1/users/{id}` + body `User`
  - _Requirements: REQ-USR-E01, REQ-USR-F01.4, REQ-USR-F01.6, REQ-USR-F02, REQ-USR-P01_

  - [ ] 10.1 Implement POST /api/v1/users in routes.py
    - Scrivere il Flask route handler con parsing, validazione, delega a business, serializzazione risposta
    - Includere handler globale per `400 MALFORMED_JSON` (body non JSON)
    - _Requirements: REQ-USR-E01.1–8, REQ-USR-F01.4, REQ-USR-F01.6, REQ-USR-F02_

- [ ] 11. **Implement routes.py — GET /api/v1/users**
  - Leggere query params `page` (default 1), `page_size` (default 20), `role`, `email`
  - Validare: `page ≥ 1`, `page_size ∈ [1,100]`, `role` in enum, `email` non vuota → `422 VALIDATION_ERROR`
  - Delegare a `business.list_users`; risposta `200` con schema `UserPage`
  - Caso `page` oltre l'ultima pagina → `items: []`, `total` corretto
  - _Requirements: REQ-USR-E02, REQ-USR-B03, REQ-USR-P01_

  - [ ] 11.1 Implement GET /api/v1/users in routes.py
    - Scrivere il Flask route handler con parsing e validazione query params, delega a business, serializzazione `UserPage`
    - _Requirements: REQ-USR-E02.1–6, REQ-USR-B03.5–6_

- [ ] 12. **Implement routes.py — GET /api/v1/users/{id}**
  - Validare `{id}` come UUID v4 → `422 VALIDATION_ERROR` se non valido
  - Delegare a `business.get_user`; tradurre `UserNotFound` → `404 NOT_FOUND`
  - Risposta `200 User`
  - _Requirements: REQ-USR-E03, REQ-USR-P01_

  - [ ] 12.1 Implement GET /api/v1/users/{id} in routes.py
    - Scrivere il Flask route handler con validazione UUID, delega a business, gestione `UserNotFound`
    - Riusare la funzione di validazione UUID per tutti i route handler successivi
    - _Requirements: REQ-USR-E03.1–3_

- [ ] 13. **Implement routes.py — PUT /api/v1/users/{id}**
  - Validare `{id}` come UUID v4; parsare e validare il body (stessa validazione di POST)
  - Delegare a `business.replace_user`; tradurre `UserNotFound` → `404`, `EmailAlreadyExists` → `409`
  - Risposta `200 User` con `updated_at` aggiornato; `company→null` e `role→attendee` se omessi dal body
  - _Requirements: REQ-USR-E04, REQ-USR-P01_

  - [ ] 13.1 Implement PUT /api/v1/users/{id} in routes.py
    - Scrivere il Flask route handler con validazione UUID + body (full replace), delega a business, serializzazione
    - _Requirements: REQ-USR-E04.1–6_

- [ ] 14. **Implement routes.py — PATCH /api/v1/users/{id}**
  - Validare `{id}` come UUID v4; parsare e validare il body (tutti i campi opzionali, schema `UserUpdate`, `additionalProperties: false`)
  - Delegare a `business.update_user`; body `{}` → `200` invariato
  - Risposta `200 User`; `updated_at` aggiornato solo se almeno un campo modificato
  - _Requirements: REQ-USR-E05, REQ-USR-P01_

  - [ ] 14.1 Implement PATCH /api/v1/users/{id} in routes.py
    - Scrivere il Flask route handler con validazione UUID + body (partial update), delega a business
    - _Requirements: REQ-USR-E05.1–8_

- [ ] 15. **Implement routes.py — DELETE /api/v1/users/{id} and global error handlers**
  - Validare `{id}` come UUID v4; delegare a `business.delete_user`
  - Risposta `204` (no body); `UserNotFound` → `404 NOT_FOUND`
  - Registrare handler globale `MethodNotAllowed` → `405 METHOD_NOT_ALLOWED` + header `Allow`
  - Registrare handler globale per body non JSON → `400 MALFORMED_JSON`
  - Registrare handler globale per `422 VALIDATION_ERROR`
  - _Requirements: REQ-USR-E06, REQ-USR-E08, REQ-USR-P01_

  - [ ] 15.1 Implement DELETE /api/v1/users/{id} and global Flask error handlers
    - Scrivere il route handler DELETE con validazione UUID e gestione `UserNotFound`
    - Registrare `@app.errorhandler(MethodNotAllowed)` con header `Allow` e body standard
    - _Requirements: REQ-USR-E06.1–3, REQ-USR-E08.1–2, REQ-USR-P01.1–3_

- [ ] 16. **Checkpoint — smoke test all endpoints**
  - Eseguire `pytest services/user-service/tests/ -q` (tutti i test fino a qui) per verificare che tutto compili e le smoke test passino.
  - Assicurarsi che tutti i test passino; chiedere all'utente se sorgono domande.

- [ ] 17. **Write integration tests (Flask test client)**
  - Scrivere `tests/integration/test_user_api.py` usando il Flask test client con backend `memory`
  - Coprire tutti i casi IT-U01–IT-U08 elencati sotto
  - Ogni test aggiunge marker `@pytest.mark.req("REQ-USR-*")`
  - _Requirements: REQ-USR-E01–E08, REQ-USR-B01–B03, REQ-USR-F01–F02_

  - [ ]* 17.1 Write integration tests for all endpoints
    - IT-U01: `POST /api/v1/users` → 201, header `Location` presente, body schema `User` valido
    - IT-U02: `POST` con campo obbligatorio mancante → 422 `VALIDATION_ERROR`
    - IT-U03: `POST` con email duplicata case-insensitive → 409 `EMAIL_ALREADY_EXISTS`
    - IT-U04: `GET /api/v1/users/{id}` esistente → 200; UUID inesistente → 404 `NOT_FOUND`
    - IT-U05: `GET /api/v1/users` paginato; filtro `role` → solo utenti con quel role
    - IT-U06: `PUT` e `PATCH` → 200, `updated_at` aggiornato; `PATCH {}` → 200 invariato
    - IT-U07: `DELETE` → 204; `GET` sullo stesso id → 404
    - IT-U08: body JSON malformato → 400 `MALFORMED_JSON`; `GET /health` → 200 schema `Health`
    - _Requirements: REQ-USR-E01–E08, REQ-USR-B01.1–3, REQ-USR-B03.1_

- [ ] 18. **Write contract tests**
  - Scrivere `tests/contract/test_user_contract.py` usando `assert_matches_contract` da `contracts/validator.py`
  - Un test per endpoint/operazione: `POST /api/v1/users`, `GET /api/v1/users`, `GET /api/v1/users/{id}`, `PUT /api/v1/users/{id}`, `PATCH /api/v1/users/{id}`, `DELETE /api/v1/users/{id}`, `GET /health`
  - _Requirements: REQ-USR-F01, REQ-USR-P01_

  - [ ]* 18.1 Write contract tests for all endpoints
    - Importare `assert_matches_contract("user-service", METHOD, PATH, response)` per ogni endpoint
    - Verificare che le risposte di successo siano conformi agli schemi `User`, `UserPage`, `Health`, `Error`
    - _Requirements: REQ-USR-F01.1–7, REQ-USR-P01.1_

- [ ] 19. **Write property-based tests (Hypothesis)**
  - Scrivere `tests/unit/test_properties.py` usando `hypothesis`
  - Implementare le 8 proprietà formali del design; `@settings(max_examples=100)` su ogni test
  - Ogni test deve includere il commento `# Feature: user-service, Property N: <titolo>`
  - _Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-E02, REQ-USR-E03, REQ-USR-E06, REQ-USR-F01, REQ-USR-P03_

  - [ ]* 19.1 Write PBT for Property 1 — round-trip creazione/lettura
    - Generare dati utente validi con `hypothesis`; verificare che POST→GET restituisca tutti i campi obbligatori con gli stessi valori
    - Commento: `# Feature: user-service, Property 1: round-trip creazione/lettura`
    - **Validates: Requirements REQ-USR-E01, REQ-USR-E03, REQ-USR-F01**

  - [ ]* 19.2 Write PBT for Property 2 — normalizzazione email invariante
    - Generare email con `st.emails()` con case arbitrario; verificare che la risposta contenga sempre `email.lower()`
    - Commento: `# Feature: user-service, Property 2: normalizzazione email invariante`
    - **Validates: Requirements REQ-USR-B02**

  - [ ]* 19.3 Write PBT for Property 3 — unicità email globale (case-insensitive)
    - Creare un utente, tentare di crearne un secondo con la stessa email in varianti di case → 409; verificare che mai due utenti abbiano la stessa email normalizzata
    - Commento: `# Feature: user-service, Property 3: unicità email globale`
    - **Validates: Requirements REQ-USR-B01**

  - [ ]* 19.4 Write PBT for Property 4 — UUID v4 generato lato server
    - Verificare che l'`id` nella risposta POST sia un UUID v4 valido; se il body include un campo `id` → 422
    - Commento: `# Feature: user-service, Property 4: UUID v4 server-side`
    - **Validates: Requirements REQ-USR-F01.3, REQ-USR-F01.4**

  - [ ]* 19.5 Write PBT for Property 5 — consistenza paginazione
    - Con un dataset di N utenti e `page_size` arbitrario, verificare che la somma degli elementi su tutte le pagine coincida con `total`
    - Commento: `# Feature: user-service, Property 5: consistenza paginazione`
    - **Validates: Requirements REQ-USR-E02**

  - [ ]* 19.6 Write PBT for Property 6 — filtro per role
    - Creare utenti con role misti, filtrare per ogni role valido; verificare che tutti gli item restituiti abbiano esattamente quel role
    - Commento: `# Feature: user-service, Property 6: filtro per role`
    - **Validates: Requirements REQ-USR-B03.1**

  - [ ]* 19.7 Write PBT for Property 7 — eliminazione rende l'id irraggiungibile
    - Creare un utente, eliminarlo; verificare che GET, PUT, PATCH, DELETE sullo stesso id restituiscano tutti 404
    - Commento: `# Feature: user-service, Property 7: eliminazione irraggiungibile`
    - **Validates: Requirements REQ-USR-E06**

  - [ ]* 19.8 Write PBT for Property 8 — intercambiabilità backend
    - Eseguire la stessa sequenza CRUD su `MemoryUserRepository`, `JsonUserRepository` (tmp_path) e `SqliteUserRepository` (tmp_path); verificare che i risultati osservabili siano identici
    - Commento: `# Feature: user-service, Property 8: intercambiabilità backend`
    - **Validates: Requirements REQ-USR-P03**

- [ ] 20. **Final checkpoint — all tests pass with coverage ≥ 80%**
  - Eseguire `pytest services/user-service/tests/ --cov=services/user-service/app --cov-report=term-missing -q`
  - Verificare coverage ≥ 80%; correggere eventuali failing test prima di procedere.
  - Assicurarsi che tutti i test passino; chiedere all'utente se sorgono domande.

---

## Notes

- I task marcati con `*` sono opzionali e possono essere saltati per un MVP più rapido
- Ogni task referenzia i requisiti specifici per la tracciabilità
- I checkpoint (task 9, 16, 20) garantiscono validazione incrementale
- I PBT (task 19.*) validano le proprietà universali di correttezza formale; i unit test (task 2.2–8.2, 17.1, 18.1) validano casi specifici e casi limite
- La sequenza di implementazione rispetta il flusso di dipendenze: setup → persistenza → business → HTTP → test
- `business.py` non deve mai importare Flask; `routes.py` non deve contenere logica di dominio
- Il campo `id` non è mai accettato in input: qualsiasi presenza → 422 VALIDATION_ERROR
- Per il self-update email in PUT/PATCH: confrontare l'email normalizzata del body con l'email normalizzata dell'utente esistente; se coincidono non è un conflitto

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1", "6.1"] },
    { "id": 5, "tasks": ["5.2", "6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2", "8.1"] },
    { "id": 7, "tasks": ["8.2", "10.1"] },
    { "id": 8, "tasks": ["11.1"] },
    { "id": 9, "tasks": ["12.1"] },
    { "id": 10, "tasks": ["13.1"] },
    { "id": 11, "tasks": ["14.1"] },
    { "id": 12, "tasks": ["15.1"] },
    { "id": 13, "tasks": ["17.1"] },
    { "id": 14, "tasks": ["18.1", "19.1", "19.2", "19.3", "19.4", "19.5", "19.6", "19.7", "19.8"] }
  ]
}
```
