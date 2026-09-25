# TechConf — Organizzazione del codice (risposte al §7)

## Repository e confini dei servizi
Un unico repository con una cartella per servizio: services/user-service,
services/event-service, services/registration-service, e in seguito
services/feedback-service, services/notification-service.
Ogni cartella ha la sua struttura interna completa (app/, tests/,
requirements.txt): è chiaro dove finisce un servizio e dove inizia l'altro
perché coincide con la cartella. Nessun servizio importa codice da un altro:
comunicano solo via HTTP tramite le variabili *_SERVICE_URL. Questo è imposto
"a mano" (revisione del codice, niente import relativi tra cartelle services/*)
perché con un solo repo Python non c'è un modo automatico semplice per bloccarlo,
ma la separazione in cartelle e il fatto che ogni servizio ha il proprio
requirements.txt lo rende evidente.

## Codice condiviso
Nessuna libreria condivisa tra servizi: ogni servizio duplica la propria
piccola utility per formato errori/paginazione. Scelta deliberata per l'esame:
più codice ripetuto, ma zero accoppiamento — se un giorno un team diverso
prendesse in carico un servizio, potrebbe lavorarci senza toccare codice
usato da altri.

## Struttura interna di un servizio
Dentro ogni services/<nome>/app/:
- routes.py — gestione HTTP (Flask), validazione formale dell'input
- business.py — regole REQ-*-B*, qui vive la logica di dominio
- repository.py — persistenza, con un'interfaccia comune e tre implementazioni
  (memory/json/sqlite) intercambiabili senza toccare business.py
- clients.py — chiamate HTTP agli altri servizi, isolate qui così nei test
  unitari si mockano facilmente con la libreria responses
- config.py — unico punto che legge PORT, *_SERVICE_URL, STORAGE_BACKEND,
  DATA_DIR dalle variabili d'ambiente

## Configurazione e avvio
Ogni servizio ha il proprio requirements.txt (evita conflitti di versione tra
servizi). Il comando di avvio in services.yaml è lo stesso pattern per tutti:
python app/main.py dentro la cwd del servizio.

## Test
Test unitari e integration test "miei" vivono dentro services/<nome>/tests/,
vicino al codice. Un comando per servizio: pytest services/<nome>/tests -q.
Un comando per tutta la piattaforma: pytest services -q (lanciato dalla root).
I miei integration test avviano i servizi reali con una fixture pytest che li
lancia come sottoprocesso su una porta libera e li spegne a fine test.

## Spec e tracciabilità
Una spec Kiro per servizio (.kiro/specs/<servizio>/), non per singola regola:
è il livello più naturale perché coincide con un contratto OpenAPI e con una
cartella di codice. Partendo da REQ-REG-B05 si trova subito il codice
(services/registration-service/app/business.py, funzione che gestisce la
capienza) e il test (cercando "REQ-REG-B05" nei marker pytest).
In structure.md vanno le regole valide per TUTTO il repository (come sopra);
in design.md di ogni servizio vanno le decisioni specifiche di quel servizio.

## Dati e Git
I file di dati (json/sqlite) finiscono in services/<nome>/data/, tutti esclusi
da git tramite .gitignore (data/). I commit seguono sempre la sequenza
spec(...) → poi feat(...) per ogni task, cosicché git log mostri chiaramente
requirements → design → tasks → codice per ogni servizio.