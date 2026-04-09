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
    st.error("Erro de conexão com o Google Sheets.")
    st.stop()

# --- FUNÇÕES DE SEGURANÇA ---
def criar_ponto_restauracao():
    backup = {
        "renda": st.session_state.renda,
        "guias_extras": list(st.session_state.guias_extras),
        "gastos_fixos": st.session_state.gastos_fixos.copy(),
        "gastos_casuais": st.session_state.gastos_casuais.copy(),
        "historico_fixos": json.loads(json.dumps(st.session_state.historico_fixos)),
        "historico_casuais": json.loads(json.dumps(st.session_state.historico_casuais))
    }
    for guia in st.session_state.guias_extras:
        if f"dados_{guia}" in st.session_state:
            backup[f"dados_{guia}"] = st.session_state[f"dados_{guia}"].copy()
    st.session_state.backup_anterior = backup

def salvar_dados_nuvem():
    mes_ano_chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
    
    casuais_save = st.session_state.gastos_casuais.copy()
    if "Data" in casuais_save.columns:
        casuais_save["Data"] = casuais_save["Data"].astype(str)
    
    st.session_state.historico_fixos[mes_ano_chave] = st.session_state.gastos_fixos.to_dict("records")
    st.session_state.historico_casuais[mes_ano_chave] = casuais_save.to_dict("records")

    dados_completos = {
        "renda": st.session_state.renda,
        "guias_extras": st.session_state.guias_extras,
        "historico_fixos": st.session_state.historico_fixos,
        "historico_casuais": st.session_state.historico_casuais
    }
    
    for guia in st.session_state.guias_extras:
        if f"dados_{guia}" in st.session_state:
            dados_completos[f"dados_{guia}"] = st.session_state[f"dados_{guia}"].to_dict("records")
    
    json_str = json.dumps(dados_completos)
    worksheet.update(values=[[json_str]], range_name='A1')
    st.toast("💾 Sincronizado!", icon="✅")

def carregar_dados_sessao():
    mes_ano_chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
    
    # --- CORREÇÃO GASTOS FIXOS ---
    if mes_ano_chave in st.session_state.historico_fixos:
        st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos[mes_ano_chave])
    else:
        if st.session_state.historico_fixos:
            ult_chave = list(st.session_state.historico_fixos.keys())[-1]
            df_base = pd.DataFrame(st.session_state.historico_fixos[ult_chave])
            df_base["Pago"] = False
            st.session_state.gastos_fixos = df_base
        else:
            # Garante que as colunas existam mesmo se estiver vazio
            st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição", "Valor (R$)", "Pago"])

    # --- CORREÇÃO DIA A DIA ---
    if mes_ano_chave in st.session_state.historico_casuais:
        df_c = pd.DataFrame(st.session_state.historico_casuais[mes_ano_chave])
        if not df_c.empty:
            df_c["Data"] = pd.to_datetime(df_c.get("Data", datetime.now().date())).dt.date
            if "Categoria" not in df_c.columns: df_c["Categoria"] = "Outros"
        st.session_state.gastos_casuais = df_c
    else:
        # Garante o "esqueleto" da tabela para permitir adicionar linhas
        st.session_state.gastos_casuais = pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])

# --- INICIALIZAÇÃO ---
if "dados_carregados" not in st.session_state:
    val = worksheet.acell('A1').value
    d = json.loads(val) if val else {}
    
    st.session_state.ano_atual = 2026
    st.session_state.mes_atual = "Abril"
    st.session_state.renda = d.get("renda", 10000.0)
    st.session_state.guias_extras = d.get("guias_extras", [])
    st.session_state.historico_fixos = d.get("historico_fixos", {})
    st.session_state.historico_casuais = d.get("historico_casuais", {})
    st.session_state.backup_anterior = None
    
    for g in st.session_state.guias_extras:
        st.session_state[f"dados_{g}"] = pd.DataFrame(d.get(f"dados_{g}", []))
    
    carregar_dados_sessao()
    st.session_state.dados_carregados = True

# --- CÁLCULO PARCELAS ---
def calcular_parcelas_v2(df, mes, ano):
    ativas, total = [], 0.0
    if df is None or df.empty: return pd.DataFrame(columns=["Descrição", "Parcela", "Valor (R$)"]), 0.0
    for _, row in df.iterrows():
        try:
            desc = row.get("Descrição")
            if not desc or pd.isna(row.get("Valor Parcela (R$)")): continue
            m_i, a_i = int(row["Mês Início (1-12)"]), int(row["Ano Início"])
            qtd, val = int(row["Qtd Parcelas"]), float(row["Valor Parcela (R$)"])
            alvo, ini = ano * 12 + mes, a_i * 12 + m_i
            fim = ini + qtd - 1
            if ini <= alvo <= fim:
                parc = alvo - ini + 1
                ativas.append({"Descrição": desc, "Parcela": f"{parc}/{qtd}", "Valor (R$)": val})
                total += val
        except: continue
    return pd.DataFrame(ativas), total

