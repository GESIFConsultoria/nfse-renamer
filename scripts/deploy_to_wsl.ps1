# Deploy do NFSe Renamer Service direto para um ambiente WSL local.
#
# Copia o codigo-fonte e arquivos de suporte para /opt/nfse-renamer dentro do WSL,
# preservando a config.env existente e convertendo quebras de linha para LF.
#
# Uso (a partir da raiz do projeto):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_to_wsl.ps1
#   powershell ... -File .\scripts\deploy_to_wsl.ps1 -Distro "Ubuntu-24.04"
#
# Apos o deploy, reinstale/reinicie dentro do WSL (como root):
#   wsl -d Ubuntu-24.04 -u root -- bash /opt/nfse-renamer/scripts/install.sh
#   # ou, se ja instalado:
#   wsl -d Ubuntu-24.04 -u root -- systemctl restart nfse-renamer

param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$TargetUnc = "\\wsl.localhost\Ubuntu-24.04\opt\nfse-renamer"
)

$ErrorActionPreference = "Stop"

# Raiz do projeto = pasta pai deste script
$src = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dst = $TargetUnc
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Output "==> Origem:  $src"
Write-Output "==> Destino: $dst"
New-Item -ItemType Directory -Path $dst -Force | Out-Null

# 1) Preservar config.env existente (nao sobrescreve configuracoes locais)
$cfg = Join-Path $dst "config.env"
$cfgExists = Test-Path $cfg
if ($cfgExists) {
    Copy-Item $cfg (Join-Path $dst "config.env.bak_$stamp") -Force
    Write-Output "==> config.env preservada (backup: config.env.bak_$stamp)"
}

# 2) Limpar diretorios de codigo antigos via WSL (robusto p/ pastas nao-vazias e arquivos de root)
wsl -d $Distro -u root -- rm -rf /opt/nfse-renamer/src /opt/nfse-renamer/docs /opt/nfse-renamer/scripts

# 3) Copiar artefatos de deploy
Copy-Item (Join-Path $src "src")                  $dst -Recurse -Force
Copy-Item (Join-Path $src "docs")                 $dst -Recurse -Force
Copy-Item (Join-Path $src "scripts")              $dst -Recurse -Force
Copy-Item (Join-Path $src "nfse-renamer.service") $dst -Force
Copy-Item (Join-Path $src "requirements.txt")     $dst -Force
if (-not $cfgExists) {
    Copy-Item (Join-Path $src "config.env") $dst -Force
    Write-Output "==> config.env padrao copiada (nao havia uma no destino)"
}

# 4) Remover arquivos desnecessarios via WSL
wsl -d $Distro -u root -- bash -c "rm -f /opt/nfse-renamer/src/extract_nfse_info.txt; rm -rf /opt/nfse-renamer/src/__pycache__; find /opt/nfse-renamer -name '*.pyc' -delete"

# 5) Criar estrutura de runtime
foreach ($d in @("files\inbound","files\processed","files\reject","logs")) {
    New-Item -ItemType Directory -Path (Join-Path $dst $d) -Force | Out-Null
}

# 6) Converter CRLF -> LF (UTF-8 sem BOM) para arquivos de texto
$exts = @("*.sh","*.py","*.service","*.env","*.txt","*.md")
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
foreach ($ext in $exts) {
    Get-ChildItem $dst -Recurse -File -Filter $ext -ErrorAction SilentlyContinue | ForEach-Object {
        $content = [System.IO.File]::ReadAllText($_.FullName)
        $content = $content -replace "`r`n", "`n"
        [System.IO.File]::WriteAllText($_.FullName, $content, $utf8NoBom)
    }
}

# 7) Tornar scripts executaveis
wsl -d $Distro -u root -- bash -c "chmod +x /opt/nfse-renamer/scripts/*.sh 2>/dev/null; true"

Write-Output "DEPLOY_OK"
