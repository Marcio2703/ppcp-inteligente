# -*- coding: utf-8 -*-
"""
processamento.py — Lógica de negócio do PPCP Inteligente.

Responsabilidades:
- Classificação de demanda por CV
- Política híbrida de estoque (por classificação)
- Takt Time
- Rupturas evitáveis
- Aderência da programação semanal
- KPIs do Painel Gerencial

PPCP Inteligente v1.0 | Márcio Dias do Amaral
Tecnologias: Python, Pandas, NumPy
"""

import numpy as np
import pandas as pd

import utils


# ── Parâmetros padrão da política de estoque ─────────────────────────────────

PARAMETROS_COBERTURA_PADRAO = {
    "estavel": 7,        # dias de cobertura alvo para SKUs Estáveis
    "intermediario": 10, # dias de cobertura alvo para SKUs Intermediários
    "intermitente": 3,   # dias de cobertura alvo para SKUs Intermitentes
    "sem_venda": 0,      # dias de cobertura para SKUs Sem Venda
}

# Cobertura mínima em dias por classificação (componente 1 da política híbrida)
COBERTURA_MINIMA_DIAS = {
    "Estável": 5,
    "Intermediário": 7,
    "Intermitente": 3,
    "Sem venda": 0,
}

# Fator de segurança sobre o lead time por classificação (componente 2 da política híbrida)
FATOR_SEGURANCA = {
    "Estável": 0.30,
    "Intermediário": 0.50,
    "Intermitente": 1.00,
    "Sem venda": 0.00,
}


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFICAÇÃO DE DEMANDA
# ═══════════════════════════════════════════════════════════════════════════════

def classificar_sku(media_pacotes, cv):
    """
    Classifica um SKU conforme o Coeficiente de Variação (CV).

    Regras:
        média = 0 ou NaN → 'Sem venda'
        CV < 0,40         → 'Estável'
        0,40 ≤ CV ≤ 0,70  → 'Intermediário'
        CV > 0,70         → 'Intermitente'

    Parâmetros
    ----------
    media_pacotes : float
    cv : float

    Retorna
    -------
    str com a classificação.
    """
    if pd.isna(media_pacotes) or media_pacotes == 0:
        return "Sem venda"
    if pd.isna(cv):
        return "Sem venda"
    if cv < 0.40:
        return "Estável"
    if cv <= 0.70:
        return "Intermediário"
    return "Intermitente"


def politica_estoque(classificacao):
    """Retorna a política de estoque textual para uma classificação."""
    politicas = {
        "Estável": "Produzir para estoque",
        "Intermediário": "Estoque controlado",
        "Intermitente": "Produzir sob pedido",
        "Sem venda": "Sem produção planejada",
    }
    return politicas.get(classificacao, "Avaliar manualmente")


def dias_estoque_por_classificacao(classificacao):
    """Retorna o número de dias de estoque padrão para a classificação (usado quando não há lead time)."""
    if classificacao == "Estável":
        return 15
    if classificacao == "Intermediário":
        return 7
    if classificacao == "Intermitente":
        return 3
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# MONTAGEM DA BASE DE VENDAS
# ═══════════════════════════════════════════════════════════════════════════════

def montar_cadastro(base):
    """
    Extrai o cadastro único de SKUs (código, produto, peso, regra) da base transacional.

    Parâmetros
    ----------
    base : pd.DataFrame — base transacional com colunas codigo_chave, SKU / produto,
                          código, peso_pacote_kg, regra_peso.

    Retorna
    -------
    pd.DataFrame deduplicado por codigo_chave.
    """
    cadastro = base[["codigo_chave", "SKU / produto", "código", "peso_pacote_kg", "regra_peso"]].copy()
    return cadastro.drop_duplicates(subset=["codigo_chave"]).reset_index(drop=True)


def montar_base_transacional(df, coluna_produto, coluna_codigo, coluna_data, coluna_volume):
    """
    Processa um arquivo de vendas no formato transacional (linha por nota/entrega).

    Faz pivot por mês agrupando pacotes e kg vendidos por SKU.

    Parâmetros
    ----------
    df : pd.DataFrame — DataFrame com colunas já normalizadas.
    coluna_produto, coluna_codigo, coluna_data, coluna_volume : str

    Retorna
    -------
    (base_pacotes, base_kg, cadastro, meses) — DataFrames pivotados + lista de meses.

    Raises
    ------
    ValueError se a coluna de código não estiver disponível ou a base ficar vazia.
    """
    if coluna_codigo is None:
        raise ValueError("A planilha de vendas precisa ter coluna de código para cruzamento com estoque.")

    base = df[[coluna_produto, coluna_codigo, coluna_data, coluna_volume]].copy()
    base = base.rename(
        columns={
            coluna_produto: "SKU / produto",
            coluna_codigo: "código",
            coluna_data: "data venda",
            coluna_volume: "pacotes",
        }
    )
    base["SKU / produto"] = base["SKU / produto"].apply(utils.normalizar_sku)
    base["código"] = base["código"].apply(utils.normalizar_codigo)
    base["codigo_chave"] = base["código"]
    base["peso_pacote_kg"] = base["codigo_chave"].apply(utils.extrair_peso_pacote_kg)
    base["regra_peso"] = base["codigo_chave"].apply(utils.extrair_regra_peso)
    base["data venda"] = utils.converter_data(base["data venda"])
    base["pacotes"] = pd.to_numeric(base["pacotes"], errors="coerce").fillna(0)
    base["vendas_kg"] = base["pacotes"] * base["peso_pacote_kg"]
    base = base[(base["codigo_chave"] != "") & (base["data venda"].notna())]

    if base.empty:
        raise ValueError("A base transacional não possui linhas válidas com código, produto, data e pacotes.")

    base["ano_mes"] = base["data venda"].dt.to_period("M").astype(str)
    meses = sorted(base["ano_mes"].dropna().unique().tolist())

    cadastro = montar_cadastro(base)
    base_pacotes = base.pivot_table(
        index="codigo_chave",
        columns="ano_mes",
        values="pacotes",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=meses, fill_value=0).reset_index()
    base_kg = base.pivot_table(
        index="codigo_chave",
        columns="ano_mes",
        values="vendas_kg",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=meses, fill_value=0).reset_index()

    return base_pacotes, base_kg, cadastro, meses


