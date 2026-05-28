import streamlit as st
import pandas as pd
from modulos.utilidades import safe_int, safe_float, MESES

def obter_mes_anterior(mes_nome, ano_atual):
    """
    Retorna (nome_mês_anterior, ano) dado o mês/ano atuais.
    Exemplo: ('Janeiro', 2025) -> ('Dezembro', 2024).
    """
    lista = list(MESES.keys())
    idx = lista.index(mes_nome)
    return (lista[idx - 1], ano_atual) if idx > 0 else ("Dezembro", ano_atual - 1)

@st.cache_data(ttl=3600)
def calc_parc_com_categoria(df, m, a):
    """
    Calcula as parcelas de um DataFrame de guias para um determinado mês (1-12) e ano.
    Retorna uma tupla: (DataFrame com as parcelas, valor total, dict de totais por categoria).
    """
    parcelas = []
    if df is None or df.empty:
        return pd.DataFrame(columns=["Descrição", "Categoria", "Valor (R$)"]), 0.0, {}
    df_valid = df.dropna(subset=["Descrição", "Valor Parcela (R$)"])
    for _, r in df_valid[df_valid["Descrição"] != ""].iterrows():
        try:
            m_i = safe_int(r["Mês Início (1-12)"])
            a_i = safe_int(r["Ano Início"])
            qtd = safe_int(r["Qtd Parcelas"])
            v = safe_float(r["Valor Parcela (R$)"])
            alvo = a * 12 + m
            ini = a_i * 12 + m_i
            if ini <= alvo <= (ini + qtd - 1):
                categoria = r.get("Categoria", "Outros")
                parcelas.append({
                    "Descrição": r["Descrição"],
                    "Categoria": categoria,
                    "Valor (R$)": v
                })
        except:
            continue
    df_parc = pd.DataFrame(parcelas)
    total = df_parc["Valor (R$)"].sum() if not df_parc.empty else 0.0
    soma_cat = df_parc.groupby("Categoria")["Valor (R$)"].sum().to_dict() if not df_parc.empty else {}
    return df_parc, total, soma_cat
