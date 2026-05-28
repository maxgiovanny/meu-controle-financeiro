import streamlit as st
import pandas as pd
from modulos.calculos import obter_mes_anterior

def carregar_dados_sessao(importar_do_anterior=False):
    """
    Carrega no st.session_state os dados do mês atual (ou de um mês anterior,
    se importar_do_anterior=True). Responsável pela lógica de auto-preenchimento
    dos gastos fixos quando um novo mês é acessado.
    """
    chave_atual = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"

    if importar_do_anterior:
        m_ant, a_ant = obter_mes_anterior(st.session_state.mes_atual, st.session_state.ano_atual)
        chave_ant = f"{m_ant}_{a_ant}"
        if chave_ant in st.session_state.historico_fixos:
            df_base = pd.DataFrame(st.session_state.historico_fixos[chave_ant])
            if not df_base.empty:
                df_base["Pago"] = False
                if "Categoria" not in df_base.columns:
                    df_base["Categoria"] = "Outros"
                if "Dia Venc." not in df_base.columns:
                    df_base["Dia Venc."] = 10
                st.session_state.gastos_fixos = df_base
                st.success(f"Importado de {m_ant}!")
            else:
                st.warning("Mês anterior vazio.")
        else:
            st.error("Sem dados no mês anterior.")
        return

    # --- Inicializa Fixos com Auto-preenchimento (Modelo Recorrente) ---
    dados_fixos_atual = st.session_state.historico_fixos.get(chave_atual, [])
    m_ant, a_ant = obter_mes_anterior(st.session_state.mes_atual, st.session_state.ano_atual)
    chave_ant = f"{m_ant}_{a_ant}"

    if not dados_fixos_atual and chave_ant in st.session_state.historico_fixos:
        # Copia os gastos fixos do mês anterior, desmarcando todos como pagos
        df_base = pd.DataFrame(st.session_state.historico_fixos[chave_ant])
        if not df_base.empty:
            df_base["Pago"] = False
            if "Categoria" not in df_base.columns:
                df_base["Categoria"] = "Outros"
            if "Dia Venc." not in df_base.columns:
                df_base["Dia Venc."] = 10
            st.session_state.gastos_fixos = df_base
            st.session_state.historico_fixos[chave_atual] = df_base.to_dict("records")
    else:
        st.session_state.gastos_fixos = pd.DataFrame(dados_fixos_atual)
        if st.session_state.gastos_fixos.empty:
            st.session_state.gastos_fixos = pd.DataFrame(
                columns=["Descrição", "Valor (R$)", "Pago", "Categoria", "Dia Venc."]
            )
        else:
            if "Categoria" not in st.session_state.gastos_fixos.columns:
                st.session_state.gastos_fixos["Categoria"] = "Outros"
            if "Dia Venc." not in st.session_state.gastos_fixos.columns:
                st.session_state.gastos_fixos["Dia Venc."] = 10

    # --- Casuais ---
    df_c = pd.DataFrame(st.session_state.historico_casuais.get(chave_atual, []))
    if not df_c.empty:
        df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
    st.session_state.gastos_casuais = (
        df_c if not df_c.empty
        else pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])
    )

    # --- Renda ---
    renda_data = st.session_state.renda_por_mes.get(chave_atual)
    if renda_data:
        st.session_state.renda_detalhada = pd.DataFrame(renda_data)
    else:
        st.session_state.renda_detalhada = pd.DataFrame(
            [{"Fonte": "Salário", "Valor (R$)": 0.0}]
        )