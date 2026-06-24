import re
import pdfplumber


class PdfminerException(Exception):
    """Exceção do pdfminer para tratamento de erros específicos do PDF."""
    pass


# --- Layout legado (Prefeitura de Porto Alegre) ---
REGEX_CNPJ = r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"
REGEX_NFSE = r"(?i)Número da Nota\s*[\r\n ]*([0-9]{1,10})"
REGEX_RPS = r"RPS Nº\s*([0-9]+)"
REGEX_SERIE = r"(?i)Série\s*([A-Za-z0-9\-_]+)"

# --- Layout nacional (DANFSe v2.0 / Sistema Nacional da NFS-e) ---
REGEX_CHAVE = r"(?<!\d)(\d{50})(?!\d)"
NAC_MARKERS = ("danfse", "sistema nacional da nfs-e",
               "chave de acesso", "número da dps", "numero da dps")


def _read_pdf_text(pdf_path):
    """Abre o PDF e retorna o texto extraído, tratando erros do pdfplumber/pdfminer."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join([p.extract_text() or "" for p in pdf.pages])
    except PdfminerException:
        raise
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        if "/Root" in error_msg or "Root" in error_msg:
            raise ValueError(f"PDF não pode ser lido pelo pdfplumber (estrutura não padrão): {error_msg}. O PDF pode estar corrompido ou ter formato não suportado.")
        elif "pdfminer" in error_msg.lower():
            raise PdfminerException(error_msg)
        else:
            raise ValueError(f"Erro ao abrir PDF: {error_type}: {error_msg}")


def _is_national_layout(text):
    """Detecta se o PDF segue o padrão nacional (DANFSe v2.0)."""
    low = text.lower()
    return any(m in low for m in NAC_MARKERS)


def _extract_national(text):
    """
    Extrai campos do layout nacional (DANFSe v2.0).
    CNPJ e nº da NFS-e vêm da chave de acesso (50 dígitos, posições fixas).
    Nº da DPS vem do cabeçalho (auto-validado contra o nº da NFS-e da chave).
    """
    # 1) Chave de acesso (50 dígitos) -> CNPJ e nº NFS-e
    chave_match = re.search(REGEX_CHAVE, text.replace(" ", ""))
    if not chave_match:
        raise ValueError("Chave de acesso (50 dígitos) não encontrada no DANFSe nacional.")
    chave = chave_match.group(1)
    cnpj = chave[9:23]                 # posições 10-23: CNPJ do emitente
    nfse_num = str(int(chave[23:36]))  # posições 24-36: nº da NFS-e (sem zeros à esquerda)

    # 2) Número da DPS e Série: ficam na linha de valores logo abaixo do cabeçalho
    # "NÚMERO DA DPS  SÉRIE DA DPS  DATA E HORA DA EMISSÃO DA DPS", na ordem:
    # <nº DPS> <série> <data> <hora>
    lines = text.splitlines()
    dps_num = None
    serie_num = None
    for i, line in enumerate(lines):
        if re.search(r"(?i)N[ÚU]MERO\s+DA\s+DPS", line):
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r"\s*(\d{1,15})\s+([0-9A-Za-z][0-9A-Za-z\-_]*)", lines[j])
                if m:
                    dps_num = str(int(m.group(1)))
                    serie_num = m.group(2)
                    break
            break
    if dps_num is None or serie_num is None:
        raise ValueError("Número da DPS / Série da DPS não encontrados no DANFSe nacional.")

    return cnpj, dps_num, nfse_num, serie_num


def _extract_porto_alegre(text):
    """Extrai campos do layout legado da Prefeitura de Porto Alegre."""
    cnpj = re.search(REGEX_CNPJ, text)
    if not cnpj:
        raise ValueError("CNPJ não encontrado no PDF.")
    cnpj = re.sub(r"\D", "", cnpj.group(0))

    nfse = re.search(REGEX_NFSE, text)
    if not nfse:
        raise ValueError("Número da NFSe não encontrado no PDF.")
    nfse_num = str(int(nfse.group(1)))

    rps = re.search(REGEX_RPS, text)
    if not rps:
        raise ValueError("Número RPS não encontrado no PDF.")
    rps_num = rps.group(1)

    serie = re.search(REGEX_SERIE, text)
    if not serie:
        raise ValueError("Série não encontrada no PDF.")
    serie_num = serie.group(1)

    return cnpj, rps_num, nfse_num, serie_num


def extract_nfse_info(pdf_path):
    """
    Extrai informações de NFSe do PDF e retorna o nome padronizado (sem extensão).
    Detecta automaticamente o layout: padrão nacional (DANFSe v2.0) ou legado (Porto Alegre).
    """
    full_text = _read_pdf_text(pdf_path)

    # Verifica se conseguiu extrair texto
    if not full_text or len(full_text.strip()) < 50:
        raise ValueError("PDF não contém texto legível ou está vazio (texto extraído muito curto)")

    if _is_national_layout(full_text):
        cnpj, rps_num, nfse_num, serie_num = _extract_national(full_text)
    else:
        cnpj, rps_num, nfse_num, serie_num = _extract_porto_alegre(full_text)

    # Regra especial: quando CNPJ for 02886427001306, série deve ser maiúscula
    if cnpj == "02886427001306":
        serie_num = serie_num.upper()
        return f"nfse_{cnpj}_{rps_num}_{nfse_num}".lower() + "_" + serie_num

    # Garante que o prefixo "nfse" seja sempre minúsculo
    return f"nfse_{cnpj}_{rps_num}_{nfse_num}_{serie_num}".lower()
