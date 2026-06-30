# -*- coding: utf-8 -*-
"""
utils.py — Funções auxiliares: normalização de texto/SKU, detecção de colunas,
           extração de peso de pacote e exportação para Excel.

PPCP Inteligente v1.0 | Márcio Dias do Amaral
Tecnologias: Python, Pandas, OpenPyXL
"""

import math
import re
import unicodedata
from io import BytesIO

import numpy as np
import pandas as pd


# ── Constantes de domínio ────────────────────────────────────────────────────

APP_NAME = "PPCP Inteligente"

# Códigos que por exceção pesam 25 kg, independente do número no código
CODIGOS_EXCECAO_25_KG = {
    "B2825",
    "B3225",
    "BE3225",
    "B3825",
    "B3625",
    "BEM4225",
    "BE4225",
    "BEG3225",
    "B2225",
    "CRA28",
    "JUR32",
    "JUR22",
    "CRA32F",
    "JUR38P",
    "CRA42",
    "JUR42P",
}

# Ações que indicam recomendação de produzir
ACOES_RECOMENDAM_PRODUZIR = {
    "Produzir urgente",
    "Programar produção",
    "Produzir sob pedido / reduzir estoque",
    "Produzir somente se houver pedido ou risco comercial",
}

# Ações que indicam recomendação de NÃO produzir
ACOES_RECOMENDAM_NAO_PRODUZIR = {
    "Manter monitoramento",
    "Reduzir estoque",
    "Não produzir",
}


# ── Normalização de texto ─────────────────────────────────────────────────────

def remover_acentos(texto):
    """Remove acentos e diacríticos de uma string."""
    texto = str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalizar_coluna(coluna):
    """
    Normaliza o nome de uma coluna para comparação fuzzy:
    remove acentos, converte para minúsculas, substitui caracteres especiais por espaço.
    """
    texto = remover_acentos(coluna).lower().strip()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def normalizar_sku(valor):
    """Normaliza um SKU/produto: strip + upper + espaços simples."""
    if pd.isna(valor):
        return ""
    return " ".join(str(valor).strip().upper().split())


def normalizar_codigo(valor):
    """Normaliza um código: strip + upper + remove espaços internos."""
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().upper()
    return re.sub(r"\s+", "", texto)


def extrair_codigo_colchetes(valor):
    """
    Extrai o código dentro de colchetes no início de um campo de produto.
    Exemplo: '[AGC01] Ração Premium' → 'AGC01'
    """
    if pd.isna(valor):
        return ""
    encontrado = re.match(r"^\s*\[([A-Z0-9]+)\]", str(valor).strip().upper())
    if encontrado:
        return normalizar_codigo(encontrado.group(1))
    return ""


def normalizar_colunas_dataframe(df):
    """Aplica normalizar_coluna() a todos os nomes de colunas do DataFrame."""
    df = df.copy()
    df.columns = [normalizar_coluna(coluna) for coluna in df.columns]
    return df


# ── Detecção fuzzy de colunas ─────────────────────────────────────────────────

def primeira_coluna_por_termos(df, termos):
    """
    Retorna o nome da primeira coluna cujo nome normalizado contém algum dos termos.
    Retorna None se nenhuma coluna for encontrada.
    """
    for coluna in df.columns:
        nome = normalizar_coluna(coluna)
        for termo in termos:
            if termo in nome:
                return coluna
    return None


def identificar_coluna_produto(df):
    """Detecta a coluna de produto/SKU/descrição."""
    return primeira_coluna_por_termos(
        df, ["produto", "sku", "item", "descricao", "referencia", "material"]
    )


def identificar_coluna_codigo(df):
    """Detecta a coluna de código/cod."""
    return primeira_coluna_por_termos(df, ["codigo", "cod"])


def identificar_coluna_data(df):
    """Detecta a coluna de data de faturamento/emissão."""
    return primeira_coluna_por_termos(
        df, ["dt faturado", "data", "faturamento", "faturado", "emissao"]
    )


