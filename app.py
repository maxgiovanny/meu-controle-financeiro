import streamlit as st
import pandas as pd
import json
import gspread
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Gestão Financeira Pro", page_icon="💰", layout="wide")

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
        "historico_casuais": st.session_state.historico_casuais,
        "metas": st.session_state.metas,
        "pericias": st.session_state.pericias.to_dict("records") if hasattr(st.session_state, 'pericias') else []
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

    st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos.get(chave_atual, []))
    if st.session_state.gastos_fixos.empty:
        st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição", "Valor (R$)", "Pago"])

    df_c = pd.DataFrame(st.session_state.historico_casuais.get(chave_atual, []))
    if not df_c.empty:
        df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
        if "Categoria" not in df_c.columns: df_c["Categoria"] = "Outros"
    st.session_state.gastos_casuais = df_c if not df_c.empty else pd.DataFrame(columns=["Data", "Categoria", "Descrição", "Valor (R$)"])

# --- INICIALIZAÇÃO ---
if "dados_carregados" not in st.session_state:
    d_raw = carregar_dados_nuvem_raw()
    hj = datetime.now()
    st.session_state.ano_atual, st.session_state.mes_atual = hj.year, list(MESES.keys())[hj.month - 1]
    st.session_state.renda = d_raw.get("renda", 10000.0)
    st.session_state.guias_extras = d_raw.get("guias_extras", [])
    st.session_state.historico_fixos = d_raw.get("historico_fixos", {})
    st.session_state.historico_casuais = d_raw.get("historico_casuais", {})
    st.session_state.metas = d_raw.get("metas", {cat: 0.0 for cat in CATEGORIAS})
    st.session_state.pericias = pd.DataFrame(d_raw.get("pericias", []))
    if st.session_state.pericias.empty:
        st.session_state.pericias = pd.DataFrame(columns=["Processo/Caso", "Honorários (R$)", "Custos (R$)", "Status"])
    
    for g in st.session_state.guias_extras:
        st.session_state[f"dados_{g}"] = pd.DataFrame(d_raw.get(f"dados_{g}", []))
    carregar_dados_sessao()
    st.session_state.dados_carregados = True

# --- CÁLCULOS ---
def calc_parc(df, m, a):
    at, tot = [], 0.0
    if df is None or df.empty: return pd.DataFrame(columns=["Descrição", "Parcela", "Valor (R$)"]), 0.0
    df_v = df.dropna(subset=["Descrição", "Valor Parcela (R$)"])
    for _, r in df_v[df_v["Descrição"] != ""].iterrows():
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
    st.header("⚙️ Painel de Controle")
    if st.button("🔄 Recarregar Nuvem"):
        st.cache_data.clear()
        st.rerun()

    m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
    a_sel = st.number_input("Ano:", 2024, 2030, st.session_state.ano_atual)
    if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
        salvar_dados_nuvem(); st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
        carregar_dados_sessao(); st.rerun()

    r_sel = st.number_input("Renda Mensal:", value=st.session_state.renda, step=100.0)
    if r_sel != st.session_state.renda: st.session_state.renda = r_sel; salvar_dados_nuvem()

    st.divider(); st.subheader("🛠️ Guias Extras")
    ng = st.text_input("Nome da Guia:")
    if st.button("➕ Criar"):
        if ng and ng not in st.session_state.guias_extras:
            st.session_state.guias_extras.append(ng)
            st.session_state[f"dados_{ng}"] = pd.DataFrame(columns=["Descrição", "Valor Parcela (R$)", "Mês Início (1-12)", "Ano Início", "Qtd Parcelas"])
            salvar_dados_nuvem(); st.rerun()

    if st.session_state.guias_extras:
        gf = st.selectbox("Ativa:", st.session_state.guias_extras)
        if st.button("🗑️ Apagar"):
            st.session_state.guias_extras.remove(gf)
            if f"dados_{gf}" in st.session_state: del st.session_state[f"dados_{gf}"]
            salvar_dados_nuvem(); st.rerun()

# --- MAIN ---
mes_n, ano_r = MESES[st.session_state.mes_atual], st.session_state.ano_atual
t_fix = float(st.session_state.gastos_fixos["Valor (R$)"].sum()) if not st.session_state.gastos_fixos.empty else 0.0
t_cas = float(st.session_state.gastos_casuais["Valor (R$)"].sum()) if not st.session_state.gastos_casuais.empty else 0.0
t_gui = sum([calc_parc(st.session_state.get(f"dados_{g}"), mes_n, ano_r)[1] for g in st.session_state.guias_extras])

sel = st.tabs(["Resumo", "Gastos Fixos", "Dia a Dia", "Projeção Futura", "Análise e Metas", "⚖️ Perícias"] + st.session_state.guias_extras)

# --- ABA: RESUMO ---
with sel[0]:
    gt = t_fix + t_cas + t_gui; sobra = st.session_state.renda - gt
    c1, c2, c3 = st.columns(3)
    c1.metric("Gasto Total", f"R$ {gt:,.2f}")
    c2.metric("Sobra Real", f"R$ {sobra:,.2f}", delta=f"{(sobra/st.session_state.renda)*100:.1f}%" if st.session_state.renda > 0 else "0%")
    c3.metric("Renda", f"R$ {st.session_state.renda:,.2f}")
    
    fig = px.pie(pd.DataFrame({"C": ["Fixos", "Dia a Dia", "Guias", "Sobra"], "V": [t_fix, t_cas, t_gui, max(0, sobra)]}), values='V', names='C', hole=.4, title="Distribuição de Gastos")
    st.plotly_chart(fig, use_container_width=True)

