# TechConf — Prodotto

TechConf è una piattaforma a microservizi per organizzare conferenze tecnologiche
(cloud, AI, security). Gestisce l'intero ciclo: utenti della piattaforma, eventi
con capienza e stato di pubblicazione, iscrizioni degli utenti agli eventi, e
(opzionalmente) feedback post-evento e notifiche agli iscritti.

## Servizi
- user-service: anagrafica utenti (attendee, speaker, organizer)
- event-service: eventi con ciclo di vita draft → published → cancelled
- registration-service: iscrizioni con controllo capienza e stato
- feedback-service (opzionale): valutazioni degli eventi da parte degli iscritti
- notification-service (opzionale): notifiche singole e broadcast agli iscritti

## Obiettivo di questo esame
Costruire i servizi rispettando i contratti OpenAPI già forniti, con sviluppo
Spec-Driven (Requirements → Design → Tasks) in Kiro, e superare la suite di
collaudo fornita dal docente.