def identificar_coluna_volume(df):
    """Detecta a coluna de volume/pacotes/quantidade."""
    return primeira_coluna_por_termos(
        df, ["pacotes", "pacote", "quantidade", "qtd", "qtde", "volume"]
    )


def identificar_coluna_estoque_pacotes(df):
    """Detecta a coluna de estoque atual em pacotes."""
    return primeira_coluna_por_termos(
        df,
        [
            "saldo em estoque pacotes",
            "estoque atual pacotes",
            "estoque pacotes",
            "saldo pacotes",
            "pacotes",
            "pacote",
            "estoque atual",
            "estoque",
            "saldo estoque",
            "saldo",
        ],
    )


def identificar_coluna_ruptura(df):
    """Detecta a coluna de ruptura/pedido não atendido."""
    return primeira_coluna_por_termos(
        df, ["pedido nao atendido", "pedido não atendido", "ruptura"]
    )


def identificar_coluna_pacotes_programados(df):
    """Detecta a coluna de pacotes programados na programação semanal.

    Termos prioritários são buscados primeiro. Somente como fallback busca
    'pacotes' genérico, excluindo colunas de velocidade (por min, por hora).
    """
    # Termos específicos — busca antes de qualquer "pacotes" genérico
    termos_especificos = [
        "plano de ensaque",
        "plano ensaque",
        "pla de ensaque",
        "pla ensaque",
        "pacotes programados",
        "quantidade programada",
        "qtd programada",
        "qtde programada",
    ]
    resultado = primeira_coluna_por_termos(df, termos_especificos)
    if resultado:
        return resultado

    # Fallback: "pacotes" genérico, excluindo colunas de velocidade/taxa
    termos_excluir = ["por min", "por hora", "velocidade", "cadencia", "taxa", "ritmo"]
    for coluna in df.columns:
        nome = normalizar_coluna(coluna)
        if "pacotes" in nome and not any(excl in nome for excl in termos_excluir):
            return coluna
    return None


def identificar_coluna_kg_programado(df):
    """Detecta a coluna de kg programado na programação semanal."""
    return primeira_coluna_por_termos(
        df, ["kg para ensacar", "kg programado", "kg_programado", "quilo programado"]
    )


def identificar_coluna_prod_programacao(df):
    """Detecta a coluna Prod (código base) na programação semanal."""
    return primeira_coluna_por_termos(
        df, ["prod", "produto", "cod", "codigo base", "código base"]
    )


def identificar_coluna_apre_programacao(df):
    """Detecta a coluna Apre (apresentação/embalagem) na programação semanal."""
    return primeira_coluna_por_termos(
        df, ["apre", "apresentacao", "apresentação", "embalagem"]
    )


def identificar_coluna_linha_programacao(df):
    """Detecta a coluna de linha de produção na programação semanal."""
    return primeira_coluna_por_termos(df, ["linhas", "linha"])


def identificar_coluna_plano_realizado(df):
    """Detecta a coluna de plano realizado na programação semanal."""
    return primeira_coluna_por_termos(
        df, ["plano realizado", "realizado", "produzido"]
    )


# ── Extração de peso de pacote pelo código ────────────────────────────────────

def extrair_peso_pacote(codigo):
    """
    Extrai o peso do pacote em kg a partir do código do SKU.

    Regras:
    - Se o código estiver em CODIGOS_EXCECAO_25_KG → 25,0 kg
    - Caso contrário, extrai o último número do código como peso em kg

    Retorna
    -------
    (float, str): (peso_kg, regra_aplicada)
    """
    codigo_normalizado = normalizar_codigo(codigo)
    if codigo_normalizado in CODIGOS_EXCECAO_25_KG:
        return 25.0, "Exceção 25 kg"

    numeros = re.findall(r"\d+", codigo_normalizado)
    if not numeros:
        return np.nan, "Não identificado"

    return float(int(numeros[-1])), "Extraído do código"


