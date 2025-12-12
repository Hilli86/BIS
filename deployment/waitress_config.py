# Waitress-Konfiguration für BIS
# Diese Datei kann für erweiterte Waitress-Konfigurationen verwendet werden
# Standardmäßig wird start_waitress.py verwendet

import multiprocessing

# Bind-Adresse (nur localhost, Nginx wird als Reverse Proxy verwendet)
bind = "127.0.0.1:8000"

# Worker-Threads
# Regel: (2 x CPU-Kerne) + 1, mindestens 4
threads = max(4, multiprocessing.cpu_count() * 2 + 1)

# Connection-Limit
connection_limit = 1000

# Channel-Timeout (in Sekunden)
channel_timeout = 120

# Logging
# Logs werden in C:\BIS\logs\ geschrieben
# Diese Konfiguration wird in start_waitress.py verwendet

