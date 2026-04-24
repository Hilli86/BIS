"""
Persönlicher Import-Unterordner (pro Personalnummer unter IMPORT_FOLDER).
"""

import os
import re


def ordnername_personlicher_import(personalnummer):
    """
    Ein sicheres Ordner-Segment unter dem zentralen Import-Ordner.
    Gibt None zurück, wenn die Personalnummer kein gültiges Segment ergibt.
    """
    if personalnummer is None:
        return None
    s = str(personalnummer).strip()
    if not s or '..' in s or '/' in s or '\\' in s:
        return None
    if not re.fullmatch(r'[0-9A-Za-z._-]+', s):
        return None
    return s


def pfad_personlicher_import(import_folder, personalnummer):
    """Absoluter Pfad zum persönlichen Unterordner oder None."""
    on = ordnername_personlicher_import(personalnummer)
    if not on:
        return None
    return os.path.join(import_folder, on)


def resolve_import_dateipfad(import_folder, filename, import_quelle, personalnummer):
    """
    import_quelle: 'import' (Wurzel) oder 'personal'.
    Gibt den absoluten Dateipfad zurück oder None, wenn die Datei nicht existiert
    oder außerhalb des Import-Baums liegt.
    """
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return None
    import_quelle = (import_quelle or 'import').strip().lower()
    import_abs = os.path.abspath(import_folder)
    if import_quelle == 'personal':
        pdir = pfad_personlicher_import(import_folder, personalnummer)
        if not pdir:
            return None
        path = os.path.join(pdir, filename)
    else:
        path = os.path.join(import_folder, filename)
    path_abs = os.path.abspath(path)
    if not path_abs.startswith(import_abs + os.sep):
        return None
    return path_abs if os.path.isfile(path_abs) else None


def resolve_import_dateipfad_auto(import_folder, filename, personalnummer):
    """
    Sucht zuerst im gemeinsamen Import-Ordner, dann im persönlichen Unterordner.
    Rückgabe: (absoluter Pfad oder None, 'import'|'personal'|None)
    """
    p = resolve_import_dateipfad(import_folder, filename, 'import', personalnummer)
    if p:
        return p, 'import'
    p = resolve_import_dateipfad(import_folder, filename, 'personal', personalnummer)
    if p:
        return p, 'personal'
    return None, None