def montar_base_mensal_aberta(df, coluna_produto, coluna_codigo, colunas_mensais):
    """
    Processa um arquivo de vendas no formato mensal aberto (colunas = meses).

    Parâmetros
    ----------
    df : pd.DataFrame — DataFrame com colunas já normalizadas.
    coluna_produto, coluna_codigo : str
    colunas_mensais : list

    Retorna
    -------
    (base_pacotes, base_kg, cadastro, colunas_mensais)

    Raises
    ------
    ValueError se a coluna de código não estiver disponível.
    """
    if coluna_codigo is None:
        raise ValueError("A planilha de vendas precisa ter coluna de código para cruzamento com estoque.")

    base = df[[coluna_produto, coluna_codigo] + colunas_mensais].copy()
    base = base.rename(columns={coluna_produto: "SKU / produto", coluna_codigo: "código"})
    base["SKU / produto"] = base["SKU / produto"].apply(utils.normalizar_sku)
    base["código"] = base["código"].apply(utils.normalizar_codigo)
    base["codigo_chave"] = base["código"]
    base["peso_pacote_kg"] = base["codigo_chave"].apply(utils.extrair_peso_pacote_kg)
    base["regra_peso"] = base["codigo_chave"].apply(utils.extrair_regra_peso)
    base = base[base["codigo_chave"] != ""]

    for coluna in colunas_mensais:
        base[coluna] = pd.to_numeric(base[coluna], errors="coerce").fillna(0)

    cadastro = montar_cadastro(base)
    base_pacotes = base.groupby("codigo_chave", as_index=False)[colunas_mensais].sum()
    base_kg = base_pacotes.merge(
        cadastro[["codigo_chave", "peso_pacote_kg"]], on="codigo_chave", how="left"
    )
    for coluna in colunas_mensais:
        base_kg[coluna] = base_kg[coluna] * base_kg["peso_pacote_kg"]
    base_kg = base_kg[["codigo_chave"] + colunas_mensais]

    return base_pacotes, base_kg, cadastro, colunas_mensais


def calcular_indicadores(base_pacotes, base_kg, cadastro, colunas_mensais):
    """
    Calcula os indicadores estatísticos de demanda por SKU.

    Indicadores calculados: média, mediana, desvio padrão, CV, meses sem venda,
    classificação e política de estoque.

    Parâmetros
    ----------
    base_pacotes, base_kg : pd.DataFrame — bases pivotadas com colunas mensais.
    cadastro : pd.DataFrame — cadastro de SKUs.
    colunas_mensais : list

    Retorna
    -------
    pd.DataFrame com indicadores por SKU, ordenado por classificação e código.
    """
    valores_pacotes = base_pacotes[colunas_mensais]
    valores_kg = base_kg[colunas_mensais]

    resultado = cadastro.copy()
    resultado = resultado.merge(
        base_pacotes[["codigo_chave"]].drop_duplicates(), on="codigo_chave", how="right"
    )
    resultado["média_pacotes"] = valores_pacotes.mean(axis=1).round(2)
    resultado["média_kg"] = valores_kg.mean(axis=1).round(2)
    resultado["mediana_pacotes"] = valores_pacotes.median(axis=1).round(2)
    resultado["mediana_kg"] = valores_kg.median(axis=1).round(2)
    resultado["desvio padrão_pacotes"] = valores_pacotes.std(axis=1, ddof=0).round(2)
    resultado["CV"] = np.where(
        resultado["média_pacotes"] > 0,
        resultado["desvio padrão_pacotes"] / resultado["média_pacotes"],
        np.nan,
    )
    resultado["meses sem venda"] = valores_pacotes.eq(0).sum(axis=1)
    resultado["classificação"] = resultado.apply(
        lambda linha: classificar_sku(linha["média_pacotes"], linha["CV"]),
        axis=1,
    )
    resultado["política de estoque"] = resultado["classificação"].apply(politica_estoque)

    ordem = {"Estável": 1, "Intermediário": 2, "Intermitente": 3, "Sem venda": 4}
    resultado["_ordem"] = resultado["classificação"].map(ordem).fillna(99)
    resultado = resultado.sort_values(["_ordem", "codigo_chave"]).drop(columns=["_ordem"])
    return resultado.reset_index(drop=True)


