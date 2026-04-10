import streamlit as st
import pandas as pd
import json
import gspread
import plotly.express as px
import math
from datetime import datetime
from google.oauth2.service_account import Credentials
from fpdf import FPDF
import unicodedata
import tempfile
import os

# --- 1. FUNÇÃO DE SEGURANÇA (LOGIN) ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.title("🔒 Acesso Restrito")
        st.text_input("Digite a senha:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔒 Acesso Restrito")
        st.text_input("Senha incorreta.", type="password", on_change=password_entered, key="password")
        st.error("😕 Senha inválida.")
        return False
    else: return True

# --- 2. INÍCIO DO APLICATIVO ---
if check_password():
    st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered")

    MESES = {"Janeiro":1,"Fevereiro":2,"Março":3,"Abril":4,"Maio":5,"Junho":6,
             "Julho":7,"Agosto":8,"Setembro":9,"Outubro":10,"Novembro":11,"Dezembro":12}
    CATEGORIAS_PADRAO_BASE = ["Alimentação","Transporte","Lazer","Saúde","Casa","Trabalho","Outros"]

    # --- FUNÇÕES DE TRATAMENTO DE DADOS ---
    def safe_float(val, default=0.0):
        try:
            if pd.isna(val) or val == "": return default
            s_val = str(val).strip()
            if "," in s_val:
                s_val = s_val.replace(".", "").replace(",", ".")
            s_val = s_val.replace("R$", "").strip()
            v = float(s_val)
            return default if math.isnan(v) else v
        except: return default

    def safe_int(val, default=1):
        try:
            if pd.isna(val) or val == "": return default
            return int(float(val))
        except: return default

    def safe_str(val):
        return str(val).strip() if not pd.isna(val) else ""

    def safe_bool(val):
        return str(val).strip().lower() in ['true', '1', 't', 'y', 'yes']

    def formatar_moeda(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def remover_acentos(texto):
        if not isinstance(texto, str): texto = str(texto)
        return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')

    @st.cache_resource
    def ligar_google_sheets():
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open_by_url(st.secrets["url_planilha"])

    def carregar_dados_nuvem():
        db_conn = ligar_google_sheets()
        try:
            ws_casuais = db_conn.worksheet("Casuais")
            ws_fixos = db_conn.worksheet("Fixos")
            ws_guias = db_conn.worksheet("Guias")
            ws_config = db_conn.worksheet("Configuracoes")
        except:
            st.error("Erro: Abas não encontradas. Verifique a planilha.")
            st.stop()

        d_cas = ws_casuais.get_all_records()
        hist_casuais = {}
        for row in d_cas:
            ma = safe_str(row.get("Mes_Ano"))
            if not ma: continue
            if ma not in hist_casuais: hist_casuais[ma] = []
            hist_casuais[ma].append({"Data": safe_str(row.get("Data")), "Categoria": safe_str(row.get("Categoria")), "Descrição": safe_str(row.get("Descrição")), "Valor (R$)": safe_float(row.get("Valor"))})

        d_fix = ws_fixos.get_all_records()
        hist_fixos = {}
        for row in d_fix:
            ma = safe_str(row.get("Mes_Ano"))
            if not ma: continue
            if ma not in hist_fixos: hist_fixos[ma] = []
            hist_fixos[ma].append({"Descrição": safe_str(row.get("Descrição")), "Categoria": safe_str(row.get("Categoria")), "Valor (R$)": safe_float(row.get("Valor")), "Pago": safe_bool(row.get("Pago"))})

        d_gui = ws_guias.get_all_records()
        dict_guias = {}
        for row in d_gui:
            g = safe_str(row.get("Guia"))
            if not g: continue
            if g not in dict_guias: dict_guias[g] = []
            dict_guias[g].append({"Descrição": safe_str(row.get("Descrição")), "Categoria": safe_str(row.get("Categoria")), "Valor Parcela (R$)": safe_float(row.get("Valor Parcela")), "Mês Início (1-12)": safe_int(row.get("Mês Início")), "Ano Início": safe_int(row.get("Ano Início")), "Qtd Parcelas": safe_int(row.get("Qtd Parcelas"))})

        val_conf = ws_config.acell('A1').value
        config = json.loads(val_conf) if val_conf else {}

        res = {
            "historico_casuais": hist_casuais, "historico_fixos": hist_fixos,
            "guias_extras": config.get("guias_extras", []), "categorias_personalizadas": config.get("categorias_personalizadas", []),
            "categorias_padrao": config.get("categorias_padrao", CATEGORIAS_PADRAO_BASE.copy()),
            "renda_por_mes": config.get("renda_por_mes", {}), "metas_orcamento": config.get("metas_orcamento", {})
        }
        for g in res["guias_extras"]:
            res[f"dados_{g}"] = pd.DataFrame(dict_guias.get(g, []))
        return res

    def salvar_dados_nuvem():
        db_conn = ligar_google_sheets()
        chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
        
        st.session_state.historico_fixos[chave] = st.session_state.gastos_fixos.to_dict("records")
        temp_cas = st.session_state.gastos_casuais.copy()
        if "Data" in temp_cas.columns: temp_cas["Data"] = temp_cas["Data"].astype(str)
        st.session_state.historico_casuais[chave] = temp_cas.to_dict("records")
        st.session_state.renda_por_mes[chave] = st.session_state.renda_detalhada.to_dict("records")

        f_cas = [["Mes_Ano", "Data", "Categoria", "Descrição", "Valor"]]
        for ma, itens in st.session_state.historico_casuais.items():
            for i in itens: f_cas.append([ma, i.get("Data"), i.get("Categoria"), i.get("Descrição"), i.get("Valor (R$)")])
        
        f_fix = [["Mes_Ano", "Descrição", "Categoria", "Valor", "Pago"]]
        for ma, itens in st.session_state.historico_fixos.items():
            for i in itens: f_fix.append([ma, i.get("Descrição"), i.get("Categoria"), i.get("Valor (R$)"), i.get("Pago")])

        f_gui = [["Guia", "Descrição", "Categoria", "Valor Parcela", "Mês Início", "Ano Início", "Qtd Parcelas"]]
        for g in st.session_state.guias_extras:
            for i in st.session_state.get(f"dados_{g}", pd.DataFrame()).to_dict("records"):
                f_gui.append([g, i.get("Descrição"), i.get("Categoria"), i.get("Valor Parcela (R$)"), i.get("Mês Início (1-12)"), i.get("Ano Início"), i.get("Qtd Parcelas")])

        db_conn.worksheet("Casuais").clear(); db_conn.worksheet("Casuais").update(values=f_cas, range_name='A1')
        db_conn.worksheet("Fixos").clear(); db_conn.worksheet("Fixos").update(values=f_fix, range_name='A1')
        db_conn.worksheet("Guias").clear(); db_conn.worksheet("Guias").update(values=f_gui, range_name='A1')
        
        conf = {"guias_extras": st.session_state.guias_extras, "categorias_personalizadas": st.session_state.categorias_personalizadas, "categorias_padrao": st.session_state.categorias_padrao, "renda_por_mes": st.session_state.renda_por_mes, "metas_orcamento": st.session_state.metas_orcamento}
        db_conn.worksheet("Configuracoes").clear(); db_conn.worksheet("Configuracoes").update(values=[[json.dumps(conf, default=str)]], range_name='A1')
        st.toast("💾 Sincronizado!", icon="✅")

    # --- INICIALIZAÇÃO ---
    if "dados_carregados" not in st.session_state:
        d = carregar_dados_nuvem()
        hj = datetime.now()
        st.session_state.ano_atual, st.session_state.mes_atual = hj.year, list(MESES.keys())[hj.month-1]
        st.session_state.update(d)
        chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
        st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos.get(chave, []))
        if st.session_state.gastos_fixos.empty: st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição","Valor (R$)","Pago","Categoria"])
        df_c = pd.DataFrame(st.session_state.historico_casuais.get(chave, []))
        if not df_c.empty: df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
        st.session_state.gastos_casuais = df_c if not df_c.empty else pd.DataFrame(columns=["Data","Categoria","Descrição","Valor (R$)"])
        st.session_state.renda_detalhada = pd.DataFrame(st.session_state.renda_por_mes.get(chave, [{"Fonte":"Salário","Valor (R$)":0.0}]))
        st.session_state.dados_carregados = True

    def get_categorias(): return st.session_state.categorias_padrao + st.session_state.categorias_personalizadas

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Configurações")
        m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
        a_sel = st.number_input("Ano:", 2024, 2030, st.session_state.ano_atual)
        if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
            salvar_dados_nuvem()
            st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
            chave = f"{m_sel}_{a_sel}"
            st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos.get(chave, []))
            if st.session_state.gastos_fixos.empty: st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição","Valor (R$)","Pago","Categoria"])
            df_c = pd.DataFrame(st.session_state.historico_casuais.get(chave, []))
            if not df_c.empty: df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
            st.session_state.gastos_casuais = df_c if not df_c.empty else pd.DataFrame(columns=["Data","Categoria","Descrição","Valor (R$)"])
            st.session_state.renda_detalhada = pd.DataFrame(st.session_state.renda_por_mes.get(chave, [{"Fonte":"Salário","Valor (R$)":0.0}]))
            st.rerun()
        
        st.divider()
        if st.button("🗑️ Limpar Cache"): st.cache_resource.clear(); st.rerun()

    # --- CÁLCULOS E LÓGICA DE GUIAS ---
    mes_n = MESES[st.session_state.mes_atual]
    ano_r = st.session_state.ano_atual
    
    def calc_parc(df, m, a):
        if df is None or df.empty: return pd.DataFrame(columns=["Descrição","Categoria","Valor (R$)"]), 0.0
        res = []
        for _, r in df.iterrows():
            try:
                ini = int(r["Ano Início"])*12 + int(r["Mês Início (1-12)"])
                alvo = a*12 + m
                if ini <= alvo <= (ini + int(r["Qtd Parcelas"]) - 1):
                    res.append({"Descrição": r["Descrição"], "Categoria": r.get("Categoria","Outros"), "Valor (R$)": safe_float(r["Valor Parcela (R$)"])})
            except: continue
        df_res = pd.DataFrame(res)
        return df_res, df_res["Valor (R$)"].sum() if not df_res.empty else 0.0

    t_fix = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
    t_cas = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
    t_guias = 0.0
    for g in st.session_state.guias_extras:
        _, sub = calc_parc(st.session_state.get(f"dados_{g}"), mes_n, ano_r)
        t_guias += sub
    
    total_renda = st.session_state.renda_detalhada["Valor (R$)"].sum()
    sobra = total_renda - (t_fix + t_cas + t_guias)

    # --- INTERFACE PRINCIPAL ---
    st.title(f"💰 {st.session_state.mes_atual} / {st.session_state.ano_atual}")
    opcoes = ["Resumo Geral", "Renda", "Gastos Fixos", "Dia a Dia", "Metas", "Pesquisa Global"] + st.session_state.guias_extras
    sel = st.selectbox("Ir para:", opcoes)
    st.divider()

    if sel == "Resumo Geral":
        c1, c2, c3 = st.columns(3)
        c1.metric("Gasto Total", formatar_moeda(t_fix + t_cas + t_guias))
        c2.metric("Sobra", formatar_moeda(sobra))
        c3.metric("Renda", formatar_moeda(total_renda))
        
        fig = px.pie(names=["Fixos", "Dia a Dia", "Faturas"], values=[t_fix, t_cas, t_guias], hole=.4)
        st.plotly_chart(fig, use_container_width=True)

    elif sel == "Renda":
        st.subheader("💵 Minhas Receitas")
        er = st.data_editor(st.session_state.renda_detalhada, num_rows="dynamic", use_container_width=True, hide_index=True)
        if not er.equals(st.session_state.renda_detalhada):
            st.session_state.renda_detalhada = er
            salvar_dados_nuvem()

    elif sel == "Gastos Fixos":
        st.subheader(f"📌 Total: {formatar_moeda(t_fix)}")
        ef = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Categoria": st.column_config.SelectboxColumn(options=get_categorias()),
                                           "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f")})
        if not ef.equals(st.session_state.gastos_fixos):
            st.session_state.gastos_fixos = ef
            salvar_dados_nuvem()

    elif sel == "Dia a Dia":
        st.subheader(f"🛍️ Total: {formatar_moeda(t_cas)}")
        ec = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Categoria": st.column_config.SelectboxColumn(options=get_categorias()),
                                           "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                           "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f")})
        if not ec.equals(st.session_state.gastos_casuais):
            st.session_state.gastos_casuais = ec
            salvar_dados_nuvem()

    elif sel == "Metas":
        st.subheader("🎯 Planejamento Mensal")
        df_m = pd.DataFrame([{"Categoria": k, "Limite (R$)": v} for k, v in st.session_state.metas_orcamento.items()])
        em = st.data_editor(df_m, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Categoria": st.column_config.SelectboxColumn(options=get_categorias()),
                                           "Limite (R$)": st.column_config.NumberColumn(format="R$ %.2f")})
        if st.button("💾 Salvar Metas"):
            st.session_state.metas_orcamento = {row["Categoria"]: safe_float(row["Limite (R$)"]) for _, row in em.iterrows() if row["Categoria"]}
            salvar_dados_nuvem()
            st.rerun()

    elif sel == "Pesquisa Global":
        st.subheader("🔍 Localizar Gastos")
        termo = st.text_input("O que procura? (ex: Mercado)").lower()
        if termo:
            res = []
            for m, itens in st.session_state.historico_casuais.items():
                for i in itens:
                    if termo in i['Descrição'].lower(): res.append({"Mês": m, "Tipo": "Casual", "Desc": i['Descrição'], "Valor": i['Valor (R$)']})
            st.table(res)

    elif sel in st.session_state.guias_extras:
        df_g, total_g = calc_parc(st.session_state.get(f"dados_{sel}"), mes_n, ano_r)
        st.subheader(f"💳 Fatura {sel}: {formatar_moeda(total_g)}")
        st.write("Registros do mês atual:")
        st.dataframe(df_g, use_container_width=True, hide_index=True)
        st.divider()
        st.write("Gerenciar Parcelamentos:")
        eg = st.data_editor(st.session_state[f"dados_{sel}"], num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Categoria": st.column_config.SelectboxColumn(options=get_categorias())})
        if not eg.equals(st.session_state[f"dados_{sel}"]):
            st.session_state[f"dados_{sel}"] = eg
            salvar_dados_nuvem()
