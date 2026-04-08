import streamlit as st
import pandas as pd
import json
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Controle Financeiro", page_icon="📈", layout="centered")

MESES = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, 
    "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8, 
    "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
}

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
except Exception as e:
    st.error("Erro ao ligar ao Google Sheets. Verifique os Secrets.")
    st.stop()

# --- FUNÇÕES DE GUARDAR E CARREGAR ---
def carregar_dados_nuvem():
    try:
        valor = worksheet.acell('A1').value
        if valor:
            return json.loads(valor)
    except:
        pass
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
    st.toast("💾 Dados guardados na nuvem!", icon="✅")

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
        if not df_casuais.empty and "Data" in df_casuais.columns:
            df_casuais["Data"] = pd.to_datetime(df_casuais["Data"]).dt.date
        else:
            df_casuais = pd.DataFrame(columns=["Data", "Descrição", "Valor (R$)"])
        st.session_state.gastos_casuais = df_casuais
        
        for guia in st.session_state.guias_extras:
            st.session_state[f"dados_{guia}"] = pd.DataFrame(dados_nuvem.get(f"dados_{guia}", []))
    else:
        st.session_state.ano_atual = 2026
        st.session_state.mes_atual = "Maio"
        st.session_state.renda = 10000.00
        st.session_state.guias_extras = ["💳 Digio", "💳 Itaú", "💳 Inter", "💳 Mercado Pago", "💳 Will"]
        st.session_state.gastos_fixos = pd.DataFrame({
            "Descrição": ["Consórcio", "Plano de Saúde", "Combustível", "Linha Claro", "Linha Mútua", "Energia", "Mário Felipe", "Pedro"],
            "Valor (R$)": [1350.00, 355.23, 1200.00, 90.00, 50.00, 70.00, 100.00, 80.00],
            "Pago": [False] * 8
        })
        st.session_state.gastos_casuais = pd.DataFrame([{"Data": datetime.now().date(), "Descrição": "Supermercado", "Valor (R$)": 600.00}])
        for guia in st.session_state.guias_extras:
             st.session_state[f"dados_{guia}"] = pd.DataFrame({"Descrição": [""], "Mês Início (1-12)": [5], "Ano Início": [2026], "Qtd Parcelas": [1], "Valor Parcela (R$)": [0.00]})
    st.session_state.dados_carregados = True

# --- CÁLCULO DE PARCELAS ---
def calcular_parcelas(df, mes_alvo, ano_alvo):
    ativas, total_valor = [], 0.0
    for index, row in df.iterrows():
        try:
            if not row.get("Descrição") or pd.isna(row.get("Valor Parcela (R$)")) or row.get("Valor Parcela (R$)") == 0: continue
            mes_inicio, ano_inicio = int(row["Mês Início (1-12)"]), int(row["Ano Início"])
            qtd_parcelas, valor = int(row["Qtd Parcelas"]), float(row["Valor Parcela (R$)"])
            data_alvo_val, data_inicio_val = ano_alvo * 12 + mes_alvo, ano_inicio * 12 + mes_inicio
            data_fim_val = data_inicio_val + qtd_parcelas - 1
            if data_inicio_val <= data_alvo_val <= data_fim_val:
                parcela_atual = data_alvo_val - data_inicio_val + 1
                ativas.append({"Descrição": row["Descrição"], "Parcela": f"{parcela_atual}/{qtd_parcelas}", "Valor (R$)": valor})
                total_valor += valor
        except: continue
    return pd.DataFrame(ativas), total_valor