def processar_vendas(df_vendas_original):
    """
    Ponto de entrada para processamento do arquivo de vendas.

    Detecta automaticamente o formato (transacional ou mensal aberto),
    normaliza as colunas, monta as bases e calcula os indicadores.

    Parâmetros
    ----------
    df_vendas_original : pd.DataFrame — DataFrame bruto do arquivo de vendas.

    Retorna
    -------
    (resultado, base_pacotes, base_kg, metadados)

    Raises
    ------
    ValueError se o formato não for detectado ou colunas obrigatórias faltarem.
    """
    df = utils.normalizar_colunas_dataframe(df_vendas_original)
    coluna_produto = utils.identificar_coluna_produto(df)
    coluna_codigo = utils.identificar_coluna_codigo(df)

    if coluna_produto is None:
        raise ValueError("Não encontrei a coluna de produto/SKU na planilha de vendas.")
    if coluna_codigo is None:
        raise ValueError("Não encontrei a coluna de código na planilha de vendas.")

    coluna_data = utils.identificar_coluna_data(df)
    coluna_volume = utils.identificar_coluna_volume(df)
    colunas_mensais = utils.identificar_colunas_mensais(df, coluna_produto, coluna_codigo)

    if coluna_data is not None and coluna_volume is not None:
        formato = "Formato transacional agrupado por mês"
        base_pacotes, base_kg, cadastro, meses_usados = montar_base_transacional(
            df, coluna_produto, coluna_codigo, coluna_data, coluna_volume
        )
    elif colunas_mensais:
        formato = "Formato mensal aberto"
        base_pacotes, base_kg, cadastro, meses_usados = montar_base_mensal_aberta(
            df, coluna_produto, coluna_codigo, colunas_mensais
        )
    else:
        raise ValueError(
            "Não consegui identificar o formato. Use base transacional com Produto, Código, "
            "Dt. Faturado e Pacotes, ou tabela mensal aberta com colunas mensais."
        )

    resultado = calcular_indicadores(base_pacotes, base_kg, cadastro, meses_usados)
    codigos_sem_peso = (
        resultado.loc[resultado["peso_pacote_kg"].isna(), "código"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    metadados = {
        "formato": formato,
        "coluna_produto": coluna_produto,
        "coluna_codigo": coluna_codigo,
        "coluna_data": coluna_data,
        "coluna_volume": coluna_volume,
        "meses_usados": meses_usados,
        "quantidade_meses": len(meses_usados),
        "quantidade_skus": len(base_pacotes),
        "codigos_sem_peso": codigos_sem_peso,
    }
    return resultado, base_pacotes, base_kg, metadados


# ═══════════════════════════════════════════════════════════════════════════════
# ESTOQUE E POLÍTICA HÍBRIDA
# ═══════════════════════════════════════════════════════════════════════════════

def preparar_estoque(df_estoque_original):
    """
    Normaliza e valida o arquivo de estoque atual.

    Detecta automaticamente as colunas de código e estoque em pacotes.
    Extrai o peso do pacote pelo código e calcula o estoque em kg.

    Parâmetros
    ----------
    df_estoque_original : pd.DataFrame

    Retorna
    -------
    pd.DataFrame com colunas: codigo_chave, código, estoque atual pacotes, estoque atual kg.

    Raises
    ------
    ValueError se colunas obrigatórias não forem encontradas.
    """
    colunas = ["codigo_chave", "código", "estoque atual pacotes", "estoque atual kg"]
    if df_estoque_original is None or df_estoque_original.empty:
        return pd.DataFrame(columns=colunas)

    df = utils.normalizar_colunas_dataframe(df_estoque_original)
    coluna_produto = utils.identificar_coluna_produto(df)
    coluna_codigo = utils.identificar_coluna_codigo(df)
    coluna_estoque = utils.identificar_coluna_estoque_pacotes(df)

    if coluna_estoque is None:
        raise ValueError("Não encontrei a coluna de estoque atual em pacotes na planilha de estoque.")

    estoque = df[[coluna_estoque]].copy()
    estoque = estoque.rename(columns={coluna_estoque: "estoque atual pacotes"})
    if coluna_codigo is not None:
        estoque["código"] = df[coluna_codigo].apply(utils.normalizar_codigo)
    elif coluna_produto is not None:
        estoque["código"] = df[coluna_produto].apply(utils.extrair_codigo_colchetes)
    else:
        raise ValueError("Não encontrei coluna de código nem Produto para extrair código do estoque.")

    estoque["codigo_chave"] = estoque["código"].apply(utils.normalizar_codigo)
    estoque["peso_pacote_kg_estoque"] = estoque["codigo_chave"].apply(utils.extrair_peso_pacote_kg)
    estoque["estoque atual pacotes"] = pd.to_numeric(
        estoque["estoque atual pacotes"], errors="coerce"
    ).fillna(0)
    estoque = estoque[estoque["codigo_chave"] != ""]
    estoque["estoque atual kg"] = estoque["estoque atual pacotes"] * estoque["peso_pacote_kg_estoque"]
    estoque = estoque.groupby("codigo_chave", as_index=False).agg(
        {"código": "first", "estoque atual pacotes": "sum", "estoque atual kg": "sum"}
    )
    return estoque[colunas]


def escolher_lead_time(classificacao, resumo_lead_time):
    """
    Seleciona o lead time a usar baseado na classificação do SKU e no resumo estatístico.

    Política:
    - Estável → P50 do lead time
    - Intermediário → P75 do lead time
    - Intermitente → P90 do lead time
    - Se resumo_lead_time for None → usa padrão por classificação

    Parâmetros
    ----------
    classificacao : str
    resumo_lead_time : dict ou None — {'p50': x, 'p75': x, 'p90': x, 'media': x, 'familias': n}

    Retorna
    -------
    (float, str): (lead_time_dias, origem)
    """
    if resumo_lead_time is None:
        return dias_estoque_por_classificacao(classificacao), "PADRÃO"
    if classificacao == "Estável":
        return float(resumo_lead_time.get("p50", 2)), "P50"
    if classificacao == "Intermediário":
        return float(resumo_lead_time.get("p75", 3)), "P75"
    if classificacao == "Intermitente":
        return float(resumo_lead_time.get("p90", 5)), "P90"
    return 0, "PADRÃO"


def cobertura_alvo_por_classificacao(classificacao, parametros_cobertura):
    """
    Retorna a cobertura alvo em dias para a classificação informada.

    Parâmetros
    ----------
    classificacao : str
    parametros_cobertura : dict — {'estavel': int, 'intermediario': int, 'intermitente': int, 'sem_venda': int}

    Retorna
    -------
    int — cobertura alvo em dias.
    """
    mapa = {
        "Estável": parametros_cobertura["estavel"],
        "Intermediário": parametros_cobertura["intermediario"],
        "Intermitente": parametros_cobertura["intermitente"],
        "Sem venda": parametros_cobertura["sem_venda"],
    }
    return mapa.get(classificacao, parametros_cobertura["sem_venda"])


def calcular_estoque_e_acao(
    resultado,
    estoque,
    resumo_lead_time=None,
    parametros_cobertura=None,
    dias_uteis_mes=30,
):
    """
    Calcula a política híbrida de estoque e a ação recomendada por SKU.

    Política Híbrida:
        estoque_alvo = max(
            consumo_diario × cobertura_minima_dias[classificacao],
            consumo_diario × lead_time × (1 + fator_seguranca[classificacao])
        )

    Ações possíveis:
    - 'Produzir urgente' — estoque < mínimo
    - 'Programar produção' — estoque entre mínimo e alvo
    - 'Manter monitoramento' — estoque >= alvo
    - 'Reduzir estoque' — estoque > alvo × 1,3
    - 'Produzir sob pedido / reduzir estoque' — intermitente com excesso
    - 'Produzir somente se houver pedido ou risco comercial' — intermitente crítico
    - 'Não produzir' — sem venda

    Parâmetros
    ----------
    resultado : pd.DataFrame — resultado de calcular_indicadores()
    estoque : pd.DataFrame — resultado de preparar_estoque()
    resumo_lead_time : dict ou None
    parametros_cobertura : dict ou None (usa PARAMETROS_COBERTURA_PADRAO se None)
    dias_uteis_mes : int — número de dias úteis no mês para consumo diário

    Retorna
    -------
    pd.DataFrame com todas as colunas de estoque e ação.
    """
    if parametros_cobertura is None:
        parametros_cobertura = PARAMETROS_COBERTURA_PADRAO.copy()

    tabela = resultado.merge(
        estoque[["codigo_chave", "estoque atual pacotes", "estoque atual kg"]],
        on="codigo_chave",
        how="left",
        indicator=True,
    )
    tabela["status_cruzamento_estoque"] = np.where(
        tabela["_merge"] == "both",
        "Encontrado no estoque",
        "Não encontrado no estoque",
    )
    tabela = tabela.drop(columns=["_merge"])
    tabela["estoque atual pacotes"] = tabela["estoque atual pacotes"].fillna(0)
    tabela["estoque atual kg"] = tabela["estoque atual kg"].fillna(0)

    # Lead time por classificação
    lead = tabela["classificação"].apply(
        lambda classif: escolher_lead_time(classif, resumo_lead_time)
    )
    tabela["lead_time_usado_dias"] = lead.apply(lambda v: v[0])
    tabela["lead time usado"] = tabela["lead_time_usado_dias"]
    tabela["origem do lead time"] = lead.apply(lambda v: v[1])
    tabela["cobertura_alvo_dias"] = tabela["classificação"].apply(
        lambda classif: cobertura_alvo_por_classificacao(classif, parametros_cobertura)
    )

    dias_uteis_mes = max(float(dias_uteis_mes), 1)
    tabela["consumo_diario_pacotes"] = np.where(
        tabela["média_pacotes"] > 0,
        tabela["média_pacotes"] / dias_uteis_mes,
        0,
    )
    tabela["consumo_diario_kg"] = np.where(
        tabela["média_kg"] > 0,
        tabela["média_kg"] / dias_uteis_mes,
        0,
    )

    # Estoque mínimo = consumo × lead time
    tabela["estoque_minimo_pacotes"] = (
        tabela["consumo_diario_pacotes"] * tabela["lead_time_usado_dias"]
    )
    tabela["estoque_minimo_kg"] = (
        tabela["consumo_diario_kg"] * tabela["lead_time_usado_dias"]
    )

    # Política híbrida
    cobertura_minima_dias_serie = tabela["classificação"].map(COBERTURA_MINIMA_DIAS).fillna(0)
    fator_seguranca_serie = tabela["classificação"].map(FATOR_SEGURANCA).fillna(0)

    estoque_por_cobertura_pacotes = (
        tabela["consumo_diario_pacotes"] * cobertura_minima_dias_serie
    )
    estoque_por_cobertura_kg = tabela["consumo_diario_kg"] * cobertura_minima_dias_serie

    estoque_por_leadtime_pacotes = (
        tabela["consumo_diario_pacotes"]
        * tabela["lead_time_usado_dias"]
        * (1 + fator_seguranca_serie)
    )
    estoque_por_leadtime_kg = (
        tabela["consumo_diario_kg"]
        * tabela["lead_time_usado_dias"]
        * (1 + fator_seguranca_serie)
    )

    tabela["estoque_alvo_pacotes"] = np.maximum(
        estoque_por_cobertura_pacotes, estoque_por_leadtime_pacotes
    )
    tabela["estoque_alvo_kg"] = np.maximum(
        estoque_por_cobertura_kg, estoque_por_leadtime_kg
    )
    tabela.loc[
        tabela["classificação"] == "Sem venda",
        ["estoque_alvo_pacotes", "estoque_alvo_kg"],
    ] = 0

    tabela["dias_cobertura"] = np.where(
        tabela["consumo_diario_pacotes"] > 0,
        tabela["estoque atual pacotes"] / tabela["consumo_diario_pacotes"],
        0,
    )
    tabela["saldo_vs_alvo_pacotes"] = (
        tabela["estoque atual pacotes"] - tabela["estoque_alvo_pacotes"]
    )
    tabela["saldo_vs_alvo_kg"] = tabela["estoque atual kg"] - tabela["estoque_alvo_kg"]

    tabela["quantidade sugerida para produzir pacotes"] = np.maximum(
        tabela["estoque_alvo_pacotes"] - tabela["estoque atual pacotes"], 0
    )
    tabela["quantidade sugerida para produzir kg"] = np.maximum(
        tabela["estoque_alvo_kg"] - tabela["estoque atual kg"], 0
    )

    # Risco de ruptura
    tabela["risco_ruptura"] = "OK"
    tabela.loc[
        tabela["estoque atual pacotes"] < tabela["estoque_minimo_pacotes"],
        "risco_ruptura",
    ] = "Crítico"
    tabela.loc[
        (tabela["estoque atual pacotes"] >= tabela["estoque_minimo_pacotes"])
        & (tabela["estoque atual pacotes"] < tabela["estoque_alvo_pacotes"]),
        "risco_ruptura",
    ] = "Atenção"

    # Ação recomendada
    tabela["ação_recomendada"] = "Manter monitoramento"
    tabela.loc[
        tabela["estoque atual pacotes"] < tabela["estoque_minimo_pacotes"],
        "ação_recomendada",
    ] = "Produzir urgente"
    tabela.loc[
        (tabela["estoque atual pacotes"] >= tabela["estoque_minimo_pacotes"])
        & (tabela["estoque atual pacotes"] < tabela["estoque_alvo_pacotes"]),
        "ação_recomendada",
    ] = "Programar produção"
    tabela.loc[
        tabela["estoque atual pacotes"] > tabela["estoque_alvo_pacotes"] * 1.3,
        "ação_recomendada",
    ] = "Reduzir estoque"
    tabela.loc[
        (tabela["classificação"] == "Intermitente")
        & (tabela["estoque atual pacotes"] > tabela["estoque_alvo_pacotes"]),
        "ação_recomendada",
    ] = "Produzir sob pedido / reduzir estoque"
    tabela.loc[
        (tabela["classificação"] == "Intermitente")
        & (tabela["estoque atual pacotes"] < tabela["estoque_minimo_pacotes"]),
        "ação_recomendada",
    ] = "Produzir somente se houver pedido ou risco comercial"
    tabela.loc[tabela["classificação"] == "Sem venda", "ação_recomendada"] = "Não produzir"

    # Arredondamentos finais
    for coluna in [
        "estoque atual pacotes", "estoque_minimo_pacotes", "estoque_alvo_pacotes",
        "saldo_vs_alvo_pacotes", "quantidade sugerida para produzir pacotes",
    ]:
        tabela[coluna] = tabela[coluna].apply(utils.arredondar_para_cima)

    for coluna in [
        "estoque atual kg", "estoque_minimo_kg", "estoque_alvo_kg",
        "dias_cobertura", "saldo_vs_alvo_kg", "quantidade sugerida para produzir kg",
    ]:
        tabela[coluna] = tabela[coluna].round(2)

    # Aliases de colunas com nomes amigáveis
    tabela["estoque mínimo pacotes"] = tabela["estoque_minimo_pacotes"]
    tabela["estoque mínimo kg"] = tabela["estoque_minimo_kg"]
    tabela["estoque alvo pacotes"] = tabela["estoque_alvo_pacotes"]
    tabela["estoque alvo kg"] = tabela["estoque_alvo_kg"]
    tabela["saldo vs alvo pacotes"] = tabela["saldo_vs_alvo_pacotes"]
    tabela["saldo vs alvo kg"] = tabela["saldo_vs_alvo_kg"]
    tabela["risco ruptura"] = tabela["risco_ruptura"]
    tabela["ação recomendada"] = tabela["ação_recomendada"]

    colunas = [
        "SKU / produto", "código", "codigo_chave", "peso_pacote_kg", "regra_peso",
        "média_pacotes", "média_kg", "mediana_pacotes", "mediana_kg",
        "CV", "classificação", "política de estoque",
        "estoque atual pacotes", "estoque atual kg",
        "lead_time_usado_dias", "origem do lead time", "cobertura_alvo_dias",
        "estoque_minimo_pacotes", "estoque_minimo_kg",
        "estoque_alvo_pacotes", "estoque_alvo_kg",
        "dias_cobertura", "saldo_vs_alvo_pacotes", "saldo_vs_alvo_kg",
        "risco_ruptura", "status_cruzamento_estoque", "ação_recomendada",
        "lead time usado", "estoque mínimo pacotes", "estoque mínimo kg",
        "estoque alvo pacotes", "estoque alvo kg",
        "saldo vs alvo pacotes", "saldo vs alvo kg",
        "risco ruptura", "ação recomendada",
    ]
    return tabela[colunas]


def gerar_resumo(resultado):
    """
    Calcula o resumo executivo com totais de estoque e contadores de risco.

    Parâmetros
    ----------
    resultado : pd.DataFrame — resultado de calcular_estoque_e_acao()

    Retorna
    -------
    dict com totais de estoque alvo/atual (pacotes, kg, ton), contadores de risco etc.
    """
    total_estoque_alvo_kg = float(resultado["estoque_alvo_kg"].fillna(0).sum())
    total_estoque_atual_kg = float(resultado["estoque atual kg"].fillna(0).sum())
    encontrados = int(
        (resultado["status_cruzamento_estoque"] == "Encontrado no estoque").sum()
    )
    nao_encontrados = int(
        (resultado["status_cruzamento_estoque"] == "Não encontrado no estoque").sum()
    )
    total = len(resultado)
    return {
        "total_estoque_alvo_pacotes": int(resultado["estoque_alvo_pacotes"].fillna(0).sum()),
        "total_estoque_alvo_kg": total_estoque_alvo_kg,
        "total_estoque_alvo_ton": total_estoque_alvo_kg / 1000,
        "total_estoque_atual_kg": total_estoque_atual_kg,
        "total_estoque_atual_ton": total_estoque_atual_kg / 1000,
        "skus_estoque_encontrado": encontrados,
        "skus_estoque_nao_encontrado": nao_encontrados,
        "percentual_match": encontrados / total if total else 0,
        "skus_criticos": int((resultado["risco_ruptura"] == "Crítico").sum()),
        "skus_atencao": int((resultado["risco_ruptura"] == "Atenção").sum()),
        "skus_excesso": int(
            (resultado["estoque atual pacotes"] > resultado["estoque_alvo_pacotes"] * 1.3).sum()
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TAKT TIME
# ═══════════════════════════════════════════════════════════════════════════════

def calcular_takt_time(resultado, dias_uteis, horas_disponiveis_dia, eficiencia_planejada):
    """
    Calcula o Takt Time de demanda por SKU.

    Fórmula: takt = tempo_disponivel_mes (min) / demanda_media_mensal

    Parâmetros
    ----------
    resultado : pd.DataFrame
    dias_uteis : int
    horas_disponiveis_dia : float
    eficiencia_planejada : float (0 a 1)

    Retorna
    -------
    (DataFrame com colunas de takt, float tempo_disponivel_min_mes)
    """
    tabela = resultado.copy()
    tempo_disponivel_min_mes = dias_uteis * horas_disponiveis_dia * 60 * eficiencia_planejada

    tabela["demanda_diaria_pacotes"] = np.where(
        dias_uteis > 0, tabela["média_pacotes"] / dias_uteis, np.nan
    )
    tabela["demanda_diaria_kg"] = np.where(
        dias_uteis > 0, tabela["média_kg"] / dias_uteis, np.nan
    )
    tabela["takt_min_por_pacote"] = np.where(
        tabela["média_pacotes"] > 0,
        tempo_disponivel_min_mes / tabela["média_pacotes"],
        np.nan,
    )
    tabela["takt_min_por_kg"] = np.where(
        tabela["média_kg"] > 0,
        tempo_disponivel_min_mes / tabela["média_kg"],
        np.nan,
    )
    tabela["takt_seg_por_pacote"] = tabela["takt_min_por_pacote"] * 60
    tabela["takt_seg_por_kg"] = tabela["takt_min_por_kg"] * 60
    tabela["parametros_takt_dias_uteis"] = dias_uteis
    tabela["parametros_takt_horas_dia"] = horas_disponiveis_dia
    tabela["parametros_takt_eficiencia"] = eficiencia_planejada

    for coluna in [
        "demanda_diaria_pacotes", "demanda_diaria_kg",
        "takt_min_por_pacote", "takt_seg_por_pacote",
        "takt_min_por_kg", "takt_seg_por_kg",
    ]:
        tabela[coluna] = tabela[coluna].round(2)

    return tabela, tempo_disponivel_min_mes


def montar_tabela_takt(resultado):
    """Extrai as colunas relevantes do resultado para a visão de Takt Time."""
    tabela_takt = resultado.copy()
    if "risco_ruptura" not in tabela_takt.columns:
        tabela_takt["risco_ruptura"] = ""
    if "ação_recomendada" not in tabela_takt.columns:
        tabela_takt["ação_recomendada"] = tabela_takt.get("ação recomendada", "")

    tabela_takt = tabela_takt.rename(columns={"SKU / produto": "SKU"})
    colunas = [
        "SKU", "média_pacotes", "média_kg",
        "demanda_diaria_pacotes", "demanda_diaria_kg",
        "takt_min_por_pacote", "takt_seg_por_pacote",
        "takt_min_por_kg", "takt_seg_por_kg",
        "classificação", "política de estoque",
        "risco_ruptura", "ação_recomendada",
    ]
    return tabela_takt[colunas]


def montar_ranking_takt(resultado, unidade_principal):
    """
    Monta o ranking de SKUs por maior pressão de demanda (menor takt).

    Parâmetros
    ----------
    resultado : pd.DataFrame
    unidade_principal : str — 'KG' ou 'Pacotes'

    Retorna
    -------
    pd.DataFrame ordenado crescente pelo takt (mais crítico primeiro).
    """
    coluna_takt = "takt_min_por_kg" if unidade_principal == "KG" else "takt_min_por_pacote"
    ranking = resultado[resultado[coluna_takt].notna() & (resultado[coluna_takt] > 0)].copy()
    ranking = ranking.sort_values(coluna_takt, ascending=True)
    return ranking[[
        "SKU / produto", "código", "classificação",
        "média_pacotes", "média_kg",
        "demanda_diaria_pacotes", "demanda_diaria_kg",
        "takt_min_por_pacote", "takt_min_por_kg",
        "ação_recomendada",
    ]]


def montar_tabela_politica_estoque(resultado):
    """Extrai as colunas relevantes para a visão de Política de Estoque."""
    tabela = resultado.copy().rename(columns={"SKU / produto": "SKU"})
    colunas = [
        "SKU", "classificação", "média_pacotes", "média_kg",
        "lead_time_usado_dias", "cobertura_alvo_dias",
        "estoque_minimo_pacotes", "estoque_alvo_pacotes",
        "estoque atual pacotes", "dias_cobertura",
        "risco_ruptura", "ação_recomendada",
    ]
    return tabela[colunas]


# ═══════════════════════════════════════════════════════════════════════════════
# RUPTURAS EVITÁVEIS
# ═══════════════════════════════════════════════════════════════════════════════

def preparar_rupturas(df_rupturas_original):
    """
    Normaliza e valida o arquivo de rupturas da semana.

    Parâmetros
    ----------
    df_rupturas_original : pd.DataFrame

    Retorna
    -------
    pd.DataFrame com colunas: codigo_chave, código, SKU, data, ruptura.
    """
    colunas = ["codigo_chave", "código", "SKU", "data", "ruptura"]
    if df_rupturas_original is None or df_rupturas_original.empty:
        return pd.DataFrame(columns=colunas)

    df = utils.normalizar_colunas_dataframe(df_rupturas_original)
    coluna_codigo = utils.identificar_coluna_codigo(df)
    coluna_produto = utils.identificar_coluna_produto(df)
    coluna_data = utils.identificar_coluna_data(df)
    coluna_ruptura = utils.identificar_coluna_ruptura(df)

    rupturas = pd.DataFrame()
    rupturas["codigo_chave"] = df[coluna_codigo].apply(utils.normalizar_codigo) if coluna_codigo else ""
    rupturas["código"] = rupturas["codigo_chave"]
    rupturas["SKU"] = df[coluna_produto].apply(utils.normalizar_sku) if coluna_produto else ""
    rupturas["data"] = utils.converter_data(df[coluna_data]) if coluna_data else pd.NaT
    rupturas["ruptura"] = (
        utils.coluna_ruptura_para_bool(df[coluna_ruptura]) if coluna_ruptura else True
    )
    rupturas = rupturas[rupturas["codigo_chave"] != ""]
    return rupturas[colunas].reset_index(drop=True)


def calcular_rupturas_evitaveis(resultado, rupturas):
    """
    Cruza as rupturas informadas com as ações recomendadas para identificar rupturas evitáveis.

    Uma ruptura é evitável quando o sistema recomendava produzir e a ruptura ocorreu mesmo assim.

    Parâmetros
    ----------
    resultado : pd.DataFrame — resultado de calcular_estoque_e_acao()
    rupturas : pd.DataFrame — resultado de preparar_rupturas()

    Retorna
    -------
    (resumo_dict, detalhe_DataFrame)
    """
    colunas = ["SKU", "código", "data", "ação_recomendada", "ruptura", "ruptura_evitavel"]
    if rupturas is None or rupturas.empty:
        resumo = {
            "total_rupturas": 0,
            "rupturas_evitaveis": 0,
            "status": "Sem planilha de rupturas carregada",
        }
        return resumo, pd.DataFrame(columns=colunas)

    base = resultado[["codigo_chave", "SKU / produto", "código", "ação_recomendada"]].copy()
    detalhe = rupturas.merge(base, on="codigo_chave", how="left", suffixes=("", "_resultado"))
    detalhe["SKU"] = detalhe["SKU"].where(
        detalhe["SKU"] != "", detalhe["SKU / produto"].fillna("")
    )
    detalhe["código"] = detalhe["código_resultado"].fillna(detalhe["código"])
    detalhe["ação_recomendada"] = detalhe["ação_recomendada"].fillna(
        "Não encontrado no resultado"
    )
    detalhe["ruptura_evitavel"] = detalhe["ruptura"] & detalhe["ação_recomendada"].isin(
        utils.ACOES_RECOMENDAM_PRODUZIR
    )

    resumo = {
        "total_rupturas": int(len(detalhe)),
        "rupturas_evitaveis": int(detalhe["ruptura_evitavel"].sum()),
        "status": "Rupturas calculadas",
    }
    return resumo, detalhe[colunas].reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRAMAÇÃO SEMANAL E ADERÊNCIA
# ═══════════════════════════════════════════════════════════════════════════════

def preparar_programacao_semanal(df_programacao_original):
    """
    Normaliza e valida o arquivo de programação semanal.

    Detecta automaticamente se o código vem de coluna direta ou de Prod + Apre.

    Parâmetros
    ----------
    df_programacao_original : pd.DataFrame

    Retorna
    -------
    pd.DataFrame com colunas:
        codigo_chave, produto_programacao, linha,
        pacotes_programados, kg_programado, plano_realizado, origem_codigo_programacao
    """
    colunas = [
        "codigo_chave", "produto_programacao", "linha",
        "pacotes_programados", "kg_programado", "plano_realizado",
        "origem_codigo_programacao",
    ]
    if df_programacao_original is None or df_programacao_original.empty:
        return pd.DataFrame(columns=colunas)

    df = df_programacao_original.copy()

    # Detecta se o cabeçalho real está na primeira linha de dados
    # (ocorre quando o arquivo tem linha de título/data antes dos headers reais)
    colunas_unnamed = sum(1 for c in df.columns if str(c).startswith("Unnamed:"))
    if colunas_unnamed > len(df.columns) / 2 and not df.empty:
        nova_header = [
            str(v).strip() if not pd.isna(v) else f"_col{i}"
            for i, v in enumerate(df.iloc[0])
        ]
        df.columns = nova_header
        df = df.iloc[1:].reset_index(drop=True)

    df = utils.normalizar_colunas_dataframe(df)
    coluna_codigo = utils.identificar_coluna_codigo(df)
    coluna_produto = utils.identificar_coluna_produto(df)
    coluna_prod = utils.identificar_coluna_prod_programacao(df)
    coluna_apre = utils.identificar_coluna_apre_programacao(df)
    coluna_linha = utils.identificar_coluna_linha_programacao(df)
    coluna_pacotes = utils.identificar_coluna_pacotes_programados(df)
    coluna_kg = utils.identificar_coluna_kg_programado(df)
    coluna_realizado = utils.identificar_coluna_plano_realizado(df)

    programacao = pd.DataFrame(index=df.index)
    if coluna_codigo:
        programacao["codigo_chave"] = df[coluna_codigo].apply(utils.normalizar_codigo)
        programacao["origem_codigo_programacao"] = "Coluna código"
    elif coluna_prod and coluna_apre:
        programacao["codigo_chave"] = [
            utils.montar_codigo_programacao_por_prod_apre(prod, apre)
            for prod, apre in zip(df[coluna_prod], df[coluna_apre])
        ]
        programacao["origem_codigo_programacao"] = "Prod + Apre"
    else:
        programacao["codigo_chave"] = ""
        programacao["origem_codigo_programacao"] = "Não identificado"

    programacao["produto_programacao"] = (
        df[coluna_produto].apply(utils.normalizar_sku) if coluna_produto else ""
    )
    programacao["linha"] = df[coluna_linha] if coluna_linha else ""
    programacao["pacotes_programados"] = (
        pd.to_numeric(df[coluna_pacotes], errors="coerce").fillna(0) if coluna_pacotes else 0
    )
    programacao["kg_programado"] = (
        pd.to_numeric(df[coluna_kg], errors="coerce").fillna(0) if coluna_kg else 0
    )
    programacao["plano_realizado"] = (
        pd.to_numeric(df[coluna_realizado], errors="coerce").fillna(0) if coluna_realizado else 0
    )
    programacao = programacao[programacao["codigo_chave"] != ""]
    programacao = programacao.groupby(
        ["codigo_chave", "produto_programacao", "linha", "origem_codigo_programacao"],
        as_index=False,
        dropna=False,
    ).agg({
        "pacotes_programados": "sum",
        "kg_programado": "sum",
        "plano_realizado": "sum",
    })
    return programacao[colunas].reset_index(drop=True)


def calcular_aderencia_programacao(resultado, programacao):
    """
    Calcula a aderência da programação semanal à recomendação do PPCP.

    Lógica:
    - Recomendação = 'Produzir' se ação está em ACOES_RECOMENDAM_PRODUZIR
    - Analista programou = 'Sim' se pacotes_programados > 0 ou kg_programado > 0
    - Aderente = recomendação e decisão estão alinhadas

    Parâmetros
    ----------
    resultado : pd.DataFrame — resultado de calcular_estoque_e_acao()
    programacao : pd.DataFrame — resultado de preparar_programacao_semanal()

    Retorna
    -------
    (resumo_dict, detalhe_DataFrame)
    """
    colunas = [
        "codigo_chave", "SKU / produto", "ação recomendada",
        "pacotes_programados", "kg_programado", "plano_realizado",
        "aderente", "motivo_aderencia",
    ]
    if programacao is None or programacao.empty:
        resumo = {
            "aderencia_percentual": None,
            "skus_aderentes": 0,
            "skus_nao_aderentes": 0,
            "skus_programacao_nao_encontrados": 0,
            "status": "Sem programação semanal carregada",
        }
        return resumo, pd.DataFrame(columns=colunas)

    coluna_acao_resultado = (
        "ação_recomendada" if "ação_recomendada" in resultado.columns
        else "ação recomendada" if "ação recomendada" in resultado.columns
        else None
    )

    base = resultado[["codigo_chave", "SKU / produto"]].copy()
    base["código"] = (
        resultado["código"] if "código" in resultado.columns else resultado["codigo_chave"]
    )
    base["ação_recomendada"] = (
        resultado[coluna_acao_resultado] if coluna_acao_resultado else "Não encontrado no resultado"
    )

    detalhe = programacao.merge(base, on="codigo_chave", how="left", suffixes=("_programacao", ""))
    detalhe["SKU / produto"] = detalhe["SKU / produto"].fillna(detalhe["produto_programacao"])
    detalhe["ação_recomendada"] = detalhe["ação_recomendada"].fillna("Não encontrado no resultado")
    detalhe["encontrado_resultado"] = detalhe["código"].notna()

    detalhe["recomendacao_sistema"] = np.where(
        detalhe["ação_recomendada"].isin(utils.ACOES_RECOMENDAM_PRODUZIR),
        "Produzir",
        "Não produzir",
    )
    detalhe["analista_programou"] = np.where(
        (detalhe["pacotes_programados"] > 0) | (detalhe["kg_programado"] > 0),
        "Sim",
        "Não",
    )

    aderente = (
        (
            (detalhe["recomendacao_sistema"] == "Produzir")
            & (detalhe["analista_programou"] == "Sim")
        )
        | (
            (detalhe["recomendacao_sistema"] == "Não produzir")
            & (detalhe["analista_programou"] == "Não")
        )
    ) & detalhe["encontrado_resultado"]

    detalhe["aderente"] = np.where(aderente, "Sim", "Não")
    detalhe["motivo_aderencia"] = np.select(
        [
            ~detalhe["encontrado_resultado"],
            aderente,
            (detalhe["recomendacao_sistema"] == "Produzir") & (detalhe["analista_programou"] == "Não"),
            (detalhe["recomendacao_sistema"] == "Não produzir") & (detalhe["analista_programou"] == "Sim"),
        ],
        [
            "Código não encontrado no resultado_final",
            "Aderente à recomendação",
            "Sistema recomendou produzir, mas não foi programado",
            "Sistema recomendou não produzir, mas foi programado",
        ],
        default="Avaliar",
    )

    avaliados = detalhe[detalhe["encontrado_resultado"]].copy()
    total = len(avaliados)
    aderentes = int((avaliados["aderente"] == "Sim").sum())

    resumo = {
        "aderencia_percentual": aderentes / total * 100 if total else None,
        "skus_aderentes": aderentes,
        "skus_nao_aderentes": int(total - aderentes),
        "skus_programacao_nao_encontrados": int((~detalhe["encontrado_resultado"]).sum()),
        "status": "Aderência calculada",
    }
    detalhe = detalhe.rename(columns={"ação_recomendada": "ação recomendada"})
    return resumo, detalhe[colunas].reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# KPIs DO PAINEL GERENCIAL
# ═══════════════════════════════════════════════════════════════════════════════

def calcular_estoque_qualificado(resultado, capacidade_maxima_kg=900_000):
    """
    Calcula o indicador de Estoque Qualificado e os KPIs de capacidade física de PA.

    Estoque qualificado: SKU com risco_ruptura = 'OK' E ação != 'Reduzir estoque'

    Parâmetros
    ----------
    resultado : pd.DataFrame
    capacidade_maxima_kg : float — capacidade física máxima do armazém de PA em kg (padrão 900.000)

    Retorna
    -------
    dict com percentual, contadores e indicadores de capacidade.
    """
    total = len(resultado)
    acao = (
        resultado["ação_recomendada"]
        if "ação_recomendada" in resultado.columns
        else resultado.get("ação recomendada", pd.Series([""] * total))
    )
    qualificados_mask = (resultado["risco_ruptura"] == "OK") & (acao != "Reduzir estoque")

    # KPIs de capacidade física
    col_estoque_kg = "estoque atual kg"
    col_alvo_kg = "estoque_alvo_kg"

    estoque_atual_total_kg = float(
        resultado[col_estoque_kg].fillna(0).sum()
    ) if col_estoque_kg in resultado.columns else 0.0

    estoque_alvo_total_kg = float(
        resultado[col_alvo_kg].fillna(0).sum()
    ) if col_alvo_kg in resultado.columns else 0.0

    estoque_qualificado_kg = float(
        resultado.loc[qualificados_mask, col_estoque_kg].fillna(0).sum()
    ) if col_estoque_kg in resultado.columns else 0.0

    cap = capacidade_maxima_kg if capacidade_maxima_kg > 0 else 1

    return {
        "estoque_qualificado_percentual": float(qualificados_mask.sum() / total * 100) if total else 0,
        "skus_qualificados": int(qualificados_mask.sum()),
        "total_skus": int(total),
        "skus_criticos": int((resultado["risco_ruptura"] == "Crítico").sum()),
        "skus_atencao": int((resultado["risco_ruptura"] == "Atenção").sum()),
        "skus_excesso": int(
            (resultado["estoque atual pacotes"] > resultado["estoque_alvo_pacotes"] * 1.3).sum()
        ),
        # Capacidade física
        "capacidade_maxima_kg": capacidade_maxima_kg,
        "capacidade_maxima_ton": capacidade_maxima_kg / 1000,
        "estoque_atual_total_kg": estoque_atual_total_kg,
        "estoque_atual_total_ton": estoque_atual_total_kg / 1000,
        "capacidade_utilizada_pct": estoque_atual_total_kg / cap * 100,
        "estoque_alvo_total_kg": estoque_alvo_total_kg,
        "estoque_alvo_total_ton": estoque_alvo_total_kg / 1000,
        "capacidade_alvo_pct": estoque_alvo_total_kg / cap * 100,
        "estoque_qualificado_kg": estoque_qualificado_kg,
        "capacidade_qualificada_pct": estoque_qualificado_kg / cap * 100,
    }


def montar_resumo_painel_gerencial(estoque_qualificado, resumo_rupturas, resumo_aderencia):
    """
    Monta o DataFrame de resumo do Painel Gerencial para exportação no Excel.

    Parâmetros
    ----------
    estoque_qualificado : dict — resultado de calcular_estoque_qualificado()
    resumo_rupturas : dict
    resumo_aderencia : dict

    Retorna
    -------
    pd.DataFrame com uma linha de resumo.
    """
    return pd.DataFrame([{
        **estoque_qualificado,
        "total_rupturas": resumo_rupturas["total_rupturas"],
        "rupturas_evitaveis": resumo_rupturas["rupturas_evitaveis"],
        "aderencia_percentual": resumo_aderencia["aderencia_percentual"],
        "skus_aderentes": resumo_aderencia["skus_aderentes"],
        "skus_nao_aderentes": resumo_aderencia["skus_nao_aderentes"],
    }])
