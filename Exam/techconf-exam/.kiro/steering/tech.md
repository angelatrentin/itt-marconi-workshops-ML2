# TechConf — Stack tecnologico

- Linguaggio: Python 3.12
- Framework HTTP: Flask
- Chiamate tra servizi: libreria requests, timeout 2s
- Test: pytest, pytest-cov, responses (per mockare le chiamate HTTP)
- Persistenza: solo librerie standard (json, sqlite3) — nessun DBMS esterno
  - backend "memory": dati in strutture Python, persi al riavvio
  - backend "json": un file JSON per risorsa/servizio dentro DATA_DIR
  - backend "sqlite": un file .db dentro DATA_DIR, usando sqlite3
  - il backend si sceglie con la variabile d'ambiente STORAGE_BACKEND
- Nessun container/Docker: ogni servizio è un normale processo Python avviato
  con il comando indicato in services.yaml