[CmdletBinding()]
param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt"),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "solo-vps\state"),
    [string]$PolicyPath = "",
    [string]$EncryptedPath = ""
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

function Invoke-SopsDecrypt {
    param([string]$Sops, [string]$Policy, [string]$Encrypted, [string]$Key)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Sops
    $psi.Arguments = @(
        "--config", (Quote-ProcessArgument $Policy),
        "decrypt", "--input-type", "yaml", "--output-type", "json",
        (Quote-ProcessArgument $Encrypted)
    ) -join " "
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["SOPS_AGE_KEY_FILE"] = $Key
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) { throw "Could not start sops.exe" }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "SOPS decrypt failed with exit code $($process.ExitCode); secret-bearing stderr was suppressed." }
    return $stdout
}

function Assert-ObservabilityPayload {
    param([Parameter(Mandatory = $true)]$Payload)
    $names = @($Payload.PSObject.Properties.Name)
    $required = @("LOKI_URL", "LOKI_USERNAME", "GRAFANA_CLOUD_API_KEY")
    foreach ($name in $required) {
        if ($names -notcontains $name -or [string]::IsNullOrEmpty([string]$Payload.$name)) { throw "Decrypted observability bundle is missing required key $name." }
    }
    foreach ($name in $names) {
        if ($required -notcontains $name) { throw "Decrypted observability bundle contains unsupported key $name." }
        if ([string]$Payload.$name -match "[`r`n`0]") { throw "Decrypted observability bundle contains a multi-line value." }
    }
    $uri = $null
    if (-not [Uri]::TryCreate([string]$Payload.LOKI_URL, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne "https" -or -not $uri.AbsolutePath.EndsWith("/loki/api/v1/push")) {
        throw "Decrypted LOKI_URL does not match the reviewed HTTPS Loki push endpoint shape."
    }
    return $names.Count
}

$sops = Resolve-SoloVpsTool -Name "sops"
$fullStateRoot = [System.IO.Path]::GetFullPath($StateRoot)
if (-not $PolicyPath) { $PolicyPath = Join-Path $fullStateRoot "sops\.sops.yaml" }
if (-not $EncryptedPath) { $EncryptedPath = Join-Path $fullStateRoot "secrets\observability.enc.yaml" }
$fullPolicyPath = [System.IO.Path]::GetFullPath($PolicyPath)
$fullEncryptedPath = [System.IO.Path]::GetFullPath($EncryptedPath)
$fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
foreach ($path in @($fullPolicyPath, $fullEncryptedPath, $fullKeyPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file is missing: $path" }
}

$json = Invoke-SopsDecrypt -Sops $sops -Policy $fullPolicyPath -Encrypted $fullEncryptedPath -Key $fullKeyPath
try { $payload = $json | ConvertFrom-Json } catch { throw "SOPS output is not valid JSON." }
$keyCount = Assert-ObservabilityPayload -Payload $payload
$json = $null
$payload = $null

Write-Host "PASS encrypted observability secret bundle decrypts and matches the expected schema"
Write-Host "  ciphertext: $fullEncryptedPath"
Write-Host "  keys present: $keyCount"
Write-Host "  plaintext printed: no"
Write-Host "  age private key copied to VPS: no"
