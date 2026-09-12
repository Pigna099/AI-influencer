# AI influencer playground v3

Un laboratorio interno per provare personalità, memoria e velocità dei modelli Ollama. Non invia messaggi a OnlyFans/Fanvue e non pubblica contenuti.

## Accensione

Nel terminale del server:

```bash
cd /data/data_ssd/pigni/ai-influencer/backend
./start.sh
```

Apri **http://192.168.1.60:8010** dal Mac sulla stessa rete. Accedi con `API_KEY` del file `.env` sul server. La chiave esistente non viene cambiata. Il browser la conserva nella sessione fino al logout.

Lo script costruisce la webUI dentro Docker, prepara il database, applica le migrazioni e avvia API e worker. Non serve installare Node o Python sul computer per avviare l'app. API, webUI, worker e PostgreSQL sono nei container; Ollama e ComfyUI rimangono i servizi AI già installati sul server, raggiunti via rete host Linux. Non vengono duplicati i modelli né modificati i servizi AI esistenti.

I container API/worker/database hanno `restart: unless-stopped`: ripartono quando riparte Docker, a meno che siano stati fermati esplicitamente.

```bash
docker compose ps                 # stato dei servizi
docker compose logs --tail=80 api # ultimi messaggi del backend
docker compose stop              # ferma senza cancellare dati
./start.sh                       # riaccende e verifica
```

## Il primo test di chat

1. Seleziona un personaggio nella colonna compatta a sinistra. Puoi crearlo, modificarlo o eliminarlo.
2. Scegli un fan fittizio. Sono disponibili Luca, Sofia e Marco, oltre all'Archivio v2.
3. Scegli un modello e premi **Nuova chat**. Il personaggio genera il primo messaggio.
4. Scrivi come il fan. Durante l'attesa compaiono puntini animati e tempo trascorso. I messaggi inviati restano nella cronologia.
5. Per cambiare modello nella conversazione corrente, selezionalo e premi **Usa nella chat**. Per un confronto senza cronologia precedente, usa **Confronta modelli**.

Ogni chat conserva una copia della personalità con cui è iniziata. Dopo aver modificato il personaggio, avvia una nuova chat per provare la nuova versione.

I modelli di soli embedding sono esclusi dalla scelta chat. I modelli di coding restano disponibili: puoi misurare direttamente quanto sono adatti a questo uso.

## Provare la memoria senza confondere gli utenti

La memoria appartiene alla coppia **personaggio + fan**, non al modello o alla singola chat. Cambiare modello mantiene i ricordi di quella coppia; cambiare fan o personaggio li separa.

- Come Luca, scrivi: «Il mio cane si chiama Milo e adoro il jazz».
- Attendi che il pannello Memoria mostri i fatti estratti.
- Apri una nuova chat con lo stesso personaggio e Luca. Chiedi come si chiama il cane.
- Passa a Sofia: i ricordi di Luca non devono comparire. Racconta a Sofia dettagli diversi per verificare la separazione.

Le **note per il test** degli account sono una traccia per te: non vengono inviate al modello. In questo modo un modello non può sembrare ricordare qualcosa che gli viene suggerito dalle note.

Puoi aggiungere, eliminare o azzerare ricordi manualmente. L'estrazione automatica usa `OLLAMA_MODEL` dopo la risposta, separatamente dal modello scelto per la chat; l'indicatore mostra pending/ready/failed. Un errore di estrazione non annulla la risposta già salvata. I ricordi vengono selezionati per corrispondenza di parole e importanza, senza richiedere un modello embedding.

L'**Archivio v2** contiene chat e ricordi precedenti, la cui provenienza per fan non era registrata. Sono conservati ma separati dai nuovi account. Non usarli per valutare l'isolamento.

## Iniziativa e tono

- **Scrivi per primo**: genera un'apertura del personaggio senza messaggio del fan.
- **Simula ritorno**: imposta le ore di assenza e prova un messaggio di riavvicinamento.
- **Un messaggio dopo 60 s di silenzio**: abilita un singolo intervento automatico nella chat aperta. Si disattiva dopo l'invio; richiede la pagina aperta. Non è un sistema di notifiche esterno.

I profili possono essere propositivi, giocosi e leggermente flirtanti, con voce e limiti personalizzabili. Il prompt base richiede messaggi naturali, rispetto dei rifiuti e nessuna pressione all'acquisto. Una risposta simulata non prova la capacità di vendere: qui puoi valutarne tono, iniziativa, coerenza e memoria.

## Ampliare la personalità

Apri **Modifica personalità**. In **Amplia con un modello installato** scegli il modello e descrivi la direzione creativa. Premi **Genera proposta**: il risultato è una bozza. Puoi scartarla o applicarla nell'editor. Solo **Salva personaggio** modifica il profilo e crea una nuova versione.

