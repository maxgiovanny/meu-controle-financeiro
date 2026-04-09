import streamlit as st
import pandas as pd
import json
import gspread
import plotly.express as px
from datetime import datetime
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered")

MESES = {"Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, "Maio": 5, "Junho": 6, 
         "Julho": 7, "Agosto": 8, "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12}
CATEGORIAS = ["Alimentação", "Transporte", "Lazer", "Saúde", "Casa", "Trabalho", "Outros"]

# --- CONEXÃO GOOGLE SHEETS ---
@st.cache_resource
def ligar_google_sheets():
    creds_dict = json.loads(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds).open_by_url(st.secrets["url_planilha"]).sheet1

try:
    worksheet = ligar_google_sheets()
except Exception:
    st.error("Erro de conexão com a nuvem.")
    st.stop()

# --- AUXILIARES ---
def criar_ponto_restauracao():
    st.session_state.backup_anterior = {
        "renda": st.session_state.renda,
        "guias_extras": list(st.session_state.guias_extras),
        "gastos_fixos": st.session_state.gastos_fixos.copy(),
        "gastos_casuais": st.session_state.gastos_casuais.copy(),
        "historico_fixos": json.loads(json.dumps(st.session_state.historico_fixos)),
        "historico_casuais": json.loads(json.dumps(st.session_state.historico_casuais))
    }

def salvar_dados_nuvem():
    chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
    casuais_save = st.session_state.gastos_casuais.copy()
    if "Data" in casuais_save.columns: casuais_save["Data"] = casuais_save["Data"].astype(str)
    
    st.session_state.historico_fixos[chave] = st.session_state.gastos_fixos.to_dict("records")
    st.session_state.historico_casuais[chave] = casuais_save.to_dict("records")

    dados = {
        "renda": st.session_state.renda, "guias_extras": st.session_state.guias_extras,
        "historico_fixos": st.session_state.historico_fixos, "historico_casuais": st.session_state.historico_casuais
    }
    for g in st.session_state.guias_extras:
        if f"dados_{g}" in st.session_state: dados[f"dados_{g}"] = st.session_state[f"dados_{g}"].to_dict("records")
    
    worksheet.update(values=[[json.dumps(dados)]], range_name='A1')
    st.toast("💾 Sincronizado!", icon="✅")

def carregar_dados_sessao(manual=False):
    chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
    
    # Busca Fixos (Lógica de Herança Cronológica)
    if chave in st.session_state.historico_fixos and not manual:
        st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos[chave])
    else:
        df_base = pd.DataFrame(columns=["Descrição", "Valor (R$)", "Pago"])
        if st.session_state.historico_fixos:
            # Ordena chaves para pegar o mês mais recente que tem dados
            ord_chaves = sorted(st.session_state.historico_fixos.keys(), key=lambda x: (int(x.split('_')[1]), MESES[x.split('_')[0]]), reverse=True)
            for k in ord_chaves:
                if len(st.session_state.historico_fixos[k]) > 0:
                    df_base = pd.DataFrame(st.session_state.historico_fixos[k])
                    if "Pago" in df_base.columns: df_base["Pago"] = False
                    break
        st.session_state.gastos_fixos = df_base

    # Busca Casuais
    if chave in st.session_state.historico_casuais and not manual:
        df_c = pd.DataFrame(st.session_state.historico_casuais[chave])
        if not df_c.empty:
            df_c["Data"] = pd.to_datetime(df_c.get("Data", datetime.now().date())).dt.date
            if "Categoria" not in df_c.columns: df_c["Categoria"] = "Outros"
        st.session_state.gastos_casuais = df_c
    else:
        st.session_state.gastos_casuais = pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])

# --- INICIALIZAÇÃO ---
if "dados_carregados" not in st.session_state:
    val = worksheet.acell('A1').value
    d = json.loads(val) if val else {}
    st.session_state.ano_atual, st.session_state.mes_atual = 2026, "Abril"
    st.session_state.renda = d.get("renda", 10000.0)
    st.session_state.guias_extras = d.get("guias_extras", [])
    st.session_state.historico_fixos = d.get("historico_fixos", {})
    st.session_state.historico_casuais = d.get("historico_casuais", {})
    st.session_state.backup_anterior = None
    for g in st.session_state.guias_extras:
        st.session_state[f"dados_{g}"] = pd.DataFrame(d.get(f"dados_{g}", []))
    carregar_dados_sessao()
    st.session_state.dados_carregados = True

# --- CÁLCULOS ---
def calc_parc(df, m, a):
    at, tot = [], 0.0
    if df is None or df.empty: return pd.DataFrame(columns=["Descrição", "Parcela", "Valor (R$)"]), 0.0
    for _, r in df.iterrows():
        try:
            m_i, a_i, qtd, v = int(r["Mês Início (1-12)"]), int(r["Ano Início"]), int(r["Qtd Parcelas"]), float(r["Valor Parcela (R$)"])
            alvo, ini = a * 12 + m, a_i * 12 + m_i
            if ini <= alvo <= (ini + qtd - 1):
                at.append({"Descrição": r["Descrição"], "Parcela": f"{alvo-ini+1}/{qtd}", "Valor (R$)": v})
                tot += v
        except: continue
    return pd.DataFrame(at), tot

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configurações")
    if st.session_state.backup_anterior:
        if st.button("🔙 Desfazer"):
            b = st.session_state.backup_anterior
            st.session_state.renda, st.session_state.guias_extras = b["renda"], b["guias_extras"]
            st.session_state.gastos_fixos, st.session_state.gastos_casuais = b["gastos_fixos"], b["gastos_casuais"]
            st.session_state.historico_fixos, st.session_state.historico_casuais = b["historico_fixos"], b["historico_casuais"]
            st.session_state.backup_anterior = None
            salvar_dados_nuvem(); st.rerun()

    m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
    a_sel = st.number_input("Ano:", 2024, 2030, st.session_state.ano_atual)
    if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
        salvar_dados_nuvem(); st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
        carregar_dados_sessao(); st.rerun()

    r_sel = st.number_input("Renda:", 0.0, 100000.0, st.session_state.renda, 100.0)
    if r_sel != st.session_state.renda: st.session_state.renda = r_sel; salvar_dados_nuvem()

    st.divider(); st.subheader("🛠️ Gerenciar Guias")
    ng = st.text_input("Nova Guia:")
    if st.button("➕ Criar"):
