import streamlit as st
import pandas as pd
from datetime import datetime
from modulos.utilidades import MESES, CATEGORIAS_PADRAO_BASE
from modulos.bd_google import carregar_dados_nuvem_raw

def carregar_estado_inicial(carregar_dados_sessao_fn):
    """
    Inicializa todos os dados da sessão no primeiro carregamento do aplicativo.
    Deve ser chamada uma única vez, antes de qualquer outro acesso ao estado.
    """
    if "dados_carregados" in st.session_state:
        return

    with st.spinner("Carregando dados da nuvem..."):
        dados_raw, _ = carregar_dados_nuvem_raw()

    hj = datetime.now()
    st.session_state.ano_atual = hj.year
    st.session_state.mes_atual = list(MESES.keys())[hj.month - 1]

    st.session_state.historico_casuais = dados_raw.get("historico_casuais", {})
    st.session_state.historico_fixos = dados_raw.get("historico_fixos", {})
    st.session_state.guias_extras = dados_raw.get("guias_extras", [])
    st.session_state.categorias_personalizadas = dados_raw.get("categorias_personalizadas", [])
    st.session_state.categorias_padrao = dados_raw.get("categorias_padrao", CATEGORIAS_PADRAO_BASE.copy())
    st.session_state.renda_por_mes = dados_raw.get("renda_por_mes", {})
    st.session_state.metas_orcamento = dados_raw.get("metas_orcamento", {})
    st.session_state.pagamento_guias = dados_raw.get("pagamento_guias", {})

    # Garante que as categorias padrão estejam corretas
    if len(st.session_state.categorias_padrao) != len(CATEGORIAS_PADRAO_BASE):
        st.session_state.categorias_padrao = CATEGORIAS_PADRAO_BASE.copy()

    # Inicializa DataFrames das guias
    colunas_guia = [
        "Descrição", "Valor Parcela (R$)", "Data da Compra",
        "Mês Início (1-12)", "Ano Início", "Qtd Parcelas", "Categoria"
    ]
    for g in st.session_state.guias_extras:
        dados_g = dados_raw.get(f"dados_{g}", [])
        if dados_g:
            df = pd.DataFrame(dados_g)
            for col in colunas_guia:
                if col not in df.columns:
                    if col == "Data da Compra":
                        df[col] = None
                    else:
                        df[col] = None
            if "Data da Compra" in df.columns:
                df["Data da Compra"] = pd.to_datetime(df["Data da Compra"], errors='coerce')
                df["Data da Compra"] = df["Data da Compra"].apply(
                    lambda x: x.date() if isinstance(x, datetime) and not pd.isna(x) else None
                )
            st.session_state[f"dados_{g}"] = df
        else:
            st.session_state[f"dados_{g}"] = pd.DataFrame(columns=colunas_guia)

    # Reseta formato antigo do pagamento de guias (global -> mensal)
    if st.session_state.pagamento_guias and not isinstance(
        list(st.session_state.pagamento_guias.values())[0], dict
    ):
        st.session_state.pagamento_guias = {}

    # Inicializa investimentos
    dados_inv = dados_raw.get("historico_investimentos", [])
    if dados_inv:
        df_inv = pd.DataFrame(dados_inv)
        df_inv["Data"] = pd.to_datetime(df_inv["Data"], errors='coerce').dt.date
        st.session_state.dados_investimentos = df_inv
    else:
        st.session_state.dados_investimentos = pd.DataFrame(
            columns=["Data", "Ativo", "Classe", "Tipo", "Valor (R$)", "Descrição"]
        )

    # Carrega os dados do mês atual
    carregar_dados_sessao_fn()
    st.session_state.dados_carregados = True
