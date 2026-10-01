# =============================================================================
# release.ps1 - Sentinela Release Script
# =============================================================================

$ErrorActionPreference = 'Stop'

Write-Host "============================================================"
Write-Host "  SENTINELA - PIPELINE DE RELEASE"
Write-Host "============================================================"

# Read version.json
$versionFile = "version.json"
if (-not (Test-Path $versionFile)) {
    Write-Error "version.json nao encontrado"
    exit 1
}
$versionData = Get-Content $versionFile -Raw -Encoding utf8 | ConvertFrom-Json
$version = $versionData.version
Write-Host "Versao detectada em version.json: v$version"

# Read manifest.json (serie 2.x) and validate.
# O manifesto legado docs/updates/manifest.json fica congelado em 1.7.0 para a serie 1.x:
# o script de assinatura recusa altera-lo e confere sua assinatura a cada release.
$manifestFile = "docs/updates/v2/manifest.json"
if (-not (Test-Path $manifestFile)) {
    Write-Error "manifest.json nao encontrado"
    exit 1
}
$manifestData = Get-Content $manifestFile -Raw -Encoding utf8 | ConvertFrom-Json
if ($manifestData.latest_version -ne $version) {
    Write-Error "Versao desalinhada! version.json=$version manifest.json=$($manifestData.latest_version)"
    exit 1
}
Write-Host "manifest.json (v2) alinhado com version.json"

# Read and validate CHANGELOG.md
$changelogFile = "CHANGELOG.md"
if (-not (Test-Path $changelogFile)) {
    Write-Error "CHANGELOG.md nao encontrado"
    exit 1
}
$changelogContent = Get-Content $changelogFile -Raw -Encoding utf8
$expectedHeader = "## [$version]"
if (-not ($changelogContent.Contains($expectedHeader))) {
    Write-Error "CHANGELOG.md nao contem a sessao da versao atual. Cabecalho esperado: '$expectedHeader'"
    exit 1
}
Write-Host "CHANGELOG.md contem a versao v$version"

$releaseTitle = "Sentinela v$version"
$exePath      = "dist/Sentinela.exe"

# Step 1: Build frontend
Write-Host "[1/5] Building frontend (npm run build)..."
Push-Location "frontend"
try {
    npm run build
} catch {
    Write-Error "Falha no build do frontend: $_"
    Pop-Location
    exit 1
}
Pop-Location
Write-Host "Frontend compilado com sucesso."

# Step 2: Sign manifest
Write-Host "[2/5] Signing manifest.json (v2) e conferindo o manifesto legado..."
python.exe .\src\scripts\sign_update_manifest.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao assinar o manifesto."
    exit 1
}
Write-Host "Manifesto assinado."

# Step 3: Deploy GitHub Pages
Write-Host "[3/5] Deploying GitHub Pages (mkdocs gh-deploy)..."
mkdocs gh-deploy --force
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha no deploy do GitHub Pages."
    exit 1
}
Write-Host "Deploy do GitHub Pages concluido."

# Step 4: Build EXE
Write-Host "[4/5] Building EXE (build_pywebview_uvicorn.ps1)..."
powershell.exe -ExecutionPolicy Bypass -File .\build_pywebview_uvicorn.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha no build do executavel."
    exit 1
}
if (-not (Test-Path $exePath)) {
    Write-Error "EXE nao encontrado em $exePath."
    exit 1
}
Write-Host "EXE gerado com sucesso: $exePath"

# Step 5: Create Release on GitHub
Write-Host "[5/5] Creating release on GitHub (v$version)..."

# Limpa tag local, tag remota e release existentes — sem falhar se nao existirem
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
git tag -d "v$version" 2>$null
git push --delete origin "v$version" 2>$null
gh release delete "v$version" --yes --cleanup-tag 2>$null
$ErrorActionPreference = $oldEAP

# Extrai apenas a seção da versão atual do CHANGELOG
$changelogLines = Get-Content $changelogFile -Encoding utf8
$inSection = $false
$sectionLines = @()
foreach ($line in $changelogLines) {
    if ($line -match "^## \[$version\]") {
        $inSection = $true
        continue
    }
    if ($inSection -and $line -match "^## \[") {
        break
    }
    if ($inSection) {
        $sectionLines += $line
    }
}
$releaseNotes = ($sectionLines | Out-String).Trim()
$tmpNotes = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tmpNotes, $releaseNotes, (New-Object System.Text.UTF8Encoding $false))

gh release create "v$version" $exePath `
    --title $releaseTitle `
    --notes-file $tmpNotes

Remove-Item $tmpNotes -Force -ErrorAction SilentlyContinue

if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao criar release no GitHub."
    exit 1
}

Write-Host "============================================================"
Write-Host "  RELEASE v$version CONCLUIDO COM SUCESSO!"
Write-Host "============================================================"
