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
def obter_mes_anterior(mes_nome, ano_atual):
    lista = list(MESES.keys())
    idx = lista.index(mes_nome)
    return (lista[idx - 1], ano_atual) if idx > 0 else ("Dezembro", ano_atual - 1)

def salvar_dados_nuvem():
    chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
    casuais_save = st.session_state.gastos_casuais.copy()
    if "Data" in casuais_save.columns:
        casuais_save["Data"] = pd.to_datetime(casuais_save["Data"]).dt.date.astype(str)

    st.session_state.historico_fixos[chave] = st.session_state.gastos_fixos.to_dict("records")
    st.session_state.historico_casuais[chave] = casuais_save.to_dict("records")

    dados = {
        "renda": st.session_state.renda,
        "guias_extras": st.session_state.guias_extras,
        "historico_fixos": st.session_state.historico_fixos,
        "historico_casuais": st.session_state.historico_casuais
    }
    for g in st.session_state.guias_extras:
        if f"dados_{g}" in st.session_state:
            dados[f"dados_{g}"] = st.session_state[f"dados_{g}"].to_dict("records")

    worksheet.update(values=[[json.dumps(dados, default=str)]], range_name='A1')
    st.toast("💾 Sincronizado!", icon="✅")

@st.cache_data(ttl=60)
def carregar_dados_nuvem_raw():
    val = worksheet.acell('A1').value
    return json.loads(val) if val else {}

def carregar_dados_sessao(importar_do_anterior=False):
    chave_atual = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"

    if importar_do_anterior:
        m_ant, a_ant = obter_mes_anterior(st.session_state.mes_atual, st.session_state.ano_atual)
        chave_ant = f"{m_ant}_{a_ant}"
        if chave_ant in st.session_state.historico_fixos:
            df_base = pd.DataFrame(st.session_state.historico_fixos[chave_ant])
            if not df_base.empty:
                df_base["Pago"] = False
                st.session_state.gastos_fixos = df_base
                st.success(f"Importado de {m_ant}!")
            else: st.warning("Mês anterior está vazio.")
        else: st.error("Sem dados no mês anterior.")
        return

    if chave_atual in st.session_state.historico_fixos:
        st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos[chave_atual])
    else:
        st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição", "Valor (R$)", "Pago"])

    if chave_atual in st.session_state.historico_casuais:
        df_c = pd.DataFrame(st.session_state.historico_casuais[chave_atual])
        if not df_c.empty:
            df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
            if "Categoria" not in df_c.columns: df_c["Categoria"] = "Outros"
        st.session_state.gastos_casuais = df_c
    else:
        st.session_state.gastos_casuais = pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])

# --- INICIALIZAÇÃO ---
if "dados_carregados" not in st.session_state:
    dados_raw = carregar_dados_nuvem_raw()
    hoje = datetime.now()
    st.session_state.ano_atual = hoje.year
    st.session_state.mes_atual = list(MESES.keys())[hoje.month - 1]
    st.session_state.renda = dados_raw.get("renda", 10000.0)
    st.session_state.guias_extras = dados_raw.get("guias_extras", [])
    st.session_state.historico_fixos = dados_raw.get("historico_fixos", {})
    st.session_state.historico_casuais = dados_raw.get("historico_casuais", {})
    for g in st.session_state.guias_extras:
        st.session_state[f"dados_{g}"] = pd.DataFrame(dados_raw.get(f"dados_{g}", []))
    carregar_dados_sessao()
    st.session_state.dados_carregados = True

# --- CÁLCULOS ---
def calc_parc(df, m, a):
    at, tot = [], 0.0
    if df is None or df.empty:
        return pd.DataFrame(columns=["Descrição", "Parcela", "Valor (R$)"]), 0.0
    
    df_valid = df.dropna(subset=["Descrição", "Valor Parcela (R$)"])
    df_valid = df_valid[df_valid["Descrição"] != ""]

    for idx, r in df_valid.iterrows():
        try:
            m_i, a_i, qtd, v = int(r["Mês Início (1-12)"]), int(r["Ano Início"]), int(r["Qtd Parcelas"]), float(r["Valor Parcela (R$)"])
            alvo, ini = a * 12 + m, a_i * 12 + m_i
            if ini <= alvo <= (ini + qtd - 1):
                at.append({"Descrição": r["Descrição"], "Parcela": f"{alvo - ini + 1}/{qtd}", "Valor (R$)": v})
                tot += v
        except: continue
    return pd.DataFrame(at), tot

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configurações")
    if st.button("🔄 Recarregar da nuvem"):
        st.cache_data.clear()
        st.rerun()

    m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
    a_sel = st.number_input("Ano:", 2024, 2030, st.session_state.ano_atual)

    if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
        salvar_dados_nuvem()
        st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
        carregar_dados_sessao()
        st.rerun()

    r_sel = st.number_input("Renda:", value=st.session_state.renda, step=100.0)
    if r_sel != st.session_state.renda:
        st.session_state.renda = r_sel; salvar_dados_nuvem()

    st.divider(); st.subheader("🛠️ Gerenciar Guias")
    ng = st.text_input("Nova Guia:")
    if st.button("➕ Criar"):
        if ng and ng not in st.session_state.guias_extras:
            st.session_state.guias_extras.append(ng)
            st.session_state[f"dados_{ng}"] = pd.DataFrame(columns=["Descrição", "Valor Parcela (R$)", "Mês Início (1-12)", "Ano Início", "Qtd Parcelas"])
            salvar_dados_nuvem(); st.rerun()

    if st.session_state.guias_extras:
        gf = st.selectbox("Guia Ativa:", st.session_state.guias_extras)
        nn = st.text_input("Renomear para:")
        if st.button("📝 Renomear"):
            if nn and nn not in st.session_state.guias_extras:
                idx = st.session_state.guias_extras.index(gf)
                st.session_state.guias_extras[idx] = nn
                st.session_state[f"dados_{nn}"] = st.session_state[f"dados_{gf}"]
                del st.session_state[f"dados_{gf}"]; salvar_dados_nuvem(); st.rerun()

        if st.button("🗑️ Apagar"):
            st.session_state.guias_extras.remove(gf)
            if f"dados_{gf}" in st.session_state: del st.session_state[f"dados_{gf}"]
            salvar_dados_nuvem(); st.rerun()

