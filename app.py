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
    st.error("Erro ao ligar ao Google Sheets.")
    st.stop()

# --- FUNÇÕES DE BACKUP E SALVAMENTO ---
def salvar_dados_nuvem():
    # Preparamos os dados mensais para salvar
    mes_ano_chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
    
    # Tratamento de data para gastos casuais
    casuais_dict = st.session_state.gastos_casuais.copy()
    if "Data" in casuais_dict.columns:
        casuais_dict["Data"] = casuais_dict["Data"].astype(str)
    
    # Estrutura do JSON
    dados_completos = {
        "renda": st.session_state.renda,
        "guias_extras": st.session_state.guias_extras,
        "historico_fixos": st.session_state.historico_fixos, # Aqui moram os meses independentes
        "historico_casuais": st.session_state.historico_casuais
    }
    
    # Salva o estado ATUAL do mês selecionado nos históricos
    dados_completos["historico_fixos"][mes_ano_chave] = st.session_state.gastos_fixos.to_dict("records")
    dados_completos["historico_casuais"][mes_ano_chave] = casuais_dict.to_dict("records")

    for guia in st.session_state.guias_extras:
        if f"dados_{guia}" in st.session_state:
            dados_completos[f"dados_{guia}"] = st.session_state[f"dados_{guia}"].to_dict("records")
    
    json_str = json.dumps(dados_completos)
    worksheet.update(values=[[json_str]], range_name='A1')
    st.toast("💾 Sincronizado!", icon="✅")

def carregar_dados_sessao():
    mes_ano_chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
    
    # 1. Carregar Gastos Fixos do Mês
    if mes_ano_chave in st.session_state.historico_fixos:
        st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos[mes_ano_chave])
    else:
        # Se é um mês novo, pegamos a lista do mês anterior (se existir) mas resetamos o "Pago"
        if st.session_state.historico_fixos:
            ultima_lista = list(st.session_state.historico_fixos.values())[-1]
            df_novo = pd.DataFrame(ultima_lista)
            df_novo["Pago"] = False # Reseta o check
            st.session_state.gastos_fixos = df_novo
        else:
            st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição", "Valor (R$)", "Pago"])

    # 2. Carregar Gastos Casuais do Mês
    if mes_ano_chave in st.session_state.historico_casuais:
        df_c = pd.DataFrame(st.session_state.historico_casuais[mes_ano_chave])
        df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
        st.session_state.gastos_casuais = df_c
    else:
        st.session_state.gastos_casuais = pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])

# --- INICIALIZAÇÃO ---
if "dados_carregados" not in st.session_state:
    valor_nuvem = worksheet.acell('A1').value
    dados = json.loads(valor_nuvem) if valor_nuvem else {}
    
    st.session_state.ano_atual = 2026
    st.session_state.mes_atual = "Abril"
    st.session_state.renda = dados.get("renda", 10000.0)
    st.session_state.guias_extras = dados.get("guias_extras", [])
    st.session_state.historico_fixos = dados.get("historico_fixos", {})
    st.session_state.historico_casuais = dados.get("historico_casuais", {})
    
    # Carrega as guias extras de cartões
    for guia in st.session_state.guias_extras:
        st.session_state[f"dados_{guia}"] = pd.DataFrame(dados.get(f"dados_{guia}", []))
    
    carregar_dados_sessao()
    st.session_state.dados_carregados = True

# --- LÓGICA DE CÁLCULO ---
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
    
    if novo_mes != st.session_state.mes_atual or novo_ano != st.session_state.ano_atual:
        # Antes de mudar, salva o que está na tela
        salvar_dados_nuvem()
        st.session_state.mes_atual, st.session_state.ano_atual = novo_mes, novo_ano
        carregar_dados_sessao()
        st.rerun()

    nova_renda = st.number_input("Renda (R$):", value=st.session_state.renda, step=100.0)
    if nova_renda != st.session_state.renda:
        st.session_state.renda = nova_renda
        salvar_dados_nuvem()

    st.divider()
    n_guia = st.text_input("Nova Guia:")
    if st.button("➕ Criar"):
        if n_guia and n_guia not in st.session_state.guias_extras:
            st.session_state.guias_extras.append(n_guia)
            st.session_state[f"dados_{n_guia}"] = pd.DataFrame(columns=["Descrição", "Mês Início (1-12)", "Ano Início", "Qtd Parcelas", "Valor Parcela (R$)"])
            salvar_dados_nuvem()
            st.rerun()

# --- INTERFACE ---
mes_num, ano_ref = MESES[st.session_state.mes_atual], st.session_state.ano_atual
t_fixos = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
t_casuais = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
t_guias = sum([calcular_parcelas_v2(st.session_state[f"dados_{g}"], mes_num, ano_ref)[1] for g in st.session_state.guias_extras])

st.title(f"💰 {st.session_state.mes_atual} / {ano_ref}")
sel = st.selectbox("Ir para:", ["Resumo", "Fixos", "Dia a Dia"] + st.session_state.guias_extras)

if sel == "Resumo":
    gasto_total = t_fixos + t_casuais + t_guias
    sobra = max(0.0, st.session_state.renda - gasto_total)
    df_grafico = pd.DataFrame({"Cat": ["Fixos", "Dia a Dia", "Guias", "Sobra"], "Val": [t_fixos, t_casuais, t_guias, sobra]})
    fig = px.pie(df_grafico, values='Val', names='Cat', hole=.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
    st.plotly_chart(fig, use_container_width=True)
    c1, c2 = st.columns(2)
    c1.metric("Gasto Total", f"R$ {gasto_total:,.2f}")
    c2.metric("Sobra", f"R$ {sobra:,.2f}")

elif sel == "Fixos":
    st.header("Gastos Fixos")
    ed_f = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)
    if not ed_f.equals(st.session_state.gastos_fixos):
        st.session_state.gastos_fixos = ed_f
        salvar_dados_nuvem()

elif sel == "Dia a Dia":
    st.header("Gastos Diários")
    ed_c = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", default=datetime.now().date()),
            "Categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS, default="Outros"),
            "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="%.2f")
        })
    if not ed_c.equals(st.session_state.gastos_casuais):
        st.session_state.gastos_casuais = ed_c
        salvar_dados_nuvem()

else:
    df_res, v_tot = calcular_parcelas_v2(st.session_state[f"dados_{sel}"], mes_num, ano_ref)
    st.subheader(f"Total no Mês: R$ {v_tot:,.2f}")
    if not df_res.empty: st.dataframe(df_res, use_container_width=True, hide_index=True)
    st.divider()
    ed_g = st.data_editor(st.session_state[f"dados_{sel}"], num_rows="dynamic", use_container_width=True, hide_index=True, key=f"ed_{sel}")
    if not ed_g.equals(st.session_state[f"dados_{sel}"]):
        st.session_state[f"dados_{sel}"] = ed_g
        salvar_dados_nuvem()
        st.rerun()
