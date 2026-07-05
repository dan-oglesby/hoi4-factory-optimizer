# Deploys a pointer descriptor into the HOI4 mod folder so the launcher can find
# the in-game companion mod that lives in this repo. Idempotent.
#
# Usage:  pwsh -File scripts/deploy-mod.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$modSrc = Join-Path $repoRoot 'mod'
$forwardModSrc = ($modSrc -replace '\\', '/')

$docs = [Environment]::GetFolderPath('MyDocuments')
$modDir = Join-Path $docs 'Paradox Interactive/Hearts of Iron IV/mod'
New-Item -ItemType Directory -Force -Path $modDir | Out-Null

$descriptor = @"
name="Factory Optimizer Companion"
path="$forwardModSrc"
supported_version="1.19.*"
tags={
	"Utilities"
}
"@

$target = Join-Path $modDir 'factory_optimizer_companion.mod'
Set-Content -Path $target -Value $descriptor -Encoding UTF8
Write-Host "Wrote $target"
Write-Host "Points at: $forwardModSrc"
Write-Host "Enable 'Factory Optimizer Companion' in the HOI4 launcher mod list."