# --- MAIN ---
mes_n, ano_r = MESES[st.session_state.mes_atual], st.session_state.ano_atual

# AGORA O TOTAL FIXO SOMA TUDO, INDEPENDENTE DO "PAGO"
t_fix = float(st.session_state.gastos_fixos["Valor (R$)"].sum()) if not st.session_state.gastos_fixos.empty else 0.0
t_cas = float(st.session_state.gastos_casuais["Valor (R$)"].sum()) if not st.session_state.gastos_casuais.empty else 0.0
t_gui = sum([calc_parc(st.session_state.get(f"dados_{g}"), mes_n, ano_r)[1] for g in st.session_state.guias_extras])

st.title(f"💰 {st.session_state.mes_atual} / {ano_r}")
sel = st.selectbox("Ir para:", ["Resumo Geral", "Gastos Fixos", "Dia a Dia"] + st.session_state.guias_extras)
st.divider()

if sel == "Resumo Geral":
    gt = t_fix + t_cas + t_gui
    sobra = st.session_state.renda - gt
    # Gráfico agora mostra Gastos Fixos como um todo
    fig = px.pie(pd.DataFrame({"C": ["Gastos Fixos", "Dia a Dia", "Guias Extras", "Sobra"], "V": [t_fix, t_cas, t_gui, max(0, sobra)]}), values='V', names='C', hole=.4)
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300); st.plotly_chart(fig, use_container_width=True)
    c1, c2 = st.columns(2); c1.metric("Gasto Total", f"R$ {gt:,.2f}")
    sobra_perc = (sobra / st.session_state.renda) * 100 if st.session_state.renda > 0 else 0
    st.metric("Sobra Real", f"R$ {sobra:,.2f}", delta=f"{sobra_perc:.1f}% da renda", delta_color="normal" if sobra >= 0 else "inverse")

elif sel == "Gastos Fixos":
    ct, cb = st.columns([3, 1]); ct.subheader("📌 Contas Fixas")
    if cb.button("🔄 Importar"): 
        carregar_dados_sessao(importar_do_anterior=True); salvar_dados_nuvem(); st.rerun()

    # Métrica simplificada para mostrar apenas o total da aba
    st.metric("Total de Gastos Fixos", f"R$ {t_fix:,.2f}")

    df_f = st.session_state.gastos_fixos if not st.session_state.gastos_fixos.empty else pd.DataFrame(columns=["Descrição", "Valor (R$)", "Pago"])
    ef = st.data_editor(df_f, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"), "Pago": st.column_config.CheckboxColumn()})
    if not ef.equals(st.session_state.gastos_fixos): st.session_state.gastos_fixos = ef; salvar_dados_nuvem()

elif sel == "Dia a Dia":
    st.subheader("🛍️ Compras Diárias")
    st.metric("Total de Gastos Casuais", f"R$ {t_cas:,.2f}")
    df_c = st.session_state.gastos_casuais if not st.session_state.gastos_casuais.empty else pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])
    ec = st.data_editor(df_c, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY"), "Categoria": st.column_config.SelectboxColumn(options=CATEGORIAS), "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f")})
    if not ec.equals(st.session_state.gastos_casuais): st.session_state.gastos_casuais = ec; salvar_dados_nuvem()
    if not st.session_state.gastos_casuais.empty:
        st.divider(); st.dataframe(st.session_state.gastos_casuais.groupby("Categoria")["Valor (R$)"].sum().reset_index(), use_container_width=True, hide_index=True)

else:
    dr, vt = calc_parc(st.session_state.get(f"dados_{sel}"), mes_n, ano_r)
    st.subheader(f"Total no Mês: R$ {vt:,.2f}")
    if not dr.empty: st.dataframe(dr, use_container_width=True, hide_index=True)
    st.divider(); st.subheader("Base de Compras")
    de = st.session_state[f"dados_{sel}"] if not st.session_state[f"dados_{sel}"].empty else pd.DataFrame(columns=["Descrição", "Valor Parcela (R$)", "Mês Início (1-12)", "Ano Início", "Qtd Parcelas"])
    eg = st.data_editor(de, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Valor Parcela (R$)": st.column_config.NumberColumn(format="R$ %.2f")})
    if not eg.equals(st.session_state[f"dados_{sel}"]): st.session_state[f"dados_{sel}"] = eg; salvar_dados_nuvem(); st.rerun()
