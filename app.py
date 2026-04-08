import streamlit as st

# Configuração da página para ficar bem no telemóvel
st.set_page_config(page_title="Controlo Financeiro", page_icon="💰", layout="centered")

st.title("💰 O Meu Controlo Financeiro")

# Criação dos separadores (Tabs)
abas = st.tabs([
    "Painel Geral", "Gastos Fixos", "Dia a Dia", 
    "💳 Digio", "💳 Itaú", "💳 Inter", "💳 Mercado Pago", "💳 Will"
])

# --- ABA 1: PAINEL GERAL ---
with abas[0]:
    st.header("Resumo do Mês")
    
    # Exibição lado a lado
    col1, col2 = st.columns(2)
    col1.metric("Renda Mensal", "R$ 10.000,00")
    col2.metric("Saldo Livre", "R$ 4.599,26")
    
    st.progress(54) # Barra de progresso visual simulando 54% da renda comprometida
    st.caption("Você já comprometeu 54% da sua renda este mês.")

# --- ABA 2: GASTOS FIXOS ---
with abas[1]:
    st.header("Gastos Fixos")
    st.write("Marque o que já foi pago este mês:")
    
    st.checkbox("Consórcio (R$ 1.350,00)")
    st.checkbox("Plano de Saúde (R$ 355,23)")
    st.checkbox("Combustível - Estimativa (R$ 1.200,00)")
    st.checkbox("Linha Claro (R$ 90,00)")
    st.checkbox("Linha Mútua (R$ 50,00)")
    st.checkbox("Energia (R$ 70,00)")
    st.checkbox("Mário Felipe (R$ 100,00)")
    st.checkbox("Pedro (R$ 80,00)")

# --- ABA 3: DIA A DIA ---
with abas[2]:
    st.header("Gastos do Dia a Dia")
    st.write("Registre aqui as compras no Pix ou Débito (ex: Mercado, Padaria).")
    
    with st.form("form_dia_a_dia"):
        descricao = st.text_input("O que comprou?")
        valor = st.number_input("Qual o valor? (R$)", min_value=0.0, format="%.2f")
        submetido = st.form_submit_button("Adicionar Gasto")
        if submetido:
            st.success(f"Gasto de R$ {valor} em '{descricao}' adicionado com sucesso!")

# --- ABAS DOS CARTÕES ---
cartoes = ["Digio", "Itaú", "Inter", "Mercado Pago", "Will"]
for i, cartao in enumerate(cartoes, start=3):
    with abas[i]:
        st.header(f"Fatura: {cartao}")
        
        # Formulário para adicionar compra parcelada
        with st.form(f"form_{cartao}"):
            desc_cartao = st.text_input(f"Nova compra no {cartao}")
            valor_cartao = st.number_input("Valor da parcela (R$)", min_value=0.0, format="%.2f")
            parcelas = st.number_input("Número de parcelas", min_value=1, step=1)
            add_cartao = st.form_submit_button("Registrar no Cartão")
            
            if add_cartao:
                st.success("Compra registrada na fatura!")
