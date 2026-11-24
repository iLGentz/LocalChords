<#
.SYNOPSIS
  Installa o aggiorna LocalChords su Windows. Idempotente: si può rieseguire.

.DESCRIPTION
  1. verifica uv (lo installa con winget se manca);
  2. scarica Python 3.12 dentro la cartella dell'app (.uv\python);
  3. crea l'ambiente .venv e installa le dipendenze;
  4. rileva GPU NVIDIA e registra il runtime scelto in .env;
  5. scarica FFmpeg portabile in tools\ffmpeg (verificandone lo SHA-256);
  6. compila l'interfaccia (serve Node.js solo qui);
  7. applica le migrazioni del database.

.PARAMETER Runtime
  auto (predefinito: NVIDIA se nvidia-smi risponde), cpu, nvidia.
.PARAMETER SkipFfmpeg
  Non scarica FFmpeg.
.PARAMETER SkipFrontend
  Non ricompila l'interfaccia.
.PARAMETER Dev
  Installa anche gli strumenti di sviluppo (pytest, mypy, ruff).
.PARAMETER YouTube
  Installa e attiva l'adapter YouTube (yt-dlp e Deno). Disattivato di default.
#>
[CmdletBinding()]
param(
    [ValidateSet('auto', 'cpu', 'nvidia')]
    [string]$Runtime = 'auto',
    [switch]$SkipFfmpeg,
    [switch]$SkipFrontend,
    [switch]$Dev,
    [switch]$YouTube
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = $PSScriptRoot
$PythonVersion = '3.12'
$FfmpegUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'

function Write-Step([string]$Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "    $Text" -ForegroundColor Green }
function Write-Note([string]$Text) { Write-Host "    $Text" -ForegroundColor Yellow }

function Invoke-Native {
    <# Esegue un programma esterno e si ferma se l'exit code non è 0. #>
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Comando non riuscito ($LASTEXITCODE): $File $($Arguments -join ' ')" }
}

function Test-Executable([string]$Path, [string]$VersionArg = '--version') {
    <# Vero se l'eseguibile parte davvero (alcuni antivirus aziendali bloccano binari non firmati). #>
    if (-not (Test-Path $Path)) { return $false }
    try {
        $null = & $Path $VersionArg 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Set-EnvValue([string]$File, [string]$Key, [string]$Value) {
    $lines = @(Get-Content $File -Encoding UTF8)
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^\s*$Key=") { $found = $true; "$Key=$Value" } else { $line }
    }
    if (-not $found) { $out = @($out) + "$Key=$Value" }
    [IO.File]::WriteAllLines($File, [string[]]$out, (New-Object Text.UTF8Encoding($false)))
}

Set-Location $Root

# --------------------------------------------------------------------------- sistema
Write-Step 'Controllo del sistema'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Serve Windows a 64 bit.' }
$os = [Environment]::OSVersion.Version
if ($os.Major -lt 10) { throw 'Serve Windows 10 o 11.' }
Write-Ok "Windows $($os.Major).$($os.Minor) build $($os.Build), 64 bit"

# --------------------------------------------------------------------------------- uv
Write-Step 'uv'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Note 'uv non trovato: lo installo con winget.'
        Invoke-Native winget @('install', '--id', 'astral-sh.uv', '-e', '--accept-source-agreements', '--accept-package-agreements')
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv non trovato. Installa con "winget install astral-sh.uv" e riapri PowerShell.'
    }
}
Write-Ok (& uv --version)

# ------------------------------------------------------------------------- Python
Write-Step "Python $PythonVersion (isolato in .uv\python)"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Root '.uv\python'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
Invoke-Native uv @('python', 'install', $PythonVersion)
# --system: ignora .venv e restituisce l'interprete base gestito da uv.
$basePython = (& uv python find --system $PythonVersion).Trim()
if (-not (Test-Path $basePython)) { throw "Python $PythonVersion non trovato dopo l'installazione." }
Write-Ok $basePython

# ----------------------------------------------------------------------- runtime
Write-Step 'Hardware e runtime di inferenza'
$gpu = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try {
        $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1)
    } catch { $gpu = $null }
}
if ($Runtime -eq 'auto') { $Runtime = if ($gpu) { 'nvidia' } else { 'cpu' } }
if ($gpu) { Write-Ok "GPU NVIDIA: $gpu" } else { Write-Note 'Nessuna GPU NVIDIA rilevata: elaborazione su CPU (più lenta, 5-20 minuti per brano).' }
if ($Runtime -eq 'nvidia' -and -not $gpu) { Write-Note 'Runtime NVIDIA richiesto ma nvidia-smi non risponde: controlla il driver.' }
Write-Ok "Runtime: $Runtime (PyTorch $(if ($Runtime -eq 'nvidia') { 'CUDA 12.6' } else { 'CPU' }))"

