# BIS - Upload to Server Script (Windows PowerShell)
# Lädt die BIS-Anwendung auf den Produktionsserver hoch

# KONFIGURATION - BITTE ANPASSEN!
$SERVER_IP = "192.168.1.100"      # IP-Adresse des Servers
$SERVER_USER = "bis"               # Benutzer auf dem Server
$SOURCE_DIR = "C:\Projekte\BIS"   # Lokales Projektverzeichnis
$TARGET_DIR = "/opt/bis"          # Zielverzeichnis auf dem Server

# ========================================

Write-Host "================================" -ForegroundColor Green
Write-Host "BIS Upload to Server" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# Prüfen ob Quellverzeichnis existiert
if (-not (Test-Path $SOURCE_DIR)) {
    Write-Host "FEHLER: Quellverzeichnis nicht gefunden: $SOURCE_DIR" -ForegroundColor Red
    exit 1
}

# Verbindungstest
Write-Host "Teste Verbindung zu ${SERVER_USER}@${SERVER_IP}..." -ForegroundColor Yellow
$testConnection = Test-Connection -ComputerName $SERVER_IP -Count 1 -Quiet

if (-not $testConnection) {
    Write-Host "WARNUNG: Server nicht erreichbar - versuche trotzdem Upload..." -ForegroundColor Yellow
}

# Dateien hochladen
Write-Host "Lade Dateien hoch..." -ForegroundColor Yellow
Write-Host "Von: $SOURCE_DIR" -ForegroundColor Cyan
Write-Host "Nach: ${SERVER_USER}@${SERVER_IP}:${TARGET_DIR}/" -ForegroundColor Cyan
Write-Host ""

# Ausschließen von unnötigen Dateien
$excludePatterns = @(
    "__pycache__",
    "*.pyc",
    ".git",
    ".gitignore",
    "venv",
    "*.db-journal",
    ".env.local",
    ".vscode"
)

# SCP-Befehl ausführen
try {
    # Wechsel zum Projektverzeichnis
    Push-Location $SOURCE_DIR
    
    # Upload durchführen
    # Hinweis: Für selektiven Upload könnten Sie rsync verwenden (WSL oder separat installiert)
    # Hier nutzen wir SCP für Einfachheit
    
    $scpCommand = "scp -r * ${SERVER_USER}@${SERVER_IP}:${TARGET_DIR}/"
    Write-Host "Führe aus: $scpCommand" -ForegroundColor Cyan
    
    Invoke-Expression $scpCommand
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "================================" -ForegroundColor Green
        Write-Host "Upload erfolgreich!" -ForegroundColor Green
        Write-Host "================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Nächste Schritte:" -ForegroundColor Yellow
        Write-Host "1. SSH-Verbindung zum Server: ssh ${SERVER_USER}@${SERVER_IP}" -ForegroundColor White
        Write-Host "2. App deployen: cd /opt/bis && ./deployment/deploy_app.sh" -ForegroundColor White
        Write-Host "3. Service neu starten (als root): systemctl restart bis.service" -ForegroundColor White
    } else {
        Write-Host ""
        Write-Host "FEHLER beim Upload (Exit Code: $LASTEXITCODE)" -ForegroundColor Red
        Write-Host ""
        Write-Host "Mögliche Lösungen:" -ForegroundColor Yellow
        Write-Host "- Prüfen Sie die Server-IP und Zugangsdaten" -ForegroundColor White
        Write-Host "- Stellen Sie sicher, dass SSH auf Port 22 läuft" -ForegroundColor White
        Write-Host "- Prüfen Sie ob der Benutzer '$SERVER_USER' existiert" -ForegroundColor White
        Write-Host "- Verwenden Sie ggf. WinSCP oder FileZilla" -ForegroundColor White
    }
} catch {
    Write-Host "FEHLER: $_" -ForegroundColor Red
} finally {
    Pop-Location
}



