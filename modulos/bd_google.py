import streamlit as st
import pandas as pd
import json
import gspread
import time
from datetime import datetime
from google.oauth2.service_account import Credentials

# Importando as utilidades que criamos no passo anterior
from modulos.utilidades import moeda_para_float, safe_float, safe_int, safe_str, safe_bool, CATEGORIAS_PADRAO_BASE

@st.cache_resource
def ligar_google_sheets(url_da_planilha):
    creds_dict = json.loads(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds).open_by_url(url_da_planilha)

def carregar_dados_nuvem_raw():
    db_conn = ligar_google_sheets(st.session_state["url_planilha"])
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
            "historico_investimentos": [],
            "guias_extras": [],
            "categorias_personalizadas": [],
            "categorias_padrao": CATEGORIAS_PADRAO_BASE.copy(),
            "renda_por_mes": {},
            "metas_orcamento": {},
            "pagamento_guias": {}
        }, False

    all_casuais = ws_casuais.get_all_values()
    all_fixos = ws_fixos.get_all_values()
    all_guias = ws_guias.get_all_values()
    config_val = ws_config.acell('A1').value

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
            if len(row) < 5: continue
            mes_ano = safe_str(row[0])
            if not mes_ano: continue
            descricao = safe_str(row[1])
            categoria = safe_str(row[2])
            valor = moeda_para_float(row[3])
            pago = safe_bool(row[4])
            
            dia_venc = 10
            if len(row) >= 6:
                dia_venc = safe_int(row[5], 10)

            if mes_ano not in hist_fixos:
                hist_fixos[mes_ano] = []
            hist_fixos[mes_ano].append({
                "Descrição": descricao,
                "Categoria": categoria,
                "Valor (R$)": valor,
                "Pago": pago,
                "Dia Venc.": dia_venc
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
        "pagamento_guias": config.get("pagamento_guias", {})
    }
    for g in result["guias_extras"]:
        result[f"dados_{g}"] = dict_guias.get(g, [])
        
    for chave in list(result["historico_casuais"].keys()):
        if "_" not in chave:
            del result["historico_casuais"][chave]
        else:
            chave_limpa = chave.strip()
            if chave_limpa != chave:
                result["historico_casuais"][chave_limpa] = result["historico_casuais"].pop(chave)
                
    return result, False

def salvar_dados_nuvem():
    db_conn = ligar_google_sheets(st.session_state["url_planilha"])

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

    flat_casuais = [["Mes_Ano", "Data", "Categoria", "Descrição", "Valor"]]
    for ma, itens in st.session_state.historico_casuais.items():
        for item in itens:
            flat_casuais.append([safe_str(ma), safe_str(item.get("Data","")), safe_str(item.get("Categoria","")), safe_str(item.get("Descrição","")), safe_float(item.get("Valor (R$)"), 0.0)])

    flat_fixos = [["Mes_Ano", "Descrição", "Categoria", "Valor", "Pago", "Dia Venc."]]
    for ma, itens in st.session_state.historico_fixos.items():
        for item in itens:
            flat_fixos.append([safe_str(ma), safe_str(item.get("Descrição","")), safe_str(item.get("Categoria","")), safe_float(item.get("Valor (R$)"), 0.0), safe_bool(item.get("Pago",False)), safe_int(item.get("Dia Venc."), 10)])

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
        "pagamento_guias": {str(k): {str(g): bool(v) for g, v in meses_guias.items()} if isinstance(meses_guias, dict) else bool(meses_guias) for k, meses_guias in st.session_state.pagamento_guias.items()}
    }

    max_tentativas = 3
    for tentativa in range(max_tentativas):
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
            break 

        except gspread.exceptions.APIError as e:
            if tentativa < max_tentativas - 1:
                time.sleep(2 * (tentativa + 1)) 
            else:
                st.error("⚠️ O Google limitou o salvamento por causa de muitas edições rápidas. Aguarde alguns segundos e tente alterar novamente.")
                break
