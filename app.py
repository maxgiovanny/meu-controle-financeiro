import streamlit as st
import pandas as pd

# Configuração da página
st.set_page_config(page_title="Controlo Financeiro", page_icon="💰", layout="centered")

# --- MEMÓRIA DA APLICAÇÃO ---
# Isso garante que as suas edições não desaparecem enquanto navega nas abas
if "mes_atual" not in st.session_state:
    st.session_state.mes_atual = "Maio"
if "renda" not in st.session_state:
    st.session_state.renda = 10000.00
if "cartoes" not in st.session_state:
    st.session_state.cartoes = ["Digio", "Itaú", "Inter", "Mercado Pago", "Will"]
if "gastos_fixos" not in st.session_state:
    st.session_state.gastos_fixos = pd.DataFrame({
        "Descrição": ["Consórcio", "Plano de Saúde", "Combustível", "Linha Claro", "Linha Mútua", "Energia", "Mário Felipe", "Pedro"],
        "Valor (R$)": [1350.00, 355.23, 1200.00, 90.00, 50.00, 70.00, 100.00, 80.00],
        "Pago": [False] * 8
    })
if "gastos_casuais" not in st.session_state:
    st.session_state.gastos_casuais = pd.DataFrame({"Descrição": ["Supermercado"], "Valor (R$)": [600.00]})

# --- MENU LATERAL (Mês, Renda e Novos Cartões) ---
with st.sidebar:
    st.header("⚙️ Configurações")
    st.session_state.mes_atual = st.selectbox("Mês de Referência:", 
        ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"], index=4)
    
    st.session_state.renda = st.number_input("Renda Mensal (R$):", value=st.session_state.renda, step=100.00)
    
    st.divider()
    st.subheader("Adicionar Cartão")
    novo_cartao = st.text_input("Nome do Novo Cartão:")
    if st.button("➕ Adicionar Cartão"):
        if novo_cartao and novo_cartao not in st.session_state.cartoes:
            st.session_state.cartoes.append(novo_cartao)
            st.rerun() # Atualiza a página para mostrar a nova aba

# Título Principal
st.title(f"💰 Controlo Financeiro - {st.session_state.mes_atual}")

# --- CRIAÇÃO DAS ABAS ---
nomes_abas = ["Painel Geral", "Gastos Fixos", "Dia a Dia"] + [f"💳 {c}" for c in st.session_state.cartoes]
abas = st.tabs(nomes_abas)

# --- ABA 1: PAINEL GERAL ---
with abas[0]:
    st.header("Resumo do Mês")
    
    # Cálculos dinâmicos baseados nas tabelas
    total_fixos = st.session_state.gastos_fixos["Valor (R$)"].sum()
    total_casuais = st.session_state.gastos_casuais["Valor (R$)"].sum()
    
    # Para simplificar agora, somamos fixos + casuais (os cartões podem ser integrados no cálculo futuro)
    total_gasto = total_fixos + total_casuais
    saldo_livre = st.session_state.renda - total_gasto
    percentual_gasto = (total_gasto / st.session_state.renda) * 100 if st.session_state.renda > 0 else 0

    col1, col2 = st.columns(2)
    col1.metric("Renda Mensal", f"R$ {st.session_state.renda:,.2f}")
    col2.metric("Saldo Livre (Sem cartões)", f"R$ {saldo_livre:,.2f}")
    
    st.progress(min(int(percentual_gasto), 100))
    st.caption(f"Você já comprometeu {percentual_gasto:.1f}% da sua renda com custos fixos e casuais.")

# --- ABA 2: GASTOS FIXOS (Editável) ---
with abas[1]:
    st.header("Gastos Fixos")
    st.info("💡 **Dica:** Clique em qualquer valor para alterar. Para apagar uma linha, clique no quadradinho à esquerda dela e aperte a tecla 'Delete' (ou use o ícone da lixeira no telemóvel). Uma linha vazia no final permite adicionar novos gastos.")
    st.session_state.gastos_fixos = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)

# --- ABA 3: DIA A DIA (Editável) ---
with abas[2]:
    st.header("Gastos Casuais")
    st.write("Adicione aqui padaria, farmácia, Pix, etc.")
    st.session_state.gastos_casuais = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True)

# --- ABAS DOS CARTÕES (Dinâmicas e Editáveis) ---
for i, cartao in enumerate(st.session_state.cartoes, start=3):
    with abas[i]:
        st.header(f"Fatura: {cartao}")
        
        # Cria uma tabela independente para cada cartão na memória
        if f"tabela_{cartao}" not in st.session_state:
            st.session_state[f"tabela_{cartao}"] = pd.DataFrame({"Compra": [""], "Parcela (ex: 1/10)": [""], "Valor (R$)": [0.00]})
        
        st.session_state[f"tabela_{cartao}"] = st.data_editor(
            st.session_state[f"tabela_{cartao}"], 
            num_rows="dynamic", 
            use_container_width=True, 
            hide_index=True,
            key=f"editor_{cartao}" # Chave única para não dar erro
        )
