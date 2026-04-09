import streamlit as st
import pandas as pd
import json
import gspread
import plotly.express as px
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from fpdf import FPDF
import unicodedata
import tempfile
import os
import io

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
        st.text_input("Senha incorreta. Tente novamente:", type="password", on_change=password_entered, key="password")
        st.error("😕 Senha inválida.")
        return False
    else:
        return True

# --- 2. INÍCIO DO APLICATIVO ---
if check_password():
    st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered")

    MESES = {"Janeiro":1,"Fevereiro":2,"Março":3,"Abril":4,"Maio":5,"Junho":6,
             "Julho":7,"Agosto":8,"Setembro":9,"Outubro":10,"Novembro":11,"Dezembro":12}
    CATEGORIAS_PADRAO = ["Alimentação","Transporte","Lazer","Saúde","Casa","Trabalho","Outros"]

    # --- CONEXÃO GOOGLE SHEETS ---
    @st.cache_resource
    def ligar_google_sheets():
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
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
        return (lista[idx-1], ano_atual) if idx>0 else ("Dezembro", ano_atual-1)

    def salvar_dados_nuvem():
        chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
        casuais_save = st.session_state.gastos_casuais.copy()
        if "Data" in casuais_save.columns:
            casuais_save["Data"] = pd.to_datetime(casuais_save["Data"]).dt.date.astype(str)

        st.session_state.historico_fixos[chave] = st.session_state.gastos_fixos.to_dict("records")
        st.session_state.historico_casuais[chave] = casuais_save.to_dict("records")
        st.session_state.renda_por_mes[chave] = st.session_state.renda_detalhada.to_dict("records")
        
        dados = {
            "renda_por_mes": st.session_state.renda_por_mes,
            "guias_extras": st.session_state.guias_extras,
            "historico_fixos": st.session_state.historico_fixos,
            "historico_casuais": st.session_state.historico_casuais,
            "categorias_personalizadas": st.session_state.categorias_personalizadas
        }
        for g in st.session_state.guias_extras:
            if f"dados_{g}" in st.session_state:
                dados[f"dados_{g}"] = st.session_state[f"dados_{g}"].to_dict("records")
        worksheet.update(values=[[json.dumps(dados, default=str)]], range_name='A1')
        st.toast("💾 Sincronizado!", icon="✅")

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
            return

        st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos.get(chave_atual, []))
        if st.session_state.gastos_fixos.empty:
            st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição","Valor (R$)","Pago"])

        df_c = pd.DataFrame(st.session_state.historico_casuais.get(chave_atual, []))
        if not df_c.empty:
            df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
        st.session_state.gastos_casuais = df_c if not df_c.empty else pd.DataFrame(columns=["Data","Categoria","Descrição","Valor (R$)"])

        renda_data = st.session_state.renda_por_mes.get(chave_atual)
        if renda_data:
            st.session_state.renda_detalhada = pd.DataFrame(renda_data)
        else:
            st.session_state.renda_detalhada = pd.DataFrame([{"Fonte":"Salário","Valor (R$)":0.0}])

    def recalcular_media_casuais(anos_meses):
        valores = []
        for ano, mes in anos_meses:
            chave = f"{mes}_{ano}"
            if chave in st.session_state.historico_casuais:
                df_mes = pd.DataFrame(st.session_state.historico_casuais[chave])
                if not df_mes.empty and "Valor (R$)" in df_mes.columns:
                    valores.append(df_mes["Valor (R$)"].sum())
        return sum(valores)/len(valores) if valores else 0.0

    def calc_parc_com_categoria(df, m, a):
        parcelas = []
        if df is None or df.empty:
            return pd.DataFrame(columns=["Descrição","Categoria","Valor (R$)"]), 0.0, {}
        df_v = df.dropna(subset=["Descrição","Valor Parcela (R$)"])
        for _, r in df_v[df_v["Descrição"]!=""].iterrows():
            try:
                m_i = int(r["Mês Início (1-12)"])
                a_i = int(r["Ano Início"])
                qtd = int(r["Qtd Parcelas"])
                v = float(r["Valor Parcela (R$)"])
                alvo = a*12 + m
                ini = a_i*12 + m_i
                if ini <= alvo <= (ini+qtd-1):
                    categoria = r.get("Categoria","Outros")
                    parcelas.append({"Descrição":r["Descrição"],"Categoria":categoria,"Valor (R$)":v})
            except: continue
        df_parc = pd.DataFrame(parcelas)
        total = df_parc["Valor (R$)"].sum() if not df_parc.empty else 0.0
        soma_cat = df_parc.groupby("Categoria")["Valor (R$)"].sum().to_dict() if not df_parc.empty else {}
        return df_parc, total, soma_cat

    def remover_acentos(texto):
        if not isinstance(texto, str): texto = str(texto)
        return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')

    def gerar_pdf_mes(mes_nome, ano, renda_df, fixos_df, casuais_df, guias_dados, total_renda, t_fix, t_cas, t_gui, sobra, dados_categoria):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, remover_acentos(f"Relatorio Financeiro - {mes_nome}/{ano}"), ln=True, align="C")
        pdf.ln(10)
        
        pdf.set_font_size(12)
        pdf.cell(0, 8, remover_acentos(f"RESUMO: Sobra R$ {sobra:.2f}"), ln=True)
        pdf.ln(5)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            temp_path = tmp.name
        pdf.output(temp_path)
        with open(temp_path, "rb") as f:
            pdf_data = f.read()
        os.remove(temp_path)
        return pdf_data

    # --- INICIALIZAÇÃO ---
    if "dados_carregados" not in st.session_state:
        dados_raw = carregar_dados_nuvem_raw()
        hj = datetime.now()
        st.session_state.ano_atual = hj.year
        st.session_state.mes_atual = list(MESES.keys())[hj.month-1]
        st.session_state.guias_extras = dados_raw.get("guias_extras", [])
        st.session_state.historico_fixos = dados_raw.get("historico_fixos", {})
        st.session_state.historico_casuais = dados_raw.get("historico_casuais", {})
        st.session_state.renda_por_mes = dados_raw.get("renda_por_mes", {})
        st.session_state.categorias_personalizadas = dados_raw.get("categorias_personalizadas", [])
        for g in st.session_state.guias_extras:
            st.session_state[f"dados_{g}"] = pd.DataFrame(dados_raw.get(f"dados_{g}", []))
        carregar_dados_sessao()
        st.session_state.dados_carregados = True

    if "pdf_ready" not in st.session_state:
        st.session_state.pdf_ready = False

    def get_categorias():
        return CATEGORIAS_PADRAO + st.session_state.categorias_personalizadas

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Configurações")
        
        m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
        a_sel = st.number_input("Ano:", 2024, 2030, st.session_state.ano_atual)
        if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
            salvar_dados_nuvem()
            st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
            carregar_dados_sessao()
            st.session_state.pdf_ready = False
            st.rerun()

        st.divider()
        
        # GERAÇÃO DO PDF
        if st.button("📄 1. Preparar Relatório PDF"):
            mes_n = MESES[st.session_state.mes_atual]
            ano_r = st.session_state.ano_atual
            t_fix_p = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
            t_cas_p = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
            
            total_guias_p = 0.0
            gastos_cat_p = {}
            for guia in st.session_state.guias_extras:
                _, tot, cats = calc_parc_com_categoria(st.session_state.get(f"dados_{guia}"), mes_n, ano_r)
                total_guias_p += tot
            
            total_renda_p = st.session_state.renda_detalhada["Valor (R$)"].sum()
            sobra_p = total_renda_p - (t_fix_p + t_cas_p + total_guias_p)

            st.session_state.pdf_data = gerar_pdf_mes(
                st.session_state.mes_atual, st.session_state.ano_atual,
                st.session_state.renda_detalhada, st.session_state.gastos_fixos,
                st.session_state.gastos_casuais, {}, # guias_dados simplificado
                total_renda_p, t_fix_p, t_cas_p, total_guias_p, sobra_p, {}
            )
            st.session_state.pdf_ready = True
            st.success("PDF Gerado com sucesso!")

        # DOWNLOAD DO PDF
        if st.session_state.pdf_ready:
            st.download_button(
                label="📥 2. Baixar PDF Agora",
                data=io.BytesIO(st.session_state.pdf_data),
                file_name=f"relatorio_{st.session_state.mes_atual}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    # --- CÁLCULOS PRINCIPAIS ---
    mes_n = MESES[st.session_state.mes_atual]
    ano_r = st.session_state.ano_atual
    t_fix = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
    t_cas = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
    total_guias = sum([calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), mes_n, ano_r)[1] for g in st.session_state.guias_extras])
    total_renda = st.session_state.renda_detalhada["Valor (R$)"].sum()
    sobra = total_renda - (t_fix + t_cas + total_guias)

    st.title(f"💰 {st.session_state.mes_atual} / {st.session_state.ano_atual}")
    opcoes = ["Resumo Geral", "Renda", "Gastos Fixos", "Dia a Dia"] + st.session_state.guias_extras
    sel = st.selectbox("Ir para:", opcoes)

    if sel == "Resumo Geral":
        c1,c2,c3 = st.columns(3)
        c1.metric("Gasto", f"R$ {t_fix+t_cas+total_guias:,.2f}")
        c2.metric("Sobra", f"R$ {sobra:,.2f}")
        c3.metric("Renda", f"R$ {total_renda:,.2f}")
        st.plotly_chart(px.pie(pd.DataFrame({"C":["Fixos","Dia a Dia","Guias","Sobra"],"V":[t_fix,t_cas,total_guias,max(0,sobra)]}), values='V', names='C', hole=.4), use_container_width=True)

    elif sel == "Renda":
        er = st.data_editor(st.session_state.renda_detalhada, num_rows="dynamic", use_container_width=True, hide_index=True)
        if not er.equals(st.session_state.renda_detalhada):
            st.session_state.renda_detalhada = er
            salvar_dados_nuvem()

    elif sel == "Gastos Fixos":
        if st.button("🔄 Importar"):
            carregar_dados_sessao(True)
            salvar_dados_nuvem()
            st.rerun()
        ef = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True)
        if not ef.equals(st.session_state.gastos_fixos):
            st.session_state.gastos_fixos = ef
            salvar_dados_nuvem()

    elif sel == "Dia a Dia":
        ec = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Categoria": st.column_config.SelectboxColumn(options=get_categorias())})
        if not ec.equals(st.session_state.gastos_casuais):
            st.session_state.gastos_casuais = ec
            salvar_dados_nuvem()

    else: # Guias extras
        df_p, tot, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{sel}"), mes_n, ano_r)
        st.subheader(f"Total: R$ {tot:,.2f}")
        de = st.data_editor(st.session_state[f"dados_{sel}"], num_rows="dynamic", use_container_width=True, hide_index=True)
        if not de.equals(st.session_state[f"dados_{sel}"]):
            st.session_state[f"dados_{sel}"] = de
            salvar_dados_nuvem()
            st.rerun()
