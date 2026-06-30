# -*- coding: utf-8 -*-

from io import BytesIO
import re
import unicodedata

import numpy as np
import pandas as pd


def _normalizar_nome(valor):
    texto = "" if pd.isna(valor) else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def _detectar_cabecalho_lead_time(arquivo_excel):
    previa = pd.read_excel(
        arquivo_excel,
        header=None,
        nrows=10,
        dtype=object,
        engine="openpyxl",
    )

    termos_obrigatorios = {
        "op": ["op", "o p", "ordem producao", "ordem de producao"],
        "data_ini": ["data ini", "data inicial", "dt ini", "dt inicial"],
        "hora_ini": ["hora ini", "hora inicial", "hr ini"],
        "data_fim": ["data fim", "data final", "dt fim", "dt final"],
        "hora_fim": ["hora fim", "hora final", "hr fim"],
    }

    melhor_linha = None
    melhor_pontos = -1

    for indice, linha in previa.iterrows():
        celulas = [_normalizar_nome(valor) for valor in linha.tolist() if not pd.isna(valor)]
        pontos = 0

        for lista_termos in termos_obrigatorios.values():
            if any(any(termo in celula for termo in lista_termos) for celula in celulas):
                pontos += 1

        if pontos > melhor_pontos:
            melhor_pontos = pontos
            melhor_linha = int(indice)

        if pontos == len(termos_obrigatorios):
            return int(indice)

    if melhor_pontos >= 4:
        return melhor_linha

    raise ValueError("Nao foi possivel detectar o cabecalho do lead time nas primeiras 10 linhas.")


def _encontrar_coluna(colunas, opcoes):
    opcoes_norm = [_normalizar_nome(opcao) for opcao in opcoes]
    for coluna in colunas:
        coluna_norm = _normalizar_nome(coluna)
        if any(opcao in coluna_norm for opcao in opcoes_norm):
            return coluna
    return None


def _op_para_texto(valor):
    if pd.isna(valor):
        return ""

    if isinstance(valor, float) and valor.is_integer():
        texto = str(int(valor))
    else:
        texto = str(valor).strip()

    digitos = re.sub(r"\D", "", texto)
    if not digitos:
        return ""

    return digitos.zfill(11)


def _combinar_data_hora(data_valor, hora_valor):
    data = pd.to_datetime(data_valor, errors="coerce", dayfirst=True)
    if pd.isna(data):
        data = pd.to_datetime(data_valor, errors="coerce")
    if pd.isna(data):
        return pd.NaT

    base = pd.Timestamp(year=data.year, month=data.month, day=data.day)

    if pd.isna(hora_valor):
        return base

    if hasattr(hora_valor, "hour") and hasattr(hora_valor, "minute"):
        return base + pd.Timedelta(
            hours=hora_valor.hour,
            minutes=hora_valor.minute,
            seconds=getattr(hora_valor, "second", 0),
        )

    if isinstance(hora_valor, (int, float)) and not pd.isna(hora_valor):
        if 0 <= float(hora_valor) < 1:
            return base + pd.Timedelta(days=float(hora_valor))

    texto_hora = str(hora_valor).strip()
    if texto_hora == "":
        return base

    tempo = pd.to_timedelta(texto_hora, errors="coerce")
    if not pd.isna(tempo):
        return base + tempo

    hora_convertida = pd.to_datetime(texto_hora, errors="coerce", dayfirst=True)
    if not pd.isna(hora_convertida):
        return base + pd.Timedelta(
            hours=hora_convertida.hour,
            minutes=hora_convertida.minute,
            seconds=hora_convertida.second,
        )

    return base


def _primeiro_nao_vazio(serie):
    valores = serie.dropna()
    valores = valores[valores.astype(str).str.strip() != ""]
    if valores.empty:
        return ""
    return valores.iloc[0]


def _calcular_resumo_lead_time(lead_time_por_chave):
    serie = pd.to_numeric(lead_time_por_chave["lead_time_dias"], errors="coerce").dropna()
    if serie.empty:
        return {
            "familias": 0,
            "p50": 0,
            "p75": 0,
            "p90": 0,
            "media": 0,
        }

    return {
        "familias": int(len(serie)),
        "p50": round(float(np.percentile(serie, 50)), 2),
        "p75": round(float(np.percentile(serie, 75)), 2),
        "p90": round(float(np.percentile(serie, 90)), 2),
        "media": round(float(serie.mean()), 2),
    }


