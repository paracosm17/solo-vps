[CmdletBinding()]
param(
    [string]$ToolsDir = (Join-Path $env:LOCALAPPDATA "solo-vps\bin")
)

$ErrorActionPreference = "Stop"

$AgeVersion = "1.3.1"
$SopsVersion = "3.13.3"
$AgeUrl = "https://github.com/FiloSottile/age/releases/download/v$AgeVersion/age-v$AgeVersion-windows-amd64.zip"
$AgeSha256 = "c56e8ce22f7e80cb85ad946cc82d198767b056366201d3e1a2b93d865be38154"
$SopsUrl = "https://github.com/getsops/sops/releases/download/v$SopsVersion/sops-v$SopsVersion.amd64.exe"
$SopsSha256 = "a4a9a398858fe8b2ef72d9686d930bf7c5cece9be74ad83ac3b53cfdd70e6b1c"

$arch = $env:PROCESSOR_ARCHITEW6432
if ([string]::IsNullOrWhiteSpace($arch)) { $arch = $env:PROCESSOR_ARCHITECTURE }
if ($arch -ne "AMD64") {
    throw "Solo VPS Windows secrets tools currently support Windows x64/AMD64 only; detected: $arch"
}

$fullToolsDir = [System.IO.Path]::GetFullPath($ToolsDir)
New-Item -ItemType Directory -Force -Path $fullToolsDir | Out-Null

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("solo-vps-secrets-tools-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir | Out-Null

function Assert-Sha256 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA-256 mismatch for $Path. Expected $Expected, got $actual"
    }
}

try {
    $ageZip = Join-Path $tempDir "age-v$AgeVersion-windows-amd64.zip"
    $sopsDownload = Join-Path $tempDir "sops-v$SopsVersion.amd64.exe"
    $ageExtract = Join-Path $tempDir "age-extract"

    Write-Host "Downloading age $AgeVersion from the official GitHub release..."
    Invoke-WebRequest -Uri $AgeUrl -OutFile $ageZip
    Assert-Sha256 -Path $ageZip -Expected $AgeSha256

    Write-Host "Downloading SOPS $SopsVersion from the official GitHub release..."
    Invoke-WebRequest -Uri $SopsUrl -OutFile $sopsDownload
    Assert-Sha256 -Path $sopsDownload -Expected $SopsSha256

    Expand-Archive -LiteralPath $ageZip -DestinationPath $ageExtract -Force
    $ageExeSource = Get-ChildItem -LiteralPath $ageExtract -Recurse -File -Filter "age.exe" | Select-Object -First 1
    $ageKeygenSource = Get-ChildItem -LiteralPath $ageExtract -Recurse -File -Filter "age-keygen.exe" | Select-Object -First 1
    if (-not $ageExeSource -or -not $ageKeygenSource) {
        throw "The pinned age archive does not contain age.exe and age-keygen.exe"
    }

    $ageExe = Join-Path $fullToolsDir "age.exe"
    $ageKeygenExe = Join-Path $fullToolsDir "age-keygen.exe"
    $sopsExe = Join-Path $fullToolsDir "sops.exe"

    Copy-Item -LiteralPath $ageExeSource.FullName -Destination $ageExe -Force
    Copy-Item -LiteralPath $ageKeygenSource.FullName -Destination $ageKeygenExe -Force
    Copy-Item -LiteralPath $sopsDownload -Destination $sopsExe -Force

    Unblock-File -LiteralPath $ageExe -ErrorAction SilentlyContinue
    Unblock-File -LiteralPath $ageKeygenExe -ErrorAction SilentlyContinue
    Unblock-File -LiteralPath $sopsExe -ErrorAction SilentlyContinue

    $ageVersionOutput = (& $ageKeygenExe --version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $ageVersionOutput -notmatch [regex]::Escape($AgeVersion)) {
        throw "Installed age-keygen version check failed: $ageVersionOutput"
    }

    $sopsVersionOutput = (& $sopsExe --version 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $sopsVersionOutput -notmatch [regex]::Escape($SopsVersion)) {
        throw "Installed SOPS version check failed: $sopsVersionOutput"
    }

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathEntries = @()
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $pathEntries = @($userPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    $alreadyInPath = $false
    foreach ($entry in $pathEntries) {
        if ([string]::Equals($entry.TrimEnd([char]92), $fullToolsDir.TrimEnd([char]92), [System.StringComparison]::OrdinalIgnoreCase)) {
            $alreadyInPath = $true
            break
        }
    }
    if (-not $alreadyInPath) {
        $newUserPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $fullToolsDir } else { "$userPath;$fullToolsDir" }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }

    Write-Host "PASS Solo VPS Windows secrets tools installed"
    Write-Host "  age:  $ageVersionOutput"
    Write-Host "  sops: $sopsVersionOutput"
    Write-Host "  path: $fullToolsDir"
    Write-Host "  SHA-256: verified for both official release downloads"
    Write-Host ""
    Write-Host "The Solo VPS Windows helpers use this directory immediately. New PowerShell windows can also use age-keygen.exe and sops.exe directly from PATH."
}
finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
