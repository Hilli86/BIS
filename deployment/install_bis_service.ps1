# PowerShell-Script zur Installation des BIS-Waitress Service
# Führen Sie dieses Script als Administrator aus

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

# Pfade
$BISDir = "C:\BIS"
$NSSMPath = Join-Path $BISDir "nssm.exe"
$ServiceName = "BIS-Waitress"
$PythonExe = Join-Path $BISDir "venv\Scripts\python.exe"
$StartScript = Join-Path $BISDir "start_waitress.py"

# Prüfen ob als Administrator ausgeführt
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "FEHLER: Dieses Script muss als Administrator ausgeführt werden!" -ForegroundColor Red
    Write-Host "Bitte PowerShell als Administrator öffnen und erneut ausführen."
    exit 1
}

# Deinstallieren
if ($Uninstall) {
    Write-Host "Deinstalliere Service: $ServiceName" -ForegroundColor Yellow
    
    # Service stoppen
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    
    # Service entfernen
    if (Test-Path $NSSMPath) {
        & $NSSMPath remove $ServiceName confirm
        Write-Host "Service entfernt." -ForegroundColor Green
    } else {
        Write-Host "NSSM nicht gefunden. Versuche Service manuell zu entfernen..." -ForegroundColor Yellow
        sc.exe delete $ServiceName
    }
    
    exit 0
}

# Prüfen ob NSSM vorhanden ist
if (-not (Test-Path $NSSMPath)) {
    Write-Host "FEHLER: NSSM nicht gefunden: $NSSMPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Bitte NSSM installieren:"
    Write-Host "  1. Download: https://nssm.cc/download"
    Write-Host "  2. Entpacken Sie win64\nssm.exe nach $NSSMPath"
    exit 1
}

# Prüfen ob Python vorhanden ist
if (-not (Test-Path $PythonExe)) {
    Write-Host "FEHLER: Python nicht gefunden: $PythonExe" -ForegroundColor Red
    Write-Host "Bitte stellen Sie sicher, dass die virtuelle Umgebung erstellt wurde."
    exit 1
}

# Prüfen ob Start-Script vorhanden ist
if (-not (Test-Path $StartScript)) {
    Write-Host "FEHLER: Start-Script nicht gefunden: $StartScript" -ForegroundColor Red
    exit 1
}

# Prüfen ob Service bereits existiert
if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Service $ServiceName existiert bereits." -ForegroundColor Yellow
    $response = Read-Host "Möchten Sie den Service neu installieren? (j/n)"
    if ($response -ne "j" -and $response -ne "J") {
        Write-Host "Abgebrochen."
        exit 0
    }
    
    # Service stoppen und entfernen
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    & $NSSMPath remove $ServiceName confirm
}

# Log-Verzeichnis erstellen
$LogDir = Join-Path $BISDir "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

Write-Host "Installiere Service: $ServiceName" -ForegroundColor Cyan
Write-Host "  Python: $PythonExe"
Write-Host "  Script: $StartScript"
Write-Host "  Logs: $LogDir"

# Service installieren
& $NSSMPath install $ServiceName $PythonExe $StartScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Service-Installation fehlgeschlagen!" -ForegroundColor Red
    exit 1
}

# Service konfigurieren
Write-Host "Konfiguriere Service..." -ForegroundColor Cyan

& $NSSMPath set $ServiceName AppDirectory $BISDir
& $NSSMPath set $ServiceName DisplayName "BIS Flask Application"
& $NSSMPath set $ServiceName Description "Betriebsinformationssystem Flask-Anwendung mit Waitress"
& $NSSMPath set $ServiceName Start SERVICE_AUTO_START
& $NSSMPath set $ServiceName AppStdout (Join-Path $LogDir "waitress_stdout.log")
& $NSSMPath set $ServiceName AppStderr (Join-Path $LogDir "waitress_stderr.log")

# Umgebungsvariablen setzen (falls .env vorhanden)
$EnvFile = Join-Path $BISDir ".env"
if (Test-Path $EnvFile) {
    Write-Host "Lade Umgebungsvariablen aus .env..." -ForegroundColor Cyan
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($key -and $value) {
                & $NSSMPath set $ServiceName AppEnvironmentExtra "$key=$value"
            }
        }
    }
}

# Service starten
Write-Host "Starte Service..." -ForegroundColor Cyan
& $NSSMPath start $ServiceName

Start-Sleep -Seconds 3

# Status prüfen
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq "Running") {
    Write-Host ""
    Write-Host "✓ Service erfolgreich installiert und gestartet!" -ForegroundColor Green
    Write-Host "  Name: $ServiceName"
    Write-Host "  Status: $($service.Status)"
    Write-Host ""
    Write-Host "Service verwalten:"
    Write-Host "  Start:   Start-Service $ServiceName"
    Write-Host "  Stop:    Stop-Service $ServiceName"
    Write-Host "  Status:  Get-Service $ServiceName"
    Write-Host "  Logs:    Get-Content $LogDir\waitress_stdout.log -Tail 50"
} else {
    Write-Host ""
    Write-Host "WARNUNG: Service wurde installiert, aber Status konnte nicht geprüft werden." -ForegroundColor Yellow
    Write-Host "Bitte prüfen Sie den Status manuell: Get-Service $ServiceName"
    Write-Host "Logs: $LogDir\waitress_stdout.log"
}

