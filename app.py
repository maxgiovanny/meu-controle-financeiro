import streamlit as st
import pandas as pd
import json
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered")

MESES = {
    "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, 
    "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8, 
    "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
}

# --- LIGAÇÃO À GOOGLE SHEET ---
@st.cache_resource
def ligar_google_sheets():
    # Lê as chaves secretas que guardou no Streamlit
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
        # Lê a célula A1 onde vamos guardar todo o "cérebro" da aplicação
        valor = worksheet.acell('A1').value
        if valor:
            return json.loads(valor)
    except:
        pass
    return None

def salvar_dados_nuvem():
    dados_completos = {
        "ano_atual": st.session_state.ano_atual,
        "mes_atual": st.session_state.mes_atual,
        "renda": st.session_state.renda,
        "guias_extras": st.session_state.guias_extras,
        "gastos_fixos": st.session_state.gastos_fixos.to_dict("records"),
        "gastos_casuais": st.session_state.gastos_casuais.to_dict("records")
    }
    for guia in st.session_state.guias_extras:
        if f"dados_{guia}" in st.session_state:
            dados_completos[f"dados_{guia}"] = st.session_state[f"dados_{guia}"].to_dict("records")
    
    json_str = json.dumps(dados_completos)
    worksheet.update(values=[[json_str]], range_name='A1')
    st.toast("💾 Dados guardados na nuvem com sucesso!", icon="✅")

# --- INICIALIZAÇÃO DA MEMÓRIA ---
if "dados_carregados" not in st.session_state:
    dados_nuvem = carregar_dados_nuvem()
    
    if dados_nuvem: # Se já existir dados no Google Sheets, carrega-os
        st.session_state.ano_atual = dados_nuvem.get("ano_atual", 2026)
        st.session_state.mes_atual = dados_nuvem.get("mes_atual", "Maio")
        st.session_state.renda = dados_nuvem.get("renda", 10000.0)
        st.session_state.guias_extras = dados_nuvem.get("guias_extras", [])
        st.session_state.gastos_fixos = pd.DataFrame(dados_nuvem.get("gastos_fixos", []))
        st.session_state.gastos_casuais = pd.DataFrame(dados_nuvem.get("gastos_casuais", []))
        
        for guia in st.session_state.guias_extras:
            st.session_state[f"dados_{guia}"] = pd.DataFrame(dados_nuvem.get(f"dados_{guia}", []))
    else:
        # Se for a primeira vez (folha em branco), carrega os seus dados iniciais
        st.session_state.ano_atual = 2026
        st.session_state.mes_atual = "Maio"
        st.session_state.renda = 10000.00
        st.session_state.guias_extras = ["💳 Digio", "💳 Itaú", "💳 Inter", "💳 Mercado Pago", "💳 Will", "🚗 Despesas Carro"]

        st.session_state.gastos_fixos = pd.DataFrame({
            "Descrição": ["Consórcio", "Plano de Saúde", "Combustível", "Linha Claro", "Linha Mútua", "Energia", "Mário Felipe", "Pedro"],
            "Valor (R$)": [1350.00, 355.23, 1200.00, 90.00, 50.00, 70.00, 100.00, 80.00],
            "Pago": [False] * 8
        })
        st.session_state.gastos_casuais = pd.DataFrame({"Descrição": ["Supermercado"], "Valor (R$)": [600.00]})

        dados_iniciais = {
            "💳 Digio": pd.DataFrame({"Descrição": ["Academia", "AliExpress (9/10)", "OneDrive"], "Mês Início (1-12)": [5, 9, 5], "Ano Início": [2026, 2025, 2026], "Qtd Parcelas": [12, 10, 12], "Valor Parcela (R$)": [120.00, 10.87, 9.00]}),
            "💳 Itaú": pd.DataFrame({"Descrição": ["Membro", "Paramount", "Netflix", "Amazon", "Google One"], "Mês Início (1-12)": [5, 5, 5, 5, 5], "Ano Início": [2026, 2026, 2026, 2026, 2026], "Qtd Parcelas": [12, 12, 12, 12, 12], "Valor Parcela (R$)": [4.99, 34.90, 54.80, 19.90, 12.50]}),
            "💳 Inter": pd.DataFrame({"Descrição": ["Spotify"], "Mês Início (1-12)": [5], "Ano Início": [2026], "Qtd Parcelas": [12], "Valor Parcela (R$)": [31.90]}),
            "💳 Mercado Pago": pd.DataFrame({"Descrição": ["Perfume", "Cafés", "Cama", "Encosto Carro", "Limpador", "Pressca", "Capa e Correia", "Compra s/ nome", "Pedestal e Suporte", "AliExpress", "Mixer", "Tenis"], "Mês Início (1-12)": [4, 4, 3, 3, 3, 2, 1, 1, 12, 12, 11, 9], "Ano Início": [2026, 2026, 2026, 2026, 2026, 2026, 2026, 2026, 2025, 2025, 2025, 2025], "Qtd Parcelas": [4, 2, 4, 7, 4, 4, 6, 5, 6, 6, 8, 11], "Valor Parcela (R$)": [106.80, 43.43, 268.23, 20.14, 12.23, 31.49, 21.69, 12.63, 21.33, 24.19, 10.09, 25.66]}),
            "💳 Will": pd.DataFrame({"Descrição": ["Air BNB", "Mariana", "Passagens"], "Mês Início (1-12)": [1, 12, 11], "Ano Início": [2026, 2025, 2025], "Qtd Parcelas": [6, 6, 10], "Valor Parcela (R$)": [374.52, 47.00, 187.22]})
        }

        for guia in st.session_state.guias_extras:
            if guia in dados_iniciais:
                st.session_state[f"dados_{guia}"] = dados_iniciais[guia]
            else:
                st.session_state[f"dados_{guia}"] = pd.DataFrame({"Descrição": [""], "Mês Início (1-12)": [5], "Ano Início": [2026], "Qtd Parcelas": [1], "Valor Parcela (R$)": [0.00]})
        
        salvar_dados_nuvem() # Guarda o estado inicial
    
    st.session_state.dados_carregados = True

