[CmdletBinding()]
param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt"),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "solo-vps\state"),
    [string]$PolicyPath = "",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

function Resolve-SoloVpsTool {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $managed = Join-Path $env:LOCALAPPDATA "solo-vps\bin\$Name.exe"
    if (Test-Path -LiteralPath $managed -PathType Leaf) { return $managed }

    throw "$Name.exe is not installed. Run .\scripts\windows\install-secrets-tools.ps1 first."
}

function Quote-ProcessArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains('"')) { throw "Unsupported quote character in process argument." }
    return '"' + $Value + '"'
}

function Invoke-TextProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$InputText,
        [hashtable]$Environment = @{}
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    foreach ($key in $Environment.Keys) {
        $psi.EnvironmentVariables[$key] = [string]$Environment[$key]
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) { throw "Could not start $FilePath" }
    $process.StandardInput.Write($InputText)
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "SOPS process failed with exit code $($process.ExitCode); secret-bearing stderr was suppressed."
    }
    return $stdout
}

function Read-SecureText {
    param([Parameter(Mandatory = $true)][string]$Prompt)
    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function New-ResticPassword {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_'))
}

$sops = Resolve-SoloVpsTool -Name "sops"
$fullStateRoot = [System.IO.Path]::GetFullPath($StateRoot)
if (-not $PolicyPath) { $PolicyPath = Join-Path $fullStateRoot "sops\.sops.yaml" }
if (-not $OutputPath) { $OutputPath = Join-Path $fullStateRoot "secrets\backup.enc.yaml" }
$fullPolicyPath = [System.IO.Path]::GetFullPath($PolicyPath)
$fullOutputPath = [System.IO.Path]::GetFullPath($OutputPath)

if (-not (Test-Path -LiteralPath $fullPolicyPath -PathType Leaf)) {
    throw "Persistent SOPS policy is missing: $fullPolicyPath. Run .\scripts\windows\init-sops-policy.ps1 first."
}
if (Test-Path -LiteralPath $fullOutputPath) {
    $fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
    $testScript = Join-Path $PSScriptRoot "test-backup-secrets.ps1"
    try {
        & $testScript -KeyPath $fullKeyPath -StateRoot $fullStateRoot -PolicyPath $fullPolicyPath -EncryptedPath $fullOutputPath
    }
    catch {
        throw "An encrypted backup bundle already exists but it cannot be validated with the current age key. If you are intentionally repeating setup and can enter the storage credentials again, run .\scripts\windows\init-sops-policy.ps1 -StartFresh first. The old ciphertext will be archived, not deleted. Validation error: $($_.Exception.Message)"
    }
    Write-Host "PASS encrypted backup secret bundle already exists; reusing it"
    Write-Host "  existing ciphertext replaced: no"
    Write-Host "  to enter new storage credentials: rotate them explicitly or start fresh"
    return
}

Write-Host "Enter the S3-compatible credentials. Secret values are hidden and will not be printed."
$accessKey = Read-SecureText -Prompt "S3 access key ID"
$secretKey = Read-SecureText -Prompt "S3 secret access key"
$sessionAnswer = (Read-Host "Do these credentials use AWS_SESSION_TOKEN? [y/N]").Trim()
$sessionToken = ""
if ($sessionAnswer -match '^(?i:y|yes)$') {
    $sessionToken = Read-SecureText -Prompt "S3 session token"
}
$resticPassword = New-ResticPassword

if ([string]::IsNullOrWhiteSpace($accessKey) -or [string]::IsNullOrEmpty($secretKey)) {
    throw "S3 access key ID and secret access key must not be empty."
}
foreach ($value in @($accessKey, $secretKey, $sessionToken, $resticPassword)) {
    if ($value -match "[`r`n`0]") { throw "Backup credential values must be single-line strings." }
}

$payload = [ordered]@{
    AWS_ACCESS_KEY_ID = $accessKey
    AWS_SECRET_ACCESS_KEY = $secretKey
    RESTIC_PASSWORD = $resticPassword
}
if ($sessionToken) { $payload.AWS_SESSION_TOKEN = $sessionToken }
$json = $payload | ConvertTo-Json -Compress
$args = @(
    "--config", (Quote-ProcessArgument $fullPolicyPath),
    "encrypt",
    "--filename-override", (Quote-ProcessArgument "secrets/backup.enc.yaml"),
    "--input-type", "json",
    "--output-type", "yaml"
) -join " "
$encrypted = Invoke-TextProcess -FilePath $sops -Arguments $args -InputText $json
if ([string]::IsNullOrWhiteSpace($encrypted)) { throw "SOPS returned empty ciphertext." }
foreach ($value in @($accessKey, $secretKey, $sessionToken, $resticPassword)) {
    if ($value -and $encrypted.Contains($value)) { throw "SOPS output unexpectedly contains a plaintext credential value." }
}

$parent = Split-Path -Parent $fullOutputPath
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$temporary = Join-Path $parent ("." + [System.IO.Path]::GetFileName($fullOutputPath) + "." + [guid]::NewGuid().ToString("N"))
try {
    [System.IO.File]::WriteAllText($temporary, $encrypted, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $fullOutputPath
}
finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    $accessKey = $null
    $secretKey = $null
    $sessionToken = $null
    $resticPassword = $null
    $json = $null
}

Write-Host "PASS encrypted backup secret bundle created"
Write-Host "  ciphertext: $fullOutputPath"
Write-Host "  restic repository password: generated automatically"
Write-Host "  plaintext file created: no"
Write-Host "  source checkout mutated: no"
