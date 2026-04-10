import streamlit as st
import pandas as pd
import json
import gspread
import plotly.express as px
import math
import re
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from fpdf import FPDF
import unicodedata
import tempfile
import os

# --- TENTAR IMPORTAR GEMINI (Nova SDK) ---
try:
    from google import genai
    GEMINI_DISPONIVEL = True
except ImportError:
    GEMINI_DISPONIVEL = False

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

    # --- VERIFICAÇÃO E INICIALIZAÇÃO DO GEMINI ---
    gemini_ok = False
    client = None

    if GEMINI_DISPONIVEL and "GEMINI_API_KEY" in st.secrets:
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            gemini_ok = True
        except Exception as e:
            st.warning(f"Erro ao inicializar Gemini: {e}")
    elif not GEMINI_DISPONIVEL:
        st.warning("Biblioteca 'google-genai' não instalada. IA desativada.")
    elif "GEMINI_API_KEY" not in st.secrets:
        st.warning("Chave GEMINI_API_KEY não encontrada nos secrets. IA desativada.")
            
    # --- CONSTANTES ---
    MESES = {"Janeiro":1,"Fevereiro":2,"Março":3,"Abril":4,"Maio":5,"Junho":6,
             "Julho":7,"Agosto":8,"Setembro":9,"Outubro":10,"Novembro":11,"Dezembro":12}
    CATEGORIAS_PADRAO_BASE = ["Alimentação","Transporte","Lazer","Saúde","Casa","Trabalho","Outros"]

    # --- FUNÇÕES DE FORMATAÇÃO BRASILEIRA ---
    def formatar_moeda_br(valor):
        if valor is None:
            valor = 0.0
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def moeda_para_float(valor_str):
        if valor_str is None or valor_str == "":
            return 0.0
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        s = str(valor_str).strip()
        s = re.sub(r'^R\$', '', s)
        s = s.replace(" ", "")
        s = s.replace(",", ".")
        s = re.sub(r'[^\d.-]', '', s)
        if s.count('.') > 1:
            partes = s.split('.')
            s = ''.join(partes[:-1]) + '.' + partes[-1]
        try:
            return float(s)
        except:
            return 0.0

    # --- FUNÇÕES SEGURAS DE LIMPEZA ---
    def safe_float(val, default=0.0):
        try:
            if pd.isna(val): return default
            v = float(val)
            if math.isnan(v) or math.isinf(v): return default
            return v
        except: return default

    def safe_int(val, default=1):
        try:
            if pd.isna(val): return default
            v = float(val)
            if math.isnan(v) or math.isinf(v): return default
            return int(v)
        except: return default

    def safe_str(val):
        try:
            if pd.isna(val): return ""
            return str(val).strip()
        except: return ""

    def safe_bool(val):
        try:
            if pd.isna(val): return False
            return str(val).strip().lower() in ['true', '1', 't', 'y', 'yes']
        except: return False

    # --- CONEXÃO GOOGLE SHEETS ---
    @st.cache_resource
    def ligar_google_sheets():
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds).open_by_url(st.secrets["url_planilha"])

    # --- LEITURA DOS DADOS (COM CONVERSÃO DE MOEDA) ---
    def carregar_dados_nuvem_raw():
        db_conn = ligar_google_sheets()
        try:
            ws_casuais = db_conn.worksheet("Casuais")
            ws_fixos = db_conn.worksheet("Fixos")
            ws_guias = db_conn.worksheet("Guias")
            ws_config = db_conn.worksheet("Configuracoes")
        except gspread.exceptions.WorksheetNotFound as e:
            st.error(f"Erro: Aba '{e}' não encontrada. Verifique a planilha.")
            return {
                "historico_casuais": {},
                "historico_fixos": {},
                "guias_extras": [],
                "categorias_personalizadas": [],
                "categorias_padrao": CATEGORIAS_PADRAO_BASE.copy(),
                "renda_por_mes": {},
                "metas_orcamento": {}
            }, False

        all_casuais = ws_casuais.get_all_values()
        all_fixos = ws_fixos.get_all_values()
        all_guias = ws_guias.get_all_values()
        config_val = ws_config.acell('A1').value

        # Processa Casuais
        hist_casuais = {}
        if len(all_casuais) > 1:
            for row in all_casuais[1:]:
                if len(row) < 5: continue
                mes_ano = safe_str(row[0])
                if not mes_ano: continue
                data = safe_str(row[1])
                categoria = safe_str(row[2])
                descricao = safe_str(row[3])
                valor = moeda_para_float(row[4])
                if mes_ano not in hist_casuais:
                    hist_casuais[mes_ano] = []
                hist_casuais[mes_ano].append({
                    "Data": data,
                    "Categoria": categoria,
                    "Descrição": descricao,
                    "Valor (R$)": valor
                })

        # Processa Fixos
        hist_fixos = {}
        if len(all_fixos) > 1:
            for row in all_fixos[1:]:
                if len(row) < 5: continue
                mes_ano = safe_str(row[0])
                if not mes_ano: continue
                descricao = safe_str(row[1])
                categoria = safe_str(row[2])
                valor = moeda_para_float(row[3])
                pago = safe_bool(row[4])
                if mes_ano not in hist_fixos:
                    hist_fixos[mes_ano] = []
                hist_fixos[mes_ano].append({
                    "Descrição": descricao,
                    "Categoria": categoria,
                    "Valor (R$)": valor,
                    "Pago": pago
                })

        # Processa Guias
        dict_guias = {}
        if len(all_guias) > 1:
            for row in all_guias[1:]:
                if len(row) < 7: continue
                guia = safe_str(row[0])
                if not guia: continue
                descricao = safe_str(row[1])
                categoria = safe_str(row[2])
                valor_parcela = moeda_para_float(row[3])
                mes_ini = safe_int(row[4], 1)
                ano_ini = safe_int(row[5], 2026)
                qtd = safe_int(row[6], 1)
                if guia not in dict_guias:
                    dict_guias[guia] = []
                dict_guias[guia].append({
                    "Descrição": descricao,
                    "Categoria": categoria,
                    "Valor Parcela (R$)": valor_parcela,
                    "Mês Início (1-12)": mes_ini,
                    "Ano Início": ano_ini,
                    "Qtd Parcelas": qtd
                })

        # Configurações
        try:
            config = json.loads(config_val) if config_val else {}
        except:
            config = {}

        result = {
            "historico_casuais": hist_casuais,
            "historico_fixos": hist_fixos,
            "guias_extras": config.get("guias_extras", []),
            "categorias_personalizadas": config.get("categorias_personalizadas", []),
            "categorias_padrao": config.get("categorias_padrao", CATEGORIAS_PADRAO_BASE.copy()),
            "renda_por_mes": config.get("renda_por_mes", {}),
            "metas_orcamento": config.get("metas_orcamento", {})
        }
        for g in result["guias_extras"]:
            result[f"dados_{g}"] = dict_guias.get(g, [])

        return result, False

    # --- ESCRITA SEGURA (protegida) ---
    def salvar_dados_nuvem():
        db_conn = ligar_google_sheets()

        total_fixos = sum(item.get("Valor (R$)", 0) for lista in st.session_state.historico_fixos.values() for item in lista)
        total_casuais = sum(item.get("Valor (R$)", 0) for lista in st.session_state.historico_casuais.values() for item in lista)
        if total_fixos == 0 and total_casuais == 0 and len(st.session_state.guias_extras) == 0:
            st.error("⚠️ Tentativa de salvar dados vazios! Operação cancelada.")
            return

        chave = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
        casuais_save = st.session_state.gastos_casuais.copy()
        if "Data" in casuais_save.columns:
            casuais_save["Data"] = pd.to_datetime(casuais_save["Data"]).dt.date.astype(str)

        st.session_state.historico_fixos[chave] = st.session_state.gastos_fixos.to_dict("records")
        st.session_state.historico_casuais[chave] = casuais_save.to_dict("records")
        st.session_state.renda_por_mes[chave] = st.session_state.renda_detalhada.to_dict("records")

        for g in st.session_state.guias_extras:
            if f"dados_{g}" in st.session_state:
                st.session_state[f"dados_raw_{g}"] = st.session_state[f"dados_{g}"].to_dict("records")

        # Preparar dados planos
        flat_casuais = [["Mes_Ano", "Data", "Categoria", "Descrição", "Valor"]]
        for ma, itens in st.session_state.historico_casuais.items():
            for item in itens:
                flat_casuais.append([safe_str(ma), safe_str(item.get("Data","")), safe_str(item.get("Categoria","")), safe_str(item.get("Descrição","")), safe_float(item.get("Valor (R$)"), 0.0)])

        flat_fixos = [["Mes_Ano", "Descrição", "Categoria", "Valor", "Pago"]]
        for ma, itens in st.session_state.historico_fixos.items():
            for item in itens:
                flat_fixos.append([safe_str(ma), safe_str(item.get("Descrição","")), safe_str(item.get("Categoria","")), safe_float(item.get("Valor (R$)"), 0.0), safe_bool(item.get("Pago",False))])

        flat_guias = [["Guia", "Descrição", "Categoria", "Valor Parcela", "Mês Início", "Ano Início", "Qtd Parcelas"]]
        for g in st.session_state.guias_extras:
            itens = st.session_state.get(f"dados_raw_{g}", [])
            for item in itens:
                flat_guias.append([
                    safe_str(g),
                    safe_str(item.get("Descrição","")),
                    safe_str(item.get("Categoria","")),
                    safe_float(item.get("Valor Parcela (R$)"), 0.0),
                    safe_int(item.get("Mês Início (1-12)"), 1),
                    safe_int(item.get("Ano Início"), 2026),
                    safe_int(item.get("Qtd Parcelas"), 1)
                ])

        renda_limpa = {}
        for ma, itens in st.session_state.renda_por_mes.items():
            renda_limpa[safe_str(ma)] = [{"Fonte": safe_str(i.get("Fonte","")), "Valor (R$)": safe_float(i.get("Valor (R$)",0))} for i in itens]

        config_json = {
            "guias_extras": [safe_str(x) for x in st.session_state.guias_extras],
            "categorias_personalizadas": [safe_str(x) for x in st.session_state.categorias_personalizadas],
            "categorias_padrao": [safe_str(x) for x in st.session_state.categorias_padrao],
            "renda_por_mes": renda_limpa,
            "metas_orcamento": {safe_str(k): safe_float(v) for k, v in st.session_state.metas_orcamento.items()}
        }

        ws_casuais = db_conn.worksheet("Casuais")
        ws_casuais.clear()
        ws_casuais.update(values=flat_casuais, range_name='A1')

        ws_fixos = db_conn.worksheet("Fixos")
        ws_fixos.clear()
        ws_fixos.update(values=flat_fixos, range_name='A1')

        ws_guias = db_conn.worksheet("Guias")
        ws_guias.clear()
        if len(flat_guias) > 1:
            ws_guias.update(values=flat_guias, range_name='A1')
        else:
            ws_guias.update(values=[flat_guias[0]], range_name='A1')

        ws_config = db_conn.worksheet("Configuracoes")
        ws_config.clear()
        ws_config.update(values=[[json.dumps(config_json, default=str)]], range_name='A1')

        st.toast("💾 Dados salvos na nuvem!", icon="✅")

    # --- DEMAIS FUNÇÕES AUXILIARES ---
    def obter_mes_anterior(mes_nome, ano_atual):
        lista = list(MESES.keys())
        idx = lista.index(mes_nome)
        return (lista[idx-1], ano_atual) if idx>0 else ("Dezembro", ano_atual-1)

    def carregar_dados_sessao(importar_do_anterior=False):
        chave_atual = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
        if importar_do_anterior:
            m_ant, a_ant = obter_mes_anterior(st.session_state.mes_atual, st.session_state.ano_atual)
            chave_ant = f"{m_ant}_{a_ant}"
            if chave_ant in st.session_state.historico_fixos:
                df_base = pd.DataFrame(st.session_state.historico_fixos[chave_ant])
                if not df_base.empty:
                    df_base["Pago"] = False
                    if "Categoria" not in df_base.columns: df_base["Categoria"] = "Outros"
                    st.session_state.gastos_fixos = df_base
                    st.success(f"Importado de {m_ant}!")
                else:
                    st.warning("Mês anterior vazio.")
            else:
                st.error("Sem dados no mês anterior.")
            return

        st.session_state.gastos_fixos = pd.DataFrame(st.session_state.historico_fixos.get(chave_atual, []))
        if st.session_state.gastos_fixos.empty:
            st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição","Valor (R$)","Pago","Categoria"])
        else:
            if "Categoria" not in st.session_state.gastos_fixos.columns:
                st.session_state.gastos_fixos["Categoria"] = "Outros"

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
                m_i = safe_int(r["Mês Início (1-12)"])
                a_i = safe_int(r["Ano Início"])
                qtd = safe_int(r["Qtd Parcelas"])
                v = safe_float(r["Valor Parcela (R$)"])
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

    # --- FUNÇÕES DE PDF (usando formatação brasileira) ---
    def remover_acentos(texto):
        if not isinstance(texto, str): texto = str(texto)
        return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')

    def formatar_moeda_pdf(valor):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def gerar_pdf_mes(mes_nome, ano, renda_df, fixos_df, casuais_df, guias_dados, total_renda, t_fix, t_cas, t_gui, sobra, dados_categoria):
        pdf = FPDF()
        pdf.add_page()
        COR_TOPO = (46, 125, 50)
        COR_TITULO_SECAO = (225, 225, 225)
        COR_LINHA_DIVISORIA = (220, 220, 220)
        
        pdf.set_font('helvetica', 'B', 16)
        pdf.set_fill_color(*COR_TOPO)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 12, remover_acentos(f"EXTRATO FINANCEIRO - {mes_nome.upper()} {ano}"), ln=True, align="C", fill=True)
        pdf.ln(4)
        pdf.set_text_color(0, 0, 0)
        
        def imprimir_secao(titulo, total, df, tipo="padrao"):
            pdf.set_font('helvetica', 'B', 11)
            pdf.set_fill_color(*COR_TITULO_SECAO)
            pdf.set_draw_color(120, 120, 120) 
            pdf.cell(140, 8, remover_acentos(f"  {titulo}"), border='TB', fill=True)
            pdf.cell(50, 8, formatar_moeda_pdf(total), border='TB', ln=True, align="R", fill=True)
            pdf.set_draw_color(*COR_LINHA_DIVISORIA)
            pdf.set_font('helvetica', '', 9)
            if df is None or df.empty:
                pdf.cell(190, 6, "  Nenhum registro.", border='B', ln=True)
                pdf.ln(3)
                return
            for _, row in df.iterrows():
                if tipo == "renda": texto_esq = f"  {row['Fonte']}"
                elif tipo == "fixos":
                    status = "(Pago)" if row.get("Pago", False) else "(Pendente)"
                    texto_esq = f"  {row.get('Descrição', '')} [{row.get('Categoria', '')}] {status}"
                elif tipo == "casuais":
                    d_str = row['Data'].strftime("%d/%m") if hasattr(row['Data'],'strftime') else str(row['Data'])[:5]
                    texto_esq = f"  {d_str} | {row.get('Categoria', '')} - {row.get('Descrição', '')}"
                if len(texto_esq) > 85: texto_esq = texto_esq[:82] + "..."
                pdf.cell(140, 6, remover_acentos(texto_esq), border='B')
                pdf.cell(50, 6, formatar_moeda_pdf(row['Valor (R$)']), border='B', ln=True, align="R")
            pdf.ln(4)

        imprimir_secao("Renda Mensal", total_renda, renda_df, "renda")
        imprimir_secao("Despesas Fixas", t_fix, fixos_df, "fixos")
        imprimir_secao("Despesas do Dia a Dia", t_cas, casuais_df, "casuais")
        
        pdf.set_font('helvetica', 'B', 11)
        pdf.set_fill_color(*COR_TITULO_SECAO)
        pdf.set_draw_color(120, 120, 120)
        pdf.cell(140, 8, remover_acentos("  Guias (Cartões e Parcelamentos)"), border='TB', fill=True)
        pdf.cell(50, 8, formatar_moeda_pdf(t_gui), border='TB', ln=True, align="R", fill=True)
        pdf.set_draw_color(*COR_LINHA_DIVISORIA)
        
        if not guias_dados:
            pdf.set_font('helvetica', '', 9)
            pdf.cell(190, 6, "  Nenhuma guia extra.", border='B', ln=True)
        else:
            for guia, parcelas in guias_dados.items():
                if not parcelas: continue
                pdf.set_font('helvetica', 'B', 9)
                pdf.set_fill_color(245, 245, 245)
                pdf.cell(190, 6, remover_acentos(f"    Fatura: {guia}"), border='B', ln=True, fill=True)
                pdf.set_font('helvetica', '', 9)
                for row in parcelas:
                    linha_texto = f"        - {row['Descrição']} ({row['Categoria']})"
                    if len(linha_texto) > 75: linha_texto = linha_texto[:72] + "..."
                    pdf.cell(140, 6, remover_acentos(linha_texto), border='B')
                    pdf.cell(50, 6, formatar_moeda_pdf(row['Valor (R$)']), border='B', ln=True, align="R")
        pdf.ln(4)
        
        pdf.set_font('helvetica', 'B', 11)
        pdf.set_fill_color(*COR_TITULO_SECAO)
        pdf.set_draw_color(120, 120, 120)
        pdf.cell(140, 8, remover_acentos("  Resumo de Gastos por Categoria"), border='TB', fill=True)
        pdf.cell(50, 8, "", border='TB', ln=True, align="R", fill=True)
        pdf.set_font('helvetica', '', 9)
        pdf.set_draw_color(*COR_LINHA_DIVISORIA)
        for cat, valor in sorted(dados_categoria.items(), key=lambda x: x[1], reverse=True):
            pdf.cell(140, 6, remover_acentos(f"  {cat}"), border='B')
            pdf.cell(50, 6, formatar_moeda_pdf(valor), border='B', ln=True, align="R")
        pdf.ln(6)
        
        pdf.set_font('helvetica', 'B', 12)
        if sobra >= 0:
            pdf.set_fill_color(220, 255, 220); pdf.set_text_color(0, 100, 0); pdf.set_draw_color(0, 150, 0)
        else:
            pdf.set_fill_color(255, 220, 220); pdf.set_text_color(150, 0, 0); pdf.set_draw_color(200, 0, 0)
        pdf.cell(140, 10, remover_acentos("  SALDO LÍQUIDO DO MÊS:"), border=1, fill=True)
        pdf.cell(50, 10, formatar_moeda_pdf(sobra), border=1, ln=True, align="R", fill=True)
        pdf.set_text_color(0,0,0)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp: temp_path = tmp.name
        pdf.output(temp_path)
        with open(temp_path, "rb") as f: pdf_data = f.read()
        os.remove(temp_path)
        return pdf_data

