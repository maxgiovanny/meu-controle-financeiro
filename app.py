import streamlit as st
import pandas as pd
import json
import gspread
import plotly.express as px
from datetime import datetime
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered")

MESES = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, 
    "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8, 
    "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
}

CATEGORIAS = ["Alimentação", "Transporte", "Lazer", "Saúde", "Casa", "Trabalho", "Outros"]

# --- LIGAÇÃO À GOOGLE SHEET ---
@st.cache_resource
def ligar_google_sheets():
    creds_dict = json.loads(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["url_planilha"]).sheet1

try:
    worksheet = ligar_google_sheets()
except Exception:
    st.error("Erro ao ligar ao Google Sheets. Verifique os Secrets.")
    st.stop()

# --- FUNÇÕES DE GUARDAR E CARREGAR ---
def carregar_dados_nuvem():
    try:
        valor = worksheet.acell('A1').value
        if valor: return json.loads(valor)
    except: pass
    return None

def salvar_dados_nuvem():
    casuais_dict = st.session_state.gastos_casuais.copy()
    if "Data" in casuais_dict.columns:
        casuais_dict["Data"] = casuais_dict["Data"].astype(str)
    
    dados_completos = {
        "ano_atual": st.session_state.ano_atual,
        "mes_atual": st.session_state.mes_atual,
        "renda": st.session_state.renda,
        "guias_extras": st.session_state.guias_extras,
        "gastos_fixos": st.session_state.gastos_fixos.to_dict("records"),
        "gastos_casuais": casuais_dict.to_dict("records")
    }
    for guia in st.session_state.guias_extras:
        if f"dados_{guia}" in st.session_state:
            dados_completos[f"dados_{guia}"] = st.session_state[f"dados_{guia}"].to_dict("records")
    
    json_str = json.dumps(dados_completos)
    worksheet.update(values=[[json_str]], range_name='A1')
    st.toast("💾 Dados salvos!", icon="✅")

# --- INICIALIZAÇÃO DA MEMÓRIA ---
if "dados_carregados" not in st.session_state:
    dados_nuvem = carregar_dados_nuvem()
    if dados_nuvem:
        st.session_state.ano_atual = dados_nuvem.get("ano_atual", 2026)
        st.session_state.mes_atual = dados_nuvem.get("mes_atual", "Maio")
        st.session_state.renda = dados_nuvem.get("renda", 10000.0)
        st.session_state.guias_extras = dados_nuvem.get("guias_extras", [])
        st.session_state.gastos_fixos = pd.DataFrame(dados_nuvem.get("gastos_fixos", []))
        df_casuais = pd.DataFrame(dados_nuvem.get("gastos_casuais", []))
        
        if not df_casuais.empty:
            if "Data" in df_casuais.columns: df_casuais["Data"] = pd.to_datetime(df_casuais["Data"]).dt.date
            if "Categoria" not in df_casuais.columns: df_casuais["Categoria"] = "Outros"
        else:
            df_casuais = pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])
        st.session_state.gastos_casuais = df_casuais
        
        for guia in st.session_state.guias_extras:
            st.session_state[f"dados_{guia}"] = pd.DataFrame(dados_nuvem.get(f"dados_{guia}", []))
    else:
        st.session_state.ano_atual, st.session_state.mes_atual, st.session_state.renda = 2026, "Maio", 10000.0
        st.session_state.guias_extras, st.session_state.gastos_fixos = [], pd.DataFrame(columns=["Descrição", "Valor (R$)", "Pago"])
        st.session_state.gastos_casuais = pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])
    st.session_state.dados_carregados = True

# --- LOGICA DE CÁLCULO ---
def calcular_parcelas_v2(df, mes_alvo, ano_alvo):
    ativas, total_valor = [], 0.0
    if df.empty: return pd.DataFrame(columns=["Descrição", "Parcela", "Valor (R$)"]), 0.0
    for _, row in df.iterrows():
        try:
            desc = row.get("Descrição")
            if not desc or pd.isna(row.get("Valor Parcela (R$)")) or row.get("Valor Parcela (R$)") == 0: continue
            m_ini, a_ini = int(row["Mês Início (1-12)"]), int(row["Ano Início"])
            qtd, valor = int(row["Qtd Parcelas"]), float(row["Valor Parcela (R$)"])
            alvo_abs, ini_abs = ano_alvo * 12 + mes_alvo, a_ini * 12 + m_ini
            fim_abs = ini_abs + qtd - 1
            if ini_abs <= alvo_abs <= fim_abs:
                parc_atual = alvo_abs - ini_abs + 1
                ativas.append({"Descrição": desc, "Parcela": f"{parc_atual}/{qtd}", "Valor (R$)": valor})
                total_valor += valor
        except: continue
    return pd.DataFrame(ativas), total_valor

