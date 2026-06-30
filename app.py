# -*- coding: utf-8 -*-
"""
app.py — Interface Streamlit do PPCP Inteligente.

Este arquivo contém apenas a camada de apresentação (UI).
Toda a lógica de negócio está em processamento.py.
Funções auxiliares estão em utils.py.
O cálculo de lead time está em modulo_lead_time.py.

PPCP Inteligente v1.0 | Márcio Dias do Amaral
"""

import pandas as pd
import streamlit as st

import processamento as proc
import utils
from modulo_lead_time import processar_lead_time


# ── Configuração da página ────────────────────────────────────────────────────

st.set_page_config(page_title=utils.APP_NAME, layout="wide")


# ── Funções de apresentação (UI pura) ────────────────────────────────────────

def destacar_linha_tabela_final(linha):
    """Aplica cores à tabela final conforme risco e ação recomendada."""
    risco = str(linha.get("risco_ruptura", ""))
    acao = str(linha.get("ação_recomendada", ""))

    if risco.startswith("Cr"):
        cor = "background-color: #fde2e2"
    elif "Aten" in risco:
        cor = "background-color: #fff4ce"
    elif "Reduzir" in acao or "reduzir" in acao:
        cor = "background-color: #e0f2fe"
    elif risco == "OK":
        cor = "background-color: #dcfce7"
    else:
        cor = ""
    return [cor] * len(linha)


def mostrar_resumo(resultado):
    """Exibe o bloco de resumo executivo na interface."""
    resumo = proc.gerar_resumo(resultado)

    st.divider()
    st.subheader("Resumo Executivo")
    st.caption("Visão executiva dos SKUs, estoque, cruzamento e risco operacional.")

    with st.container():
        st.markdown("**Classificação dos SKUs**")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total de SKUs", len(resultado))
        col2.metric("Estáveis", int((resultado["classificação"] == "Estável").sum()))
        col3.metric("Intermediários", int((resultado["classificação"] == "Intermediário").sum()))
        col4.metric("Intermitentes", int((resultado["classificação"] == "Intermitente").sum()))
        col5.metric("Sem venda", int((resultado["classificação"] == "Sem venda").sum()))

    st.divider()

    with st.container():
        st.markdown("**Estoque e capacidade física**")
        col6, col7, col8, col9, col10 = st.columns(5)
        col6.metric("Alvo pacotes", f"{resumo['total_estoque_alvo_pacotes']:,.0f}")
        col7.metric("Alvo kg", f"{resumo['total_estoque_alvo_kg']:,.2f}")
        col8.metric("Alvo toneladas", f"{resumo['total_estoque_alvo_ton']:,.3f}")
        col9.metric("Estoque atual kg", f"{resumo['total_estoque_atual_kg']:,.2f}")
        col10.metric("Estoque atual ton", f"{resumo['total_estoque_atual_ton']:,.3f}")

    with st.container():
        st.markdown("**Cruzamento com estoque atual**")
        col11, col12, col13 = st.columns(3)
        col11.metric("SKUs com estoque encontrado", resumo["skus_estoque_encontrado"])
        col12.metric("SKUs não encontrados", resumo["skus_estoque_nao_encontrado"])
        col13.metric("Percentual de match", f"{resumo['percentual_match']:.1%}")

    with st.container():
        st.markdown("**Risco de ruptura e excesso**")
        col14, col15, col16 = st.columns(3)
        col14.metric("SKUs críticos", resumo["skus_criticos"])
        col15.metric("SKUs em atenção", resumo["skus_atencao"])
        col16.metric("SKUs com excesso", resumo["skus_excesso"])

    st.divider()