def extrair_peso_pacote_kg(codigo):
    """Retorna apenas o peso em kg (sem a regra). Veja extrair_peso_pacote()."""
    peso, _ = extrair_peso_pacote(codigo)
    return peso


def extrair_regra_peso(codigo):
    """Retorna apenas a regra de extração de peso. Veja extrair_peso_pacote()."""
    _, regra = extrair_peso_pacote(codigo)
    return regra


# ── Utilitários de data e detecção de colunas mensais ────────────────────────

def arredondar_para_cima(valor):
    """Arredonda um número para o inteiro superior (math.ceil). Retorna NaN se NaN."""
    if pd.isna(valor):
        return np.nan
    return int(math.ceil(valor))


def coluna_parece_data(nome_coluna, serie):
    """
    Heurística para detectar se uma coluna é de data (e não de vendas mensais).

    Considera data se:
    - Nome contém termos como 'data', 'dt', 'faturado', 'emissao'
    - Série é datetime64
    - Série numérica com valores entre 20000 e 60000 (números seriais de data Excel)
    """
    nome = normalizar_coluna(nome_coluna)
    termos_data = ["data", "dt", "faturado", "faturamento", "emissao", "ano mes"]

    if any(termo in nome for termo in termos_data):
        return True
    if pd.api.types.is_datetime64_any_dtype(serie):
        return True
    if pd.api.types.is_numeric_dtype(serie):
        valores = pd.to_numeric(serie, errors="coerce").dropna()
        if not valores.empty and valores.between(20000, 60000).mean() > 0.80:
            return True
    return False


def identificar_colunas_mensais(df, coluna_produto, coluna_codigo):
    """
    Identifica as colunas de vendas mensais em um DataFrame de formato mensal aberto.

    Critérios: nome contém termos mensais (jan, fev, ..., 202x) e
    ao menos 60% dos valores são numéricos.

    Parâmetros
    ----------
    df : pd.DataFrame (com colunas já normalizadas)
    coluna_produto : str ou None
    coluna_codigo : str ou None

    Retorna
    -------
    list com nomes das colunas mensais identificadas.
    """
    termos_mensais = [
        "jan", "fev", "mar", "abr", "mai", "jun",
        "jul", "ago", "set", "out", "nov", "dez",
        "mes", "venda", "consumo", "201", "202",
    ]

    colunas_ignorar = [coluna_produto, coluna_codigo]
    colunas_mensais = []

    for coluna in df.columns:
        if coluna in colunas_ignorar:
            continue
        if coluna_parece_data(coluna, df[coluna]):
            continue

        serie_numerica = pd.to_numeric(df[coluna], errors="coerce")
        proporcao_numerica = serie_numerica.notna().mean() if len(df) else 0
        nome_parece_mes = any(termo in coluna for termo in termos_mensais)

        if proporcao_numerica >= 0.60 and nome_parece_mes:
            colunas_mensais.append(coluna)

    return colunas_mensais


def converter_data(serie):
    """
    Converte uma série de datas em formato misto (ISO ou dayfirst).
    Tenta formato ISO primeiro; se falhar, tenta dayfirst=True.
    """
    texto = serie.astype(str).str.strip()
    parece_iso = texto.str.match(r"^\d{4}-\d{1,2}-\d{1,2}").mean() > 0.60
    if parece_iso:
        datas = pd.to_datetime(serie, errors="coerce")
    else:
        datas = pd.to_datetime(serie, errors="coerce", dayfirst=True)
    return datas.fillna(pd.to_datetime(serie, errors="coerce"))


# ── Normalização da programação semanal ───────────────────────────────────────

def normalizar_prod_programacao(valor):
    """Normaliza o campo Prod da programação: remove acentos, upper, só alfanumérico."""
    if pd.isna(valor):
        return ""
    texto = remover_acentos(str(valor)).upper().strip()
    return re.sub(r"[^A-Z0-9]", "", texto)


