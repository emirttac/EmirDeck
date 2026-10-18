# Build self-contained EmirDeck.exe + Inno Setup installer
$ErrorActionPreference = "Stop"

$InstallerDir = $PSScriptRoot
$Root = Split-Path -Parent $InstallerDir
$AppDist = Join-Path $InstallerDir "app_dist"
$Icon = Join-Path $Root "assets\emirdeck.ico"

function Find-Python {
    $candidates = @(
        (Join-Path (Split-Path -Parent $Root) ".venv\Scripts\python.exe"),
        (Join-Path $Root ".venv\Scripts\python.exe")
    )
    foreach ($c in $candidates) {
        try {
            $full = [System.IO.Path]::GetFullPath($c)
            if (Test-Path $full) { return $full }
        } catch {}
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python not found"
}

function Find-ISCC {
    foreach ($c in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $c) { return $c }
    }
    throw "Inno Setup 6 not found. winget install JRSoftware.InnoSetup"
}

$Python = Find-Python
$Iscc = Find-ISCC
Write-Host "Python: $Python"
Write-Host "ISCC:   $Iscc"

Write-Host "Installing build deps..."
& $Python -m pip install -q --upgrade pip pyinstaller pillow
& $Python -m pip install -q -r (Join-Path $Root "requirements.txt")

Write-Host "Generating assets\emirdeck.ico (same as tray logo)..."
Set-Location $Root
& $Python -c "from branding import export_ico; export_ico(r'$Icon'); print('ico ok')"
if (-not (Test-Path $Icon)) { throw "Icon not generated: $Icon" }

# Default config for first install
$Cfg = Join-Path $InstallerDir "default_config.json"
@"
{
  "language": "auto",
  "macros": []
}
"@ | Set-Content -Path $Cfg -Encoding utf8

Write-Host "Building EmirDeck.exe..."
if (Test-Path $AppDist) { Remove-Item $AppDist -Recurse -Force }
$Work = Join-Path $InstallerDir "build_app"
if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }

Set-Location $Root
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name EmirDeck `
    --icon $Icon `
    --distpath $AppDist `
    --workpath $Work `
    --specpath $Work `
    --collect-all PyQt6 `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pynput.mouse._win32 `
    --hidden-import branding `
    --hidden-import hotkey_listener `
    --hidden-import ffmpeg_silence `
    --hidden-import i18n `
    --hidden-import logger `
    (Join-Path $Root "main.py")

$Inner = Join-Path $AppDist "EmirDeck"
if (Test-Path $Inner) {
    Get-ChildItem $Inner | ForEach-Object {
        Move-Item $_.FullName -Destination $AppDist -Force
    }
    Remove-Item $Inner -Recurse -Force
}

$Exe = Join-Path $AppDist "EmirDeck.exe"
if (-not (Test-Path $Exe)) { throw "EmirDeck.exe missing" }
Copy-Item $Cfg (Join-Path $AppDist "config.json") -Force
# Beside exe — Windows taskbar reads this more reliably than painted QIcon alone
Copy-Item $Icon (Join-Path $AppDist "emirdeck.ico") -Force
Write-Host "EmirDeck.exe OK"

Write-Host "Compiling installer..."
Set-Location $InstallerDir
& $Iscc (Join-Path $InstallerDir "EmirDeck.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed: $LASTEXITCODE" }

$Setup = Join-Path $InstallerDir "dist\EmirDeck-Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer not found" }
Copy-Item $Setup (Join-Path $Root "EmirDeck-Setup.exe") -Force

Write-Host ""
Write-Host "DONE"
Write-Host "  App:       $Exe"
Write-Host "  Installer: $(Join-Path $Root 'EmirDeck-Setup.exe')"
