import streamlit as st
import pandas as pd

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered")

MESES = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, 
    "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8, 
    "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
}

# --- MEMÓRIA DA APLICAÇÃO ---
if "ano_atual" not in st.session_state:
    st.session_state.ano_atual = 2026
if "mes_atual" not in st.session_state:
    st.session_state.mes_atual = "Maio"
if "renda" not in st.session_state:
    st.session_state.renda = 10000.00
if "guias_extras" not in st.session_state:
    st.session_state.guias_extras = ["💳 Digio", "💳 Itaú", "💳 Inter", "💳 Mercado Pago", "💳 Will", "🚗 Despesas Carro"]

if "gastos_fixos" not in st.session_state:
    st.session_state.gastos_fixos = pd.DataFrame({
        "Descrição": ["Consórcio", "Plano de Saúde", "Combustível", "Linha Claro", "Linha Mútua", "Energia", "Mário Felipe", "Pedro"],
        "Valor (R$)": [1350.00, 355.23, 1200.00, 90.00, 50.00, 70.00, 100.00, 80.00],
        "Pago": [False] * 8
    })
if "gastos_casuais" not in st.session_state:
    st.session_state.gastos_casuais = pd.DataFrame({"Descrição": ["Supermercado"], "Valor (R$)": [600.00]})

# --- DADOS PRÉ-CADASTRADOS DA SUA PLANILHA ---
dados_iniciais = {
    "💳 Digio": pd.DataFrame({
        "Descrição": ["Academia", "AliExpress (9/10)", "OneDrive"],
        "Mês Início (1-12)": [5, 9, 5],
        "Ano Início": [2026, 2025, 2026],
        "Qtd Parcelas": [12, 10, 12],
        "Valor Parcela (R$)": [120.00, 10.87, 9.00]
    }),
    "💳 Itaú": pd.DataFrame({
        "Descrição": ["Membro", "Paramount", "Netflix", "Amazon", "Google One"],
        "Mês Início (1-12)": [5, 5, 5, 5, 5],
        "Ano Início": [2026, 2