def processar_lead_time(arquivo_excel):
    linha_header = _detectar_cabecalho_lead_time(arquivo_excel)

    try:
        arquivo_excel.seek(0)
    except Exception:
        pass

    df = pd.read_excel(
        arquivo_excel,
        header=linha_header,
        dtype=object,
        engine="openpyxl",
    )
    df = df.dropna(how="all")
    df.columns = [_normalizar_nome(coluna) for coluna in df.columns]

    col_produto = _encontrar_coluna(df.columns, ["produto", "sku", "descricao produto", "descricao do produto"])
    col_op = _encontrar_coluna(df.columns, ["op", "o p", "ordem producao", "ordem de producao"])
    col_data_ini = _encontrar_coluna(df.columns, ["data ini", "data inicial", "dt ini", "dt inicial"])
    col_hora_ini = _encontrar_coluna(df.columns, ["hora ini", "hora inicial", "hr ini"])
    col_data_fim = _encontrar_coluna(df.columns, ["data fim", "data final", "dt fim", "dt final"])
    col_hora_fim = _encontrar_coluna(df.columns, ["hora fim", "hora final", "hr fim"])
    col_equipamento = _encontrar_coluna(df.columns, ["equipamento", "recurso", "maquina"])

    colunas_obrigatorias = {
        "Produto": col_produto,
        "OP": col_op,
        "Data Ini": col_data_ini,
        "Hora Ini": col_hora_ini,
        "Data Fim": col_data_fim,
        "Hora Fim": col_hora_fim,
        "Equipamento": col_equipamento,
    }
    faltantes = [nome for nome, coluna in colunas_obrigatorias.items() if coluna is None]
    if faltantes:
        raise ValueError("Colunas obrigatorias nao encontradas: " + ", ".join(faltantes))

    colunas_detectadas = {
        "linha_header": linha_header + 1,
        "produto": col_produto,
        "op": col_op,
        "data_ini": col_data_ini,
        "hora_ini": col_hora_ini,
        "data_fim": col_data_fim,
        "hora_fim": col_hora_fim,
        "equipamento": col_equipamento,
        "colunas_lidas": list(df.columns),
    }

    df["op_texto"] = df[col_op].apply(_op_para_texto)
    df["chave_op"] = df["op_texto"].str[:6]
    df["inicio"] = df.apply(lambda linha: _combinar_data_hora(linha[col_data_ini], linha[col_hora_ini]), axis=1)
    df["fim"] = df.apply(lambda linha: _combinar_data_hora(linha[col_data_fim], linha[col_hora_fim]), axis=1)

    df_valido = df[
        (df["op_texto"] != "")
        & (df["chave_op"] != "")
        & (df["inicio"].notna())
        & (df["fim"].notna())
    ].copy()

    if df_valido.empty:
        raise ValueError("Nenhuma linha valida encontrada para calcular lead time.")

    registros = []
    for chave_op, grupo in df_valido.groupby("chave_op"):
        grupo_inicio = grupo.sort_values("inicio")
        grupo_fim = grupo.sort_values("fim")
        inicio_familia = grupo["inicio"].min()
        fim_familia = grupo["fim"].max()
        lead_time_horas = (fim_familia - inicio_familia).total_seconds() / 3600
        lead_time_dias = lead_time_horas / 24

        registros.append(
            {
                "chave_op": chave_op,
                "produto": _primeiro_nao_vazio(grupo[col_produto]),
                "inicio_familia": inicio_familia,
                "fim_familia": fim_familia,
                "lead_time_horas": round(lead_time_horas, 2),
                "lead_time_dias": round(lead_time_dias, 2),
                "quantidade_ops": grupo["op_texto"].nunique(),
                "quantidade_recursos": grupo[col_equipamento].nunique(),
                "equipamento_inicial": _primeiro_nao_vazio(grupo_inicio[col_equipamento]),
                "equipamento_final": _primeiro_nao_vazio(grupo_fim[col_equipamento].iloc[::-1]),
            }
        )

    lead_time_por_chave = pd.DataFrame(registros)
    lead_time_por_chave = lead_time_por_chave[
        [
            "chave_op",
            "produto",
            "inicio_familia",
            "fim_familia",
            "lead_time_horas",
            "lead_time_dias",
            "quantidade_ops",
            "quantidade_recursos",
            "equipamento_inicial",
            "equipamento_final",
        ]
    ]

    resumo_lead_time = _calcular_resumo_lead_time(lead_time_por_chave)
    return lead_time_por_chave, resumo_lead_time, colunas_detectadas


def _gerar_excel_lead_time(df_lead_time, resumo):
    saida = BytesIO()
    with pd.ExcelWriter(saida, engine="openpyxl") as writer:
        df_lead_time.to_excel(writer, sheet_name="Lead Time por chave OP", index=False)
        pd.DataFrame([resumo]).to_excel(writer, sheet_name="Resumo Lead Time", index=False)
    return saida.getvalue()