# --- MENU LATERAL ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    if st.session_state.backup_anterior:
        if st.button("🔙 Desfazer Última Ação", use_container_width=True, type="primary"):
            b = st.session_state.backup_anterior
            st.session_state.renda, st.session_state.guias_extras = b["renda"], b["guias_extras"]
            st.session_state.gastos_fixos, st.session_state.gastos_casuais = b["gastos_fixos"], b["gastos_casuais"]
            st.session_state.historico_fixos, st.session_state.historico_casuais = b["historico_fixos"], b["historico_casuais"]
            st.session_state.backup_anterior = None
            salvar_dados_nuvem()
            st.rerun()

    m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
    a_sel = st.number_input("Ano:", min_value=2024, max_value=2030, value=st.session_state.ano_atual)
    if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
        salvar_dados_nuvem()
        st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
        carregar_dados_sessao()
        st.rerun()

    r_sel = st.number_input("Renda (R$):", value=st.session_state.renda, step=100.0)
    if r_sel != st.session_state.renda:
        st.session_state.renda = r_sel
        salvar_dados_nuvem()

    st.divider()
    n_g = st.text_input("Criar Nova Guia:")
    if st.button("➕ Adicionar"):
        if n_g and n_g not in st.session_state.guias_extras:
            criar_ponto_restauracao()
            st.session_state.guias_extras.append(n_g)
            st.session_state[f"dados_{n_g}"] = pd.DataFrame(columns=["Descrição", "Mês Início (1-12)", "Ano Início", "Qtd Parcelas", "Valor Parcela (R$)"])
            salvar_dados_nuvem()
            st.rerun()

# --- INTERFACE ---
mes_n, ano_r = MESES[st.session_state.mes_atual], st.session_state.ano_atual
t_fix = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
t_cas = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
t_gui = sum([calcular_parcelas_v2(st.session_state.get(f"dados_{g}"), mes_n, ano_r)[1] for g in st.session_state.guias_extras])

st.title(f"💰 {st.session_state.mes_atual} / {ano_r}")
sel = st.selectbox("Ir para:", ["Resumo Geral", "Gastos Fixos", "Dia a Dia"] + st.session_state.guias_extras)
st.divider()

if sel == "Resumo Geral":
    g_total = t_fix + t_cas + t_gui
    sobra = max(0.0, st.session_state.renda - g_total)
    df_pie = pd.DataFrame({"Cat": ["Fixos", "Dia a Dia", "Guias", "Sobra"], "Val": [t_fix, t_cas, t_gui, sobra]})
    fig = px.pie(df_pie, values='Val', names='Cat', hole=.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
    st.plotly_chart(fig, use_container_width=True)
    c1, c2 = st.columns(2)
    c1.metric("Gasto Total", f"R$ {g_total:,.2f}")
    c2.metric("Sobra", f"R$ {sobra:,.2f}")

elif sel == "Gastos Fixos":
    st.subheader("📌 Contas do Mês")
    # Correção: Adição de linha se estiver vazio para destravar o celular
    if st.session_state.gastos_fixos.empty:
        st.session_state.gastos_fixos = pd.DataFrame([{"Descrição": "", "Valor (R$)": 0.0, "Pago": False}])
    
    ed_f = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)
    if not ed_f.equals(st.session_state.gastos_fixos):
        criar_ponto_restauracao()
        st.session_state.gastos_fixos = ed_f
        salvar_dados_nuvem()

elif sel == "Dia a Dia":
    st.subheader("🛍️ Compras Diárias")
    # Correção: Adição de linha se estiver vazio para destravar o celular
    if st.session_state.gastos_casuais.empty:
        st.session_state.gastos_casuais = pd.DataFrame([{"Data": datetime.now().date(), "Categoria": "Outros", "Descrição": "", "Valor (R$)": 0.0}])
    
    ed_c = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", default=datetime.now().date()),
            "Categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS, default="Outros"),
            "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="%.2f")
        })
    if not ed_c.equals(st.session_state.gastos_casuais):
        criar_ponto_restauracao()
        st.session_state.gastos_casuais = ed_c
        salvar_dados_nuvem()
    if not st.session_state.gastos_casuais.empty:
        st.divider()
        st.write("**Total por Categoria:**")
        st.dataframe(st.session_state.gastos_casuais.groupby("Categoria")["Valor (R$)"].sum().reset_index(), use_container_width=True, hide_index=True)

else:
    df_res, v_tot = calcular_parcelas_v2(st.session_state.get(f"dados_{sel}"), mes_n, ano_r)
    st.subheader(f"Total no Mês: R$ {v_tot:,.2f}")
    if not df_res.empty: st.dataframe(df_res, use_container_width=True, hide_index=True)
    st.divider()
    ed_g = st.data_editor(st.session_state[f"dados_{sel}"], num_rows="dynamic", use_container_width=True, hide_index=True, key=f"ed_{sel}")
    if not ed_g.equals(st.session_state[f"dados_{sel}"]):
        criar_ponto_restauracao()
        st.session_state[f"dados_{sel}"] = ed_g
        salvar_dados_nuvem()
        st.rerun()