## Confrontare i modelli

Nella scheda **Confronta modelli**:

1. Seleziona i modelli, uno scenario o un messaggio personalizzato.
2. Scegli il numero di prove per modello (1–5) e la temperatura.
3. Avvia: le prove sono eseguite in sequenza per non competere deliberatamente per la GPU.
4. Leggi risposte, media totale, tempo medio di caricamento, numero di prove riuscite ed errori.

Il primo campione fissa personalità e ricordi del confronto. Tutti i campioni successivi dello stesso confronto riusano quel contesto. Non leggono la cronologia di una chat e non estraggono nuovi ricordi dalle risposte. Le prove sono salvate nel database, ricaricabili ed esportabili in JSON.

Il tempo totale della richiesta comprende attesa e caricamento del modello. I token/secondo misurano solo la generazione, quando Ollama fornisce quei dati. La prima prova dopo un caricamento può essere più lenta; le medie comprendono anche le prove a freddo. Le prove fallite non entrano nella media. Il pannello Tempi in chat include saluti, risposte e ritorni della coppia selezionata, senza mescolarli ai benchmark.

Chat e benchmark usano 512 token massimi e una finestra di contesto di 8192 token. Il ragionamento opzionale viene disattivato. Le varianti che dichiarano `general.finetune=Thinking` richiedono invece ragionamento: per queste il limite totale sale a 2048 token e solo la risposta finale viene mostrata. Il budget effettivo e la modalità sono registrati nelle metriche esportate. Sul server `qwen3:30b` è una variante Thinking. La gestione usa [le capacità e il parametro think di Ollama](https://docs.ollama.com/capabilities/thinking). Se un modello non produce una risposta visibile entro il limite viene mostrato un errore, non un messaggio vuoto. Altri carichi GPU sul server possono comunque influenzare i tempi: queste sono misure operative, non un benchmark hardware controllato.

## Dati, eliminazione e backup

- Il database resta nel volume Docker `ai-influencer_postgres_data`.
- I media restano in `data/media` sull'SSD.
- Eliminare una chat conserva i ricordi del fan; eliminarne l'account cancella chat e ricordi associati.
- Eliminare un personaggio cancella chat, ricordi, risultati dei confronti e contenuti associati. La UI chiede conferma. L'eliminazione è rifiutata se una generazione o una risposta è in corso.
- Non usare `docker compose down -v`: rimuoverebbe il volume del database.

Prima dell'aggiornamento v3 sono state salvate copie del codice e del database nella cartella `../backups/`. Non sono caricate in Git. Il ripristino deve usare la coppia corretta di codice e database; non ripristinare un dump sopra dati nuovi senza averli salvati.

## Struttura e controlli per chi modifica il codice

- `app/characters.py`: API di personaggi, fan, chat e benchmark.
- `app/chat_service.py`: prompt, recupero ricordi, estrazione e misure.
- `app/integrations/ollama.py`: collegamento ai modelli.
- `app/auth.py`: autenticazione comune.
- `app/main.py`: applicazione, webUI e pipeline contenuti preesistente.
- `webui/src/components/Playground.tsx`: schermata principale.
- `ChatPanel.tsx`, `CharacterForm.tsx`, `BenchmarkPanel.tsx`: chat, editor, confronto.
- `alembic/versions/0003_playground_v3.py`: migrazione v3, conserva i dati v2 in Archivio.

```bash
uv sync --locked
uv run pytest -q
uv run ruff check app tests scripts
uv run ruff format --check app tests scripts alembic
# Dentro webui:
npm ci
npm run lint
npm run build
# Dentro il container avviato:
docker compose exec -T api alembic check
```

I test automatici usano un database temporaneo SQLite con chiavi esterne attive. Non modificano i dati veri. `scripts/verify_playground.py` è una verifica opzionale con Ollama reale: crea e poi elimina solo i suoi record temporanei. Il suo valore predefinito punta all'anteprima sulla porta 8011; per un altro ambiente impostare `VERIFY_URL` e `VERIFY_KEY` senza mettere la chiave nel repository.

## Limiti attuali

Il playground usa una chiave condivisa per il proprietario: i fan sono identità simulate, non utenti autenticati reali. L'estrazione memoria è un'attività in background non persistente: se l'API si arresta durante l'estrazione, la risposta salvata resta disponibile ma il ricordo potrebbe dover essere aggiunto manualmente. Non sono implementati invio su OnlyFans/Fanvue, pagamenti, campagne o notifiche esterne. La pipeline immagini preesistente resta disponibile, ma non è il focus della v3.