# --- MENU LATERAL ---
with st.sidebar:
    st.header("⚙️ Configurações")
    novo_mes = st.selectbox("Mês de Referência:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
    novo_ano = st.number_input("Ano de Referência:", min_value=2020, max_value=2050, value=st.session_state.ano_atual, step=1)
    nova_renda = st.number_input("Renda Mensal (R$):", value=st.session_state.renda, step=100.00)
    
    if novo_mes != st.session_state.mes_atual or novo_ano != st.session_state.ano_atual or nova_renda != st.session_state.renda:
        st.session_state.mes_atual, st.session_state.ano_atual, st.session_state.renda = novo_mes, novo_ano, nova_renda
        salvar_dados_nuvem()
        st.rerun()
    
    st.divider()
    st.subheader("Gerenciar Guias")
    nova_guia = st.text_input("Nome da nova guia:")
    if st.button("➕ Criar Guia"):
        if nova_guia and nova_guia not in st.session_state.guias_extras:
            st.session_state.guias_extras.append(nova_guia)
            st.session_state[f"dados_{nova_guia}"] = pd.DataFrame({"Descrição": [""], "Mês Início (1-12)": [5], "Ano Início": [2026], "Qtd Parcelas": [1], "Valor Parcela (R$)": [0.00]})
            salvar_dados_nuvem()
            st.rerun()

    if len(st.session_state.guias_extras) > 0:
        guia_a_remover = st.selectbox("Selecione para apagar:", st.session_state.guias_extras)
        if st.button("🗑️ Apagar Guia"):
            st.session_state.guias_extras.remove(guia_a_remover)
            if f"dados_{guia_a_remover}" in st.session_state: del st.session_state[f"dados_{guia_a_remover}"]
            salvar_dados_nuvem()
            st.rerun()

# --- CÁLCULOS GLOBAIS ---
mes_atual_num, ano_atual = MESES[st.session_state.mes_atual], st.session_state.ano_atual
total_fixos = st.session_state.gastos_fixos["Valor (R$)"].sum()
total_casuais = st.session_state.gastos_casuais["Valor (R$)"].sum()
total_todas_guias = sum([calcular_parcelas(st.session_state[f"dados_{g}"], mes_atual_num, ano_atual)[1] for g in st.session_state.guias_extras])

# --- INTERFACE COM SELETOR ÚNICO ---
st.title(f"💰 {st.session_state.mes_atual} / {st.session_state.ano_atual}")

# Otimização para Celular: Caixa de seleção em vez de abas
opcoes_menu = ["Painel Geral", "Gastos Fixos", "Dia a Dia"] + st.session_state.guias_extras
escolha = st.selectbox("Ir para:", opcoes_menu)

st.divider()

if escolha == "Painel Geral":
    total_gasto = total_fixos + total_casuais + total_todas_guias
    saldo_livre = st.session_state.renda - total_gasto
    st.metric("Saldo Livre", f"R$ {saldo_livre:,.2f}")
    st.progress(min(int((total_gasto/st.session_state.renda)*100), 100) if st.session_state.renda > 0 else 0)
    st.write(f"Fixos: R$ {total_fixos:,.2f} | Dia a Dia: R$ {total_casuais:,.2f} | Guias: R$ {total_todas_guias:,.2f}")

elif escolha == "Gastos Fixos":
    st.header("Gastos Fixos")
    edit_fixos = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)
    if not edit_fixos.equals(st.session_state.gastos_fixos):
        st.session_state.gastos_fixos = edit_fixos
        salvar_dados_nuvem()

elif escolha == "Dia a Dia":
    st.header("Dia a Dia")
    edit_casuais = st.data_editor(
        st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", default=datetime.now().date())}
    )
    if not edit_casuais.equals(st.session_state.gastos_casuais):
        st.session_state.gastos_casuais = edit_casuais
        salvar_dados_nuvem()

else:
    # Caso a escolha seja uma das Guias Extras
    guia = escolha
    df_ativas, total_guia = calcular_parcelas(st.session_state[f"dados_{guia}"], mes_atual_num, ano_atual)
    st.subheader(f"📅 Ativos no Mês: R$ {total_guia:,.2f}")
    if not df_ativas.empty: st.dataframe(df_ativas, use_container_width=True, hide_index=True)
    st.divider()
    st.subheader("📝 Base de Dados")
    edit_guia = st.data_editor(st.session_state[f"dados_{guia}"], num_rows="dynamic", use_container_width=True, hide_index=True, key=f"ed_{guia}")
    if not edit_guia.equals(st.session_state[f"dados_{guia}"]):
        st.session_state[f"dados_{guia}"] = edit_guia
        salvar_dados_nuvem()
        st.rerun()
