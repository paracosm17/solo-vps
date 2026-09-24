[CmdletBinding()]
param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt")
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
$Sentinel = "solo-vps-m13-workstation-proof-v1"

$ageKeygen = Resolve-SoloVpsTool -Name "age-keygen"
$sops = Resolve-SoloVpsTool -Name "sops"

$fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
if (-not (Test-Path -LiteralPath $fullKeyPath -PathType Leaf)) {
    throw "Age key does not exist: $fullKeyPath"
}

$recipient = (& $ageKeygen -y $fullKeyPath 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $recipient -notmatch '^age1[0-9a-z]+$') {
    throw "Could not derive a valid public recipient from the age key."
}

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("solo-vps-m13-" + [guid]::NewGuid().ToString("N"))
$plain = Join-Path $tempDir "proof.yaml"
$encrypted = Join-Path $tempDir "proof.enc.yaml"
New-Item -ItemType Directory -Path $tempDir | Out-Null

$oldKeyFile = $env:SOPS_AGE_KEY_FILE
try {
    [System.IO.File]::WriteAllText($plain, "value: $Sentinel`n", [System.Text.UTF8Encoding]::new($false))

    & $sops encrypt --age $recipient --output $encrypted $plain
    if ($LASTEXITCODE -ne 0) { throw "sops.exe encrypt failed." }

    $env:SOPS_AGE_KEY_FILE = $fullKeyPath
    $decrypted = (& $sops decrypt $encrypted | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "sops.exe decrypt failed." }
    if ($decrypted -notmatch [regex]::Escape($Sentinel)) {
        throw "Decrypted proof did not contain the expected sentinel."
    }

    Write-Host "PASS Solo VPS production age key SOPS roundtrip"
    Write-Host "  public recipient: $recipient"
    Write-Host "  temporary proof files removed: yes"
}
finally {
    if ($null -eq $oldKeyFile) {
        Remove-Item Env:SOPS_AGE_KEY_FILE -ErrorAction SilentlyContinue
    } else {
        $env:SOPS_AGE_KEY_FILE = $oldKeyFile
    }
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