# --- MENU LATERAL ---
with st.sidebar:
    st.header("⚙️ Ajustes")
    novo_mes = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
    novo_ano = st.number_input("Ano:", min_value=2024, max_value=2030, value=st.session_state.ano_atual)
    nova_renda = st.number_input("Renda (R$):", value=st.session_state.renda, step=100.0)
    
    if novo_mes != st.session_state.mes_atual or novo_ano != st.session_state.ano_atual or nova_renda != st.session_state.renda:
        st.session_state.mes_atual, st.session_state.ano_atual, st.session_state.renda = novo_mes, novo_ano, nova_renda
        salvar_dados_nuvem()
        st.rerun()
        
    st.divider()
    n_guia = st.text_input("Nova Guia:")
    if st.button("➕ Criar"):
        if n_guia and n_guia not in st.session_state.guias_extras:
            st.session_state.guias_extras.append(n_guia)
            st.session_state[f"dados_{n_guia}"] = pd.DataFrame(columns=["Descrição", "Mês Início (1-12)", "Ano Início", "Qtd Parcelas", "Valor Parcela (R$)"])
            salvar_dados_nuvem()
            st.rerun()
    if st.session_state.guias_extras:
        g_rem = st.selectbox("Apagar Guia:", st.session_state.guias_extras)
        if st.button("🗑️ Apagar"):
            st.session_state.guias_extras.remove(g_rem)
            salvar_dados_nuvem()
            st.rerun()

# --- INTERFACE ---
mes_num, ano_ref = MESES[st.session_state.mes_atual], st.session_state.ano_atual
t_fixos = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
t_casuais = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
t_guias = sum([calcular_parcelas_v2(st.session_state[f"dados_{g}"], mes_num, ano_ref)[1] for g in st.session_state.guias_extras])

st.title(f"💰 {st.session_state.mes_atual} / {ano_ref}")
sel = st.selectbox("Navegar para:", ["Resumo Geral", "Custos Fixos", "Dia a Dia"] + st.session_state.guias_extras)
st.divider()

if sel == "Resumo Geral":
    gasto_total = t_fixos + t_casuais + t_guias
    sobra = max(0.0, st.session_state.renda - gasto_total)
    
    df_grafico = pd.DataFrame({
        "Categoria": ["Fixos", "Dia a Dia", "Guias/Cartões", "Sobra"],
        "Valor": [t_fixos, t_casuais, t_guias, sobra]
    })
    fig = px.pie(df_grafico, values='Valor', names='Categoria', hole=.4, 
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    c1.metric("Total Gasto", f"R$ {gasto_total:,.2f}")
    c2.metric("Sobra Real", f"R$ {sobra:,.2f}")
    st.progress(min(int((gasto_total/st.session_state.renda)*100), 100) if st.session_state.renda > 0 else 0)

elif sel == "Custos Fixos":
    st.header("Custos Fixos")
    ed_f = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)
    if not ed_f.equals(st.session_state.gastos_fixos):
        st.session_state.gastos_fixos = ed_f
        salvar_dados_nuvem()

elif sel == "Dia a Dia":
    st.header("Gastos Diários")
    ed_c = st.data_editor(
        st.session_state.gastos_casuais, 
        num_rows="dynamic", 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", default=datetime.now().date()),
            "Categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS, default="Outros"),
            "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="%.2f")
        }
    )
    if not ed_c.equals(st.session_state.gastos_casuais):
        st.session_state.gastos_casuais = ed_c
        salvar_dados_nuvem()
    
    if not st.session_state.gastos_casuais.empty:
        st.divider()
        st.subheader("📊 Por Categoria")
        resumo_cat = st.session_state.gastos_casuais.groupby("Categoria")["Valor (R$)"].sum().reset_index()
        st.dataframe(resumo_cat, use_container_width=True, hide_index=True)

else:
    guia_sel = sel
    df_resumo, v_total = calcular_parcelas_v2(st.session_state[f"dados_{guia_sel}"], mes_num, ano_ref)
    st.subheader(f"Gastos de {st.session_state.mes_atual}: R$ {v_total:,.2f}")
    if not df_resumo.empty:
        st.dataframe(df_resumo, use_container_width=True, hide_index=True)
    else:
        st.info("Sem gastos para este mês.")
    st.divider()
    st.subheader("Base Histórica")
    ed_g = st.data_editor(st.session_state[f"dados_{guia_sel}"], num_rows="dynamic", use_container_width=True, hide_index=True, key=f"editor_{guia_sel}")
    if not ed_g.equals(st.session_state[f"dados_{guia_sel}"]):
        st.session_state[f"dados_{guia_sel}"] = ed_g
        salvar_dados_nuvem()
        st.rerun()
