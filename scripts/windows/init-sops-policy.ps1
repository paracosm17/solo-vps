[CmdletBinding()]
param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".config\solo-vps\age-key.txt"),
    [string]$ProjectRoot = ([System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "solo-vps\state"),
    [switch]$ResetPublicPolicy,
    [switch]$StartFresh
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

function Write-PublicFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content,
        [string]$LegacyContent = ""
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $current = [System.IO.File]::ReadAllText($Path)
        if ($current -eq $Content) {
            return "unchanged"
        }
        if ([string]::IsNullOrEmpty($LegacyContent) -or $current -ne $LegacyContent) {
            throw "Refusing to overwrite existing public SOPS policy file: $Path. Review recipient rotation explicitly instead."
        }

        $temporary = Join-Path $parent ("." + [System.IO.Path]::GetFileName($Path) + "." + [guid]::NewGuid().ToString("N"))
        $backup = Join-Path $parent ("." + [System.IO.Path]::GetFileName($Path) + ".backup." + [guid]::NewGuid().ToString("N"))
        try {
            [System.IO.File]::WriteAllText($temporary, $Content, [System.Text.UTF8Encoding]::new($false))
            # A real Windows policy-migration run rejected the earlier null
            # backup-path Replace call before SOPS was reached. Use a legal
            # same-directory backup path, then remove that short-lived public
            # policy backup after the atomic replacement succeeds.
            [System.IO.File]::Replace($temporary, $Path, $backup)
        }
        finally {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
        }
        return "migrated"
    }

    $temporary = Join-Path $parent ("." + [System.IO.Path]::GetFileName($Path) + "." + [guid]::NewGuid().ToString("N"))
    try {
        [System.IO.File]::WriteAllText($temporary, $Content, [System.Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $Path
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
    return "created"
}

function Get-PublicStateRecipients {
    param(
        [Parameter(Mandatory = $true)][string]$PolicyPath,
        [Parameter(Mandatory = $true)][string]$RecipientPath
    )

    $values = @()
    $malformed = @()

    if (Test-Path -LiteralPath $RecipientPath -PathType Leaf) {
        $value = ([System.IO.File]::ReadAllText($RecipientPath)).Trim()
        if ($value -match '^age1[0-9a-z]+$') {
            $values += $value
        }
        else {
            $malformed += $RecipientPath
        }
    }

    if (Test-Path -LiteralPath $PolicyPath -PathType Leaf) {
        $text = [System.IO.File]::ReadAllText($PolicyPath)
        $matches = [regex]::Matches($text, '(?m)^\s*-\s*(age1[0-9a-z]+)\s*$')
        if ($matches.Count -eq 0) {
            $malformed += $PolicyPath
        }
        else {
            foreach ($match in $matches) {
                $values += $match.Groups[1].Value
            }
        }
    }

    [pscustomobject]@{
        Recipients = @($values | Sort-Object -Unique)
        MalformedPaths = @($malformed)
    }
}

function Get-EncryptedStateBundles {
    param([Parameter(Mandatory = $true)][string]$Root)

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        return @()
    }

    return @(
        Get-ChildItem -LiteralPath $Root -Recurse -File -Filter "*.enc.yaml" -ErrorAction SilentlyContinue |
            Sort-Object FullName
    )
}

function Backup-And-RemovePublicState {
    param(
        [Parameter(Mandatory = $true)][string[]]$Paths,
        [Parameter(Mandatory = $true)][string]$ArchiveRoot
    )

    $existing = @($Paths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    if ($existing.Count -eq 0) {
        return $null
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $archive = Join-Path $ArchiveRoot $stamp
    $suffix = 0
    while (Test-Path -LiteralPath $archive) {
        $suffix += 1
        $archive = Join-Path $ArchiveRoot ("$stamp-$suffix")
    }
    New-Item -ItemType Directory -Force -Path $archive | Out-Null

    foreach ($path in $existing) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $archive ([System.IO.Path]::GetFileName($path)))
    }
    foreach ($path in $existing) {
        Remove-Item -LiteralPath $path -Force
    }

    return $archive
}


function Archive-And-RemoveLocalSecretState {
    param(
        [Parameter(Mandatory = $true)][string[]]$Paths,
        [Parameter(Mandatory = $true)][string]$StateRoot,
        [Parameter(Mandatory = $true)][string]$ArchiveRoot,
        [Parameter(Mandatory = $true)][string]$CurrentRecipient,
        [string[]]$ExistingRecipients = @()
    )

    $existing = @(
        $Paths |
            Sort-Object -Unique |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    )
    if ($existing.Count -eq 0) {
        return $null
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $archive = Join-Path $ArchiveRoot $stamp
    $suffix = 0
    while (Test-Path -LiteralPath $archive) {
        $suffix += 1
        $archive = Join-Path $ArchiveRoot ("$stamp-$suffix")
    }
    New-Item -ItemType Directory -Force -Path $archive | Out-Null

    $statePrefix = $StateRoot.TrimEnd([char[]]"\/") + [System.IO.Path]::DirectorySeparatorChar
    foreach ($path in $existing) {
        $fullPath = [System.IO.Path]::GetFullPath($path)
        if (-not $fullPath.StartsWith($statePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to archive a path outside Solo VPS state: $fullPath"
        }
        $relative = $fullPath.Substring($statePrefix.Length)
        $destination = Join-Path $archive $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $fullPath -Destination $destination
    }

    $previousText = if ($ExistingRecipients.Count -gt 0) { $ExistingRecipients -join ", " } else { "unknown/unreadable" }
    $manifest = @(
        "Solo VPS local encrypted-state archive",
        "Created: $([DateTime]::Now.ToString('o'))",
        "Reason: operator explicitly requested -StartFresh",
        "Previous public recipient(s): $previousText",
        "Current age key recipient: $CurrentRecipient",
        "Private age key copied here: no",
        "Archived files: $($existing.Count)"
    ) -join "`n"
    [System.IO.File]::WriteAllText(
        (Join-Path $archive "README.txt"),
        $manifest + "`n",
        [System.Text.UTF8Encoding]::new($false)
    )

    foreach ($path in $existing) {
        Remove-Item -LiteralPath $path -Force
    }
    return $archive
}

$ageKeygen = Resolve-SoloVpsTool -Name "age-keygen"
$sops = Resolve-SoloVpsTool -Name "sops"
$fullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
$fullProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$fullStateRoot = [System.IO.Path]::GetFullPath($StateRoot)

if (-not (Test-Path -LiteralPath $fullKeyPath -PathType Leaf)) {
    throw "Age key does not exist: $fullKeyPath. Run .\scripts\windows\new-age-key.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $fullProjectRoot "PROJECT_PASSPORT.md") -PathType Leaf)) {
    throw "ProjectRoot is not a Solo VPS checkout: $fullProjectRoot"
}

$recipient = (& $ageKeygen -y $fullKeyPath 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $recipient -notmatch '^age1[0-9a-z]+$') {
    throw "Could not derive a valid public recipient from the age key."
}

$sopsContent = @"
---
creation_rules:
  - path_regex: '(^|[\\/])secrets[\\/].*\.enc\.yaml$'
    age:
      - $recipient
    mac_only_encrypted: false

stores:
  yaml:
    indent: 2
"@ -replace "`r`n", "`n"
if (-not $sopsContent.EndsWith("`n")) { $sopsContent += "`n" }
$legacySopsContent = $sopsContent.Replace("(^|[\\/])secrets[\\/]", "(^|/)secrets/")
$recipientContent = "$recipient`n"

$sopsPath = Join-Path $fullStateRoot "sops\.sops.yaml"
$recipientPath = Join-Path $fullStateRoot "sops\production.txt"
$publicState = Get-PublicStateRecipients -PolicyPath $sopsPath -RecipientPath $recipientPath
$mismatchedRecipients = @($publicState.Recipients | Where-Object { $_ -ne $recipient })
$needsExplicitReset = ($mismatchedRecipients.Count -gt 0 -or $publicState.MalformedPaths.Count -gt 0)
$encryptedBundles = @(Get-EncryptedStateBundles -Root $fullStateRoot)
$publicStateArchive = $null
$freshStateArchive = $null
$freshArchivedBundleCount = 0

if ($ResetPublicPolicy -and $StartFresh) {
    throw "Choose only one reset mode: -ResetPublicPolicy or -StartFresh."
}

if ($StartFresh) {
    $freshArchivedBundleCount = $encryptedBundles.Count
    $archiveRoot = Join-Path (Split-Path -Parent $fullStateRoot) "archive\workstation-secrets"
    $pathsToArchive = @($sopsPath, $recipientPath) + @($encryptedBundles | ForEach-Object { $_.FullName })
    $freshStateArchive = Archive-And-RemoveLocalSecretState `
        -Paths $pathsToArchive `
        -StateRoot $fullStateRoot `
        -ArchiveRoot $archiveRoot `
        -CurrentRecipient $recipient `
        -ExistingRecipients $publicState.Recipients
    $needsExplicitReset = $false
}
elseif ($needsExplicitReset) {
    if (-not $ResetPublicPolicy) {
        $existingText = if ($publicState.Recipients.Count -gt 0) { $publicState.Recipients -join ", " } else { "unreadable/malformed" }
        $message = @"
Existing public SOPS state does not match the current age key.
  current key recipient: $recipient
  existing public recipient: $existingText
  encrypted bundles found: $($encryptedBundles.Count)
No files were changed.

If you are intentionally repeating the Solo VPS setup on this workstation and can enter the credentials again, archive the old local ciphertext and start clean:
  .\scripts\windows\init-sops-policy.ps1 -StartFresh

-StartFresh does not delete the old encrypted files. It moves the active public policy and *.enc.yaml bundles to %LOCALAPPDATA%\solo-vps\archive\workstation-secrets\<timestamp> and creates a policy for the current key.

If you still need to decrypt the old bundles, do not start fresh. Recover the previous age private key and rotate/re-encrypt them instead.
"@
        throw $message.Trim()
    }

    if ($encryptedBundles.Count -gt 0) {
        $bundleList = ($encryptedBundles | ForEach-Object { "  - $($_.FullName)" }) -join "`n"
        throw "Refusing -ResetPublicPolicy because encrypted state bundles exist:`n$bundleList`nFor a deliberate clean rerun that preserves those ciphertext files in an archive, use -StartFresh. If you need to decrypt them, recover the previous age key instead."
    }

    $archiveRoot = Join-Path $fullStateRoot "sops\archive"
    $publicStateArchive = Backup-And-RemovePublicState -Paths @($sopsPath, $recipientPath) -ArchiveRoot $archiveRoot
}

$sopsStatus = Write-PublicFile -Path $sopsPath -Content $sopsContent -LegacyContent $legacySopsContent
$recipientStatus = Write-PublicFile -Path $recipientPath -Content $recipientContent

# Probe the generated creation rule with fixed non-sensitive input so Windows path
# matching failures are detected here, before a real secret helper asks for values.
$probeInput = '{"SOLO_VPS_SOPS_POLICY_PROBE":"ok"}'
$probeOutput = ($probeInput | & $sops --config $sopsPath encrypt --filename-override "secrets/policy-probe.enc.yaml" --input-type json --output-type yaml 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Generated SOPS policy probe failed with exit code $LASTEXITCODE. Safe diagnostic output: $($probeOutput.Trim())"
}
if ([string]::IsNullOrWhiteSpace($probeOutput) -or $probeOutput -notmatch '(?m)^sops:') {
    throw "Generated SOPS policy probe returned unexpected output."
}

Write-Host "PASS Solo VPS local SOPS policy initialized"
Write-Host "  policy: $sopsPath ($sopsStatus)"
Write-Host "  recipient: $recipientPath ($recipientStatus)"
Write-Host "  public recipient: $recipient"
if ($publicStateArchive) {
    Write-Host "  previous public state archived: $publicStateArchive"
}
if ($freshStateArchive) {
    Write-Host "  previous local secret state archived: $freshStateArchive"
    Write-Host "  encrypted bundles archived: $freshArchivedBundleCount"
}
Write-Host "  private age key copied to repository/VPS: no"
Write-Host "  cross-platform SOPS policy probe: PASS"
Write-Host ""
Write-Host "  source checkout mutated: no"
Write-Host ""
Write-Host "Review the persistent public policy files with:"
Write-Host "  Get-Content `"$sopsPath`""
Write-Host "  Get-Content `"$recipientPath`""
Write-Host "These files live outside the Git checkout and survive source replacement/reclone."
