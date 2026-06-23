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
REGEX_SERIE_NAC = r"(?i)S[ÉE]RIE\s+DA\s+DPS\s*[\r\n ]*([0-9A-Za-z]+)"
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

    # 2) Número da DPS: os dois primeiros números do cabeçalho são, em ordem,
    # o nº da NFS-e e o nº da DPS. Valida o 1º contra a chave; se bater, usa o 2º.
    top_nums = re.findall(r"(?m)^\s*(\d{3,12})\s*$", text)
    dps_num = None
    if len(top_nums) >= 2 and str(int(top_nums[0])) == nfse_num:
        dps_num = str(int(top_nums[1]))
    else:
        # fallback: primeiro número do topo que não seja o nº da NFS-e
        for n in top_nums:
            if str(int(n)) != nfse_num and len(n) <= 10:
                dps_num = str(int(n))
                break
    if dps_num is None:
        raise ValueError("Número da DPS não encontrado no DANFSe nacional.")

    # 3) Série da DPS
    serie_match = re.search(REGEX_SERIE_NAC, text)
    if not serie_match:
        raise ValueError("Série da DPS não encontrada no DANFSe nacional.")
    serie_num = serie_match.group(1)

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
