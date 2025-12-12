#!/usr/bin/env python
"""Startet die BIS-Anwendung mit Waitress"""
import os
import sys

# Projektverzeichnis zum Python-Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Umgebungsvariablen aus .env laden
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Falls python-dotenv nicht installiert ist, Umgebungsvariablen manuell laden
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# Waitress importieren und starten
from waitress import serve
from app import app

if __name__ == '__main__':
    # Log-Verzeichnis erstellen
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Waitress-Konfiguration
    # Threads basierend auf CPU-Kernen
    import multiprocessing
    threads = max(4, multiprocessing.cpu_count() * 2 + 1)
    
    print(f"Starte BIS mit Waitress auf 127.0.0.1:8000")
    print(f"Threads: {threads}")
    print(f"Log-Verzeichnis: {log_dir}")
    
    # Waitress starten
    serve(
        app,
        host='127.0.0.1',
        port=8000,
        threads=threads,
        channel_timeout=120,
        connection_limit=1000
    )

