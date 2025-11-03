# BIS - Modulare Projekt-Struktur

## Neue Struktur mit Blueprints

```
BIS/
├── app.py                      # Hauptdatei (nur noch Initialisierung)
├── config.py                   # Konfiguration (existiert)
├── requirements.txt            # Dependencies
│
├── modules/                    # Alle Module
│   ├── __init__.py
│   │
│   ├── auth/                   # Authentifizierung
│   │   ├── __init__.py
│   │   ├── routes.py          # Login, Logout
│   │   └── templates/
│   │       └── login.html
│   │
│   ├── schichtbuch/           # Schichtbuch-Modul
│   │   ├── __init__.py
│   │   ├── routes.py          # Themenliste, Thema-Detail, etc.
│   │   └── templates/
│   │       ├── sbThemaListe.html
│   │       ├── sbThemaDetail.html
│   │       └── sbThemaNeu.html
│   │
│   ├── admin/                 # Admin-Modul
│   │   ├── __init__.py
│   │   ├── routes.py          # Stammdaten-Verwaltung
│   │   └── templates/
│   │       └── admin.html
│   │
│   ├── wartung/               # Wartungs-Modul (zukünftig)
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── models.py
│   │   └── templates/
│   │
│   └── ersatzteile/           # Ersatzteil-Modul (zukünftig)
│       ├── __init__.py
│       ├── routes.py
│       ├── models.py
│       └── templates/
│
├── utils/                      # Hilfsfunktionen
│   ├── __init__.py
│   ├── database.py            # DB-Helpers
│   ├── decorators.py          # login_required, etc.
│   └── abteilungen.py         # Abteilungs-Funktionen
│
├── templates/                  # Gemeinsame Templates
│   ├── layout/
│   │   └── base.html
│   ├── errors/
│   │   ├── 404.html
│   │   └── 500.html
│   └── dashboard/
│       └── dashboard.html
│
├── static/                     # CSS, JS, Bilder
│   ├── css/
│   ├── js/
│   └── img/
│
├── migrations/                 # Datenbank-Migrationen
│   ├── migration_abteilungen.sql
│   └── ...
│
└── database_main.db           # Datenbank
```

## Vorteile dieser Struktur:

1. **Modular**: Jedes Modul ist unabhängig
2. **Wartbar**: Code ist logisch getrennt
3. **Erweiterbar**: Neue Module einfach hinzufügen
4. **Testbar**: Module können einzeln getestet werden
5. **Team-freundlich**: Mehrere Entwickler können parallel arbeiten

## Blueprints:

- `auth_bp` → `/login`, `/logout`
- `schichtbuch_bp` → `/schichtbuch/*`
- `admin_bp` → `/admin/*`
- `wartung_bp` → `/wartung/*` (später)
- `ersatzteile_bp` → `/ersatzteile/*` (später)