# --- ABA: GASTOS FIXOS ---
with sel[1]:
    ct, cb = st.columns([3, 1]); ct.subheader("📌 Contas Fixas")
    if cb.button("🔄 Importar do Mês Anterior"): carregar_dados_sessao(True); salvar_dados_nuvem(); st.rerun()
    st.metric("Total da Aba", f"R$ {t_fix:,.2f}")
    ef = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)
    if not ef.equals(st.session_state.gastos_fixos): st.session_state.gastos_fixos = ef; salvar_dados_nuvem()

# --- ABA: DIA A DIA ---
with sel[2]:
    st.subheader("🛍️ Compras Casuais")
    st.metric("Total da Aba", f"R$ {t_cas:,.2f}")
    ec = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY"), "Categoria": st.column_config.SelectboxColumn(options=CATEGORIAS)})
    if not ec.equals(st.session_state.gastos_casuais): st.session_state.gastos_casuais = ec; salvar_dados_nuvem()

# --- ABA: PROJEÇÃO FUTURA ---
with sel[3]:
    st.subheader("📅 Fluxo de Caixa Previsto (Próximos 6 Meses)")
    proj_dados = []
    for i in range(6):
        futuro = hj + timedelta(days=30*i)
        f_mes, f_ano = futuro.month, futuro.year
        f_gui = sum([calc_parc(st.session_state.get(f"dados_{g}"), f_mes, f_ano)[1] for g in st.session_state.guias_extras])
        proj_dados.append({"Mês": f"{list(MESES.keys())[f_mes-1]}/{f_ano}", "Fixo": t_fix, "Parcelas": f_gui, "Total": t_fix + f_gui})
    
    df_proj = pd.DataFrame(proj_dados)
    fig_proj = px.bar(df_proj, x="Mês", y=["Fixo", "Parcelas"], title="Comprometimento de Renda Futuro", barmode="stack")
    st.plotly_chart(fig_proj, use_container_width=True)
    st.table(df_proj)

# --- ABA: ANÁLISE E METAS ---
with sel[4]:
    st.subheader("🎯 Planejamento por Categoria")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.write("**Definir Metas Mensais:**")
        df_metas = pd.DataFrame(list(st.session_state.metas.items()), columns=["Categoria", "Meta (R$)"])
        ed_metas = st.data_editor(df_metas, use_container_width=True, hide_index=True)
        if not ed_metas.equals(df_metas):
            st.session_state.metas = dict(ed_metas.values)
            salvar_dados_nuvem(); st.rerun()
    
    with col_m2:
        st.write("**Progresso das Metas:**")
        if not st.session_state.gastos_casuais.empty:
            atual_cat = st.session_state.gastos_casuais.groupby("Categoria")["Valor (R$)"].sum().to_dict()
            for cat in CATEGORIAS:
                meta = st.session_state.metas.get(cat, 0)
                gasto = atual_cat.get(cat, 0)
                if meta > 0:
                    prog = min(1.0, gasto/meta)
                    st.write(f"**{cat}**: R$ {gasto:.2f} / R$ {meta:.2f}")
                    st.progress(prog)

# --- ABA: PERÍCIAS ---
with sel[5]:
    st.subheader("⚖️ Gestão de Perícias e Projetos")
    st.info("Utilize esta tabela para calcular a rentabilidade dos seus trabalhos técnicos.")
    ep = st.data_editor(st.session_state.pericias, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Status": st.column_config.SelectboxColumn(options=["Em andamento", "Concluído", "Pago"])})
    if not ep.equals(st.session_state.pericias):
        st.session_state.pericias = ep; salvar_dados_nuvem()
    
    if not st.session_state.pericias.empty:
        # Honorários - Custos = Saldo
        st.session_state.pericias["Honorários (R$)"] = pd.to_numeric(st.session_state.pericias["Honorários (R$)"], errors='coerce').fillna(0)
        st.session_state.pericias["Custos (R$)"] = pd.to_numeric(st.session_state.pericias["Custos (R$)"], errors='coerce').fillna(0)
        total_hon = st.session_state.pericias["Honorários (R$)"].sum()
        total_cus = st.session_state.pericias["Custos (R$)"].sum()
        lucro = total_hon - total_cus
        
        c_p1, c_p2, c_p3 = st.columns(3)
        c_p1.metric("Total Honorários", f"R$ {total_hon:,.2f}")
        c_p2.metric("Custos Totais", f"R$ {total_cus:,.2f}")
        c_p3.metric("Lucro Acumulado", f"R$ {lucro:,.2f}")

# --- ABAS DINÂMICAS (GUIAS EXTRAS) ---
for i, g_nome in enumerate(st.session_state.guias_extras):
    with sel[6 + i]:
        dr, vt = calc_parc(st.session_state.get(f"dados_{g_nome}"), mes_n, ano_r)
        st.subheader(f"Total: R$ {vt:,.2f}")
        if not dr.empty: st.dataframe(dr, use_container_width=True, hide_index=True)
        st.divider(); st.write("**Base de Lançamentos:**")
        de = st.data_editor(st.session_state[f"dados_{g_nome}"], num_rows="dynamic", use_container_width=True, hide_index=True)
        if not de.equals(st.session_state[f"dados_{g_nome}"]):
            st.session_state[f"dados_{g_nome}"] = de; salvar_dados_nuvem(); st.rerun()
