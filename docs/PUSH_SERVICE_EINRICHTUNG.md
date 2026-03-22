# Web-Push (VAPID) einrichten

Kurzanleitung für Server, Umgebungsvariablen und Browser. Technische Details stehen in `config.py` und im Modul `utils/benachrichtigungen_push.py`.

## Voraussetzungen

- Python-Umgebung mit installierten Abhängigkeiten: `pip install -r requirements.txt` (u. a. `pywebpush`, `python-dotenv`).
- Im Browser: **HTTPS** oder lokal nur **`http://localhost`** bzw. **`http://127.0.0.1`** (sicherer Kontext). Unter einer **anderen IP oder einem Hostnamen ohne HTTPS** funktioniert Web-Push in der Regel **nicht**.

## 1. VAPID-Schlüssel erzeugen

Im **Projektroot** (Ordner mit `app.py`), in einer Konsole (PowerShell oder CMD):

```powershell
cd C:\Pfad\zu\BIS
.\.venv\Scripts\python.exe -m flask --app app vapid-generate
```

Es wird u. a. eine private PEM-Datei unter `instance\vapid_private.pem` angelegt. Die Ausgabe enthält **eine Zeile** für `VAPID_PUBLIC_KEY` – diese unverändert übernehmen.

**Prüfen, ob öffentlicher und privater Schlüssel zusammenpassen:**

```powershell
.\.venv\Scripts\python.exe -m flask --app app vapid-verify
```

Erwartung: Meldung **„VAPID-Schlüsselpaar ist konsistent.“**

> **Wo eingeben?** Jede Konsole im Projektverzeichnis – z. B. **Cursor-Terminal**, **Windows-Terminal**, **VS Code integriertes Terminal**. Wichtig ist der Pfad zu `app.py` und die Nutzung der **venv**-Python-Version (wie oben).

## 2. Umgebungsvariablen setzen

Die App liest `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY` und optional `VAPID_EMAIL` aus der Umgebung. `config.py` lädt beim Start optional eine Datei **`.env`** im Projektroot (über `python-dotenv`).

**Empfohlen:** `env_example.txt` nach `.env` kopieren und ergänzen:

```env
VAPID_PRIVATE_KEY=C:\Pfad\zu\BIS\instance\vapid_private.pem
VAPID_PUBLIC_KEY=<eine Zeile aus der Ausgabe von vapid-generate>
VAPID_EMAIL=ihre-mail@firma.de
```

- `VAPID_PRIVATE_KEY` kann der **volle Pfad** zur PEM-Datei sein (oder der PEM-Inhalt).
- `VAPID_PUBLIC_KEY` ist **eine einzige Zeile** (Base64-URL), ohne Anführungszeichen in der `.env`, sofern keine Leerzeichen darin vorkommen.

Anschließend **Flask neu starten** (Prozess beenden und erneut starten), damit die Variablen geladen werden.

## 3. Browser und URL

1. BIS unter **`http://localhost:5000`** (oder dem konfigurierten Port) öffnen – zum Testen **`localhost`** statt **`127.0.0.1`** verwenden, falls Push zickt.
2. Anmelden, **Profil** öffnen, Bereich **Benachrichtigungen**.
3. **Push-Benachrichtigungen** aktivieren und im Browser **Zulassen** wählen.
4. Optional **„Test-Push senden“** nutzen, wenn der Button erscheint.

**Produktion / Intranet:** Zugriff über **HTTPS** (z. B. Reverse-Proxy mit TLS, siehe `docs/DEPLOYMENT_GUIDE.md` oder `docs/SSL_SELFSIGNED_SETUP.md`). Ohne HTTPS funktioniert Push auf „normalen“ HTTP-Hostnamen nicht zuverlässig.

## 4. Häufige Probleme

| Symptom | Mögliche Ursache |
|--------|-------------------|
| „Push ist auf dem Server nicht konfiguriert“ | `VAPID_PUBLIC_KEY` fehlt oder App wurde ohne `.env`/Umgebung neu gestartet. |
| `vapid-verify` schlägt fehl | Öffentlicher und privater Key stammen nicht aus derselben Erzeugung – `vapid-generate` wiederholen und beide Werte neu setzen. |
| „push service error“ | Falscher Host (kein sicherer Kontext), **127.0.0.1** statt **localhost** testen, Windows-Benachrichtigungen für den Browser prüfen, VPN/Firewall (Zugriff auf den Push-Dienst des Browsers). |
| Test-Push kommt nicht an | Subscription gespeichert? `pywebpush` installiert? Server-Logs prüfen. |

## 5. Befehle (Überblick)

| Befehl | Zweck |
|--------|--------|
| `flask --app app vapid-generate` | Neues Schlüsselpaar + PEM-Datei |
| `flask --app app vapid-verify` | Prüfung, ob Public/Private zusammenpassen |
| `flask --app app push-test <MitarbeiterID>` | Test-Push an einen Benutzer (serverseitig, benötigt gespeicherte Subscription) |

Alle Befehle im **Projektroot** mit derselben Python-Umgebung ausführen wie die laufende App.
