import streamlit as st
import pandas as pd
import json
import gspread
import plotly.express as px
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from fpdf import FPDF
import unicodedata

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
        st.error("Erro de conexão com a nuvem. Verifique a planilha e a chave.")
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
                else:
                    st.warning("Mês anterior vazio.")
            else:
                st.error("Sem dados no mês anterior.")
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
            except:
                continue
        df_parc = pd.DataFrame(parcelas)
        total = df_parc["Valor (R$)"].sum() if not df_parc.empty else 0.0
        soma_cat = df_parc.groupby("Categoria")["Valor (R$)"].sum().to_dict() if not df_parc.empty else {}
        return df_parc, total, soma_cat

    # --- REMOVER ACENTOS PARA PDF ---
    def remover_acentos(texto):
        if not isinstance(texto, str):
            texto = str(texto)
        return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')

    # --- GERAR PDF ---
    def gerar_pdf_mes(mes_nome, ano, renda_df, fixos_df, casuais_df, guias_dados, total_renda, t_fix, t_cas, t_gui, sobra, dados_categoria):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('helvetica', '', 12)
        pdf.set_font_size(16)
        pdf.cell(0, 10, remover_acentos(f"Relatorio Financeiro - {mes_nome}/{ano}"), ln=True, align="C")
        pdf.ln(5)
        
        pdf.set_font_size(12)
        pdf.set_font(style='B')
        pdf.cell(0, 8, remover_acentos(f"Renda Total: R$ {total_renda:.2f}"), ln=True)
        pdf.set_font(style='')
        for _, row in renda_df.iterrows():
            pdf.cell(0, 6, remover_acentos(f"{row['Fonte']}: R$ {row['Valor (R$)']:.2f}"), ln=True)
        pdf.ln(5)
        
        pdf.set_font(style='B')
        pdf.cell(0, 8, remover_acentos(f"Despesas Fixas: R$ {t_fix:.2f}"), ln=True)
        pdf.set_font(style='')
        for _, row in fixos_df.iterrows():
            status = "Pago" if row.get("Pago", False) else "Pendente"
            desc = row['Descrição'] if 'Descrição' in row else ''
            pdf.cell(0, 6, remover_acentos(f"{desc}: R$ {row['Valor (R$)']:.2f} ({status})"), ln=True)
        pdf.ln(5)
        
        pdf.set_font(style='B')
        pdf.cell(0, 8, remover_acentos(f"Despesas do Dia a Dia: R$ {t_cas:.2f}"), ln=True)
        pdf.set_font(style='')
        for _, row in casuais_df.iterrows():
            data_str = row['Data'].strftime("%d/%m/%Y") if hasattr(row['Data'],'strftime') else str(row['Data'])
            desc = row['Descrição'] if 'Descrição' in row else ''
            pdf.cell(0, 6, remover_acentos(f"{data_str} - {row['Categoria']} - {desc}: R$ {row['Valor (R$)']:.2f}"), ln=True)
        pdf.ln(5)
        
        pdf.set_font(style='B')
        pdf.cell(0, 8, remover_acentos(f"Guias (Parcelamentos): R$ {t_gui:.2f}"), ln=True)
        pdf.set_font(style='')
        for guia, parcelas in guias_dados.items():
            for row in parcelas:
                pdf.cell(0, 6, remover_acentos(f"{guia} - {row['Descrição']} ({row['Categoria']}): R$ {row['Valor (R$)']:.2f}"), ln=True)
        pdf.ln(5)
        
        pdf.set_font(style='B')
        pdf.cell(0, 8, remover_acentos("Gastos por Categoria"), ln=True)
        pdf.set_font(style='')
        for cat, valor in dados_categoria.items():
            pdf.cell(0, 6, remover_acentos(f"{cat}: R$ {valor:.2f}"), ln=True)
        pdf.ln(5)
        
        pdf.set_font(style='B')
        if sobra >= 0:
            pdf.set_text_color(0,150,0)
        else:
            pdf.set_text_color(200,0,0)
        pdf.cell(0, 8, remover_acentos(f"Sobra do Mes: R$ {sobra:.2f}"), ln=True)
        pdf.set_text_color(0,0,0)
        
        return pdf.output(dest='S')

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
            dados_g = dados_raw.get(f"dados_{g}", [])
            if dados_g and isinstance(dados_g, list) and len(dados_g)>0:
                if "Categoria" not in dados_g[0]:
                    for item in dados_g:
                        item["Categoria"] = "Outros"
            st.session_state[f"dados_{g}"] = pd.DataFrame(dados_g)
            if st.session_state[f"dados_{g}"].empty:
                st.session_state[f"dados_{g}"] = pd.DataFrame(columns=["Descrição","Valor Parcela (R$)","Mês Início (1-12)","Ano Início","Qtd Parcelas","Categoria"])
        carregar_dados_sessao()
        st.session_state.dados_carregados = True

    # Inicializa estado para o PDF
    if "pdf_bytes" not in st.session_state:
        st.session_state.pdf_bytes = None
    if "pdf_nome" not in st.session_state:
        st.session_state.pdf_nome = None

    def get_categorias():
        return CATEGORIAS_PADRAO + st.session_state.categorias_personalizadas

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Configurações")
        if st.button("🔄 Recarregar Nuvem"):
            novos_dados = carregar_dados_nuvem_raw()
            st.session_state.guias_extras = novos_dados.get("guias_extras", [])
            st.session_state.historico_fixos = novos_dados.get("historico_fixos", {})
            st.session_state.historico_casuais = novos_dados.get("historico_casuais", {})
            st.session_state.renda_por_mes = novos_dados.get("renda_por_mes", {})
            st.session_state.categorias_personalizadas = novos_dados.get("categorias_personalizadas", [])
            for g in st.session_state.guias_extras:
                st.session_state[f"dados_{g}"] = pd.DataFrame(novos_dados.get(f"dados_{g}", []))
            carregar_dados_sessao()
            st.rerun()

        m_sel = st.selectbox("Mês:", list(MESES.keys()), index=list(MESES.keys()).index(st.session_state.mes_atual))
        a_sel = st.number_input("Ano:", 2024, 2030, st.session_state.ano_atual)
        if m_sel != st.session_state.mes_atual or a_sel != st.session_state.ano_atual:
            salvar_dados_nuvem()
            st.session_state.mes_atual, st.session_state.ano_atual = m_sel, a_sel
            carregar_dados_sessao()
            # Limpa PDF anterior ao mudar de mês
            st.session_state.pdf_bytes = None
            st.session_state.pdf_nome = None
            st.rerun()

        st.divider()
        # Botão para gerar PDF
        if st.button("📄 Gerar Relatório PDF deste mês", use_container_width=True):
            with st.spinner("Gerando PDF... aguarde"):
                mes_n = MESES[st.session_state.mes_atual]
                ano_r = st.session_state.ano_atual
                t_fix_pdf = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
                t_cas_pdf = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
                
                total_guias_pdf = 0.0
                gastos_categoria_pdf = {}
                for _, row in st.session_state.gastos_casuais.iterrows():
                    cat = row["Categoria"]
                    gastos_categoria_pdf[cat] = gastos_categoria_pdf.get(cat, 0.0) + row["Valor (R$)"]
                
                guias_dados = {}
                for guia in st.session_state.guias_extras:
                    df_parc, tot_guia, cats_guia = calc_parc_com_categoria(st.session_state.get(f"dados_{guia}"), mes_n, ano_r)
                    total_guias_pdf += tot_guia
                    for cat, val in cats_guia.items():
                        gastos_categoria_pdf[cat] = gastos_categoria_pdf.get(cat, 0.0) + val
                    guias_dados[guia] = df_parc.to_dict('records')
                
                total_renda_pdf = st.session_state.renda_detalhada["Valor (R$)"].sum()
                sobra_pdf = total_renda_pdf - (t_fix_pdf + t_cas_pdf + total_guias_pdf)

                pdf_bytes = gerar_pdf_mes(
                    st.session_state.mes_atual, st.session_state.ano_atual,
                    st.session_state.renda_detalhada,
                    st.session_state.gastos_fixos,
                    st.session_state.gastos_casuais,
                    guias_dados,
                    total_renda_pdf, t_fix_pdf, t_cas_pdf, total_guias_pdf, sobra_pdf,
                    gastos_categoria_pdf
                )
                # Garante que é bytes
                if isinstance(pdf_bytes, str):
                    pdf_bytes = pdf_bytes.encode('latin-1')
                st.session_state.pdf_bytes = pdf_bytes
                st.session_state.pdf_nome = f"relatorio_{st.session_state.mes_atual}_{st.session_state.ano_atual}.pdf"
                st.rerun()

        # Exibe o botão de download se o PDF estiver disponível
        if st.session_state.pdf_bytes is not None:
            st.download_button(
                label="📥 Baixar PDF",
                data=st.session_state.pdf_bytes,
                file_name=st.session_state.pdf_nome,
                mime="application/pdf",
                use_container_width=True
            )

        st.divider()
        ver_projecao = st.checkbox("📈 Ver Projeção Futura (6 meses)")

        st.divider()
        st.subheader("🏷️ Categorias Personalizadas")
        nova_cat = st.text_input("Nova categoria:")
        if st.button("➕ Adicionar Categoria"):
            if nova_cat and nova_cat not in get_categorias():
                st.session_state.categorias_personalizadas.append(nova_cat)
                salvar_dados_nuvem()
                st.rerun()
        if st.session_state.categorias_personalizadas:
            cat_remover = st.selectbox("Remover categoria:", [""] + st.session_state.categorias_personalizadas)
            if cat_remover and st.button("🗑️ Remover"):
                st.session_state.categorias_personalizadas.remove(cat_remover)
                salvar_dados_nuvem()
                st.rerun()

        st.divider()
        st.subheader("🛠️ Gerenciar Guias")
        with st.expander("⚙️ Opções de gerenciamento"):
            ng = st.text_input("Nova Guia:")
            if st.button("➕ Criar"):
                if ng and ng not in st.session_state.guias_extras:
                    st.session_state.guias_extras.append(ng)
                    st.session_state[f"dados_{ng}"] = pd.DataFrame(columns=["Descrição","Valor Parcela (R$)","Mês Início (1-12)","Ano Início","Qtd Parcelas","Categoria"])
                    salvar_dados_nuvem()
                    st.rerun()
            if st.session_state.guias_extras:
                g_ativa = st.selectbox("Guia para editar:", st.session_state.guias_extras)
                novo_nome = st.text_input("Renomear para:")
                if st.button("📝 Renomear"):
                    if novo_nome and novo_nome not in st.session_state.guias_extras:
                        idx = st.session_state.guias_extras.index(g_ativa)
                        st.session_state.guias_extras[idx] = novo_nome
                        st.session_state[f"dados_{novo_nome}"] = st.session_state[f"dados_{g_ativa}"]
                        del st.session_state[f"dados_{g_ativa}"]
                        salvar_dados_nuvem()
                        st.rerun()
                if st.button("🗑️ Apagar"):
                    st.session_state.guias_extras.remove(g_ativa)
                    if f"dados_{g_ativa}" in st.session_state:
                        del st.session_state[f"dados_{g_ativa}"]
                    salvar_dados_nuvem()
                    st.rerun()

                st.markdown("---")
                st.write("🔼 Reordenar Guias")
                guia_mover = st.selectbox("Selecione a guia:", st.session_state.guias_extras, key="mover")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⬆️ Mover para Cima"):
                        idx = st.session_state.guias_extras.index(guia_mover)
                        if idx>0:
                            st.session_state.guias_extras[idx], st.session_state.guias_extras[idx-1] = st.session_state.guias_extras[idx-1], st.session_state.guias_extras[idx]
                            salvar_dados_nuvem()
                            st.rerun()
                with col2:
                    if st.button("⬇️ Mover para Baixo"):
                        idx = st.session_state.guias_extras.index(guia_mover)
                        if idx < len(st.session_state.guias_extras)-1:
                            st.session_state.guias_extras[idx], st.session_state.guias_extras[idx+1] = st.session_state.guias_extras[idx+1], st.session_state.guias_extras[idx]
                            salvar_dados_nuvem()
                            st.rerun()

    # --- CÁLCULOS PRINCIPAIS ---
    mes_n = MESES[st.session_state.mes_atual]
    ano_r = st.session_state.ano_atual
    t_fix = st.session_state.gastos_fixos["Valor (R$)"].sum() if not st.session_state.gastos_fixos.empty else 0.0
    t_cas = st.session_state.gastos_casuais["Valor (R$)"].sum() if not st.session_state.gastos_casuais.empty else 0.0
    
    total_guias = 0.0
    gastos_categoria = {}
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

    opcoes = ["Resumo Geral", "Renda", "Gastos Fixos", "Dia a Dia", "Resumo das Guias"] + st.session_state.guias_extras
    sel = st.selectbox("Ir para:", opcoes)
    st.divider()

    if sel == "Resumo Geral":
        gt = t_fix + t_cas + total_guias
        c1,c2,c3 = st.columns(3)
        c1.metric("Gasto Total", f"R$ {gt:,.2f}")
        c2.metric("Sobra Real", f"R$ {sobra:,.2f}", delta=f"{(sobra/total_renda)*100:.1f}%" if total_renda>0 else "0%")
        c3.metric("Renda Total", f"R$ {total_renda:,.2f}")
        fig = px.pie(pd.DataFrame({"C":["Fixos","Dia a Dia","Guias","Sobra"],"V":[t_fix,t_cas,total_guias,max(0,sobra)]}), values='V', names='C', hole=.4)
        fig.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=300)
        st.plotly_chart(fig, use_container_width=True)

    elif sel == "Renda":
        st.subheader("💵 Fontes de Renda")
        er = st.data_editor(st.session_state.renda_detalhada, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Valor (R$)": st.column_config.NumberColumn(min_value=0, format="R$ %.2f")})
        if not er.equals(st.session_state.renda_detalhada):
            st.session_state.renda_detalhada = er
            salvar_dados_nuvem()

    elif sel == "Gastos Fixos":
        ct, cb = st.columns([3,1])
        ct.subheader("📌 Contas Fixas")
        if cb.button("🔄 Importar"):
            carregar_dados_sessao(True)
            salvar_dados_nuvem()
            st.rerun()
        ef = st.data_editor(st.session_state.gastos_fixos, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0),
                                           "Pago": st.column_config.CheckboxColumn()})
        if not ef.equals(st.session_state.gastos_fixos):
            st.session_state.gastos_fixos = ef
            salvar_dados_nuvem()

    elif sel == "Dia a Dia":
        st.subheader("🛍️ Compras Casuais")
        ec = st.data_editor(st.session_state.gastos_casuais, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                           "Categoria": st.column_config.SelectboxColumn(options=get_categorias()),
                                           "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0)})
        if not ec.equals(st.session_state.gastos_casuais):
            st.session_state.gastos_casuais = ec
            salvar_dados_nuvem()

    elif sel == "Resumo das Guias":
        st.subheader("📊 Comparativo de Custos por Guia")
        dados_guias = []
        for g in st.session_state.guias_extras:
            _, tot, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), mes_n, ano_r)
            dados_guias.append({"Guia":g, "Custo Total (R$)":tot})
        if dados_guias:
            df_guias = pd.DataFrame(dados_guias)
            total_geral = df_guias['Custo Total (R$)'].sum()
            st.metric("💰 Total Geral de Todas as Guias", f"R$ {total_geral:,.2f}")
            st.dataframe(df_guias, use_container_width=True, hide_index=True)
            fig_guias = px.bar(df_guias, x="Guia", y="Custo Total (R$)", color="Guia", text_auto='.2f')
            st.plotly_chart(fig_guias, use_container_width=True)
        else:
            st.info("Nenhuma guia extra criada.")
        
        st.divider()
        st.subheader("📊 Gastos por Categoria (Geral do Mês)")
        if gastos_categoria:
            df_cat = pd.DataFrame(gastos_categoria.items(), columns=["Categoria","Valor (R$)"]).sort_values("Valor (R$)", ascending=False)
            st.dataframe(df_cat, use_container_width=True, hide_index=True)
            fig_cat = px.bar(df_cat, x="Categoria", y="Valor (R$)", color="Categoria", text_auto='.2f')
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("Nenhum gasto registrado neste mês.")

    else:  # Guias extras individuais
        df_parc, total_parc, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{sel}"), mes_n, ano_r)
        st.subheader(f"Total no Mês: R$ {total_parc:,.2f}")
        if not df_parc.empty:
            st.dataframe(df_parc, use_container_width=True, hide_index=True)
        st.divider()
        st.write("**Base de Lançamentos (parcelas):**")
        de = st.data_editor(st.session_state[f"dados_{sel}"], num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={
                                "Valor Parcela (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0),
                                "Mês Início (1-12)": st.column_config.NumberColumn(min_value=1, max_value=12, step=1),
                                "Ano Início": st.column_config.NumberColumn(min_value=2000, max_value=2030, step=1),
                                "Qtd Parcelas": st.column_config.NumberColumn(min_value=1, step=1),
                                "Categoria": st.column_config.SelectboxColumn(options=get_categorias())
                            })
        if not de.equals(st.session_state[f"dados_{sel}"]):
            st.session_state[f"dados_{sel}"] = de
            salvar_dados_nuvem()
            st.rerun()

    # --- PROJEÇÃO FUTURA ---
    if ver_projecao:
        st.divider()
        st.subheader("📅 Fluxo de Caixa Previsto (6 Meses)")
        meses_anteriores = []
        for i in range(1,4):
            m_c = mes_n - i
            a_c = ano_r
            if m_c <= 0:
                m_c += 12
                a_c -= 1
            meses_anteriores.append((a_c, m_c))
        media_casuais = recalcular_media_casuais(meses_anteriores)
        if media_casuais == 0 and t_cas > 0:
            media_casuais = t_cas
        proj = []
        for i in range(6):
            m_f = mes_n + i
            a_f = ano_r
            while m_f > 12:
                m_f -= 12
                a_f += 1
            t_g_f = 0.0
            for g in st.session_state.guias_extras:
                _, tot, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), m_f, a_f)
                t_g_f += tot
            t_d_f = t_fix + media_casuais + t_g_f
            proj.append({"Mês": f"{list(MESES.keys())[m_f-1]}/{a_f}", "Renda": total_renda, "Fixos": t_fix,
                         "Casuais (média)": media_casuais, "Guias": t_g_f, "Despesa Total": t_d_f, "Sobra": total_renda - t_d_f})
        df_proj = pd.DataFrame(proj)
        st.plotly_chart(px.bar(df_proj, x="Mês", y=["Fixos","Casuais (média)","Guias"], barmode="stack", text_auto='.2f'), use_container_width=True)
        st.dataframe(df_proj.style.format({c:"R$ {:.2f}" for c in df_proj.columns if c!="Mês"}), use_container_width=True)
        if (df_proj["Sobra"] < 0).any():
            st.warning("⚠️ Atenção: há meses com sobra negativa prevista.")