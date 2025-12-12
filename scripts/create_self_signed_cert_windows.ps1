# PowerShell-Script zum Erstellen eines Self-Signed SSL-Zertifikats für BIS auf Windows
# Verwendung: .\create_self_signed_cert_windows.ps1 -ServerName "192.168.1.100"
# oder: .\create_self_signed_cert_windows.ps1 -ServerName "bis-server.local"

param(
    [Parameter(Mandatory=$false)]
    [string]$ServerName = "localhost"
)

# Verzeichnis für Zertifikate
$CertDir = "C:\nginx\conf\ssl\bis"

# Verzeichnis erstellen
if (-not (Test-Path $CertDir)) {
    New-Item -ItemType Directory -Path $CertDir -Force | Out-Null
    Write-Host "Verzeichnis erstellt: $CertDir"
}

Write-Host "Erstelle Self-Signed Certificate für: $ServerName"
Write-Host "Verzeichnis: $CertDir"

# Prüfen ob OpenSSL verfügbar ist
$openssl = Get-Command openssl -ErrorAction SilentlyContinue
if (-not $openssl) {
    Write-Host "FEHLER: OpenSSL ist nicht installiert oder nicht im PATH!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Bitte installieren Sie OpenSSL für Windows:"
    Write-Host "  - Download: https://slproweb.com/products/Win32OpenSSL.html"
    Write-Host "  - Oder via Chocolatey: choco install openssl"
    Write-Host ""
    Write-Host "Alternativ können Sie das Python-Script verwenden:"
    Write-Host "  python scripts\create_self_signed_cert_windows.py $ServerName"
    exit 1
}

# Prüfen ob es eine IP-Adresse ist (Format: xxx.xxx.xxx.xxx)
$isIP = $ServerName -match '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'

# Subject Alternative Names erstellen
# WICHTIG: Moderne Browser benötigen SANs, besonders bei IP-Adressen!
if ($isIP) {
    # Wenn IP-Adresse: IP in SANs hinzufügen (nicht DNS!)
    Write-Host "Erkenne IP-Adresse: $ServerName" -ForegroundColor Green
    $sanString = "IP:$ServerName,IP:127.0.0.1,DNS:localhost"
} else {
    # Wenn Hostname: DNS in SANs hinzufügen
    Write-Host "Erkenne Hostname: $ServerName" -ForegroundColor Green
    $sanString = "DNS:$ServerName,DNS:*.$ServerName,IP:127.0.0.1"
}

# Pfade für Zertifikat-Dateien
$keyPath = Join-Path $CertDir "bis.key"
$certPath = Join-Path $CertDir "bis.crt"

# Alte Zertifikate sichern (falls vorhanden)
if (Test-Path $keyPath) {
    $backupKey = "$keyPath.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item $keyPath $backupKey
    Write-Host "Alter Key gesichert: $backupKey" -ForegroundColor Yellow
}

if (Test-Path $certPath) {
    $backupCert = "$certPath.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item $certPath $backupCert
    Write-Host "Altes Zertifikat gesichert: $backupCert" -ForegroundColor Yellow
}

# Zertifikat erstellen (gültig für 10 Jahre)
Write-Host ""
Write-Host "Erstelle Zertifikat..." -ForegroundColor Cyan

$opensslArgs = @(
    "req",
    "-x509",
    "-nodes",
    "-days", "3650",
    "-newkey", "rsa:4096",
    "-keyout", $keyPath,
    "-out", $certPath,
    "-subj", "/C=DE/ST=State/L=City/O=BIS/CN=$ServerName",
    "-addext", "subjectAltName=$sanString"
)

try {
    & openssl $opensslArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✓ Zertifikat erfolgreich erstellt!" -ForegroundColor Green
        Write-Host "  Key: $keyPath"
        Write-Host "  Cert: $certPath"
        Write-Host "  SANs: $sanString"
        Write-Host ""
        Write-Host "Sie können das Zertifikat jetzt in der Nginx-Konfiguration verwenden."
        Write-Host ""
        
        # Zertifikat-Details anzeigen
        Write-Host "Zertifikat-Details:" -ForegroundColor Cyan
        & openssl x509 -in $certPath -text -noout | Select-String -Pattern "Subject:|Issuer:|Subject Alternative Name" -Context 0,2
    } else {
        Write-Host "FEHLER: OpenSSL-Befehl fehlgeschlagen!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "FEHLER beim Erstellen des Zertifikats: $_" -ForegroundColor Red
    exit 1
}

# Berechtigungen setzen (Windows-spezifisch)
# Nur für den aktuellen Benutzer und Administratoren lesbar
try {
    $acl = Get-Acl $keyPath
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
        "FullControl",
        "Allow"
    )
    $acl.SetAccessRule($rule)
    Set-Acl $keyPath $acl
    Write-Host "Berechtigungen für Key gesetzt." -ForegroundColor Green
} catch {
    Write-Host "Warnung: Berechtigungen konnten nicht gesetzt werden: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Fertig!" -ForegroundColor Green

