# 📄 NFSe Renamer Service — README

Serviço Linux em Python para extração automática de metadados de NFSe a partir de arquivos PDF, com renomeação padronizada e movimentação por diretórios monitorados.

**⚠️ Importante**: O serviço processa **qualquer arquivo PDF** colocado na pasta de entrada, independentemente do nome. Os arquivos já processados são renomeados para o padrão `nfse_...` (minúsculo) e, por isso, são automaticamente ignorados em ciclos seguintes, evitando reprocessamento. Os arquivos que não puderem ser lidos/extraídos são movidos para `reject` (e também não são reprocessados).

**Observação sobre extração**: as regras de extração (regex) foram desenvolvidas e testadas com o layout da Prefeitura de Porto Alegre. PDFs de outros municípios são lidos normalmente, mas só serão renomeados se o conteúdo casar com as regex; caso contrário vão para `reject`. Para suportar outros municípios, as regex precisam ser estendidas (ver seção 6).

O objetivo é garantir que todos os PDFs entregues ao conector fiscal sigam o padrão definido pelo cliente:

```
nfse_<CNPJ_EMITENTE>_<NUM_RPS>_<NUM_NFSE>_<SERIE>.pdf
```

**Exemplo real extraído do PDF:**
```
nfse_02886427002450_146345_8_1.pdf
```

## 📋 Modos de Operação

O serviço oferece dois modos principais de funcionamento:

1. **Modo de Monitoramento**:
   - **Watchdog** (padrão): Detecta novos arquivos imediatamente via inotify
   - **Polling**: Verifica diretório em intervalos configuráveis

2. **Modo de Processamento**:
   - **Movimentação** (padrão): Move arquivos para pastas `processed` ou `reject`
   - **Renomear no lugar**: Renomeia arquivos na própria pasta `inbound` sem mover
   - **Upload FTP**: Envia arquivos processados para servidor FTP (opcional, pode combinar com outros modos)

