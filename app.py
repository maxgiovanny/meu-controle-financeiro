import streamlit as st
import pandas as pd

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered")

# Dicionário para converter o nome do mês em número (facilita os cálculos)
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
    # Transformado de Cartões para Guias (você pode adicionar e apagar como quiser)
    st.session_state.guias_extras = ["💳 Digio", "💳 Itaú", "💳 Inter", "💳 Mercado Pago", "💳 Will", "🚗 Despesas Carro"]
if "gastos_fixos" not in st.session_state:
    st.session_state.gastos_fixos = pd.DataFrame({
        "Descrição": ["Consórcio", "Plano de Saúde", "Combustível", "Linha Claro", "Linha Mútua", "Energia", "Mário Felipe", "Pedro"],
        "Valor (R$)": [1350.00, 355.23, 1200.00, 90.00, 50.00, 70.00, 100.00, 80.00],
        "Pago": [False] * 8
    })
if "gastos_casuais" not in st.session_state:
    st.session_state.gastos_casuais = pd.DataFrame({"Descrição": ["Supermercado"], "Valor (R$)": [600.00]})

# Cria a base de dados em branco para cada guia nova ou existente
for guia in st.session_state.guias_extras:
    if f"dados_{guia}" not in st.session_state:
        st.session_state[f"dados_{guia}"] = pd.DataFrame({
            "Descrição": [""],
            "Mês Início (1-12)": [5],
            "Ano Início": [2026],
            "Qtd Parcelas": [1],
            "Valor Parcela (R$)": [0.00]
        })

# --- FUNÇÃO MATEMÁTICA: CALCULAR PARCELAS ATIVAS ---
def calcular_parcelas(df, mes_alvo, ano_alvo):
    ativas = []
    total_valor = 0.0
    
    for index, row in df.iterrows():
        try:
            if not row["Descrição"] or row["Valor Parcela (R$)"] == 0:
                continue
            
            mes_inicio = int(row["Mês Início (1-12)"])
            ano_inicio = int(row["Ano Início"])
            qtd_parcelas = int(row["Qtd Parcelas"])
            valor = float(row["Valor Parcela (R$)"])
            
            # Converte as datas em "meses totais" para facilitar a comparação
            data_alvo_val = ano_alvo * 12 + mes_alvo
            data_inicio_val = ano_inicio * 12 + mes_inicio
            data_fim_val = data_inicio_val + qtd_parcelas - 1
            
            # Se o mês alvo está dentro do período da compra
            if data_inicio_val <= data_alvo_val <= data_fim_val:
                parcela_atual = data_alvo_val - data_inicio_val + 1
                ativas.append({
                    "Descrição": row["Descrição"],
                    "Parcela": f"{parcela_atual}/{qtd_parcelas}",
                    "Valor (R$)": valor
                })
                total_valor += valor
        except:
            continue # Ignora linhas preenchidas pela metade
            
    return pd.DataFrame(ativas), total_valor

# --- MENU LATERAL ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    st.session_state.mes_atual = st.selectbox("Mês de Referência:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
    st.session_state.ano_atual = st.number_input("Ano de Referência:", min_value=2020, max_value=2050, value=st.session_state.ano_atual, step=1)
    
    st.session_state.renda = st.number_input("Renda Mensal (R$):", value=st.session_state.renda, step=100.00)
    
    st.divider()
    st.subheader("Adicionar Nova Guia")
    nova_guia = st.text_input("Nome da Guia (ex: Reforma, Viagem):")
    if st.button("➕ Criar Guia"):
        if nova_guia and nova_guia not in st.session_state.guias_extras:
            st.session_state.guias_extras.append(nova_guia)
            st.rerun()

# --- CÁLCULOS GLOBAIS DO MÊS ---
mes_atual_num = MESES[st.session_state.mes_atual]
ano_atual = st.session_state.ano_atual

total_fixos = st.session_state.gastos_fixos["Valor (R$)"].sum()
total_casuais = st.session_state.gastos_casuais["Valor (R$)"].sum()

total_todas_guias = 0.0
for guia in st.session_state.guias_extras:
    _, valor_guia = calcular_parcelas(st.session_state[f"dados_{guia}"], mes_atual_num, ano_atual)
    total_todas_guias += valor_guia

# --- CRIAÇÃO DAS ABAS NA TELA ---
st.title(f"💰 Resumo de {st.session_state.mes_atual} / {st.session_state.ano_atual}")

nomes_abas = ["Painel Geral", "Gastos Fixos", "Dia a Dia"] + st.session_state.guias_extras
abas = st.tabs(nomes_abas)

# --- ABA 1: PAINEL GERAL ---
with abas[0]:
    total_gasto = total_fixos + total_casuais + total_todas_guias
    saldo_livre = st.session_state.renda - total_gasto
    percentual_gasto = (total_gasto / st.session_state.renda) * 100 if st.session_state.renda > 0 else 0

    col1, col2 = st.columns(2)
    col1.metric("Sua Renda", f"R$ {st.session_state.renda:,.2f}")
    col2.metric("Saldo Livre (Sobra)", f"R$ {saldo_livre:,.2f}")
    
    st.progress(min(int(percentual_gasto), 100))
    st.caption(f"Você já comprometeu {percentual_gasto:.1f}% da sua renda neste mês.")
    
    st.divider()
    st.markdown(f"**Detalhes do Gasto (R$ {total_gasto:,.2f}):**")
    st.write(f"- Gastos Fixos: R$ {total_fixos:,.2f}")
    st.write(f"- Gastos Casuais: R$ {total_casuais:,.2f}")
    st.write(f"- Total nas Guias Extra: R$ {total_todas_guias:,.2f}")

# --- ABA 2: GASTOS FIXOS ---
with abas[1]:
    st.header("Gastos Fixos")
    st.session_state.gastos_fixos = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)

# --- ABA 3: DIA A DIA ---
with abas[2]:
    st.header("Gastos Casuais")
    st.session_state.gastos_casuais = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True)

# --- ABAS DAS GUIAS EXTRAS (Dinâmicas) ---
for i, guia in enumerate(st.session_state.guias_extras, start=3):
    with abas[i]:
        # Mostra o resumo apenas do mês selecionado
        df_ativas, total_guia = calcular_parcelas(st.session_state[f"dados_{guia}"], mes_atual_num, ano_atual)
        
        st.subheader(f"📅 Ativos em {st.session_state.mes_atual}/{ano_atual}")
        if not df_ativas.empty:
            st.dataframe(df_ativas, use_container_width=True, hide_index=True)
            st.metric(f"Impacto no Mês", f"R$ {total_guia:,.2f}")
        else:
            st.success("Nada constando para este mês!")
        
        st.divider()
        
        # Área onde você realmente cadastra e edita a base de dados inteira
        st.subheader("📝 Base de Dados de Compras")
        st.caption("Cadastre aqui. A aplicação calculará automaticamente quando exibir em cada mês.")
        st.session_state[f"dados_{guia}"] = st.data_editor(
            st.session_state[f"dados_{guia}"], 
            num_rows="dynamic", 
            use_container_width=True, 
            hide_index=True,
            key=f"editor_{guia}"
        )