# ------------------------------------------------------------------------ ambiente
Write-Step 'Ambiente virtuale e dipendenze'
$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
$venvCfg = Join-Path $Root '.venv\pyvenv.cfg'
$venvMatches = (Test-Path $venvCfg) -and (Select-String -Path $venvCfg -Pattern "^\s*version(_info)?\s*=\s*$([regex]::Escape($PythonVersion))\." -Quiet)
if (-not $venvMatches -or -not (Test-Executable $venvPython)) {
    if (Test-Path (Join-Path $Root '.venv')) {
        Write-Note '.venv esistente non utilizzabile o di un''altra versione di Python: lo ricreo.'
        Remove-Item -Recurse -Force (Join-Path $Root '.venv')
    }
    # Venv creato con il modulo standard di CPython: il suo launcher è accettato anche
    # dagli antivirus aziendali che bloccano quello generato da uv (vedi docs\DECISIONI.md).
    Invoke-Native $basePython @('-m', 'venv', '--without-pip', (Join-Path $Root '.venv'))
}
$syncArgs = @('sync')
if (Test-Path (Join-Path $Root 'uv.lock')) { $syncArgs += '--frozen' }
if (-not $Dev) { $syncArgs += '--no-dev' }
$youtubeInstalled = $YouTube -or ((Test-Path (Join-Path $Root '.env')) -and (Select-String -Path (Join-Path $Root '.env') -Pattern '^LOCALCHORDS_YOUTUBE_ENABLED=true' -Quiet))
if ($youtubeInstalled) { $syncArgs += @('--extra', 'youtube') }
# Runtime di separazione (torch + audio-separator): CPU oppure CUDA, mai entrambi.
$syncArgs += @('--extra', $Runtime)
Invoke-Native uv $syncArgs
Write-Ok 'Dipendenze installate (il primo download di PyTorch può richiedere qualche minuto)'

$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root '.env.example') $envFile
    Write-Ok '.env creato da .env.example'
}
Set-EnvValue $envFile 'LOCALCHORDS_INSTALLED_RUNTIME' $Runtime
if ($YouTube) {
    Set-EnvValue $envFile 'LOCALCHORDS_YOUTUBE_ENABLED' 'true'
    Write-Ok 'Adapter YouTube installato e attivato'
}

# ------------------------------------------------------------------------- FFmpeg
Write-Step 'FFmpeg'
$ffmpegDir = Join-Path $Root 'tools\ffmpeg'
$ffmpegExe = Join-Path $ffmpegDir 'bin\ffmpeg.exe'
$systemFfmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (Test-Path $ffmpegExe) {
    Write-Ok "Copia portabile: $ffmpegExe"
} elseif ($systemFfmpeg) {
    Write-Ok "Nel PATH: $($systemFfmpeg.Source)"
} elseif ($SkipFfmpeg) {
    Write-Note 'FFmpeg mancante (saltato con -SkipFfmpeg): l''import audio non funzionerà.'
} else {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("localchords-ffmpeg-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp 'ffmpeg.zip'
        Write-Note "Scarico $FfmpegUrl"
        Invoke-WebRequest -Uri $FfmpegUrl -OutFile $zip -UseBasicParsing
        $expected = ((Invoke-WebRequest -Uri "$FfmpegUrl.sha256" -UseBasicParsing).Content | Out-String).Trim().Split(' ')[0].ToLower()
        $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
        if ($expected -ne $actual) { throw "Checksum FFmpeg non valido (atteso $expected, ottenuto $actual)." }
        Write-Ok 'Checksum SHA-256 verificato'
        Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'x')
        $inner = Get-ChildItem (Join-Path $tmp 'x') -Directory | Select-Object -First 1
        if (-not (Test-Path (Join-Path $inner.FullName 'bin\ffmpeg.exe'))) { throw 'Archivio FFmpeg inatteso.' }
        if (Test-Path $ffmpegDir) { Remove-Item -Recurse -Force $ffmpegDir }
        New-Item -ItemType Directory -Force -Path (Split-Path $ffmpegDir) | Out-Null
        Move-Item $inner.FullName $ffmpegDir
        Write-Ok "Installato in $ffmpegDir"
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}
if ((Test-Path $ffmpegExe) -and -not (Test-Executable $ffmpegExe '-version')) {
    Write-Note 'ffmpeg.exe è presente ma non si avvia (antivirus?). Controlla le eccezioni dell''antivirus.'
}

# ----------------------------------------------------------------------- frontend
Write-Step 'Interfaccia'
$frontend = Join-Path $Root 'frontend'
$dist = Join-Path $frontend 'dist\index.html'
if ($SkipFrontend) {
    Write-Note 'Compilazione saltata (-SkipFrontend).'
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location $frontend
    try {
        if (Test-Path 'package-lock.json') { Invoke-Native npm @('ci', '--no-fund', '--no-audit') }
        else { Invoke-Native npm @('install', '--no-fund', '--no-audit') }
        Invoke-Native npm @('run', 'build')
    } finally { Pop-Location }
    Write-Ok 'Interfaccia compilata'
} elseif (Test-Path $dist) {
    Write-Note 'Node.js non trovato: uso l''interfaccia già compilata.'
} else {
    throw 'Node.js non trovato e interfaccia non compilata. Installa Node.js LTS (winget install OpenJS.NodeJS.LTS).'
}

# ------------------------------------------------------------------------ database
Write-Step 'Database'
Invoke-Native $venvPython @('-m', 'app.db.migrate')

Write-Host "`nInstallazione completata. Avvia LocalChords con LocalChords.bat" -ForegroundColor Green