# --- CÁLCULO DE PARCELAS ---
def calcular_parcelas(df, mes_alvo, ano_alvo):
    ativas = []
    total_valor = 0.0
    for index, row in df.iterrows():
        try:
            if not row.get("Descrição") or pd.isna(row.get("Valor Parcela (R$)")) or row.get("Valor Parcela (R$)") == 0:
                continue
            mes_inicio, ano_inicio = int(row["Mês Início (1-12)"]), int(row["Ano Início"])
            qtd_parcelas, valor = int(row["Qtd Parcelas"]), float(row["Valor Parcela (R$)"])
            data_alvo_val = ano_alvo * 12 + mes_alvo
            data_inicio_val = ano_inicio * 12 + mes_inicio
            data_fim_val = data_inicio_val + qtd_parcelas - 1
            
            if data_inicio_val <= data_alvo_val <= data_fim_val:
                parcela_atual = data_alvo_val - data_inicio_val + 1
                ativas.append({"Descrição": row["Descrição"], "Parcela": f"{parcela_atual}/{qtd_parcelas}", "Valor (R$)": valor})
                total_valor += valor
        except:
            continue
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
    st.subheader("Adicionar Nova Guia")
    nova_guia = st.text_input("Nome da Guia:")
    if st.button("➕ Criar Guia"):
        if nova_guia and nova_guia not in st.session_state.guias_extras:
            st.session_state.guias_extras.append(nova_guia)
            st.session_state[f"dados_{nova_guia}"] = pd.DataFrame({"Descrição": [""], "Mês Início (1-12)": [5], "Ano Início": [2026], "Qtd Parcelas": [1], "Valor Parcela (R$)": [0.00]})
            salvar_dados_nuvem()
            st.rerun()

    st.divider()
    if st.button("💾 FORÇAR GUARDAR", type="primary"):
        salvar_dados_nuvem()

# --- CÁLCULOS GLOBAIS ---
mes_atual_num, ano_atual = MESES[st.session_state.mes_atual], st.session_state.ano_atual
total_fixos = st.session_state.gastos_fixos["Valor (R$)"].sum()
total_casuais = st.session_state.gastos_casuais["Valor (R$)"].sum()

total_todas_guias = 0.0
for guia in st.session_state.guias_extras:
    _, valor_guia = calcular_parcelas(st.session_state[f"dados_{guia}"], mes_atual_num, ano_atual)
    total_todas_guias += valor_guia

# --- INTERFACE (ECRÃ) ---
st.title(f"💰 Resumo de {st.session_state.mes_atual} / {st.session_state.ano_atual}")
nomes_abas = ["Painel Geral", "Gastos Fixos", "Dia a Dia"] + st.session_state.guias_extras
abas = st.tabs(nomes_abas)

with abas[0]:
    total_gasto = total_fixos + total_casuais + total_todas_guias
    saldo_livre = st.session_state.renda - total_gasto
    percentual_gasto = (total_gasto / st.session_state.renda) * 100 if st.session_state.renda > 0 else 0

    col1, col2 = st.columns(2)
    col1.metric("Sua Renda", f"R$ {st.session_state.renda:,.2f}")
    col2.metric("Saldo Livre (Sobra)", f"R$ {saldo_livre:,.2f}")
    
    st.progress(min(int(percentual_gasto), 100))
    st.caption(f"Já comprometeu {percentual_gasto:.1f}% da sua renda.")
    
    st.divider()
    st.markdown(f"**Detalhes do Gasto (R$ {total_gasto:,.2f}):**")
    st.write(f"- Gastos Fixos: R$ {total_fixos:,.2f}")
    st.write(f"- Gastos Casuais: R$ {total_casuais:,.2f}")
    st.write(f"- Total nas Guias: R$ {total_todas_guias:,.2f}")

with abas[1]:
    st.header("Gastos Fixos")
    editado_fixos = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)
    if not editado_fixos.equals(st.session_state.gastos_fixos):
        st.session_state.gastos_fixos = editado_fixos
        salvar_dados_nuvem()

with abas[2]:
    st.header("Gastos Casuais")
    editado_casuais = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True)
    if not editado_casuais.equals(st.session_state.gastos_casuais):
        st.session_state.gastos_casuais = editado_casuais
        salvar_dados_nuvem()

for i, guia in enumerate(st.session_state.guias_extras, start=3):
    with abas[i]:
        df_ativas, total_guia = calcular_parcelas(st.session_state[f"dados_{guia}"], mes_atual_num, ano_atual)
        st.subheader(f"📅 Ativos em {st.session_state.mes_atual}/{ano_atual}")
        if not df_ativas.empty:
            st.dataframe(df_ativas, use_container_width=True, hide_index=True)
            st.metric("Impacto no Mês", f"R$ {total_guia:,.2f}")
        else:
            st.success("Nada a constar para este mês!")
        
        st.divider()
        st.subheader("📝 Base de Dados de Compras")
        editado_guia = st.data_editor(st.session_state[f"dados_{guia}"], num_rows="dynamic", use_container_width=True, hide_index=True, key=f"editor_{guia}")
        if not editado_guia.equals(st.session_state[f"dados_{guia}"]):
            st.session_state[f"dados_{guia}"] = editado_guia
            salvar_dados_nuvem()
            st.rerun()
