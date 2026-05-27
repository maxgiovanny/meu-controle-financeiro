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
import io

# --- TENTAR IMPORTAR GEMINI (Nova SDK) ---
try:
    from google import genai
    GEMINI_DISPONIVEL = True
except ImportError:
    GEMINI_DISPONIVEL = False

# --- 1. FUNÇÃO DE SEGURANÇA (LOGIN MULTI-USUÁRIO) ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 Acesso Restrito")
    
    with st.form("login_form"):
        usuario_digitado = st.text_input("Usuário:").strip().lower()
        senha_digitada = st.text_input("Senha:", type="password")
        botao_entrar = st.form_submit_button("Entrar")

        if botao_entrar:
            if "usuarios" in st.secrets and usuario_digitado in st.secrets["usuarios"]:
                dados_usuario = st.secrets["usuarios"][usuario_digitado]
                if senha_digitada == dados_usuario["senha"]:
                    st.session_state["password_correct"] = True
                    st.session_state["usuario_logado"] = usuario_digitado
                    st.session_state["url_planilha"] = dados_usuario["url_planilha"]
                    st.rerun()
                else:
                    st.error("😕 Senha inválida. Tente novamente.")
            else:
                st.error("🚫 Usuário não encontrado.")
                
    return False

# --- 2. INÍCIO DO APLICATIVO ---
if check_password():
    st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="centered", initial_sidebar_state="expanded")

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

    # --- CONEXÃO GOOGLE SHEETS (com tratamento de erros) ---
    @st.cache_resource
    def ligar_google_sheets(url_da_planilha):
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        try:
            return gspread.authorize(creds).open_by_url(url_da_planilha)
        except Exception as e:
            st.error(f"❌ Não foi possível acessar a planilha. Verifique a URL e as permissões. Erro: {e}")
            st.stop()
        
    # --- LEITURA DOS DADOS (robusta) ---
    def carregar_dados_nuvem_raw():
        db_conn = ligar_google_sheets(st.session_state["url_planilha"])
        try:
            ws_casuais = db_conn.worksheet("Casuais")
            ws_fixos = db_conn.worksheet("Fixos")
            ws_guias = db_conn.worksheet("Guias")
            ws_config = db_conn.worksheet("Configuracoes")
        except gspread.exceptions.WorksheetNotFound as e:
            st.error(f"Erro: Aba '{e}' não encontrada. Verifique a planilha e execute novamente.")
            st.stop()
        except Exception as e:
            st.error(f"Erro ao acessar a planilha: {e}. Tente recarregar.")
            st.stop()

        try:
            all_casuais = ws_casuais.get_all_values()
            all_fixos = ws_fixos.get_all_values()
            all_guias = ws_guias.get_all_values()
            config_val = ws_config.acell('A1').value
        except Exception as e:
            st.error(f"Erro ao ler dados da planilha: {e}")
            st.stop()

        try:
            ws_investimentos = db_conn.worksheet("Investimentos")
            all_invest = ws_investimentos.get_all_values()
        except:
            all_invest = []

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

        hist_fixos = {}
        if len(all_fixos) > 1:
            for row in all_fixos[1:]:
                if len(row) < 6: continue   # agora espera 6 colunas (inclui Data de Vencimento)
                mes_ano = safe_str(row[0])
                if not mes_ano: continue
                descricao = safe_str(row[1])
                categoria = safe_str(row[2])
                valor = moeda_para_float(row[3])
                pago = safe_bool(row[4])
                vencimento_str = safe_str(row[5])
                vencimento = None
                if vencimento_str:
                    try: vencimento = datetime.strptime(vencimento_str, "%Y-%m-%d").date()
                    except: pass
                if mes_ano not in hist_fixos:
                    hist_fixos[mes_ano] = []
                hist_fixos[mes_ano].append({
                    "Descrição": descricao,
                    "Categoria": categoria,
                    "Valor (R$)": valor,
                    "Pago": pago,
                    "Data de Vencimento": vencimento
                })

        dict_guias = {}
        if len(all_guias) > 1:
            for row in all_guias[1:]:
                if len(row) < 7: continue
                guia = safe_str(row[0])
                if not guia: continue
                descricao = safe_str(row[1])
                categoria = safe_str(row[2])
                valor_parcela = moeda_para_float(row[3])
                
                num_cols = len(row)
                if num_cols >= 9:
                    data_compra_str = safe_str(row[4])
                    mes_ini = safe_int(row[5], 1)
                    ano_ini = safe_int(row[6], 2026)
                    qtd = safe_int(row[7], 1)
                elif num_cols >= 8:
                    data_compra_str = safe_str(row[4])
                    mes_ini = safe_int(row[5], 1)
                    ano_ini = safe_int(row[6], 2026)
                    qtd = safe_int(row[7], 1)
                else:
                    data_compra_str = ""
                    mes_ini = safe_int(row[4], 1)
                    ano_ini = safe_int(row[5], 2026)
                    qtd = safe_int(row[6], 1)
                
                data_compra = None
                if data_compra_str:
                    try: data_compra = datetime.strptime(data_compra_str, "%Y-%m-%d").date()
                    except: pass
                
                if guia not in dict_guias:
                    dict_guias[guia] = []
                dict_guias[guia].append({
                    "Descrição": descricao,
                    "Categoria": categoria,
                    "Valor Parcela (R$)": valor_parcela,
                    "Data da Compra": data_compra,
                    "Mês Início (1-12)": mes_ini,
                    "Ano Início": ano_ini,
                    "Qtd Parcelas": qtd
                })

        hist_invest = []
        if len(all_invest) > 1:
            for row in all_invest[1:]:
                if len(row) < 6: continue
                hist_invest.append({
                    "Data": safe_str(row[0]),
                    "Ativo": safe_str(row[1]),
                    "Classe": safe_str(row[2]),
                    "Tipo": safe_str(row[3]),
                    "Valor (R$)": moeda_para_float(row[4]),
                    "Descrição": safe_str(row[5])
                })

        try:
            config = json.loads(config_val) if config_val else {}
        except:
            config = {}

        result = {
            "historico_casuais": hist_casuais,
            "historico_fixos": hist_fixos,
            "historico_investimentos": hist_invest,
            "guias_extras": config.get("guias_extras", []),
            "categorias_personalizadas": config.get("categorias_personalizadas", []),
            "categorias_padrao": config.get("categorias_padrao", CATEGORIAS_PADRAO_BASE.copy()),
            "renda_por_mes": config.get("renda_por_mes", {}),
            "metas_orcamento": config.get("metas_orcamento", {}),
            "pagamento_guias": config.get("pagamento_guias", {}),
            "modelos_fixos": config.get("modelos_fixos", []),
            "meta_sobra": config.get("meta_sobra", 0.0)
        }
        for g in result["guias_extras"]:
            result[f"dados_{g}"] = dict_guias.get(g, [])

        return result, False

    # --- ESCRITA SEGURA (protegida) ---
    def salvar_dados_nuvem():
        db_conn = ligar_google_sheets(st.session_state["url_planilha"])

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

        flat_casuais = [["Mes_Ano", "Data", "Categoria", "Descrição", "Valor"]]
        for ma, itens in st.session_state.historico_casuais.items():
            for item in itens:
                flat_casuais.append([safe_str(ma), safe_str(item.get("Data","")), safe_str(item.get("Categoria","")), safe_str(item.get("Descrição","")), safe_float(item.get("Valor (R$)"), 0.0)])

        flat_fixos = [["Mes_Ano", "Descrição", "Categoria", "Valor", "Pago", "Data de Vencimento"]]
        for ma, itens in st.session_state.historico_fixos.items():
            for item in itens:
                venc = item.get("Data de Vencimento")
                venc_str = ""
                if hasattr(venc, 'strftime') and not pd.isna(venc):
                    venc_str = venc.strftime("%Y-%m-%d")
                flat_fixos.append([safe_str(ma), safe_str(item.get("Descrição","")), safe_str(item.get("Categoria","")), safe_float(item.get("Valor (R$)"), 0.0), safe_bool(item.get("Pago",False)), venc_str])

        flat_guias = [["Guia", "Descrição", "Categoria", "Valor Parcela", "Data Compra", "Mês Início", "Ano Início", "Qtd Parcelas"]]
        for g in st.session_state.guias_extras:
            itens = st.session_state.get(f"dados_raw_{g}", [])
            for item in itens:
                data_compra = item.get("Data da Compra")
                if isinstance(data_compra, datetime) and not pd.isna(data_compra):
                    data_str = data_compra.strftime("%Y-%m-%d")
                elif hasattr(data_compra, 'strftime') and not pd.isna(data_compra):
                    try:
                        data_str = data_compra.strftime("%Y-%m-%d")
                    except:
                        data_str = ""
                else:
                    data_str = str(data_compra) if data_compra else ""
                flat_guias.append([
                    safe_str(g),
                    safe_str(item.get("Descrição","")),
                    safe_str(item.get("Categoria","")),
                    safe_float(item.get("Valor Parcela (R$)"), 0.0),
                    data_str,
                    safe_int(item.get("Mês Início (1-12)"), 1),
                    safe_int(item.get("Ano Início"), 2026),
                    safe_int(item.get("Qtd Parcelas"), 1)
                ])

        flat_invest = [["Data", "Ativo", "Classe", "Tipo", "Valor", "Descrição"]]
        if "dados_investimentos" in st.session_state:
            for _, item in st.session_state.dados_investimentos.iterrows():
                d_str = item["Data"].strftime("%Y-%m-%d") if hasattr(item.get("Data"), 'strftime') else safe_str(item.get("Data"))
                flat_invest.append([d_str, safe_str(item.get("Ativo","")), safe_str(item.get("Classe","")), safe_str(item.get("Tipo","")), safe_float(item.get("Valor (R$)"), 0.0), safe_str(item.get("Descrição",""))])

        renda_limpa = {}
        for ma, itens in st.session_state.renda_por_mes.items():
            renda_limpa[safe_str(ma)] = [{"Fonte": safe_str(i.get("Fonte","")), "Valor (R$)": safe_float(i.get("Valor (R$)",0))} for i in itens]

        config_json = {
            "guias_extras": [safe_str(x) for x in st.session_state.guias_extras],
            "categorias_personalizadas": [safe_str(x) for x in st.session_state.categorias_personalizadas],
            "categorias_padrao": [safe_str(x) for x in st.session_state.categorias_padrao],
            "renda_por_mes": renda_limpa,
            "metas_orcamento": {safe_str(k): safe_float(v) for k, v in st.session_state.metas_orcamento.items()},
            "pagamento_guias": {safe_str(k): bool(v) for k, v in st.session_state.pagamento_guias.items()},
            "modelos_fixos": st.session_state.modelos_fixos,
            "meta_sobra": st.session_state.meta_sobra
        }

        try:
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

            try:
                ws_invest = db_conn.worksheet("Investimentos")
                ws_invest.clear()
                ws_invest.update(values=flat_invest, range_name='A1')
            except:
                pass 
            st.toast("💾 Dados salvos na nuvem!", icon="✅")
        except Exception as e:
            st.error(f"❌ Erro ao salvar dados: {e}")

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
                    if "Data de Vencimento" not in df_base.columns: df_base["Data de Vencimento"] = None
                    st.session_state.gastos_fixos = df_base
                    st.success(f"Importado de {m_ant}!")
                else:
                    st.warning("Mês anterior vazio.")
            else:
                st.error("Sem dados no mês anterior.")
            return

        fixos_existentes = st.session_state.historico_fixos.get(chave_atual, [])
        if not fixos_existentes and st.session_state.modelos_fixos:
            novos = []
            for modelo in st.session_state.modelos_fixos:
                novos.append({
                    "Descrição": modelo.get("descricao", ""),
                    "Categoria": modelo.get("categoria", "Outros"),
                    "Valor (R$)": safe_float(modelo.get("valor", 0)),
                    "Pago": False,
                    "Data de Vencimento": modelo.get("vencimento", None)
                })
            st.session_state.historico_fixos[chave_atual] = novos
            st.session_state.gastos_fixos = pd.DataFrame(novos)
        else:
            st.session_state.gastos_fixos = pd.DataFrame(fixos_existentes)
            if st.session_state.gastos_fixos.empty:
                st.session_state.gastos_fixos = pd.DataFrame(columns=["Descrição","Valor (R$)","Pago","Categoria","Data de Vencimento"])
            else:
                if "Categoria" not in st.session_state.gastos_fixos.columns:
                    st.session_state.gastos_fixos["Categoria"] = "Outros"
                if "Data de Vencimento" not in st.session_state.gastos_fixos.columns:
                    st.session_state.gastos_fixos["Data de Vencimento"] = None

        df_c = pd.DataFrame(st.session_state.historico_casuais.get(chave_atual, []))
        if not df_c.empty:
            df_c["Data"] = pd.to_datetime(df_c["Data"]).dt.date
        st.session_state.gastos_casuais = df_c if not df_c.empty else pd.DataFrame(columns=["Data","Categoria","Descrição","Valor (R$)"])

        renda_data = st.session_state.renda_por_mes.get(chave_atual)
        if renda_data:
            st.session_state.renda_detalhada = pd.DataFrame(renda_data)
        else:
            st.session_state.renda_detalhada = pd.DataFrame([{"Fonte":"Salário","Valor (R$)":0.0}])

    @st.cache_data(ttl=3600)
    def calc_parc_com_categoria_cached(_df_json, m, a):
    df = pd.read_json(io.StringIO(_df_json)) if _df_json else pd.DataFrame()
    parcelas = []
    if df is None or df.empty:
        return pd.DataFrame(columns=["Descrição","Categoria","Valor (R$)"]).to_dict('records'), 0.0, {}
    df_valid = df.dropna(subset=["Descrição","Valor Parcela (R$)"])
    for _, r in df_valid[df_valid["Descrição"]!=""].iterrows():
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
    return df_parc.to_dict('records'), total, soma_cat

    def calc_parc_com_categoria(df, m, a):
        if df is None or df.empty:
            return pd.DataFrame(), 0.0, {}
        json_str = df.to_json()
        records, total, cats = calc_parc_com_categoria_cached(json_str, m, a)
        return pd.DataFrame(records), total, cats

    # --- FUNÇÕES DE PDF ---
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
    @st.cache_data(ttl=3600)
    def api_analise_gemini(prompt_text):
        try:
            resposta = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_text)
            return resposta.text
        except Exception as e:
            if "404" in str(e) or "503" in str(e):
                resposta = client.models.generate_content(model="gemini-1.5-flash", contents=prompt_text)
                return resposta.text
            raise e

    @st.cache_data(ttl=86400)
    def api_sugestao_gemini(prompt_text):
        try:
            resposta = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_text)
            return resposta.text.strip()
        except Exception as e:
            if "404" in str(e) or "503" in str(e):
                resposta = client.models.generate_content(model="gemini-1.5-flash", contents=prompt_text)
                return resposta.text.strip()
            raise e

    def analise_financeira_gemini(renda_total, despesa_total, sobra, gastos_categoria):
        if not gemini_ok or client is None: return "IA não disponível."
        top_categorias = sorted(gastos_categoria.items(), key=lambda x: x[1], reverse=True)[:3]
        texto_categorias = ", ".join([f"{cat} (R$ {val:,.2f})" for cat, val in top_categorias])
        prompt = f"""
        Você é um assistente financeiro. Analise os dados do mês:
        Renda: R$ {renda_total:.2f}
        Despesas: R$ {despesa_total:.2f}
        Sobra: R$ {sobra:.2f}
        Top categorias: {texto_categorias}
        Forneça um feedback (max 150 palavras) e uma dica prática direta.
        """
        try:
            return api_analise_gemini(prompt)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower(): return "⚠️ Limite de IA atingido. Tente depois."
            if "503" in str(e): return "⏳ A IA está com alta demanda. Tente depois."
            return f"Erro na IA: {e}"

    def sugerir_categoria_gemini(descricao):
        if not gemini_ok or client is None: return "Outros"
        categorias_disponiveis = get_categorias()
        prompt = f"""Com base na descrição, sugira a categoria mais adequada.\nOpções: {', '.join(categorias_disponiveis)}.\nDescrição: "{descricao}"\nResponda APENAS com o nome."""
        try:
            return api_sugestao_gemini(prompt)
        except: return "Outros"      

    def extrair_dados_recibo_gemini(imagem_pil):
        if not gemini_ok or client is None: return None
        categorias_disponiveis = get_categorias()
        prompt = f"""
        Extraia as informações do recibo e retorne EXATAMENTE no formato JSON abaixo, sem markdown (```json).
        {{
            "descricao": "Nome do local",
            "valor": 0.00,
            "categoria": "Uma destas: {', '.join(categorias_disponiveis)}",
            "data": "YYYY-MM-DD"
        }}
        """
        try:
            resposta = client.models.generate_content(model="gemini-2.5-flash", contents=[imagem_pil, prompt])
            texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
            import json
            return json.loads(texto_limpo)
        except Exception as e:
            st.error(f"Erro ao extrair: {e}")
            return None
    
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
        st.session_state.pagamento_guias = dados_raw.get("pagamento_guias", {})
        st.session_state.modelos_fixos = dados_raw.get("modelos_fixos", [])
        st.session_state.meta_sobra = dados_raw.get("meta_sobra", 0.0)

        if len(st.session_state.categorias_padrao) != len(CATEGORIAS_PADRAO_BASE):
            st.session_state.categorias_padrao = CATEGORIAS_PADRAO_BASE.copy()

        colunas_guia = ["Descrição", "Valor Parcela (R$)", "Data da Compra", "Mês Início (1-12)", "Ano Início", "Qtd Parcelas", "Categoria"]
        for g in st.session_state.guias_extras:
            dados_g = dados_raw.get(f"dados_{g}", [])
            if dados_g:
                df = pd.DataFrame(dados_g)
                for col in colunas_guia:
                    if col not in df.columns:
                        if col == "Data da Compra":
                            df[col] = None
                        else:
                            df[col] = None
                if "Data da Compra" in df.columns:
                    df["Data da Compra"] = pd.to_datetime(df["Data da Compra"], errors='coerce')
                    df["Data da Compra"] = df["Data da Compra"].apply(lambda x: x.date() if isinstance(x, datetime) and not pd.isna(x) else None)
                st.session_state[f"dados_{g}"] = df
            else:
                st.session_state[f"dados_{g}"] = pd.DataFrame(columns=colunas_guia)
            if g not in st.session_state.pagamento_guias:
                st.session_state.pagamento_guias[g] = False

        dados_inv = dados_raw.get("historico_investimentos", [])
        if dados_inv:
            df_inv = pd.DataFrame(dados_inv)
            df_inv["Data"] = pd.to_datetime(df_inv["Data"], errors='coerce').dt.date
            st.session_state.dados_investimentos = df_inv
        else:
            st.session_state.dados_investimentos = pd.DataFrame(columns=["Data", "Ativo", "Classe", "Tipo", "Valor (R$)", "Descrição"])

        carregar_dados_sessao()
        st.session_state.dados_carregados = True

    if "pdf_ready" not in st.session_state: st.session_state.pdf_ready = False
    if "pdf_data" not in st.session_state: st.session_state.pdf_data = None

    def get_categorias():
        return st.session_state.categorias_padrao + st.session_state.categorias_personalizadas

    # --- SIDEBAR ---
    opcoes = ["Resumo Geral", "Renda", "Gastos Fixos", "Dia a Dia", "Investimentos", "Cartões e Guias", "Resumo das Guias", "Metas de Orçamento", "Pesquisa Global"]

    with st.sidebar:
        st.markdown(f"<h3 style='text-align: center;'>👤 Olá, {str(st.session_state.get('usuario_logado', '')).title()}</h3>", unsafe_allow_html=True)
        st.markdown("---")
        
        st.subheader("📅 Mês de Referência")
        
        c_esq, c_meio, c_dir = st.columns([1, 2, 1])
        lista_meses = list(MESES.keys())
        idx_mes_atual = lista_meses.index(st.session_state.mes_atual)

        with c_esq:
            if st.button("◀", use_container_width=True, key="btn_mes_ant"):
                if idx_mes_atual == 0:
                    st.session_state.mes_atual = lista_meses[11]
                    st.session_state.ano_atual -= 1
                else:
                    st.session_state.mes_atual = lista_meses[idx_mes_atual - 1]
                salvar_dados_nuvem()
                carregar_dados_sessao()
                st.session_state.pdf_ready = False
                st.rerun()

        with c_meio:
            st.markdown(f"<div style='text-align: center; font-weight: bold; margin-top: 5px; font-size: 16px;'>{st.session_state.mes_atual}<br><span style='font-size: 12px; color: #A0A0A0;'>{st.session_state.ano_atual}</span></div>", unsafe_allow_html=True)

        with c_dir:
            if st.button("▶", use_container_width=True, key="btn_mes_prox"):
                if idx_mes_atual == 11:
                    st.session_state.mes_atual = lista_meses[0]
                    st.session_state.ano_atual += 1
                else:
                    st.session_state.mes_atual = lista_meses[idx_mes_atual + 1]
                salvar_dados_nuvem()
                carregar_dados_sessao()
                st.session_state.pdf_ready = False
                st.rerun()
                
        st.markdown("---")
        st.subheader("Navegação Principal")
        sel = st.radio("", opcoes, label_visibility="collapsed")
        
        st.markdown("---")
        st.subheader("⚙️ Configurações")

        if st.button("🔄 Recarregar Nuvem", use_container_width=True):
            for key in ["dados_carregados", "historico_fixos", "historico_casuais", "guias_extras", 
                        "categorias_personalizadas", "categorias_padrao", "renda_por_mes", "metas_orcamento",
                        "dados_investimentos", "pagamento_guias", "modelos_fixos", "meta_sobra"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

        # Meta de poupança
        st.divider()
        st.subheader("💰 Meta de Poupança Mensal")
        nova_meta = st.number_input("Valor desejado (R$):", min_value=0.0, step=100.0, value=st.session_state.meta_sobra, format="%.2f")
        if nova_meta != st.session_state.meta_sobra:
            st.session_state.meta_sobra = nova_meta
            salvar_dados_nuvem()
            st.rerun()

        # Modelos de gastos fixos
        st.divider()
        st.subheader("📋 Modelos de Gastos Fixos")
        with st.expander("Gerenciar modelos"):
            st.caption("Esses gastos serão carregados automaticamente em um novo mês.")
            for i, modelo in enumerate(st.session_state.modelos_fixos):
                col1, col2, col3, col4 = st.columns([3,2,2,1])
                with col1:
                    st.write(modelo.get("descricao",""))
                with col2:
                    st.write(formatar_moeda_br(safe_float(modelo.get("valor",0))))
                with col3:
                    st.write(modelo.get("categoria","Outros"))
                with col4:
                    if st.button("🗑️", key=f"del_modelo_{i}"):
                        st.session_state.modelos_fixos.pop(i)
                        salvar_dados_nuvem()
                        st.rerun()
            with st.form("novo_modelo"):
                m_desc = st.text_input("Descrição*", help="Nome do gasto recorrente")
                m_cat = st.selectbox("Categoria", get_categorias())
                m_val = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
                m_venc = st.date_input("Vencimento (opcional)", value=None, help="Data de vencimento típica")
                if st.form_submit_button("Adicionar modelo"):
                    if m_desc:
                        st.session_state.modelos_fixos.append({
                            "descricao": m_desc,
                            "categoria": m_cat,
                            "valor": m_val,
                            "vencimento": m_venc.strftime("%Y-%m-%d") if m_venc else None
                        })
                        salvar_dados_nuvem()
                        st.rerun()

        st.divider()
        if st.button("📄 1. Preparar Relatório PDF", use_container_width=True):
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

        # Gerenciar categorias (com confirmação)
        st.divider()
        st.subheader("🏷️ Gerenciar Categorias")
        with st.expander("Opções de categorias"):
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
                        if "confirm_delete_cat" not in st.session_state or st.session_state.confirm_delete_cat != cat_para_editar:
                            st.session_state.confirm_delete_cat = cat_para_editar
                            st.warning(f"Tem certeza que deseja apagar '{cat_para_editar}'? Todos os gastos dessa categoria serão movidos para 'Outros'.")
                        else:
                            st.session_state.categorias_personalizadas.remove(cat_para_editar)
                            if not st.session_state.gastos_fixos.empty: st.session_state.gastos_fixos.loc[st.session_state.gastos_fixos["Categoria"] == cat_para_editar, "Categoria"] = "Outros"
                            if not st.session_state.gastos_casuais.empty: st.session_state.gastos_casuais.loc[st.session_state.gastos_casuais["Categoria"] == cat_para_editar, "Categoria"] = "Outros"
                            for guia in st.session_state.guias_extras:
                                df_g = st.session_state[f"dados_{guia}"]
                                if not df_g.empty and "Categoria" in df_g.columns:
                                    df_g.loc[df_g["Categoria"] == cat_para_editar, "Categoria"] = "Outros"
                                    st.session_state[f"dados_{guia}"] = df_g
                            salvar_dados_nuvem()
                            del st.session_state.confirm_delete_cat
                            st.rerun()

        st.divider()
        st.subheader("🛠️ Gerenciar Guias")
        with st.expander("Opções de gerenciamento"):
            ng = st.text_input("Nova Guia/Cartão:")
            if st.button("➕ Criar", key="add_guia"):
                if ng and ng not in st.session_state.guias_extras:
                    st.session_state.guias_extras.append(ng)
                    colunas_guia = ["Descrição","Valor Parcela (R$)","Data da Compra","Mês Início (1-12)","Ano Início","Qtd Parcelas","Categoria"]
                    st.session_state[f"dados_{ng}"] = pd.DataFrame(columns=colunas_guia)
                    st.session_state.pagamento_guias[ng] = False
                    salvar_dados_nuvem()
                    st.rerun()
            if st.session_state.guias_extras:
                g_ativa = st.selectbox("Cartão para editar:", st.session_state.guias_extras, key="guia_edit")
                novo_nome = st.text_input("Renomear para:", key="rename_guia")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📝 Renomear", key="rename_guia_btn"):
                        if novo_nome and novo_nome not in st.session_state.guias_extras:
                            idx = st.session_state.guias_extras.index(g_ativa)
                            st.session_state.guias_extras[idx] = novo_nome
                            st.session_state[f"dados_{novo_nome}"] = st.session_state[f"dados_{g_ativa}"]
                            del st.session_state[f"dados_{g_ativa}"]
                            st.session_state.pagamento_guias[novo_nome] = st.session_state.pagamento_guias.pop(g_ativa, False)
                            salvar_dados_nuvem()
                            st.rerun()
                with col2:
                    if st.button("🗑️ Apagar", key="delete_guia"):
                        if "confirm_delete_guia" not in st.session_state or st.session_state.confirm_delete_guia != g_ativa:
                            st.session_state.confirm_delete_guia = g_ativa
                            st.warning(f"Tem certeza que deseja apagar a guia '{g_ativa}'? Todos os dados serão perdidos.")
                        else:
                            st.session_state.guias_extras.remove(g_ativa)
                            if f"dados_{g_ativa}" in st.session_state: del st.session_state[f"dados_{g_ativa}"]
                            st.session_state.pagamento_guias.pop(g_ativa, None)
                            del st.session_state.confirm_delete_guia
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

    def obter_totais_mes_anterior():
        m_ant, a_ant = obter_mes_anterior(st.session_state.mes_atual, st.session_state.ano_atual)
        chave_ant = f"{m_ant}_{a_ant}"
        df_fix_ant = pd.DataFrame(st.session_state.historico_fixos.get(chave_ant, []))
        t_fix_ant = df_fix_ant["Valor (R$)"].sum() if not df_fix_ant.empty else 0.0
        df_cas_ant = pd.DataFrame(st.session_state.historico_casuais.get(chave_ant, []))
        t_cas_ant = df_cas_ant["Valor (R$)"].sum() if not df_cas_ant.empty else 0.0
        renda_ant = st.session_state.renda_por_mes.get(chave_ant, [])
        t_renda_ant = sum(item["Valor (R$)"] for item in renda_ant) if renda_ant else 0.0
        total_guias_ant = 0.0
        for guia in st.session_state.guias_extras:
            df_g = st.session_state.get(f"dados_{guia}")
            if df_g is not None:
                _, tot, _ = calc_parc_com_categoria(df_g, MESES[m_ant], a_ant)
                total_guias_ant += tot
        t_despesas_ant = t_fix_ant + t_cas_ant + total_guias_ant
        sobra_ant = t_renda_ant - t_despesas_ant
        return t_renda_ant, t_despesas_ant, sobra_ant

    renda_ant, despesas_ant, sobra_ant = obter_totais_mes_anterior()

    def variacao(atual, anterior):
        if anterior == 0:
            return "N/A"
        return f"{((atual - anterior) / anterior * 100):+.1f}%"

    st.markdown(f"<h2>Painel de Controle • {st.session_state.mes_atual} {st.session_state.ano_atual}</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if sel == "Resumo Geral":
        gt = t_fix + t_cas + total_guias
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""
            <div style="background-color: #1E1E1E; padding: 20px; border-radius: 10px; border-left: 5px solid #F24C3D; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <p style="margin:0; font-size: 14px; color: #A0A0A0; font-weight: bold;">GASTO TOTAL</p>
                <h3 style="margin:0; color: #FFFFFF; padding-top: 5px;">{formatar_moeda_br(gt)}</h3>
                <small style="color: #A0A0A0;">vs mês anterior: {variacao(gt, despesas_ant)}</small>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            cor_sobra = "#00B862" if sobra >= 0 else "#F24C3D"
            st.markdown(f"""
            <div style="background-color: #1E1E1E; padding: 20px; border-radius: 10px; border-left: 5px solid {cor_sobra}; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <p style="margin:0; font-size: 14px; color: #A0A0A0; font-weight: bold;">SOBRA REAL</p>
                <h3 style="margin:0; color: #FFFFFF; padding-top: 5px;">{formatar_moeda_br(sobra)}</h3>
                <small style="color: #A0A0A0;">vs mês anterior: {variacao(sobra, sobra_ant)}</small>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div style="background-color: #1E1E1E; padding: 20px; border-radius: 10px; border-left: 5px solid #4A90E2; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <p style="margin:0; font-size: 14px; color: #A0A0A0; font-weight: bold;">RENDA TOTAL</p>
                <h3 style="margin:0; color: #FFFFFF; padding-top: 5px;">{formatar_moeda_br(total_renda)}</h3>
                <small style="color: #A0A0A0;">vs mês anterior: {variacao(total_renda, renda_ant)}</small>
            </div>
            """, unsafe_allow_html=True)
        
        if st.session_state.meta_sobra > 0:
            progresso = max(0.0, min(1.0, sobra / st.session_state.meta_sobra))
            st.progress(progresso, text=f"🎯 Meta de poupança: {formatar_moeda_br(sobra)} de {formatar_moeda_br(st.session_state.meta_sobra)}")

        hoje = datetime.now().date()
        vencimentos = []
        for _, row in st.session_state.gastos_fixos.iterrows():
            if not row.get("Pago", False) and pd.notna(row.get("Data de Vencimento")):
                try:
                    dt = row["Data de Vencimento"]
                    if isinstance(dt, str):
                        dt = datetime.strptime(dt, "%Y-%m-%d").date()
                    if dt <= hoje + timedelta(days=7):
                        vencimentos.append((row["Descrição"], dt, row["Valor (R$)"]))
                except: pass
        if vencimentos:
            with st.expander("📅 Próximos vencimentos (7 dias)", expanded=True):
                for desc, dt, val in sorted(vencimentos, key=lambda x: x[1]):
                    status = "🔴" if dt < hoje else "🟡"
                    st.write(f"{status} {desc} – {dt.strftime('%d/%m')} : {formatar_moeda_br(val)}")

        guias_nao_marcadas = [g for g in st.session_state.guias_extras if not st.session_state.pagamento_guias.get(g, False)]
        if guias_nao_marcadas:
            with st.expander("⚠️ Guias com pagamento pendente (lembrete)", expanded=False):
                for guia in guias_nao_marcadas:
                    df_parc, tot_parc, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{guia}"), mes_n, ano_r)
                    st.markdown(f"- **{guia}**: {formatar_moeda_br(tot_parc)} neste mês")
                st.caption("Marque a guia como paga em 'Cartões e Guias' apenas para controle.")

        st.markdown("<br>", unsafe_allow_html=True)

        col_graf1, col_graf2 = st.columns([1, 2])
        with col_graf1:
            st.markdown("#### Divisão de Despesas")
            df_pizza = pd.DataFrame({"C":["Fixos","Dia a Dia","Guias","Sobra"],"V":[t_fix,t_cas,total_guias,max(0,sobra)]})
            fig = px.pie(df_pizza, values='V', names='C', hole=.5, color_discrete_sequence=['#FF6B6B', '#FFD93D', '#6BCB77', '#4D96FF'])
            fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=10,b=10,l=0,r=0), height=250, showlegend=False)
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)

        with col_graf2:
            st.markdown("#### Evolução Anual")
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
                            "Mês": f"{mes_str[:3]}/{str(ano_str)[2:]}",
                            "Renda": tot_r,
                            "Despesas": tot_d,
                            "Sobra": tot_r - tot_d
                        })
                    except: continue
                if historico_df_dados:
                    df_hist = pd.DataFrame(historico_df_dados).sort_values("Data_Sort")
                    fig_hist = px.area(df_hist, x="Mês", y=["Renda", "Despesas", "Sobra"], color_discrete_sequence=['#4D96FF', '#FF6B6B', '#6BCB77'])
                    fig_hist.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=10,b=10,l=0,r=0), height=250, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
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
            column_config={"Valor (R$)": st.column_config.NumberColumn(min_value=0, format="R$ %.2f")}
        )
        if not er.equals(st.session_state.renda_detalhada):
            st.session_state.renda_detalhada = er
            salvar_dados_nuvem()

    elif sel == "Gastos Fixos":
        ct, cb = st.columns([3,1])
        with ct:
            st.subheader("📌 Contas Fixas")
            st.markdown(f"**Total no Mês:** {formatar_moeda_br(t_fix)}")
        with cb:
            st.write("")
            if st.button("🔄 Importar Anterior", use_container_width=True):
                carregar_dados_sessao(True)
                salvar_dados_nuvem()
                st.rerun()

        with st.expander("➕ Lançamento Rápido de Fixos", expanded=False):
            with st.form("form_novo_fixo"):
                c1, c2, c3 = st.columns([2, 1, 1])
                n_desc = c1.text_input("Descrição do Gasto")
                n_cat = c2.selectbox("Categoria", get_categorias())
                n_val = c3.number_input("Valor (R$)", min_value=0.0, format="%.2f")
                n_venc = st.date_input("Data de Vencimento (opcional)", value=None, help="Data prevista para pagamento")
                if st.form_submit_button("Guardar Lançamento"):
                    if n_desc:
                        nova_linha = pd.DataFrame([{
                            "Descrição": n_desc,
                            "Valor (R$)": n_val,
                            "Pago": False,
                            "Categoria": n_cat,
                            "Data de Vencimento": n_venc
                        }])
                        st.session_state.gastos_fixos = pd.concat([st.session_state.gastos_fixos, nova_linha], ignore_index=True)
                        salvar_dados_nuvem()
                        st.success("Adicionado!")
                        st.rerun()
                    else: st.warning("Preencha a descrição.")
            
            st.divider()
            desc_temp = st.text_input("Não sabe a categoria? Digite a descrição aqui:", key="desc_sugestao_fixo")
            if st.button("✨ Sugerir categoria (IA)", key="sugerir_fixo"):
                if desc_temp and gemini_ok:
                    with st.spinner("Pensando..."):
                        sugestao = sugerir_categoria_gemini(desc_temp)
                        st.info(f"Categoria sugerida: **{sugestao}**")

        ef = st.data_editor(
            st.session_state.gastos_fixos,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0),
                "Pago": st.column_config.CheckboxColumn(),
                "Categoria": st.column_config.SelectboxColumn(options=get_categorias()),
                "Data de Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY")
            }
        )
        if not ef.equals(st.session_state.gastos_fixos):
            st.session_state.gastos_fixos = ef
            salvar_dados_nuvem()

    elif sel == "Dia a Dia":
        st.subheader("🛍️ Compras Casuais")
        st.markdown(f"**Total no Mês:** {formatar_moeda_br(t_cas)}")

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
                        st.success("Registrado!")
                        st.rerun()
                    else: st.warning("A descrição não pode estar vazia.")
            
            st.divider()
            desc_temp = st.text_input("Não sabe a categoria? Digite a descrição:", key="desc_sugestao_casual")
            if st.button("✨ Sugerir categoria (IA)", key="sugerir_casual"):
                if desc_temp and gemini_ok:
                    with st.spinner("Pensando..."):
                        sugestao = sugerir_categoria_gemini(desc_temp)
                        st.info(f"Categoria sugerida: **{sugestao}**")
                        
        with st.expander("📸 Escanear Cupom Fiscal com IA", expanded=False):
            from PIL import Image
            imagem_up = st.file_uploader("Envie a foto do cupom", type=["png", "jpg", "jpeg"])
            
            if imagem_up is not None:
                img = Image.open(imagem_up)
                st.image(img, width=300)
                if st.button("🪄 Extrair Dados", use_container_width=True):
                    with st.spinner("Lendo cupom..."):
                        dados = extrair_dados_recibo_gemini(img)
                        if dados:
                            st.session_state["recibo_pendente"] = dados
                            st.success("Dados extraídos!")
                            
            if "recibo_pendente" in st.session_state:
                dados = st.session_state["recibo_pendente"]
                st.info("Verifique os dados:")
                c1, c2 = st.columns(2)
                r_data = pd.to_datetime(dados.get('data', datetime.now().date())).date()
                r_desc = c1.text_input("Descrição (IA)", dados.get('descricao', ''))
                r_cat = c2.selectbox("Categoria (IA)", get_categorias(), index=get_categorias().index(dados.get('categoria')) if dados.get('categoria') in get_categorias() else 0)
                r_val = st.number_input("Valor (R$)", value=float(dados.get('valor', 0.0)), format="%.2f")
                
                col_conf, col_canc = st.columns(2)
                with col_conf:
                    if st.button("✅ Salvar"):
                        nova_linha = pd.DataFrame([{"Data": r_data, "Categoria": r_cat, "Descrição": r_desc, "Valor (R$)": r_val}])
                        st.session_state.gastos_casuais = pd.concat([st.session_state.gastos_casuais, nova_linha], ignore_index=True)
                        salvar_dados_nuvem()
                        del st.session_state["recibo_pendente"]
                        st.success("Cupom salvo!")
                        st.rerun()
                with col_canc:
                    if st.button("❌ Cancelar"):
                        del st.session_state["recibo_pendente"]
                        st.rerun()
        st.divider()

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

    elif sel == "Investimentos":
        st.subheader("📈 Carteira de Investimentos")
        CLASSES_INV = ["Renda Fixa (CDB/Tesouro)", "Ações (Bolsa)", "Fundos Imobiliários (FIIs)", "Previdência Privada", "Criptomoedas", "Outros"]
        TIPOS_MOV = ["Aporte", "Rendimento", "Resgate"]
        df_inv = st.session_state.dados_investimentos
        
        patrimonio_total = 0.0
        patrimonio_por_classe = {c: 0.0 for c in CLASSES_INV}
        
        if not df_inv.empty:
            for _, row in df_inv.iterrows():
                val = safe_float(row.get("Valor (R$)", 0.0))
                tipo = row.get("Tipo", "")
                classe = row.get("Classe", "Outros")
                if classe not in patrimonio_por_classe: patrimonio_por_classe[classe] = 0.0
                if tipo in ["Aporte", "Rendimento"]:
                    patrimonio_total += val
                    patrimonio_por_classe[classe] += val
                elif tipo == "Resgate":
                    patrimonio_total -= val
                    patrimonio_por_classe[classe] -= val
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"""
            <div style="background-color: #1E1E1E; padding: 20px; border-radius: 10px; border-left: 5px solid #FFD93D; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                <p style="margin:0; font-size: 14px; color: #A0A0A0; font-weight: bold;">PATRIMÔNIO ACUMULADO</p>
                <h3 style="margin:0; color: #FFFFFF; padding-top: 5px;">{formatar_moeda_br(patrimonio_total)}</h3>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            if patrimonio_total > 0:
                df_grafico = pd.DataFrame([{"Classe": k, "Saldo": v} for k, v in patrimonio_por_classe.items() if v > 0])
                if not df_grafico.empty:
                    fig_inv = px.pie(df_grafico, values='Saldo', names='Classe', hole=0.5)
                    fig_inv.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=0,b=0,l=0,r=0), height=150)
                    st.plotly_chart(fig_inv, use_container_width=True)

        st.divider()
        with st.expander("➕ Nova Movimentação", expanded=False):
            with st.form("form_novo_investimento"):
                col1, col2, col3 = st.columns(3)
                n_data = col1.date_input("Data", datetime.now().date())
                n_tipo = col2.selectbox("Tipo", TIPOS_MOV)
                n_classe = col3.selectbox("Classe", CLASSES_INV)
                
                col4, col5, col6 = st.columns([2, 1, 2])
                n_ativo = col4.text_input("Ativo (Ex: CDB Itaú)")
                n_val = col5.number_input("Valor (R$)", min_value=0.0, format="%.2f")
                n_desc = col6.text_input("Observação")
                
                if st.form_submit_button("Registrar"):
                    if n_ativo and n_val > 0:
                        nova_linha = pd.DataFrame([{"Data": n_data, "Ativo": n_ativo, "Classe": n_classe, "Tipo": n_tipo, "Valor (R$)": n_val, "Descrição": n_desc}])
                        st.session_state.dados_investimentos = pd.concat([st.session_state.dados_investimentos, nova_linha], ignore_index=True)
                        salvar_dados_nuvem()
                        st.success("Registrado!")
                        st.rerun()
                    else:
                        st.warning("Preencha o Ativo e insira valor maior que zero.")

        ed_inv = st.data_editor(
            st.session_state.dados_investimentos,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Ativo": st.column_config.TextColumn(required=True),
                "Classe": st.column_config.SelectboxColumn(options=CLASSES_INV, required=True),
                "Tipo": st.column_config.SelectboxColumn(options=TIPOS_MOV, required=True),
                "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0, required=True)
            }
        )
        if not ed_inv.equals(st.session_state.dados_investimentos):
            st.session_state.dados_investimentos = ed_inv
            salvar_dados_nuvem()
            st.rerun()

    elif sel == "Metas de Orçamento":
        st.subheader("🎯 Metas Mensais")
        with st.expander("➕ Adicionar Nova Meta", expanded=False):
            with st.form("form_metas"):
                cat_meta = st.selectbox("Categoria:", get_categorias())
                val_meta = st.number_input("Orçamento (R$):", min_value=0.0, step=50.0, format="%.2f")
                if st.form_submit_button("Salvar Meta"):
                    if val_meta > 0:
                        st.session_state.metas_orcamento[cat_meta] = val_meta
                        salvar_dados_nuvem()
                        st.success(f"Meta criada!")
                        st.rerun()
        
        st.markdown("---")
        if not st.session_state.metas_orcamento:
            st.info("Nenhuma meta definida.")
        else:
            for cat, limite in list(st.session_state.metas_orcamento.items()):
                gasto_atual = gastos_categoria.get(cat, 0.0)
                perc = (gasto_atual / limite) if limite > 0 else 0
                perc_visual = min(perc, 1.0)
                
                col1, col2, col3 = st.columns([2, 3, 1])
                with col1:
                    st.write(f"**{cat}**")
                    st.caption(f"Meta: {formatar_moeda_br(limite)}")
                with col2:
                    st.write(f"Gasto: {formatar_moeda_br(gasto_atual)} ({(perc*100):.1f}%)")
                    st.progress(perc_visual)
                with col3:
                    if st.button("🗑️", key=f"del_meta_{cat}"):
                        del st.session_state.metas_orcamento[cat]
                        salvar_dados_nuvem()
                        st.rerun()
                st.divider()

    elif sel == "Pesquisa Global":
        st.subheader("🔍 Procurar no Histórico")
        termo = st.text_input("Escreva uma palavra:").strip().lower()
        if termo:
            resultados = []
            for chave, df_list in st.session_state.historico_fixos.items():
                for row in df_list:
                    if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                        resultados.append({"Referência": chave, "Tipo": "Fixa", "Data": "-", "Categoria": row.get('Categoria',''), "Descrição": row.get('Descrição',''), "Valor": formatar_moeda_br(row.get('Valor (R$)',0))})
            for chave, df_list in st.session_state.historico_casuais.items():
                for row in df_list:
                    if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                        resultados.append({"Referência": chave, "Tipo": "Casual", "Data": row.get('Data','-'), "Categoria": row.get('Categoria',''), "Descrição": row.get('Descrição',''), "Valor": formatar_moeda_br(row.get('Valor (R$)',0))})
            for g in st.session_state.guias_extras:
                df_g = st.session_state.get(f"dados_{g}")
                if df_g is not None and not df_g.empty:
                    for _, row in df_g.iterrows():
                        if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                            data_compra = row.get('Data da Compra')
                            data_str = data_compra.strftime("%d/%m/%Y") if hasattr(data_compra, 'strftime') and not pd.isna(data_compra) else str(data_compra) if data_compra else "-"
                            resultados.append({"Referência": f"Guia: {g}", "Tipo": "Parcela", "Data": data_str, "Categoria": row.get('Categoria',''), "Descrição": row.get('Descrição',''), "Valor": formatar_moeda_br(row.get('Valor Parcela (R$)',0))})
            if "dados_investimentos" in st.session_state and not st.session_state.dados_investimentos.empty:
                for _, row in st.session_state.dados_investimentos.iterrows():
                    if termo in str(row.get('Ativo','')).lower() or termo in str(row.get('Classe','')).lower() or termo in str(row.get('Descrição','')).lower():
                        d_str = row['Data'].strftime("%d/%m/%Y") if hasattr(row.get('Data'),'strftime') else str(row.get('Data'))
                        resultados.append({"Referência": "Carteira", "Tipo": f"Invest ({row.get('Tipo','')})", "Data": d_str, "Categoria": row.get('Classe',''), "Descrição": f"{row.get('Ativo','')} - {row.get('Descrição','')}", "Valor": formatar_moeda_br(row.get('Valor (R$)',0))})

            if resultados:
                st.success(f"{len(resultados)} encontrados!")
                st.dataframe(pd.DataFrame(resultados), use_container_width=True, hide_index=True)
            else: st.warning("Nenhum registro encontrado.")

    elif sel == "Resumo das Guias":
        st.subheader("📊 Custos por Guia")
        dados_guias = []
        for g in st.session_state.guias_extras:
            _, custo, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), mes_n, ano_r)
            dados_guias.append({"Guia": g, "Custo (R$)": custo})
        if dados_guias:
            df_guias = pd.DataFrame(dados_guias)
            st.markdown(f"**Total Guias:** {formatar_moeda_br(df_guias['Custo (R$)'].sum())}")
            fig_guias = px.bar(df_guias, x="Guia", y="Custo (R$)", color="Guia")
            fig_guias.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_guias, use_container_width=True)
        else: st.info("Nenhuma guia extra.")
        
        st.divider()
        st.subheader("📊 Gastos por Categoria")
        if gastos_categoria:
            df_cat = pd.DataFrame(gastos_categoria.items(), columns=["Categoria","Valor (R$)"]).sort_values("Valor (R$)", ascending=False)
            fig_cat = px.bar(df_cat, x="Categoria", y="Valor (R$)", color="Categoria")
            fig_cat.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_cat, use_container_width=True)
        else: st.info("Nenhum gasto registrado.")

    elif sel == "Cartões e Guias":
        st.subheader("💳 Cartões de Crédito e Guias Extras")
        if not st.session_state.guias_extras:
            st.info("Nenhum cartão cadastrado. Vá na barra lateral em 'Gerenciar Guias' para criar.")
        else:
            guia_ativa = st.selectbox("Selecione o cartão/guia para editar:", st.session_state.guias_extras, key="guia_ativa")
            
            pago_guia = st.session_state.pagamento_guias.get(guia_ativa, False)
            novo_status = st.checkbox("✅ Marcar como paga (apenas lembrete, não afeta os cálculos)", value=pago_guia)
            if novo_status != pago_guia:
                st.session_state.pagamento_guias[guia_ativa] = novo_status
                salvar_dados_nuvem()
                st.rerun()
            
            df_guia = st.session_state[f"dados_{guia_ativa}"]
            if "Data da Compra" not in df_guia.columns:
                df_guia["Data da Compra"] = None
            else:
                df_guia["Data da Compra"] = pd.to_datetime(df_guia["Data da Compra"], errors='coerce').apply(
                    lambda x: x.date() if isinstance(x, datetime) and not pd.isna(x) else None
                )
            
            # Sempre calcular e mostrar as parcelas
            df_parc, total_parc, _ = calc_parc_com_categoria(df_guia, mes_n, ano_r)
            
            st.markdown(f"**Parcelas neste mês:** {formatar_moeda_br(total_parc)}")
            if not df_parc.empty:
                # Parcelas sempre visíveis
                df_parc_format = df_parc.copy()
                df_parc_format['Valor (R$)'] = df_parc_format['Valor (R$)'].apply(formatar_moeda_br)
                st.dataframe(df_parc_format, use_container_width=True, hide_index=True)
            else:
                st.caption("Nenhuma parcela prevista para este mês.")
            
            st.divider()
            
            # Nova despesa em expander
            with st.expander(f"➕ Nova despesa em {guia_ativa}", expanded=False):
                with st.form(f"form_nova_guia_{guia_ativa}"):
                    c1, c2 = st.columns(2)
                    n_desc = c1.text_input("Descrição")
                    n_cat = c2.selectbox("Categoria", get_categorias())
                    c3, c4 = st.columns(2)
                    n_val = c3.number_input("Valor Parcela (R$)", min_value=0.0, format="%.2f")
                    n_data_compra = c4.date_input("Data da Compra", value=datetime.now().date())
                    c5, c6, c7 = st.columns(3)
                    n_qtd = c5.number_input("Qtd Parcelas", min_value=1, step=1, value=1)
                    n_mes_ini = c6.number_input("Mês Início", min_value=1, max_value=12, step=1, value=mes_n)
                    n_ano_ini = c7.number_input("Ano Início", min_value=2000, max_value=2050, step=1, value=ano_r)
                    
                    if st.form_submit_button("Guardar"):
                        if n_desc:
                            nova_linha = pd.DataFrame([{
                                "Descrição": n_desc,
                                "Valor Parcela (R$)": n_val,
                                "Data da Compra": n_data_compra,
                                "Mês Início (1-12)": n_mes_ini,
                                "Ano Início": n_ano_ini,
                                "Qtd Parcelas": n_qtd,
                                "Categoria": n_cat
                            }])
                            st.session_state[f"dados_{guia_ativa}"] = pd.concat([df_guia, nova_linha], ignore_index=True)
                            salvar_dados_nuvem()
                            st.success("Despesa adicionada!")
                            st.rerun()
                        else:
                            st.warning("Preencha a descrição.")
            
            # Tabela de edição dentro de um expander
            with st.expander("📝 Editar todas as despesas"):
                de = st.data_editor(
                    df_guia,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Valor Parcela (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0),
                        "Data da Compra": st.column_config.DateColumn(format="DD/MM/YYYY"),
                        "Mês Início (1-12)": st.column_config.NumberColumn(min_value=1, max_value=12, step=1),
                        "Ano Início": st.column_config.NumberColumn(min_value=2000, max_value=2050, step=1),
                        "Qtd Parcelas": st.column_config.NumberColumn(min_value=1, step=1),
                        "Categoria": st.column_config.SelectboxColumn(options=get_categorias())
                    },
                    key=f"editor_guia_{guia_ativa}"
                )
                if not de.equals(df_guia):
                    st.session_state[f"dados_{guia_ativa}"] = de
                    salvar_dados_nuvem()
                    st.rerun()