def mostrar_painel_gerencial(
    resultado,
    resumo_rupturas,
    rupturas_detalhe,
    resumo_aderencia,
    aderencia_detalhe,
    programacao_tratada=None,
    capacidade_maxima_kg=900_000,
):
    """Exibe o Painel Gerencial com KPIs de estoque qualificado, rupturas e aderência."""
    estoque_qualificado = proc.calcular_estoque_qualificado(resultado, capacidade_maxima_kg)

    st.divider()
    st.subheader("Painel Gerencial PPCP")
    st.caption(
        "Acompanhamento da qualidade do estoque, rupturas evitáveis e aderência à recomendação do PPCP."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Estoque Qualificado (%)",
        f"{estoque_qualificado['estoque_qualificado_percentual']:.1f}%",
    )
    col1.caption(
        f"{estoque_qualificado['skus_qualificados']} de {estoque_qualificado['total_skus']} SKUs"
    )
    col2.metric("Rupturas Evitáveis", resumo_rupturas["rupturas_evitaveis"])
    col2.caption(resumo_rupturas["status"])

    if resumo_aderencia["aderencia_percentual"] is None:
        col3.metric("Aderência à Recomendação", "Não calculada")
    else:
        col3.metric(
            "Aderência à Recomendação",
            f"{resumo_aderencia['aderencia_percentual']:.1f}%",
        )
    col3.caption(resumo_aderencia["status"])

    col4, col5, col6 = st.columns(3)
    col4.metric("SKUs críticos", estoque_qualificado["skus_criticos"])
    col5.metric("SKUs em atenção", estoque_qualificado["skus_atencao"])
    col6.metric("SKUs com excesso", estoque_qualificado["skus_excesso"])

    # ── KPIs de Capacidade Física de PA ──────────────────────────────────────
    st.divider()
    st.markdown("**Capacidade Física de PA**")
    cap_ton = estoque_qualificado["capacidade_maxima_ton"]
    atual_ton = estoque_qualificado["estoque_atual_total_ton"]
    alvo_ton = estoque_qualificado["estoque_alvo_total_ton"]
    util_pct = estoque_qualificado["capacidade_utilizada_pct"]
    alvo_pct = estoque_qualificado["capacidade_alvo_pct"]
    qualif_pct = estoque_qualificado["capacidade_qualificada_pct"]

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Estoque atual / Capacidade",
        f"{util_pct:.1f}%",
        help=f"{atual_ton:,.1f} t de {cap_ton:,.0f} t",
    )
    c1.caption(f"{atual_ton:,.1f} ton de {cap_ton:,.0f} ton")

    c2.metric(
        "Estoque alvo / Capacidade",
        f"{alvo_pct:.1f}%",
        help=f"Se seguir a política, o alvo total seria {alvo_ton:,.1f} t",
    )
    c2.caption(f"Alvo: {alvo_ton:,.1f} ton")
    if alvo_pct > 100:
        st.warning(
            f"⚠️ O estoque alvo ({alvo_ton:,.1f} t) ultrapassa a capacidade máxima de {cap_ton:,.0f} t. "
            "Revise a política de cobertura ou a capacidade do armazém."
        )

    c3.metric(
        "Estoque qualificado / Capacidade",
        f"{qualif_pct:.1f}%",
        help="Fração da capacidade ocupada por estoque dentro da política (sem críticos, atenção ou excesso)",
    )
    c3.caption(f"{estoque_qualificado['estoque_qualificado_kg']/1000:,.1f} ton qualificadas")

    with st.expander("Detalhe de rupturas evitáveis"):
        if rupturas_detalhe.empty:
            st.info("Sem planilha de rupturas carregada")
        else:
            st.metric("Total de rupturas informadas", resumo_rupturas["total_rupturas"])
            st.dataframe(rupturas_detalhe, use_container_width=True, hide_index=True)

    with st.expander("Detalhe de aderência da programação"):
        if aderencia_detalhe.empty:
            st.info("Sem programação semanal carregada")
        else:
            c1, c2 = st.columns(2)
            c1.metric("SKUs aderentes", resumo_aderencia["skus_aderentes"])
            c2.metric("SKUs não aderentes", resumo_aderencia["skus_nao_aderentes"])
            st.dataframe(aderencia_detalhe, use_container_width=True, hide_index=True)

    return estoque_qualificado


# ── Aplicação principal ───────────────────────────────────────────────────────