def normalizar_apresentacao_programacao(valor):
    """
    Normaliza o campo Apre (apresentação/kg) da programação semanal.
    Extrai o número e formata com zero-pad se necessário (1→01, 5→05, 7→07).
    """
    if pd.isna(valor):
        return ""
    texto = remover_acentos(str(valor)).upper().strip()
    texto = texto.replace("KG", "")
    texto = texto.replace(",", ".")
    encontrado = re.search(r"\d+(?:\.\d+)?", texto)
    if not encontrado:
        return ""
    numero = int(float(encontrado.group(0)))
    if numero in {1, 5, 7}:
        return f"{numero:02d}"
    return str(numero)


def montar_codigo_programacao_por_prod_apre(prod, apre):
    """
    Constrói o código de SKU a partir de Prod + Apre.
    Exemplo: Prod='AGC', Apre='01' → 'AGC01'
    """
    prod_normalizado = normalizar_prod_programacao(prod)
    apre_normalizada = normalizar_apresentacao_programacao(apre)
    if not prod_normalizado or not apre_normalizada:
        return ""
    return prod_normalizado + apre_normalizada


def coluna_ruptura_para_bool(serie):
    """
    Converte a coluna de ruptura para booleano.
    Aceita numérico (>0 = True) ou texto ('sim', 's', 'x', '1', 'true' = True).
    """
    if serie is None:
        return pd.Series(dtype=bool)
    valores_numericos = pd.to_numeric(serie, errors="coerce")
    if valores_numericos.notna().any():
        return valores_numericos.fillna(0) > 0
    texto = serie.astype(str).str.strip().str.lower()
    return texto.isin(["sim", "s", "true", "1", "x", "ruptura"]) | (texto != "")


# ── Exportação ────────────────────────────────────────────────────────────────

def gerar_excel(
    resultado,
    base_pacotes,
    base_kg,
    estoque,
    lead_time_por_chave=None,
    tabela_takt=None,
    tabela_politica_estoque=None,
    painel_gerencial=None,
    rupturas_evitaveis=None,
    aderencia_programacao=None,
    programacao_tratada=None,
):
    """
    Gera o arquivo Excel de resultado com múltiplas abas.

    Abas geradas:
    - Resultado (obrigatória)
    - Base Mensal Pacotes
    - Base Mensal KG
    - Estoque Atual
    - Lead Time por chave OP (se fornecido)
    - Takt Time (se fornecido)
    - Politica Estoque (se fornecido)
    - Painel Gerencial (se fornecido)
    - Rupturas Evitáveis (se fornecido)
    - Aderência Programação (se fornecido)

    Retorna
    -------
    bytes do arquivo .xlsx.
    """
    saida = BytesIO()
    with pd.ExcelWriter(saida, engine="openpyxl") as writer:
        resultado.to_excel(writer, sheet_name="Resultado", index=False)
        base_pacotes.to_excel(writer, sheet_name="Base Mensal Pacotes", index=False)
        base_kg.to_excel(writer, sheet_name="Base Mensal KG", index=False)
        estoque.to_excel(writer, sheet_name="Estoque Atual", index=False)
        if lead_time_por_chave is not None and not lead_time_por_chave.empty:
            lead_time_por_chave.to_excel(writer, sheet_name="Lead Time por chave OP", index=False)
        if tabela_takt is not None and not tabela_takt.empty:
            tabela_takt.to_excel(writer, sheet_name="Takt Time", index=False)
        if tabela_politica_estoque is not None and not tabela_politica_estoque.empty:
            tabela_politica_estoque.to_excel(writer, sheet_name="Politica Estoque", index=False)
        if painel_gerencial is not None and not painel_gerencial.empty:
            painel_gerencial.to_excel(writer, sheet_name="Painel Gerencial", index=False)
        if rupturas_evitaveis is not None and not rupturas_evitaveis.empty:
            rupturas_evitaveis.to_excel(writer, sheet_name="Rupturas Evitáveis", index=False)
        if aderencia_programacao is not None and not aderencia_programacao.empty:
            aderencia_programacao.to_excel(writer, sheet_name="Aderência Programação", index=False)
    return saida.getvalue()
