[CmdletBinding()]
param(
    [Parameter()]
    [string]$BackupDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-GitCommand {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $result = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $details = ($result -join [Environment]::NewLine).Trim()
        throw "Comando Git falhou: git $($Arguments -join ' ')`n$details"
    }

    return ($result -join [Environment]::NewLine).Trim()
}

try {
    $repoRoot = Invoke-GitCommand -Arguments @('rev-parse', '--show-toplevel')
    if ([string]::IsNullOrWhiteSpace($repoRoot)) {
        throw 'Nao foi possivel identificar a raiz do repositorio.'
    }

    $repoRoot = [IO.Path]::GetFullPath($repoRoot)
    Push-Location -LiteralPath $repoRoot
    try {
        $commit = Invoke-GitCommand -Arguments @('rev-parse', 'HEAD')
        if ($commit -notmatch '^[0-9a-fA-F]{40}$') {
            throw "HEAD invalido: $commit"
        }

        $trackedFilesOutput = Invoke-GitCommand -Arguments @('ls-files')
        $trackedFiles = if ([string]::IsNullOrWhiteSpace($trackedFilesOutput)) {
            @()
        }
        else {
            $trackedFilesOutput -split '\r?\n'
        }

        $trackedSensitiveFiles = @(
            $trackedFiles | Where-Object {
                $normalizedPath = $_ -replace '\\', '/'
                $isEnvironmentExample = $normalizedPath -match '(^|/)\.env\.example$'
                $isEnvironmentFile = $normalizedPath -match '(^|/)\.env($|\.)' -and -not $isEnvironmentExample
                $isSecretsPath = $normalizedPath -match '(^|/)(\.secrets|secrets)(/|$)'
                $isEnvironmentFile -or $isSecretsPath
            }
        )
        if ($trackedSensitiveFiles.Count -gt 0) {
            throw "Arquivos potencialmente sensiveis estao rastreados e impedem o backup: $($trackedSensitiveFiles -join ', ')"
        }

        $backupPassword = $env:SENTINELA_BACKUP_PASSWORD
        if ([string]::IsNullOrWhiteSpace($backupPassword)) {
            $envFile = Join-Path $repoRoot '.env'
            if (Test-Path -LiteralPath $envFile) {
                foreach ($line in Get-Content -LiteralPath $envFile) {
                    if ($line -match '^\s*SENTINELA_BACKUP_PASSWORD\s*=\s*(.+?)\s*$') {
                        $backupPassword = $Matches[1].Trim('"', "'")
                        break
                    }
                }
            }
        }
        if ([string]::IsNullOrWhiteSpace($backupPassword)) {
            throw "SENTINELA_BACKUP_PASSWORD nao definida (.env ou ambiente); o backup nao pode ser criptografado."
        }

        $sevenZip = Get-Command 7z -ErrorAction SilentlyContinue
        if ($null -eq $sevenZip) {
            $sevenZipPath = 'C:\Program Files\7-Zip\7z.exe'
            if (Test-Path -LiteralPath $sevenZipPath) {
                $sevenZip = @{ Source = $sevenZipPath }
            }
            else {
                throw "7z/NanaZip nao encontrado no PATH nem em '$sevenZipPath'."
            }
        }
        $sevenZipExe = $sevenZip.Source

        if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
            $BackupDirectory = $env:SENTINELA_BACKUP_DIRECTORY
        }
        if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
            $envFile = Join-Path $repoRoot '.env'
            if (Test-Path -LiteralPath $envFile) {
                foreach ($line in Get-Content -LiteralPath $envFile) {
                    if ($line -match '^\s*SENTINELA_BACKUP_DIRECTORY\s*=\s*(.+?)\s*$') {
                        $BackupDirectory = $Matches[1].Trim('"', "'")
                        break
                    }
                }
            }
        }
        if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
            $documentsDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
            if ([string]::IsNullOrWhiteSpace($documentsDirectory)) {
                throw 'Nao foi possivel determinar a pasta Documentos para salvar o backup.'
            }

            $BackupDirectory = Join-Path $documentsDirectory 'SentinelaBackups'
        }

        $BackupDirectory = [IO.Path]::GetFullPath($BackupDirectory)
        New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null

        $shortCommit = $commit.Substring(0, 12).ToLowerInvariant()
        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $archiveName = "sentinela-$shortCommit-$timestamp"
        $temporaryZipPath = Join-Path $BackupDirectory "$archiveName-tmp.zip"
        $archivePath = Join-Path $BackupDirectory "$archiveName.7z"

        if (Test-Path -LiteralPath $archivePath) {
            throw "O arquivo de backup ja existe: $archivePath"
        }
        if (Test-Path -LiteralPath $temporaryZipPath) {
            throw "O arquivo temporario de backup ja existe: $temporaryZipPath"
        }

        try {
            & git archive --format=zip "--output=$temporaryZipPath" $commit
            if ($LASTEXITCODE -ne 0) {
                throw "git archive falhou para o commit $commit."
            }

            $archive = Get-Item -LiteralPath $temporaryZipPath -ErrorAction Stop
            if ($archive.Length -le 0) {
                throw "O backup foi criado vazio: $temporaryZipPath"
            }

            # Empacota o zip do commit dentro de um .7z com AES-256 e nomes de
            # arquivos criptografados; depois valida integridade com a senha.
            & $sevenZipExe a -t7z -mhe=on "-p$backupPassword" $archivePath $temporaryZipPath | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "7z falhou ao criptografar o backup do commit $commit."
            }

            & $sevenZipExe t "-p$backupPassword" $archivePath | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Validacao do backup criptografado falhou: $archivePath"
            }
        }
        finally {
            if (Test-Path -LiteralPath $temporaryZipPath) {
                Remove-Item -LiteralPath $temporaryZipPath -Force -ErrorAction SilentlyContinue
            }
        }

        $encrypted = Get-Item -LiteralPath $archivePath -ErrorAction Stop
        if ($encrypted.Length -le 0) {
            throw "O backup criptografado ficou vazio: $archivePath"
        }

        Write-Host "Backup criptografado do commit $shortCommit criado em $archivePath"
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Error "Falha no backup pos-commit: $($_.Exception.Message)"
    exit 1
}