def main():
    st.title(utils.APP_NAME)
    st.write("Classificação de SKUs, política de estoque e recomendação de ação para o PPCP.")

    # ── Sidebar: uploads ─────────────────────────────────────────────────────

    st.sidebar.header("Arquivos")
    arquivo_vendas = st.sidebar.file_uploader(
        "Upload da planilha de vendas",
        type=["xlsx", "xlsm"],
        help="Exemplo transacional: Dt. Faturado, Código, Produto e Pacotes.",
    )
    arquivo_estoque = st.sidebar.file_uploader(
        "Upload opcional da planilha de estoque atual",
        type=["xlsx", "xlsm"],
        help="Use Código ou Produto no formato [AGC01] Nome do produto, mais saldo em estoque em pacotes.",
    )
    arquivo_lead_time = st.sidebar.file_uploader(
        "Upload opcional da planilha de lead time interno",
        type=["xlsx", "xlsm"],
        help="Layout esperado: Produto, OP, Data Ini, Hora Ini, Data Fim, Hora Fim e Equipamento.",
    )
    arquivo_rupturas = st.sidebar.file_uploader(
        "Upload opcional da planilha de rupturas da semana",
        type=["xlsx", "xlsm"],
        help="Layout esperado: codigo, produto, data e ruptura.",
    )
    arquivo_programacao = st.sidebar.file_uploader(
        "Upload opcional da programação semanal",
        type=["xlsx", "xlsm"],
        help="Layout esperado: codigo, produto, pacotes_programados e kg_programado opcional.",
    )

    # ── Sidebar: Política de Estoque ─────────────────────────────────────────

    st.sidebar.header("Política de Estoque")
    cobertura_alvo_estavel_dias = st.sidebar.number_input(
        "Cobertura alvo estável (dias)", min_value=0, max_value=90, value=7, step=1,
    )
    cobertura_alvo_intermediario_dias = st.sidebar.number_input(
        "Cobertura alvo intermediário (dias)", min_value=0, max_value=90, value=10, step=1,
    )
    cobertura_alvo_intermitente_dias = st.sidebar.number_input(
        "Cobertura alvo intermitente (dias)", min_value=0, max_value=90, value=3, step=1,
    )
    cobertura_minima_sem_venda_dias = st.sidebar.number_input(
        "Cobertura sem venda (dias)", min_value=0, max_value=90, value=0, step=1,
    )
    parametros_cobertura = {
        "estavel": cobertura_alvo_estavel_dias,
        "intermediario": cobertura_alvo_intermediario_dias,
        "intermitente": cobertura_alvo_intermitente_dias,
        "sem_venda": cobertura_minima_sem_venda_dias,
    }

    # ── Sidebar: Capacidade de PA ────────────────────────────────────────────

    st.sidebar.header("Capacidade de PA")
    capacidade_maxima_ton = st.sidebar.number_input(
        "Capacidade máxima de PA (toneladas)",
        min_value=0.0,
        max_value=50_000.0,
        value=900.0,
        step=10.0,
        help="Limite físico do armazém de produto acabado em toneladas.",
    )
    capacidade_maxima_kg = capacidade_maxima_ton * 1000

    # ── Sidebar: Takt Time ───────────────────────────────────────────────────

    st.sidebar.header("Takt Time")
    dias_uteis = st.sidebar.number_input(
        "Dias úteis considerados no mês", min_value=1, max_value=31, value=22, step=1,
    )
    horas_disponiveis_dia = st.sidebar.number_input(
        "Horas disponíveis por dia", min_value=0.5, max_value=24.0, value=8.0, step=0.5,
    )
    eficiencia_percentual = st.sidebar.number_input(
        "Eficiência planejada (%)", min_value=1.0, max_value=100.0, value=85.0, step=1.0,
    )
    unidade_principal = st.sidebar.selectbox("Unidade principal para análise", ["Pacotes", "KG"])
    eficiencia_planejada = eficiencia_percentual / 100
    tempo_disponivel_previsto = dias_uteis * horas_disponiveis_dia * 60 * eficiencia_planejada
    st.sidebar.caption(f"Tempo disponível mensal em minutos: {tempo_disponivel_previsto:,.2f}")

    # ── Guarda de entrada ────────────────────────────────────────────────────

    if arquivo_vendas is None:
        st.info("Carregue a planilha de vendas para iniciar.")
        return

    # ── Processamento: Vendas ─────────────────────────────────────────────────

    try:
        df_vendas = pd.read_excel(arquivo_vendas, engine="openpyxl")
    except Exception as erro:
        st.error("Não foi possível ler a planilha de vendas.")
        st.exception(erro)
        return

    try:
        resultado_base, base_pacotes, base_kg, metadados = proc.processar_vendas(df_vendas)
    except Exception as erro:
        st.error(str(erro))
        st.subheader("Colunas encontradas na planilha de vendas")
        st.write(list(df_vendas.columns))
        return

    # ── Processamento: Estoque ────────────────────────────────────────────────

    if arquivo_estoque is not None:
        try:
            df_estoque = pd.read_excel(arquivo_estoque, engine="openpyxl")
            estoque = proc.preparar_estoque(df_estoque)
        except Exception as erro:
            st.error(str(erro))
            return
    else:
        estoque = pd.DataFrame(
            columns=["codigo_chave", "código", "estoque atual pacotes", "estoque atual kg"]
        )

    # ── Processamento: Lead Time ──────────────────────────────────────────────

    lead_time_por_chave = pd.DataFrame()
    resumo_lead_time = None
    colunas_detectadas_lead_time = None

    if arquivo_lead_time is not None:
        try:
            lead_time_por_chave, resumo_lead_time, colunas_detectadas_lead_time = processar_lead_time(
                arquivo_lead_time
            )
        except Exception as erro:
            st.error("Não foi possível processar a planilha de lead time interno.")
            st.exception(erro)
            return

    # ── Processamento: Estoque & Ação ─────────────────────────────────────────

    resultado_final = proc.calcular_estoque_e_acao(
        resultado_base,
        estoque,
        resumo_lead_time,
        parametros_cobertura,
        dias_uteis,
    )

    resultado_final, tempo_disponivel_min_mes = proc.calcular_takt_time(
        resultado_final, dias_uteis, horas_disponiveis_dia, eficiencia_planejada
    )
    tabela_takt = proc.montar_tabela_takt(resultado_final)
    tabela_politica_estoque = proc.montar_tabela_politica_estoque(resultado_final)

    # ── Processamento: Rupturas ───────────────────────────────────────────────

    if arquivo_rupturas is not None:
        try:
            df_rupturas = pd.read_excel(arquivo_rupturas, engine="openpyxl")
            rupturas = proc.preparar_rupturas(df_rupturas)
        except Exception as erro:
            st.error("Não foi possível processar a planilha de rupturas da semana.")
            st.exception(erro)
            return
    else:
        rupturas = pd.DataFrame(
            columns=["codigo_chave", "código", "SKU", "data", "ruptura"]
        )

    # ── Processamento: Programação Semanal ───────────────────────────────────

    if arquivo_programacao is not None:
        try:
            df_programacao = pd.read_excel(arquivo_programacao, engine="openpyxl")
            programacao = proc.preparar_programacao_semanal(df_programacao)
        except Exception as erro:
            st.error("Não foi possível processar a programação semanal.")
            st.exception(erro)
            return
    else:
        programacao = pd.DataFrame(
            columns=["codigo_chave", "código", "SKU", "pacotes_programados", "kg_programado"]
        )

    resumo_rupturas, rupturas_detalhe = proc.calcular_rupturas_evitaveis(resultado_final, rupturas)
    resumo_aderencia, aderencia_detalhe = proc.calcular_aderencia_programacao(
        resultado_final, programacao
    )

    # ── Mensagens de status ───────────────────────────────────────────────────

    st.success("Processamento concluído.")
    st.info("Formato detectado: " + metadados["formato"])
    st.info("Cruzamento de estoque feito por codigo_chave.")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Produto/SKU", str(metadados["coluna_produto"]))
    col2.metric("Código", str(metadados["coluna_codigo"]))
    col3.metric("Data", str(metadados["coluna_data"]))
    col4.metric("Pacotes", str(metadados["coluna_volume"]))

    col5, col6 = st.columns(2)
    col5.metric("Quantidade de meses", metadados["quantidade_meses"])
    col6.metric("Quantidade de SKUs", metadados["quantidade_skus"])

    st.caption("Meses usados no cálculo: " + ", ".join(metadados["meses_usados"]))

    if metadados["codigos_sem_peso"]:
        st.warning(
            "Há códigos sem número para extrair o peso do pacote em kg: "
            + ", ".join(metadados["codigos_sem_peso"])
        )
    if arquivo_estoque is None:
        st.warning("Nenhum estoque foi carregado. O app considerou estoque atual igual a zero.")

    # ── Resumo Executivo ──────────────────────────────────────────────────────

    mostrar_resumo(resultado_final)

    # ── Painel Gerencial ──────────────────────────────────────────────────────

    estoque_qualificado = mostrar_painel_gerencial(
        resultado_final,
        resumo_rupturas,
        rupturas_detalhe,
        resumo_aderencia,
        aderencia_detalhe,
        programacao,
        capacidade_maxima_kg=capacidade_maxima_kg,
    )
    painel_gerencial = proc.montar_resumo_painel_gerencial(
        estoque_qualificado, resumo_rupturas, resumo_aderencia
    )

    # ── Takt Time ─────────────────────────────────────────────────────────────

    st.divider()
    st.subheader("Takt Time de Demanda")
    st.caption("Pressão de demanda considerando disponibilidade mensal planejada.")
    st.markdown("**Parâmetros utilizados**")
    st.caption("Dias úteis considerados: " + str(dias_uteis))
    st.caption("Horas disponíveis por dia: " + f"{horas_disponiveis_dia:.2f}")
    st.caption("Eficiência considerada: " + f"{eficiencia_planejada:.0%}")
    st.caption("Tempo disponível mensal em minutos: " + f"{tempo_disponivel_min_mes:,.2f}")

    menor_takt_pacote = resultado_final.loc[
        resultado_final["takt_min_por_pacote"].notna()
        & (resultado_final["takt_min_por_pacote"] > 0),
        "takt_min_por_pacote",
    ].min()
    maior_demanda_pacotes = resultado_final["demanda_diaria_pacotes"].fillna(0).max()
    maior_demanda_kg = resultado_final["demanda_diaria_kg"].fillna(0).max()
    skus_sem_venda = int((resultado_final["classificação"] == "Sem venda").sum())

    st.markdown("**Indicadores de demanda**")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(
        "Menor takt por pacote",
        "0" if pd.isna(menor_takt_pacote) else f"{menor_takt_pacote:,.2f} min",
    )
    kpi2.metric("Maior demanda diária pacotes", f"{maior_demanda_pacotes:,.2f}")
    kpi3.metric("Maior demanda diária kg", f"{maior_demanda_kg:,.2f}")
    kpi4.metric("SKUs sem venda", skus_sem_venda)

    with st.expander("Ranking de SKUs por maior pressão de demanda"):
        ranking_takt = proc.montar_ranking_takt(resultado_final, unidade_principal)
        st.dataframe(ranking_takt, use_container_width=True, hide_index=True)

    # ── Lead Time ─────────────────────────────────────────────────────────────

    if arquivo_lead_time is not None:
        st.divider()
        st.subheader("Lead Time Interno")
        st.caption("Diagnóstico estatístico por família de OP carregada.")
        st.markdown("**Resumo estatístico do lead time**")
        lt1, lt2, lt3, lt4, lt5 = st.columns(5)
        lt1.metric("Famílias analisadas", resumo_lead_time["familias"])
        lt2.metric("P50 dias", resumo_lead_time["p50"])
        lt3.metric("P75 dias", resumo_lead_time["p75"])
        lt4.metric("P90 dias", resumo_lead_time["p90"])
        lt5.metric("Média dias", resumo_lead_time["media"])

        with st.expander("Colunas detectadas no lead time"):
            st.write(colunas_detectadas_lead_time)

        st.dataframe(lead_time_por_chave, use_container_width=True, hide_index=True)

    # ── Tabela Final ──────────────────────────────────────────────────────────

    st.divider()
    st.subheader("Tabela Final")
    st.caption(
        "Destaques visuais: crítico em vermelho, atenção em amarelo, excesso em azul e OK em verde."
    )
    tabela_final_visual = resultado_final.style.apply(destacar_linha_tabela_final, axis=1)
    st.dataframe(tabela_final_visual, use_container_width=True, hide_index=True, height=650)

    with st.expander("Base mensal em pacotes"):
        st.dataframe(base_pacotes, use_container_width=True, hide_index=True)
    with st.expander("Base mensal em kg"):
        st.dataframe(base_kg, use_container_width=True, hide_index=True)
    with st.expander("Estoque atual usado no cruzamento"):
        st.dataframe(estoque, use_container_width=True, hide_index=True)

    # ── Download Excel ────────────────────────────────────────────────────────

    arquivo_excel = utils.gerar_excel(
        resultado_final,
        base_pacotes,
        base_kg,
        estoque,
        lead_time_por_chave,
        tabela_takt,
        tabela_politica_estoque,
        painel_gerencial,
        rupturas_detalhe,
        aderencia_detalhe,
        programacao,
    )
    st.download_button(
        label="Baixar Excel com resultado",
        data=arquivo_excel,
        file_name="ppcp_inteligente_resultado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


if __name__ == "__main__":
    main()
