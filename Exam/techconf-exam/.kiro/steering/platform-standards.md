# TechConf — Platform Standards (vincolanti per tutti i servizi)

- Avvio: ogni servizio legge PORT dalla variabile d'ambiente e ci ascolta sopra.
  services.yaml nella root dichiara cwd e command per ogni servizio.
- Base path API: /api/v1/<risorsa>
- Formato: JSON, campi in snake_case
- id: sempre UUID v4 generato dal server, mai accettato in input
- Timestamp: ISO 8601 UTC, es. 2026-10-15T09:30:00Z; ogni risorsa ha
  created_at e updated_at
- Date: formato YYYY-MM-DD. Importi: numerici con 2 decimali, valuta EUR implicita
- Paginazione: query ?page=1&page_size=20 (max 100) →
  {"items": [...], "page": 1, "page_size": 20, "total": 57}
- Errori sempre nel formato:
  {"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}
- Status code:
  201 creazione (+ header Location) · 200 lettura/modifica · 204 cancellazione
  400 JSON malformato · 404 NOT_FOUND · 405 metodo non previsto
  409 conflitto · 422 VALIDATION_ERROR / REFERENCE_NOT_FOUND / regole di business
  503 DEPENDENCY_UNAVAILABLE
- Chiamate tra servizi: SOLO tramite variabili d'ambiente
  (USER_SERVICE_URL, EVENT_SERVICE_URL, REGISTRATION_SERVICE_URL),
  default http://localhost:<porta>. Timeout 2s.
  - 404 dal servizio chiamato → 422 REFERENCE_NOT_FOUND
  - timeout / connessione rifiutata / 5xx → 503 DEPENDENCY_UNAVAILABLE
- Health check: GET /health → 200 {"status": "ok", "service": "<nome>"}
- Persistenza: STORAGE_BACKEND = memory (default) | json | sqlite.
  File dati in DATA_DIR (default ./data, escluso da git).
  Il cambio backend non deve mai toccare la logica di business.
- Dipendenze Python: flask, requests (runtime); pytest, pytest-cov,
  responses (test)