# --- FUNÇÕES DE IA (GEMINI) ---
    
    # 1. Funções internas (O Cache só guarda se der certo)
    @st.cache_data(ttl=3600)
    def api_analise_gemini(prompt_text):
        try:
            # Tenta usar o modelo 2.5 Flash (que está no seu painel)
            resposta = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_text
            )
            return resposta.text
        except Exception as e:
            if "404" in str(e):
                # Se o 2.5 der 404, cai automaticamente para o 2.0 Flash
                resposta = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt_text
                )
                return resposta.text
            raise e

    @st.cache_data(ttl=86400)
    def api_sugestao_gemini(prompt_text):
        try:
            resposta = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_text
            )
            return resposta.text.strip()
        except Exception as e:
            if "404" in str(e):
                resposta = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt_text
                )
                return resposta.text.strip()
            raise e

    # 2. Funções do aplicativo (Tratam erros de limite sem memorizá-los)
    def analise_financeira_gemini(renda_total, despesa_total, sobra, gastos_categoria):
        if not gemini_ok or client is None:
            return "IA não disponível. Verifique a chave da API."
        
        top_categorias = sorted(gastos_categoria.items(), key=lambda x: x[1], reverse=True)[:3]
        texto_categorias = ", ".join([f"{cat} (R$ {val:,.2f})" for cat, val in top_categorias])
        
        prompt = f"""
        Você é um assistente financeiro. Analise os dados do mês:
        Renda: R$ {renda_total:.2f}
        Despesas: R$ {despesa_total:.2f}
        Sobra: R$ {sobra:.2f}
        Top categorias: {texto_categorias}
        Forneça um feedback curto (max 80 palavras) e uma dica prática direta.
        """
        try:
            return api_analise_gemini(prompt)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                return "⚠️ O limite gratuito de IA foi atingido. Aguarde cerca de 1 minuto e tente novamente."
            return f"Erro na IA: {e}"

    def sugerir_categoria_gemini(descricao):
        if not gemini_ok or client is None:
            return "Outros"
            
        categorias_disponiveis = get_categorias()
        prompt = f"""
        Com base na descrição da despesa, sugira a categoria mais adequada.
        Opções: {', '.join(categorias_disponiveis)}.
        Descrição: "{descricao}"
        Responda APENAS com o nome da categoria.
        """
        try:
            return api_sugestao_gemini(prompt)
        except Exception as e:
            return "Outros"
        
    # --- INICIALIZAÇÃO ---
    if "dados_carregados" not in st.session_state:
        with st.spinner("Carregando dados da nuvem..."):
            dados_raw, _ = carregar_dados_nuvem_raw()
        hj = datetime.now()
        st.session_state.ano_atual = hj.year
        st.session_state.mes_atual = list(MESES.keys())[hj.month-1]

        st.session_state.historico_casuais = dados_raw.get("historico_casuais", {})
        st.session_state.historico_fixos = dados_raw.get("historico_fixos", {})
        st.session_state.guias_extras = dados_raw.get("guias_extras", [])
        st.session_state.categorias_personalizadas = dados_raw.get("categorias_personalizadas", [])
        st.session_state.categorias_padrao = dados_raw.get("categorias_padrao", CATEGORIAS_PADRAO_BASE.copy())
        st.session_state.renda_por_mes = dados_raw.get("renda_por_mes", {})
        st.session_state.metas_orcamento = dados_raw.get("metas_orcamento", {})

        if len(st.session_state.categorias_padrao) != len(CATEGORIAS_PADRAO_BASE):
            st.session_state.categorias_padrao = CATEGORIAS_PADRAO_BASE.copy()

        for g in st.session_state.guias_extras:
            dados_g = dados_raw.get(f"dados_{g}", [])
            st.session_state[f"dados_{g}"] = pd.DataFrame(dados_g)
            if st.session_state[f"dados_{g}"].empty:
                st.session_state[f"dados_{g}"] = pd.DataFrame(columns=["Descrição","Valor Parcela (R$)","Mês Início (1-12)","Ano Início","Qtd Parcelas","Categoria"])

        carregar_dados_sessao()
        st.session_state.dados_carregados = True

    if "pdf_ready" not in st.session_state: st.session_state.pdf_ready = False
    if "pdf_data" not in st.session_state: st.session_state.pdf_data = None

    def get_categorias():
        return st.session_state.categorias_padrao + st.session_state.categorias_personalizadas

    # --- SIDEBAR (configurações, PDF, categorias, guias) ---
    with st.sidebar:
        st.header("⚙️ Configurações")
        if st.button("🔄 Recarregar Nuvem"):
            for key in ["dados_carregados", "historico_fixos", "historico_casuais", "guias_extras", 
                        "categorias_personalizadas", "categorias_padrao", "renda_por_mes", "metas_orcamento"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

        m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
        a_sel = st.number_input("Ano:", 2024, 2030, st.session_state.ano_atual)
        if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
            salvar_dados_nuvem()
            st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
            carregar_dados_sessao()
            st.session_state.pdf_ready = False
            st.rerun()

        st.divider()
        if st.button("📄 1. Preparar Relatório PDF"):
            with st.spinner("Construindo o arquivo..."):
                mes_n = MESES[st.session_state.mes_atual]
                ano_r = st.session_state.ano_atual
                t_fix_p = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
                t_cas_p = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
                total_guias_p = 0.0
                gastos_cat_p = {}
                for _, row in st.session_state.gastos_fixos.iterrows():
                    cat = row.get("Categoria", "Outros")
                    gastos_cat_p[cat] = gastos_cat_p.get(cat, 0.0) + row["Valor (R$)"]
                for _, row in st.session_state.gastos_casuais.iterrows():
                    cat = row["Categoria"]
                    gastos_cat_p[cat] = gastos_cat_p.get(cat, 0.0) + row["Valor (R$)"]
                guias_dados_p = {}
                for guia in st.session_state.guias_extras:
                    df_parc, tot, cats = calc_parc_com_categoria(st.session_state.get(f"dados_{guia}"), mes_n, ano_r)
                    total_guias_p += tot
                    for cat, val in cats.items(): gastos_cat_p[cat] = gastos_cat_p.get(cat, 0.0) + val
                    guias_dados_p[guia] = df_parc.to_dict('records')
                total_renda_p = st.session_state.renda_detalhada["Valor (R$)"].sum()
                sobra_p = total_renda_p - (t_fix_p + t_cas_p + total_guias_p)

                st.session_state.pdf_data = gerar_pdf_mes(
                    st.session_state.mes_atual, st.session_state.ano_atual,
                    st.session_state.renda_detalhada, st.session_state.gastos_fixos,
                    st.session_state.gastos_casuais, guias_dados_p,
                    total_renda_p, t_fix_p, t_cas_p, total_guias_p, sobra_p, gastos_cat_p
                )
                st.session_state.pdf_ready = True
                st.success("✅ Arquivo pronto! Clique abaixo para salvar.")

        if st.session_state.pdf_ready and st.session_state.pdf_data is not None:
            st.download_button(
                label="📥 2. Baixar PDF Agora",
                data=st.session_state.pdf_data,
                file_name=f"relatorio_{st.session_state.mes_atual}_{st.session_state.ano_atual}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        # --- GERENCIAMENTO DE CATEGORIAS ---
        st.divider()
        st.subheader("🏷️ Gerenciar Categorias")
        with st.expander("⚙️ Opções de categorias"):
            nova_cat = st.text_input("Nova categoria personalizada:", key="nova_cat_input")
            if st.button("➕ Adicionar", key="add_cat"):
                if nova_cat and nova_cat not in get_categorias():
                    st.session_state.categorias_personalizadas.append(nova_cat)
                    salvar_dados_nuvem()
                    st.rerun()
                else: st.warning("Categoria já existe ou nome inválido.")
            
            st.markdown("---")
            st.write("✏️ **Editar categorias existentes**")
            cat_para_editar = st.selectbox("Selecione a categoria:", get_categorias(), key="cat_edit_select")
            is_padrao = cat_para_editar in st.session_state.categorias_padrao
            is_personalizada = cat_para_editar in st.session_state.categorias_personalizadas
            
            if is_padrao: st.info("📌 Categoria padrão (apenas renomeável).")
            elif is_personalizada: st.info("✨ Categoria personalizada (pode editar ou apagar).")
            
            novo_nome_cat = st.text_input("Novo nome:", key="novo_nome_cat")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✏️ Renomear", key="rename_cat"):
                    if novo_nome_cat and novo_nome_cat not in get_categorias():
                        antigo = cat_para_editar
                        if is_padrao:
                            st.session_state.categorias_padrao[st.session_state.categorias_padrao.index(antigo)] = novo_nome_cat
                        else:
                            st.session_state.categorias_personalizadas[st.session_state.categorias_personalizadas.index(antigo)] = novo_nome_cat
                        
                        if not st.session_state.gastos_fixos.empty: st.session_state.gastos_fixos.loc[st.session_state.gastos_fixos["Categoria"] == antigo, "Categoria"] = novo_nome_cat
                        if not st.session_state.gastos_casuais.empty: st.session_state.gastos_casuais.loc[st.session_state.gastos_casuais["Categoria"] == antigo, "Categoria"] = novo_nome_cat
                        for guia in st.session_state.guias_extras:
                            df_g = st.session_state[f"dados_{guia}"]
                            if not df_g.empty and "Categoria" in df_g.columns:
                                df_g.loc[df_g["Categoria"] == antigo, "Categoria"] = novo_nome_cat
                                st.session_state[f"dados_{guia}"] = df_g
                        salvar_dados_nuvem()
                        st.success(f"Renomeada para '{novo_nome_cat}'.")
                        st.rerun()
            with col2:
                if is_personalizada:
                    if st.button("🗑️ Apagar", key="delete_cat"):
                        if cat_para_editar:
                            st.session_state.categorias_personalizadas.remove(cat_para_editar)
                            if not st.session_state.gastos_fixos.empty: st.session_state.gastos_fixos.loc[st.session_state.gastos_fixos["Categoria"] == cat_para_editar, "Categoria"] = "Outros"
                            if not st.session_state.gastos_casuais.empty: st.session_state.gastos_casuais.loc[st.session_state.gastos_casuais["Categoria"] == cat_para_editar, "Categoria"] = "Outros"
                            for guia in st.session_state.guias_extras:
                                df_g = st.session_state[f"dados_{guia}"]
                                if not df_g.empty and "Categoria" in df_g.columns:
                                    df_g.loc[df_g["Categoria"] == cat_para_editar, "Categoria"] = "Outros"
                                    st.session_state[f"dados_{guia}"] = df_g
                            salvar_dados_nuvem()
                            st.rerun()

        # --- GERENCIAMENTO DE GUIAS ---
        st.divider()
        st.subheader("🛠️ Gerenciar Guias")
        with st.expander("⚙️ Opções de gerenciamento"):
            ng = st.text_input("Nova Guia:")
            if st.button("➕ Criar", key="add_guia"):
                if ng and ng not in st.session_state.guias_extras:
                    st.session_state.guias_extras.append(ng)
                    st.session_state[f"dados_{ng}"] = pd.DataFrame(columns=["Descrição","Valor Parcela (R$)","Mês Início (1-12)","Ano Início","Qtd Parcelas","Categoria"])
                    salvar_dados_nuvem()
                    st.rerun()
            if st.session_state.guias_extras:
                g_ativa = st.selectbox("Guia para editar:", st.session_state.guias_extras, key="guia_edit")
                novo_nome = st.text_input("Renomear para:", key="rename_guia")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📝 Renomear", key="rename_guia_btn"):
                        if novo_nome and novo_nome not in st.session_state.guias_extras:
                            idx = st.session_state.guias_extras.index(g_ativa)
                            st.session_state.guias_extras[idx] = novo_nome
                            st.session_state[f"dados_{novo_nome}"] = st.session_state[f"dados_{g_ativa}"]
                            del st.session_state[f"dados_{g_ativa}"]
                            salvar_dados_nuvem()
                            st.rerun()
                with col2:
                    if st.button("🗑️ Apagar", key="delete_guia"):
                        st.session_state.guias_extras.remove(g_ativa)
                        if f"dados_{g_ativa}" in st.session_state: del st.session_state[f"dados_{g_ativa}"]
                        salvar_dados_nuvem()
                        st.rerun()

                st.markdown("---")
                st.write("🔼 Reordenar Guias")
                guia_mover = st.selectbox("Selecione a guia:", st.session_state.guias_extras, key="guia_mover")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("⬆️ Mover Cima", key="move_up"):
                        idx = st.session_state.guias_extras.index(guia_mover)
                        if idx>0:
                            st.session_state.guias_extras[idx], st.session_state.guias_extras[idx-1] = st.session_state.guias_extras[idx-1], st.session_state.guias_extras[idx]
                            salvar_dados_nuvem()
                            st.rerun()
                with col_b:
                    if st.button("⬇️ Mover Baixo", key="move_down"):
                        idx = st.session_state.guias_extras.index(guia_mover)
                        if idx < len(st.session_state.guias_extras)-1:
                            st.session_state.guias_extras[idx], st.session_state.guias_extras[idx+1] = st.session_state.guias_extras[idx+1], st.session_state.guias_extras[idx]
                            salvar_dados_nuvem()
                            st.rerun()
                            
        # --- BOTÃO DE SAIR ---
        st.divider()
        if st.button("🚪 Sair do App", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
            
    # --- CÁLCULOS PRINCIPAIS ---
    mes_n = MESES[st.session_state.mes_atual]
    ano_r = st.session_state.ano_atual
    t_fix = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
    t_cas = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
    
    total_guias = 0.0
    gastos_categoria = {}
    for _, row in st.session_state.gastos_fixos.iterrows():
        cat = row.get("Categoria", "Outros")
        gastos_categoria[cat] = gastos_categoria.get(cat, 0.0) + row["Valor (R$)"]
    for _, row in st.session_state.gastos_casuais.iterrows():
        cat = row["Categoria"]
        gastos_categoria[cat] = gastos_categoria.get(cat, 0.0) + row["Valor (R$)"]
    for guia in st.session_state.guias_extras:
        _, tot_guia, cats_guia = calc_parc_com_categoria(st.session_state.get(f"dados_{guia}"), mes_n, ano_r)
        total_guias += tot_guia
        for cat, val in cats_guia.items():
            gastos_categoria[cat] = gastos_categoria.get(cat, 0.0) + val
    
    total_renda = st.session_state.renda_detalhada["Valor (R$)"].sum()
    sobra = total_renda - (t_fix + t_cas + total_guias)

    st.title(f"💰 {st.session_state.mes_atual} / {st.session_state.ano_atual}")

    opcoes = ["Resumo Geral", "Renda", "Gastos Fixos", "Dia a Dia", "Resumo das Guias", "Metas de Orçamento", "Pesquisa Global"] + st.session_state.guias_extras
    sel = st.selectbox("Navegação do App:", opcoes)
    st.divider()

    if sel == "Resumo Geral":
        gt = t_fix + t_cas + total_guias
        c1, c2, c3 = st.columns(3)
        c1.metric("Gasto Total", formatar_moeda_br(gt))
        c2.metric("Sobra Real", formatar_moeda_br(sobra), delta=f"{(sobra/total_renda)*100:.1f}%" if total_renda>0 else "0%")
        c3.metric("Renda Total", formatar_moeda_br(total_renda))
        fig = px.pie(pd.DataFrame({"C":["Fixos","Dia a Dia","Guias","Sobra"],"V":[t_fix,t_cas,total_guias,max(0,sobra)]}), values='V', names='C', hole=.4)
        fig.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=300)
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("📈 Evolução Financeira Anual")
        historico_df_dados = []
        chaves_todas = set(list(st.session_state.historico_fixos.keys()) + list(st.session_state.historico_casuais.keys()) + list(st.session_state.renda_por_mes.keys()))
        if chaves_todas:
            for chave in chaves_todas:
                try:
                    mes_str, ano_str = chave.split('_')
                    mes_idx = MESES.get(mes_str, 1)
                    ano_num = int(ano_str)
                    
                    df_fixos = pd.DataFrame(st.session_state.historico_fixos.get(chave, []))
                    tot_f = df_fixos['Valor (R$)'].sum() if not df_fixos.empty and 'Valor (R$)' in df_fixos.columns else 0.0
                    
                    df_cas = pd.DataFrame(st.session_state.historico_casuais.get(chave, []))
                    tot_c = df_cas['Valor (R$)'].sum() if not df_cas.empty and 'Valor (R$)' in df_cas.columns else 0.0
                    
                    tot_g = 0.0
                    for g in st.session_state.guias_extras:
                        _, t_g, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), mes_idx, ano_num)
                        tot_g += t_g
                        
                    df_ren = pd.DataFrame(st.session_state.renda_por_mes.get(chave, []))
                    tot_r = df_ren['Valor (R$)'].sum() if not df_ren.empty and 'Valor (R$)' in df_ren.columns else 0.0
                    
                    tot_d = tot_f + tot_c + tot_g
                    
                    historico_df_dados.append({
                        "Data_Sort": datetime(ano_num, mes_idx, 1),
                        "Mês": f"{mes_str}/{ano_str}",
                        "Renda": tot_r,
                        "Despesas": tot_d,
                        "Sobra": tot_r - tot_d
                    })
                except: continue
                
            if historico_df_dados:
                df_hist = pd.DataFrame(historico_df_dados).sort_values("Data_Sort")
                fig_hist = px.line(df_hist, x="Mês", y=["Renda", "Despesas", "Sobra"], markers=True)
                st.plotly_chart(fig_hist, use_container_width=True)

        st.divider()
        if st.button("🤖 Análise da IA para este mês"):
            with st.spinner("Consultando o Gemini..."):
                analise = analise_financeira_gemini(total_renda, gt, sobra, gastos_categoria)
            st.info(analise)

    elif sel == "Renda":
        st.subheader("💵 Fontes de Renda")
        er = st.data_editor(
            st.session_state.renda_detalhada,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Valor (R$)": st.column_config.NumberColumn(min_value=0, format="R$ %.2f")
            }
        )
        if not er.equals(st.session_state.renda_detalhada):
            st.session_state.renda_detalhada = er
            salvar_dados_nuvem()

    elif sel == "Gastos Fixos":
        ct, cb = st.columns([3,1])
        with ct:
            st.subheader("📌 Contas Fixas")
            st.subheader(f"Total no Mês: {formatar_moeda_br(t_fix)}")
        with cb:
            st.write("")
            if st.button("🔄 Importar de Mês Anterior"):
                carregar_dados_sessao(True)
                salvar_dados_nuvem()
                st.rerun()

        with st.expander("➕ Lançamento Rápido de Fixos", expanded=False):
            with st.form("form_novo_fixo"):
                c1, c2, c3 = st.columns([2, 1, 1])
                n_desc = c1.text_input("Descrição do Gasto")
                n_cat = c2.selectbox("Categoria", get_categorias())
                n_val = c3.number_input("Valor (R$)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Guardar Lançamento"):
                    if n_desc:
                        nova_linha = pd.DataFrame([{"Descrição": n_desc, "Valor (R$)": n_val, "Pago": False, "Categoria": n_cat}])
                        st.session_state.gastos_fixos = pd.concat([st.session_state.gastos_fixos, nova_linha], ignore_index=True)
                        salvar_dados_nuvem()
                        st.success("Adicionado com sucesso!")
                        st.rerun()
                    else: st.warning("Por favor, preencha a descrição.")
            
            st.divider()
            desc_temp = st.text_input("Não sabe a categoria? Digite a descrição aqui para sugestão:", key="desc_sugestao_fixo")
            if st.button("✨ Sugerir categoria via IA", key="sugerir_fixo"):
                if desc_temp and gemini_ok:
                    with st.spinner("IA pensando..."):
                        sugestao = sugerir_categoria_gemini(desc_temp)
                        st.info(f"A categoria sugerida é: **{sugestao}**")

        ef = st.data_editor(
            st.session_state.gastos_fixos,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0),
                "Pago": st.column_config.CheckboxColumn(),
                "Categoria": st.column_config.SelectboxColumn(options=get_categorias())
            }
        )
        if not ef.equals(st.session_state.gastos_fixos):
            st.session_state.gastos_fixos = ef
            salvar_dados_nuvem()

    elif sel == "Dia a Dia":
        st.subheader("🛍️ Compras Casuais")
        st.subheader(f"Total no Mês: {formatar_moeda_br(t_cas)}")

        with st.expander("➕ Lançamento Rápido do Dia a Dia", expanded=False):
            with st.form("form_novo_casual"):
                c1, c2 = st.columns(2)
                n_data = c1.date_input("Data do Registo", datetime.now().date())
                n_desc = st.text_input("Descrição da Compra")
                n_cat = c2.selectbox("Categoria", get_categorias())
                n_val = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
                if st.form_submit_button("Guardar Registo"):
                    if n_desc:
                        nova_linha = pd.DataFrame([{"Data": n_data, "Categoria": n_cat, "Descrição": n_desc, "Valor (R$)": n_val}])
                        st.session_state.gastos_casuais = pd.concat([st.session_state.gastos_casuais, nova_linha], ignore_index=True)
                        salvar_dados_nuvem()
                        st.success("Compra registada com sucesso!")
                        st.rerun()
                    else: st.warning("A descrição não pode estar vazia.")
            
            st.divider()
            desc_temp = st.text_input("Não sabe a categoria? Digite a descrição aqui para sugestão:", key="desc_sugestao_casual")
            if st.button("✨ Sugerir categoria via IA", key="sugerir_casual"):
                if desc_temp and gemini_ok:
                    with st.spinner("IA pensando..."):
                        sugestao = sugerir_categoria_gemini(desc_temp)
                        st.info(f"A categoria sugerida é: **{sugestao}**")

        ec = st.data_editor(
            st.session_state.gastos_casuais,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Categoria": st.column_config.SelectboxColumn(options=get_categorias()),
                "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0)
            }
        )
        if not ec.equals(st.session_state.gastos_casuais):
            st.session_state.gastos_casuais = ec
            salvar_dados_nuvem()

    elif sel == "Metas de Orçamento":
        st.subheader("🎯 Metas e Limites Mensais")
        st.write("Defina um orçamento para cada categoria e acompanhe seus gastos.")
        
        with st.expander("➕ Adicionar Nova Meta", expanded=False):
            with st.form("form_metas"):
                todas_categorias = get_categorias()
                cat_meta = st.selectbox("Categoria:", todas_categorias, key="meta_cat_select")
                val_meta = st.number_input("Orçamento Máximo (R$):", min_value=0.0, step=50.0, format="%.2f", key="meta_val")
                if st.form_submit_button("💾 Salvar Meta"):
                    if val_meta > 0:
                        st.session_state.metas_orcamento[cat_meta] = val_meta
                        salvar_dados_nuvem()
                        st.success(f"Meta para '{cat_meta}' definida em {formatar_moeda_br(val_meta)}")
                        st.rerun()
                    else:
                        st.warning("O valor deve ser maior que zero.")
        
        st.markdown("---")
        metas_ativas = st.session_state.metas_orcamento
        if not metas_ativas:
            st.info("Nenhuma meta definida. Use o formulário acima para criar seu primeiro orçamento.")
        else:
            for cat, limite in list(metas_ativas.items()):
                gasto_atual = gastos_categoria.get(cat, 0.0)
                perc = (gasto_atual / limite) if limite > 0 else 0
                perc_visual = min(perc, 1.0)
                
                col1, col2, col3 = st.columns([2, 3, 1])
                with col1:
                    st.write(f"**{cat}**")
                    st.caption(f"Meta: {formatar_moeda_br(limite)}")
                with col2:
                    st.write(f"Gasto atual: {formatar_moeda_br(gasto_atual)} ({(perc*100):.1f}%)")
                    st.progress(perc_visual)
                    if perc >= 1.0:
                        st.error(f"⚠️ Excedido em {formatar_moeda_br(gasto_atual - limite)}")
                with col3:
                    if st.button("✏️", key=f"edit_meta_{cat}"):
                        st.session_state.edit_meta_cat = cat
                        st.session_state.edit_meta_val = limite
                        st.rerun()
                    if st.button("🗑️", key=f"del_meta_{cat}"):
                        del st.session_state.metas_orcamento[cat]
                        salvar_dados_nuvem()
                        st.success(f"Meta para '{cat}' removida.")
                        st.rerun()
                st.divider()
            
            if "edit_meta_cat" in st.session_state:
                with st.expander(f"✏️ Editando meta para {st.session_state.edit_meta_cat}", expanded=True):
                    with st.form("edit_meta_form"):
                        novo_valor = st.number_input(
                            "Novo valor (R$):", 
                            min_value=0.0, 
                            value=st.session_state.edit_meta_val, 
                            step=50.0, 
                            format="%.2f"
                        )
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.form_submit_button("✅ Atualizar"):
                                st.session_state.metas_orcamento[st.session_state.edit_meta_cat] = novo_valor
                                salvar_dados_nuvem()
                                del st.session_state.edit_meta_cat
                                st.success("Meta atualizada!")
                                st.rerun()
                        with col_btn2:
                            if st.form_submit_button("❌ Cancelar"):
                                del st.session_state.edit_meta_cat
                                st.rerun()

    elif sel == "Pesquisa Global":
        st.subheader("🔍 Procurar no Histórico")
        termo = st.text_input("Escreva uma palavra (Ex: Colchão, Amazon, Combustível, Médico):").strip().lower()
        if termo:
            resultados = []
            for chave, df_list in st.session_state.historico_fixos.items():
                for row in df_list:
                    if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                        resultados.append({"Referência": chave, "Tipo": "Despesa Fixa", "Data": "-", "Categoria": row.get('Categoria',''), "Descrição": row.get('Descrição',''), "Valor": formatar_moeda_br(row.get('Valor (R$)',0))})
            for chave, df_list in st.session_state.historico_casuais.items():
                for row in df_list:
                    if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                        resultados.append({"Referência": chave, "Tipo": "Dia a Dia", "Data": row.get('Data','-'), "Categoria": row.get('Categoria',''), "Descrição": row.get('Descrição',''), "Valor": formatar_moeda_br(row.get('Valor (R$)',0))})
            for g in st.session_state.guias_extras:
                df_g = st.session_state.get(f"dados_{g}")
                if df_g is not None and not df_g.empty:
                    for _, row in df_g.iterrows():
                        if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                            resultados.append({"Referência": f"Fatura: {g}", "Tipo": "Parcelamento", "Data": f"Mês {row.get('Mês Início (1-12)')}/{row.get('Ano Início')}", "Categoria": row.get('Categoria',''), "Descrição": row.get('Descrição',''), "Valor": formatar_moeda_br(row.get('Valor Parcela (R$)',0))})
            if resultados:
                df_res = pd.DataFrame(resultados)
                st.success(f"Foram encontrados {len(df_res)} registos em toda a sua conta!")
                st.dataframe(df_res, use_container_width=True, hide_index=True)
            else:
                st.warning("Não foi encontrado nenhum registo com essa palavra. Tente outro termo.")

    elif sel == "Resumo das Guias":
        st.subheader("📊 Comparativo de Custos por Guia")
        dados_guias = []
        for g in st.session_state.guias_extras:
            _, tot, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), mes_n, ano_r)
            dados_guias.append({"Guia": g, "Custo Total (R$)": tot})
        if dados_guias:
            df_guias = pd.DataFrame(dados_guias)
            total_geral = df_guias['Custo Total (R$)'].sum()
            st.metric("💰 Total Geral de Todas as Guias", formatar_moeda_br(total_geral))
            df_guias['Custo Total (R$)'] = df_guias['Custo Total (R$)'].apply(formatar_moeda_br)
            st.dataframe(df_guias, use_container_width=True, hide_index=True)
            # Gráfico (usar valores numéricos)
            df_guias_num = pd.DataFrame(dados_guias)
            if not df_guias_num.empty:
                fig_guias = px.bar(df_guias_num, x="Guia", y="Custo Total (R$)", color="Guia", text_auto='.2f')
                st.plotly_chart(fig_guias, use_container_width=True)
        else:
            st.info("Nenhuma guia extra criada.")
        
        st.divider()
        st.subheader("📊 Gastos por Categoria (Geral do Mês)")
        if gastos_categoria:
            df_cat = pd.DataFrame(gastos_categoria.items(), columns=["Categoria","Valor (R$)"]).sort_values("Valor (R$)", ascending=False)
            df_cat['Valor (R$)'] = df_cat['Valor (R$)'].apply(formatar_moeda_br)
            st.dataframe(df_cat, use_container_width=True, hide_index=True)
            # Gráfico
            df_cat_num = pd.DataFrame(gastos_categoria.items(), columns=["Categoria","Valor (R$)"]).sort_values("Valor (R$)", ascending=False)
            if not df_cat_num.empty:
                fig_cat = px.bar(df_cat_num, x="Categoria", y="Valor (R$)", color="Categoria", text_auto='.2f')
                st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("Nenhum gasto registado neste mês.")

    else:  # --- ABAS INDIVIDUAIS DAS GUIAS EXTRAS ---
        df_parc, total_parc, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{sel}"), mes_n, ano_r)
        st.subheader(f"Total no Mês: {formatar_moeda_br(total_parc)}")
        if not df_parc.empty:
            df_parc['Valor (R$)'] = df_parc['Valor (R$)'].apply(formatar_moeda_br)
            st.dataframe(df_parc, use_container_width=True, hide_index=True)
        st.divider()
        
        with st.expander(f"➕ Novo Lançamento em {sel}", expanded=False):
            with st.form(f"form_nova_guia_{sel}"):
                c1, c2 = st.columns(2)
                n_desc = c1.text_input("Descrição da Compra")
                n_cat = c2.selectbox("Categoria", get_categorias())
                
                c3, c4, c5, c6 = st.columns(4)
                n_val = c3.number_input("Valor Parcela (R$)", min_value=0.0, format="%.2f")
                n_qtd = c4.number_input("Qtd Parcelas", min_value=1, step=1, value=1)
                n_mes_ini = c5.number_input("Mês Início", min_value=1, max_value=12, step=1, value=mes_n)
                n_ano_ini = c6.number_input("Ano Início", min_value=2000, max_value=2050, step=1, value=ano_r)
                
                if st.form_submit_button("Guardar Lançamento"):
                    if n_desc:
                        nova_linha = pd.DataFrame([{
                            "Descrição": n_desc, 
                            "Valor Parcela (R$)": n_val, 
                            "Mês Início (1-12)": n_mes_ini,
                            "Ano Início": n_ano_ini,
                            "Qtd Parcelas": n_qtd,
                            "Categoria": n_cat
                        }])
                        st.session_state[f"dados_{sel}"] = pd.concat([st.session_state[f"dados_{sel}"], nova_linha], ignore_index=True)
                        salvar_dados_nuvem()
                        st.success("Lançamento adicionado com sucesso!")
                        st.rerun()
                    else:
                        st.warning("Por favor, preencha a descrição.")

            st.divider()
            desc_temp = st.text_input("Dúvida na categoria? Digite a descrição para sugestão:", key=f"desc_sugestao_{sel}")
            if st.button("✨ Sugerir categoria via IA", key=f"sugerir_guia_{sel}"):
                if desc_temp and gemini_ok:
                    with st.spinner("IA analisando..."):
                        sugestao = sugerir_categoria_gemini(desc_temp)
                        st.info(f"Sugestão da IA: **{sugestao}**")

        st.write("**Base de Lançamentos (parcelas):**")
        de = st.data_editor(
            st.session_state[f"dados_{sel}"],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Valor Parcela (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0),
                "Mês Início (1-12)": st.column_config.NumberColumn(min_value=1, max_value=12, step=1),
                "Ano Início": st.column_config.NumberColumn(min_value=2000, max_value=2030, step=1),
                "Qtd Parcelas": st.column_config.NumberColumn(min_value=1, step=1),
                "Categoria": st.column_config.SelectboxColumn(options=get_categorias())
            }
        )
        if not de.equals(st.session_state[f"dados_{sel}"]):
            st.session_state[f"dados_{sel}"] = de
            salvar_dados_nuvem()
            st.rerun()