Consulte a seção [Configuração Parametrizada](#-5-configuração-parametrizada-configenv) para detalhes sobre como configurar cada modo.

## ✔️ 1. Arquitetura da Solução

A solução é composta por quatro módulos principais:

1. **Monitoramento de Diretório** (Watchdog ou Polling)

   - **Modo Watchdog (padrão)**: Monitoramento contínuo via biblioteca watchdog/inotify. Dispara processamento imediatamente ao detectar criação de novos PDFs. Mais eficiente e responsivo.

   - **Modo Polling**: Verifica o diretório em intervalos configuráveis. Útil quando inotify não está disponível ou para ambientes com restrições específicas. Frequência configurável via `POLLING_INTERVAL`.

2. **Extractor NFSe**

Módulo dedicado à extração estruturada dos campos:
   - CNPJ Emitente
   - RPS (Número)
   - Série
   - NFSe (Número da Nota)

Usa regex, normalização e leitura via pdfplumber.

3. **Dispatcher com Retry Logic**

   Gerencia a movimentação/renomeação de arquivos e upload FTP:
   - **Modo padrão** (`RENAME_IN_PLACE="false"`):
     - `/processed` → sucesso (ou FTP se `USE_FTP="true"`)
     - `/reject` → erro de leitura/extração após todas as tentativas
   - **Modo renomear no lugar** (`RENAME_IN_PLACE="true"`):
     - Arquivo é renomeado na própria pasta INPUT_DIR (sucesso)
     - Se `USE_FTP="true"`, também envia para FTP
     - Em caso de erro, arquivo é movido para REJECT_DIR
   - **Modo FTP** (`USE_FTP="true"`):
     - Arquivos processados são enviados para servidor FTP
     - Suporta FTP anônimo e autenticado (com ou sem TLS)
     - Fallback automático para OUTPUT_DIR em caso de falha
   
   Inclui sistema robusto de retry, validação de arquivos e tratamento de erros.

4. **systemd Service**

   Executa o serviço de forma contínua, resiliente e auditável, com:
   - Restart automático em caso de falha
   - Logs integrados ao journald
   - Controle de recursos e timeouts
   - Política de restart configurável

## ✔️ 2. Estrutura de Diretórios

**Nota**: Os caminhos dos diretórios de trabalho (`INPUT_DIR`, `OUTPUT_DIR`, `REJECT_DIR`) são configuráveis via `config.env` e podem estar em qualquer local do servidor. A estrutura abaixo mostra apenas o padrão de instalação.

```
/opt/nfse-renamer/
│
├── config.env               # Configurações parametrizadas (define caminhos dos diretórios)
├── nfse-renamer.service     # Arquivo systemd
│
├── src/                     # ✅ Todo o código-fonte do serviço
│   ├── __init__.py          # Pacote Python
│   ├── __main__.py          # Ponto de entrada (execução como módulo)
│   ├── nfse_service.py      # Lógica principal do serviço
│   └── extract_nfse_info.py # Módulo de extração NFSe
│
├── docs/                    # Documentação
│   └── README_NFSE_RENAMER.md
│
├── scripts/                  # Scripts auxiliares
│   ├── install.sh           # Script de instalação automática
│   └── run_local.sh         # Script para execução local (desenvolvimento)
│
├── files/                   # Diretórios de trabalho (caminhos configuráveis em config.env)
│   ├── inbound/             # PDFs de entrada (monitorado) - caminho definido por INPUT_DIR
│   ├── processed/           # PDFs processados (caminho definido por OUTPUT_DIR, opcional se RENAME_IN_PLACE="true")
│   └── reject/              # PDFs rejeitados (caminho definido por REJECT_DIR, sempre necessário)
│
└── logs/                    # Arquivos de log (caminho definido por LOG_FILE)
    └── nfse_renamer.log
```

**Importante**: 
- Os diretórios `INPUT_DIR`, `OUTPUT_DIR` e `REJECT_DIR` podem estar em qualquer caminho do servidor
- Configure os caminhos desejados no arquivo `config.env`
- O serviço criará automaticamente os diretórios se não existirem

## ✔️ 3. Instalação

### Instalação Automática (Recomendada)

Use o script de instalação automática:

```bash
sudo ./scripts/install.sh
```

O script irá:
- Criar todos os diretórios necessários
- Copiar arquivos para `/opt/nfse-renamer`
- Instalar dependências Python
- Configurar e iniciar o serviço systemd
- Verificar se tudo está funcionando

### Instalação em Red Hat Enterprise Linux 9.6

O serviço é totalmente compatível com RHEL 9.6. Siga os passos abaixo:

**Pré-requisitos**:

1. **Instalar Python 3 e pip3** (se não estiverem instalados):
```bash
sudo dnf install -y python3 python3-pip
```

2. **(Opcional) Instalar dependências do sistema para pdfplumber**:
   
   Se você encontrar erros ao processar PDFs, pode ser necessário instalar bibliotecas do sistema:
```bash
sudo dnf install -y poppler poppler-utils poppler-cpp-devel
```

3. **Executar instalação automática**:
```bash
sudo ./scripts/install.sh
```

**Notas importantes para RHEL 9.6**:

- ✅ O script de instalação já trata automaticamente o erro "externally-managed-environment" usando `--break-system-packages`
- ✅ O RHEL 9.6 inclui Python 3.9+ por padrão, totalmente compatível
- ✅ O systemd está disponível e configurado corretamente
- ✅ Todas as bibliotecas Python padrão (`ftplib`, `os`, `shutil`, etc.) estão disponíveis

**Verificações antes da instalação**:

```bash
# Verificar versão do Python (deve ser 3.9+)
python3 --version

# Verificar se pip3 está disponível
pip3 --version

# Se pip3 não estiver instalado:
sudo dnf install -y python3-pip
```

**Após a instalação**:

```bash
# Verificar status do serviço
systemctl status nfse-renamer

# Ver logs
journalctl -u nfse-renamer -f
```

### Instalação em Ambiente com Proxy

Se o servidor estiver em ambiente com proxy corporativo, o `pip3` precisa de configuração para baixar pacotes do PyPI durante a instalação.

**⚠️ Importante**: O serviço em execução **não precisa de proxy** (exceto para FTP, se configurado). O proxy é necessário apenas durante a instalação para baixar as dependências Python.

**Opção 1 - Variáveis de ambiente (recomendado)**:

Os scripts de instalação detectam automaticamente variáveis de proxy. Configure antes de executar:

```bash
# Configurar proxy HTTP/HTTPS
export http_proxy="http://proxy.empresa.com:8080"
export https_proxy="http://proxy.empresa.com:8080"
export HTTP_PROXY="http://proxy.empresa.com:8080"
export HTTPS_PROXY="http://proxy.empresa.com:8080"

# Se o proxy requer autenticação:
export http_proxy="http://usuario:senha@proxy.empresa.com:8080"
export https_proxy="http://usuario:senha@proxy.empresa.com:8080"

# Executar instalação (sudo -E preserva variáveis de ambiente)
sudo -E ./scripts/install.sh
```

**Opção 2 - Configurar pip.conf**:

```bash
# Criar diretório de configuração do pip
sudo mkdir -p /etc/pip

# Criar arquivo de configuração
sudo tee /etc/pip/pip.conf > /dev/null <<EOF
[global]
proxy = http://proxy.empresa.com:8080
# Se precisar de autenticação:
# proxy = http://usuario:senha@proxy.empresa.com:8080
EOF

# Executar instalação
sudo ./scripts/install.sh
```

**Opção 3 - Instalar dependências manualmente**:

```bash
# Configurar proxy
export http_proxy="http://proxy.empresa.com:8080"
export https_proxy="http://proxy.empresa.com:8080"

# Instalar dependências manualmente
sudo pip3 install --break-system-packages --proxy http://proxy.empresa.com:8080 watchdog pdfplumber

# Depois executar o script de instalação (pulará a instalação de dependências)
sudo ./scripts/install.sh
```

**Verificar se proxy está funcionando**:

```bash
# Testar acesso ao PyPI através do proxy
pip3 install --proxy http://proxy.empresa.com:8080 --dry-run watchdog
```

**Notas importantes**:

- ✅ Os scripts `install.sh` e `run_local.sh` detectam automaticamente variáveis `http_proxy`, `https_proxy`, `HTTP_PROXY` e `HTTPS_PROXY`
- ✅ O serviço em execução **não faz requisições HTTP/HTTPS** - apenas processa arquivos localmente
- ✅ Se usar FTP (`USE_FTP="true"`), o FTP não usa proxy HTTP por padrão. Se o servidor FTP precisar passar por proxy, pode ser necessário configuração adicional no sistema ou uso de proxy FTP específico
- ✅ O proxy é necessário apenas durante a instalação para baixar `watchdog` e `pdfplumber` do PyPI

### Instalação Manual

1. Criar diretório base

**Nota**: Os caminhos dos diretórios são configuráveis via `config.env`. Os comandos abaixo usam os caminhos padrão. Se você configurar caminhos diferentes, ajuste os comandos conforme necessário.

**Nota**: Se você usar `RENAME_IN_PLACE="true"`, a pasta `processed` é opcional, mas `reject` é sempre necessária (arquivos com erro são movidos para reject mesmo neste modo).

```bash
# Criar todos os diretórios (recomendado) - usando caminhos padrão
mkdir -p /opt/nfse-renamer/files/{inbound,processed,reject}
mkdir -p /opt/nfse-renamer/logs

# Ou apenas o diretório obrigatório (se usar RENAME_IN_PLACE="true")
mkdir -p /opt/nfse-renamer/files/inbound
mkdir -p /opt/nfse-renamer/logs

# IMPORTANTE: Após criar os diretórios, configure os caminhos desejados em config.env
# O serviço criará automaticamente os diretórios configurados se não existirem
```

2. Descompactar o ZIP
```bash
unzip nfse-renamer.zip -d /opt/
```

3. Instalar bibliotecas Python

**Opção A - Instalação direta (se permitido pelo sistema)**:
```bash
pip3 install watchdog pdfplumber
```

**Opção B - Se receber erro "externally-managed-environment"**:

Este erro ocorre em sistemas Linux modernos (Debian 12+, Ubuntu 23.04+) que protegem o ambiente Python do sistema. Use uma das soluções abaixo:

**Solução 1: Usar flag --break-system-packages (recomendado para serviços systemd)**
```bash
pip3 install --break-system-packages watchdog pdfplumber
```

**Solução 2: Criar virtual environment (alternativa mais segura)**
```bash
# Criar virtual environment
python3 -m venv /opt/nfse-renamer/venv

# Ativar e instalar dependências
source /opt/nfse-renamer/venv/bin/activate
pip install watchdog pdfplumber
deactivate

# IMPORTANTE: Se usar venv, atualize o arquivo systemd para usar o Python do venv:
# ExecStart=/opt/nfse-renamer/venv/bin/python3 -m src
```

**Nota**: Para serviços systemd rodando como root, a Solução 1 é geralmente mais simples e adequada.

4. Configurar o systemd
```bash
cp /opt/nfse-renamer/nfse-renamer.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable nfse-renamer
systemctl start nfse-renamer
```

5. Verificar
```bash
systemctl status nfse-renamer
```

### Características do Serviço systemd

O arquivo `nfse-renamer.service` foi configurado com:

- ✅ **Restart automático**: Reinicia automaticamente em caso de falha
- ✅ **Política de restart inteligente**: Limita tentativas excessivas (5 tentativas em 5 minutos)
- ✅ **Logs integrados**: Logs disponíveis via `journalctl`
- ✅ **Timeout de parada**: 30 segundos para encerramento gracioso
- ✅ **Segurança**: `NoNewPrivileges` e `PrivateTmp` habilitados
- ✅ **Documentação**: Link para README no systemd

### Logs do Serviço

**Logs em tempo real**:
```bash
journalctl -u nfse-renamer -f
```

**Últimas 100 linhas**:
```bash
journalctl -u nfse-renamer -n 100
```

**Logs desde hoje**:
```bash
journalctl -u nfse-renamer --since today
```

## ✔️ 4. Funcionamento do Serviço

### Fluxo Operacional

1. **Usuário coloca um PDF** em `/opt/nfse-renamer/files/inbound/`

2. **Detecção automática**:
   - **Modo Watchdog**: Detecta imediatamente via inotify
   - **Modo Polling**: Detecta no próximo ciclo de verificação (configurável)

3. **Validação e preparação**:
   - Valida extensão PDF (apenas arquivos `.pdf` são considerados)
   - Ignora arquivos já processados (que começam com `nfse_` em minúsculo)
   - Aguarda arquivo estar completamente escrito
   - Verifica se não está em uso por outro processo
   
   **Importante**: O serviço processa **qualquer PDF** colocado na pasta de entrada, independentemente do nome. Arquivos já processados ficam com o prefixo `nfse_` (minúsculo) e são automaticamente ignorados em ciclos seguintes, evitando reprocessamento.

4. **Extração de metadados** (com retry em caso de erro):
   - CNPJ emitente
   - RPS
   - Número da Nota (NFSe)
   - Série

5. **Geração do novo nome**:
   ```
nfse_<cnpj>_<rps>_<nfse>_<serie>.pdf
   ```

6. **Renomeação/Movimentação/Upload**:
   - **Modo padrão** (`RENAME_IN_PLACE="false"`):
     - `/processed` → sucesso (ou FTP se `USE_FTP="true"`)
     - `/reject` → falha após todas as tentativas (log detalhado gerado)
   - **Modo renomear no lugar** (`RENAME_IN_PLACE="true"`):
     - Arquivo é renomeado na própria pasta `/inbound` (sucesso)
     - Se `USE_FTP="true"`, também envia para FTP
     - Em caso de erro, arquivo é movido para `/reject`
   - **Modo FTP** (`USE_FTP="true"`):
     - Arquivo processado é enviado para servidor FTP
     - Arquivo local é removido após upload bem-sucedido (se `RENAME_IN_PLACE="false"`)
     - Em caso de falha no upload, fallback para OUTPUT_DIR (se `RENAME_IN_PLACE="false"`)

### Características de Robustez

- ✅ **Retry automático**: Até 3 tentativas em caso de erro temporário
- ✅ **Validação de arquivo**: Aguarda arquivo estar completamente escrito
- ✅ **Prevenção de duplicatas**: Evita processar o mesmo arquivo simultaneamente
- ✅ **Timeout de processamento**: Limite configurável para evitar travamentos
- ✅ **Tratamento de arquivos em uso**: Detecta e aguarda liberação
- ✅ **Ajuste automático de permissões**: Garante permissões consistentes em todos os PDFs processados
- ✅ **Logs detalhados**: Todos os eventos são registrados com stack trace em erros

## ✔️ 5. Configuração Parametrizada (config.env)

Arquivo central de configuração com todas as opções disponíveis:

### Diretórios

```bash
INPUT_DIR="/opt/nfse-renamer/files/inbound"
OUTPUT_DIR="/opt/nfse-renamer/files/processed"
REJECT_DIR="/opt/nfse-renamer/files/reject"
LOG_FILE="/opt/nfse-renamer/logs/nfse_renamer.log"
```

### Modo de Operação e Frequência

```bash
# Modo de operação: "true" para polling, "false" para watchdog (event-driven)
USE_POLLING="false"

# Intervalo de verificação em segundos (apenas quando USE_POLLING=true)
# Exemplo: 5 = verifica a cada 5 segundos, 30 = a cada 30 segundos
POLLING_INTERVAL="5"
```

**Recomendações**:
- Use `USE_POLLING="false"` (watchdog) para melhor desempenho e resposta imediata
- Use `USE_POLLING="true"` apenas se inotify não estiver disponível ou houver restrições específicas
- Para polling, ajuste `POLLING_INTERVAL` conforme necessidade:
  - **5-10 segundos**: Alta frequência, maior uso de recursos
  - **30-60 segundos**: Frequência moderada, balanceado
  - **300+ segundos**: Baixa frequência, menor uso de recursos

### Resistência a Erros

```bash
# Número máximo de tentativas em caso de erro
MAX_RETRIES="3"

# Tempo de espera entre tentativas (segundos)
RETRY_DELAY="2"

# Timeout máximo para processamento de um arquivo (segundos)
PROCESS_TIMEOUT="60"

# Permissões dos arquivos PDF após processamento (formato octal: 644 = rw-r--r--)
FILE_PERMISSIONS="644"

# Permissões dos diretórios de processamento (formato octal: 755 = rwxr-xr-x)
DIR_PERMISSIONS="755"

# Ajustar permissões de todos os PDFs nas pastas a cada ciclo (true/false)
FIX_PERMISSIONS_ON_CYCLE="true"

# Renomear arquivo na própria pasta INPUT_DIR sem mover (true/false)
RENAME_IN_PLACE="false"
```

**Explicação**:
- `MAX_RETRIES`: Quantas vezes o serviço tentará processar um arquivo antes de mover para `/reject`
- `RETRY_DELAY`: Tempo de espera entre cada tentativa (útil para arquivos ainda sendo escritos)
- `PROCESS_TIMEOUT`: Limite máximo de tempo para processar um arquivo (evita travamentos)
- `FILE_PERMISSIONS`: Permissões dos arquivos PDF após processamento (formato octal, padrão: 644 = rw-r--r--)
- `DIR_PERMISSIONS`: Permissões dos diretórios de processamento (formato octal, padrão: 755 = rwxr-xr-x)
- `FIX_PERMISSIONS_ON_CYCLE`: Se `true`, ajusta permissões de todos os PDFs e diretórios a cada ciclo de iteração
- `RENAME_IN_PLACE`: Se `true`, renomeia o arquivo na própria pasta INPUT_DIR quando processado com sucesso

**Modo Renomear no Lugar**:
- `RENAME_IN_PLACE="true"`: 
  - **Sucesso**: Renomeia o arquivo na própria pasta INPUT_DIR (não move para processed)
  - **Erro**: Move arquivo para REJECT_DIR (mesmo comportamento do modo padrão)
- `RENAME_IN_PLACE="false"`: Comportamento padrão - move arquivos para processed (sucesso) ou reject (erro)
- Útil quando você quer manter arquivos processados na mesma pasta, apenas renomeados
- **Importante**: Arquivos com erro são sempre movidos para REJECT_DIR, independente do modo
- Exemplo de sucesso: `nota.pdf` → `nfse_02886427002450_146345_8_1.pdf` (na mesma pasta INPUT_DIR)

### Upload para FTP

```bash
# Usar FTP como destino (true/false)
# Quando true, arquivos processados são enviados para FTP em vez de OUTPUT_DIR
USE_FTP="false"

# Configurações FTP (apenas quando USE_FTP=true)
# FTP_HOST é obrigatório. FTP_USER e FTP_PASSWORD são opcionais (vazio = anônimo)
FTP_HOST=""
FTP_PORT="21"
FTP_USER=""
FTP_PASSWORD=""
FTP_PATH="/"
FTP_PASSIVE="true"
FTP_TIMEOUT="30"
FTP_USE_TLS="false"
```

**Explicação**:
- `USE_FTP`: Se `true`, arquivos processados são enviados para servidor FTP em vez de serem movidos para OUTPUT_DIR
- `FTP_HOST`: Endereço do servidor FTP (obrigatório quando USE_FTP="true")
- `FTP_PORT`: Porta do servidor FTP (padrão: 21)
- `FTP_USER`: Usuário para autenticação (opcional - vazio = login anônimo)
- `FTP_PASSWORD`: Senha para autenticação (opcional - vazio = login anônimo)
- `FTP_PATH`: Caminho remoto no servidor FTP onde os arquivos serão enviados (padrão: "/")
- `FTP_PASSIVE`: Modo passivo FTP (recomendado para firewalls, padrão: true)
- `FTP_TIMEOUT`: Timeout da conexão FTP em segundos (padrão: 30)
- `FTP_USE_TLS`: Usar FTP com TLS/SSL (FTPS) para conexão segura (padrão: false)

**Comportamento com FTP**:

1. **Modo padrão com FTP** (`RENAME_IN_PLACE="false"` e `USE_FTP="true"`):
   - Arquivo processado com sucesso → enviado para FTP e removido localmente
   - Se upload FTP falhar → arquivo é movido para OUTPUT_DIR como fallback
   - Arquivo com erro → movido para REJECT_DIR (não é enviado para FTP)

2. **Modo renomear no lugar com FTP** (`RENAME_IN_PLACE="true"` e `USE_FTP="true"`):
   - Arquivo processado com sucesso → renomeado localmente E enviado para FTP
   - Se upload FTP falhar → arquivo permanece renomeado localmente (processamento considerado sucesso)
   - Arquivo com erro → movido para REJECT_DIR (não é enviado para FTP)

3. **FTP Anônimo vs Autenticado**:
   - **Anônimo**: Deixe `FTP_USER=""` e `FTP_PASSWORD=""` vazios
   - **Autenticado**: Preencha `FTP_USER` e `FTP_PASSWORD` com as credenciais

**Exemplo de configuração FTP anônimo**:
```bash
USE_FTP="true"
FTP_HOST="ftp.exemplo.com"
FTP_PORT="21"
FTP_USER=""
FTP_PASSWORD=""
FTP_PATH="/public/uploads"
FTP_PASSIVE="true"
FTP_TIMEOUT="30"
FTP_USE_TLS="false"
```

**Exemplo de configuração FTP autenticado com TLS**:
```bash
USE_FTP="true"
FTP_HOST="ftp.exemplo.com"
FTP_PORT="21"
FTP_USER="usuario"
FTP_PASSWORD="senha_segura"
FTP_PATH="/uploads/nfse"
FTP_PASSIVE="true"
FTP_TIMEOUT="30"
FTP_USE_TLS="true"
```

**Notas importantes**:
- O serviço cria automaticamente o diretório remoto (`FTP_PATH`) se não existir
- Arquivos são enviados com o nome padronizado (ex: `nfse_02886427002450_146345_8_1.pdf`)
- Em caso de falha no upload FTP, o serviço tenta fallback para OUTPUT_DIR (se `RENAME_IN_PLACE="false"`)
- A senha FTP é armazenada em texto no `config.env` - proteja o arquivo com permissões adequadas (`chmod 600 config.env`)

**Permissões e Movimentação de Arquivos**:
- ✅ **O serviço consegue mover e renomear PDFs**: O serviço roda como `root` (configurado no systemd), então tem todas as permissões necessárias para mover arquivos, independentemente das permissões do arquivo ou diretório
- ✅ **Permissões de arquivo (644)**: Aplicadas aos PDFs após processamento para garantir consistência e segurança
- ✅ **Permissões de diretório (755)**: Garantem que os diretórios tenham permissões corretas para leitura/escrita
- ✅ **Ajuste automático**: O serviço ajusta automaticamente as permissões de todos os PDFs e diretórios:
  - No modo **polling**: ajusta permissões a cada ciclo de verificação
  - No modo **watchdog**: ajusta permissões a cada 5 minutos e imediatamente após processar cada arquivo
- ✅ **Importante**: As permissões do arquivo (644) **não impedem** a movimentação. Para mover um arquivo, o que importa são as permissões do **diretório** (que o serviço ajusta automaticamente para 755)

Altere conforme necessidade de cada cliente/ambiente.

## ✔️ 6. Regras de Extração (Regex)
Campo	Regex
CNPJ do Emitente	\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b
Número da Nota (NFSe)	Número da Nota\s*([0-9]{1,10})
RPS Número	RPS Nº\s*([0-9]+)
Série	(?i)Série\s*([A-Za-z0-9\-_]+)

**Nota**: A série aceita letras, números, hífens e underscores (ex: "1", "A", "NF", "1-A", etc.).

Essas regex foram testadas com PDFs reais da Prefeitura de Porto Alegre.

**Suporte a outros municípios**: o serviço lê **qualquer PDF** colocado na pasta de entrada, mas a extração depende do conteúdo casar com as regex acima. Layouts de NFSe variam por município (rótulos e posições diferentes), então PDFs de outras prefeituras só serão renomeados se o texto contiver os mesmos padrões; caso contrário, são movidos para `reject`. Para suportar um novo município, ajuste/estenda as regex em `src/extract_nfse_info.py` com base em um PDF de exemplo daquele município.

## ✔️ 7. Tratamento de Erros

### Sistema de Retry Automático

O serviço implementa um sistema robusto de retry que tenta processar arquivos até `MAX_RETRIES` vezes. Isso garante que erros temporários (arquivo ainda sendo escrito, rede instável, etc.) não resultem em rejeição imediata.

**Comportamento por modo**:
- **Modo padrão** (`RENAME_IN_PLACE="false"`): Após todas as tentativas, arquivo é movido para `/reject`
- **Modo renomear no lugar** (`RENAME_IN_PLACE="true"`): Após todas as tentativas, arquivo é movido para `/reject` (mesmo comportamento)
- **Importante**: Independente do modo, arquivos com erro são sempre movidos para `/reject`

### Situações que levam à pasta /reject ou permanência em /inbound (após todas as tentativas):

- PDF sem texto legível
- Campos obrigatórios ausentes
- PDF corrompido
- Permissão negada ao mover (após retries)
- Timeout de processamento excedido
- Erro de leitura persistente

### Validações Implementadas

- ✅ **Aguarda arquivo estar pronto**: Verifica se arquivo foi completamente escrito antes de processar
- ✅ **Detecção de arquivo em uso**: Evita processar arquivos que estão sendo acessados por outros processos
- ✅ **Prevenção de duplicatas**: Evita processar o mesmo arquivo simultaneamente
- ✅ **Validação de destino**: Verifica se arquivo destino já existe e adiciona timestamp se necessário
- ✅ **Tratamento de exceções**: Captura e registra todos os tipos de erro com stack trace completo

### Logs

Todos os eventos são logados em:
- **Arquivo de log**: `/opt/nfse-renamer/logs/nfse_renamer.log`
- **Journald**: `journalctl -u nfse-renamer -f` (logs do systemd)

Os logs incluem:
- Informações de processamento bem-sucedido
- Avisos sobre arquivos em uso ou timeouts
- Erros detalhados com stack trace
- Movimentações para `/reject` com motivo

## ✔️ 8. Atualização do Serviço

### Atualizar Configuração

Editar `config.env`:
```bash
vim /opt/nfse-renamer/config.env
```

Recarregar serviço (não requer restart, mas recomendado):
```bash
systemctl restart nfse-renamer
```

### Atualizar Código

Todos os arquivos de código estão em `/opt/nfse-renamer/src/`:
```bash
vim /opt/nfse-renamer/src/nfse_service.py
vim /opt/nfse-renamer/src/extract_nfse_info.py
```

Recarregar serviço:
```bash
systemctl restart nfse-renamer
```

**Nota**: O serviço é executado como módulo Python (`python3 -m src`), garantindo que todo o código fique organizado na pasta `src/`.

### Verificar Status

```bash
# Status do serviço
systemctl status nfse-renamer

# Logs em tempo real
journalctl -u nfse-renamer -f

# Últimas 50 linhas de log
journalctl -u nfse-renamer -n 50
```

## ✔️ 9. Testes
1. Copie um PDF válido para inbound:
```bash
cp exemplo.pdf /opt/nfse-renamer/files/inbound/
```

2. Observe processamento:
```bash
journalctl -u nfse-renamer -f
```

3. Verifique saída:

**Se `RENAME_IN_PLACE="false"` (padrão)**:
```bash
/opt/nfse-renamer/files/processed/nfse_<cnpj>_<rps>_<nfse>_<serie>.pdf
```

**Se `RENAME_IN_PLACE="true"`**:
```bash
/opt/nfse-renamer/files/inbound/nfse_<cnpj>_<rps>_<nfse>_<serie>.pdf
```

## ✔️ 10. Permissões e Movimentação de Arquivos

### ✅ O serviço consegue mover e renomear PDFs?

**Sim!** O serviço está configurado para rodar como `root` no systemd (`User=root`), o que garante todas as permissões necessárias para:

- ✅ Mover arquivos entre diretórios
- ✅ Renomear arquivos
- ✅ Criar novos arquivos
- ✅ Ajustar permissões de arquivos e diretórios

### Como funcionam as permissões?

1. **Permissões do arquivo (644)**: 
   - Aplicadas aos PDFs **após** o processamento
   - **Não impedem** a movimentação (o serviço roda como root)
   - Garantem que arquivos processados tenham permissões consistentes

2. **Permissões do diretório (755)**:
   - Aplicadas aos diretórios de processamento
   - Garantem acesso adequado aos diretórios
   - Ajustadas automaticamente na inicialização e a cada ciclo

3. **Processo de movimentação**:
   - O serviço move arquivos **antes** de ajustar permissões
   - As permissões 644 são aplicadas **após** a movimentação
   - Isso garante que o arquivo já está no destino correto quando as permissões são definidas

### Exemplo de fluxo:

```
1. PDF chega em /inbound com permissões 777 (qualquer)
2. Serviço (root) move para /processed (funciona sempre)
3. Serviço ajusta permissões do arquivo para 644
4. Serviço ajusta permissões do diretório para 755
```

## ✔️ 11. Troubleshooting

### ❗ Serviço não inicia

**Verificar permissões**:
```bash
chown -R root:root /opt/nfse-renamer
chmod -R 755 /opt/nfse-renamer/src
```

**Verificar dependências**:
```bash
# Tentar instalação normal
pip3 install watchdog pdfplumber

# Se receber erro "externally-managed-environment", usar:
pip3 install --break-system-packages watchdog pdfplumber

# Verificar se estão instalados
python3 -c "import watchdog; import pdfplumber; print('OK')"
```

**Verificar configuração**:
```bash
# Verificar se config.env existe e está correto
cat /opt/nfse-renamer/config.env

# Verificar se diretórios existem
ls -la /opt/nfse-renamer/
```

**Verificar logs do systemd**:
```bash
journalctl -u nfse-renamer -n 100
```

### ❗ PDF não aparece na pasta processed

**Consultar logs**:
```bash
# Log do arquivo
tail -n 50 /opt/nfse-renamer/logs/nfse_renamer.log

# Log do systemd
journalctl -u nfse-renamer -n 50
```

**Verificar se arquivo está em /reject** (apenas se `RENAME_IN_PLACE="false"`):
```bash
ls -la /opt/nfse-renamer/files/reject/
```

**Verificar se arquivo ainda está em /inbound**:
```bash
ls -la /opt/nfse-renamer/files/inbound/
```

**Nota**: Se `RENAME_IN_PLACE="true"`, apenas arquivos processados com sucesso permanecem em `/inbound/`. Arquivos com erro são movidos para `/reject/`.

### ❗ Regex não encontrou campos

- Verificar se PDF é da Prefeitura de Porto Alegre
- Enviar exemplo de PDF para revisão da regex
- Verificar se PDF contém texto legível (não é apenas imagem)

### ❗ Serviço reinicia constantemente

**Verificar logs para identificar erro**:
```bash
journalctl -u nfse-renamer -n 100 --no-pager
```

**Verificar configuração do systemd**:
```bash
systemctl cat nfse-renamer
```

**Ajustar política de restart** (se necessário):
Editar `/etc/systemd/system/nfse-renamer.service` e ajustar `StartLimitInterval` e `StartLimitBurst`.

### ❗ Arquivos ficam presos em /inbound

**Se `RENAME_IN_PLACE="false"`**:
- Verificar permissões de escrita em `/processed` e `/reject`
- Verificar espaço em disco: `df -h`
- Consultar logs para erros específicos
- Verificar se arquivo está sendo usado por outro processo: `lsof /opt/nfse-renamer/files/inbound/arquivo.pdf`

**Se `RENAME_IN_PLACE="true"`**:
- Arquivos processados com sucesso permanecem em `/inbound/` (renomeados)
- Arquivos com erro são movidos para `/reject/` (mesmo comportamento do modo padrão)
- Verificar se arquivo foi renomeado corretamente em `/inbound/`
- Verificar se arquivo com erro foi movido para `/reject/`
- Consultar logs para verificar se houve erro no processamento

## ✔️ 12. Roadmap Futuro

Processamento paralelo

API REST para consulta de status

Registro de auditoria Syslog

Regras customizadas por município

## ✔️ 13. Autor / Suporte Técnico

NFSe Renamer Service
Desenvolvido para automação de integração fiscal, padrão corporativo e alto desempenho operacional.

Para evoluções, troubleshooting e extensões, abra issue no repositório.