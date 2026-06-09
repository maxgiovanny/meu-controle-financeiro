import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
import PyPDF2

# --- IMPORTAÇÃO DOS NOSSOS MÓDULOS ---
from modulos.utilidades import (
    formatar_moeda_br, remover_acentos,
    safe_float, safe_int, safe_str, safe_bool,
    MESES, CATEGORIAS_PADRAO_BASE
)
from modulos.bd_google import carregar_dados_nuvem_raw, salvar_dados_nuvem
from modulos.sidebar import renderizar_sidebar
from modulos.inicializacao import carregar_estado_inicial
from modulos.relatorios import gerar_pdf_mes, formatar_moeda_pdf
from modulos.calculos import obter_mes_anterior, calc_parc_com_categoria
from modulos.sessao import carregar_dados_sessao

# Importações da IA isolada
from modulos.ia_gemini import (
    gemini_ok,
    analise_financeira_gemini,
    sugerir_categoria_gemini,
    extrair_dados_recibo_gemini,
    extrair_lote_extrato_gemini
)

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
    st.set_page_config(
        page_title="Controle Financeiro", page_icon="💰",
        layout="centered", initial_sidebar_state="expanded"
    )

    if not gemini_ok:
        st.sidebar.warning("🤖 IA Desativada: Verifique a configuração do Gemini.")

    # --- INICIALIZAÇÃO ---
    carregar_estado_inicial(carregar_dados_sessao)

    if "pdf_ready" not in st.session_state:
        st.session_state.pdf_ready = False
    if "pdf_data" not in st.session_state:
        st.session_state.pdf_data = None

    def get_categorias():
        return st.session_state.categorias_padrao + st.session_state.categorias_personalizadas

    # --- SIDEBAR (em módulo separado) ---
    sel = renderizar_sidebar(
        get_categorias_fn=get_categorias,
        carregar_dados_sessao_fn=carregar_dados_sessao,
        gerar_pdf_mes_fn=gerar_pdf_mes,
        calc_parc_com_categoria_fn=calc_parc_com_categoria
    )

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
        _, tot_guia, cats_guia = calc_parc_com_categoria(
            st.session_state.get(f"dados_{guia}"), mes_n, ano_r
        )
        total_guias += tot_guia
        for cat, val in cats_guia.items():
            gastos_categoria[cat] = gastos_categoria.get(cat, 0.0) + val

    total_renda = st.session_state.renda_detalhada["Valor (R$)"].sum()
    sobra = total_renda - (t_fix + t_cas + total_guias)

    st.markdown(
        f"<h2>Painel de Controle • {st.session_state.mes_atual} {st.session_state.ano_atual}</h2>",
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # ========== SEÇÕES ==========
    if sel == "Resumo Geral":
        gt = t_fix + t_cas + total_guias

        m_ant, a_ant = obter_mes_anterior(st.session_state.mes_atual, st.session_state.ano_atual)
        chave_ant = f"{m_ant}_{a_ant}"

        df_fix_ant = pd.DataFrame(st.session_state.historico_fixos.get(chave_ant, []))
        t_fix_ant = df_fix_ant['Valor (R$)'].sum() if not df_fix_ant.empty and 'Valor (R$)' in df_fix_ant.columns else 0.0

        df_cas_ant = pd.DataFrame(st.session_state.historico_casuais.get(chave_ant, []))
        t_cas_ant = df_cas_ant['Valor (R$)'].sum() if not df_cas_ant.empty and 'Valor (R$)' in df_cas_ant.columns else 0.0

        t_guias_ant = 0.0
        for g in st.session_state.guias_extras:
            _, tot_g_ant, _ = calc_parc_com_categoria(
                st.session_state.get(f"dados_{g}"), MESES[m_ant], a_ant
            )
            t_guias_ant += tot_g_ant

        gt_ant = t_fix_ant + t_cas_ant + t_guias_ant

        df_ren_ant = pd.DataFrame(st.session_state.renda_por_mes.get(chave_ant, []))
        t_renda_ant = df_ren_ant['Valor (R$)'].sum() if not df_ren_ant.empty and 'Valor (R$)' in df_ren_ant.columns else 0.0
        sobra_ant = t_renda_ant - gt_ant

        c1, c2, c3 = st.columns(3)
        with c1:
            dif_gasto = gt - gt_ant
            st.metric("GASTO TOTAL", formatar_moeda_br(gt),
                      delta=f"{dif_gasto:,.2f} vs Mês Ant.", delta_color="inverse")
        with c2:
            dif_sobra = sobra - sobra_ant
            st.metric("SOBRA REAL", formatar_moeda_br(sobra),
                      delta=f"{dif_sobra:,.2f} vs Mês Ant.")
        with c3:
            dif_renda = total_renda - t_renda_ant
            st.metric("RENDA TOTAL", formatar_moeda_br(total_renda),
                      delta=f"{dif_renda:,.2f} vs Mês Ant.")

        hoje = datetime.now()
        if hoje.month == mes_n and hoje.year == ano_r:
            if "Dia Venc." in st.session_state.gastos_fixos.columns:
                df_pendentes = st.session_state.gastos_fixos[st.session_state.gastos_fixos['Pago'] == False]
                contas_vencendo = df_pendentes[pd.to_numeric(df_pendentes['Dia Venc.'], errors='coerce') <= (hoje.day + 3)]
                if not contas_vencendo.empty:
                    with st.error("⚠️ Atenção: Contas fixas vencendo em breve ou em atraso!"):
                        for _, row in contas_vencendo.iterrows():
                            st.write(f"- **{row['Descrição']}**: {formatar_moeda_br(row['Valor (R$)'])} (Vence dia {int(row['Dia Venc.'])})")

        chave_atual = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
        if chave_atual not in st.session_state.pagamento_guias:
            st.session_state.pagamento_guias[chave_atual] = {}

        guias_nao_marcadas = [
            g for g in st.session_state.guias_extras
            if not st.session_state.pagamento_guias[chave_atual].get(g, False)
        ]
        if guias_nao_marcadas:
            with st.expander("⚠️ Guias com pagamento pendente (lembrete)", expanded=False):
                for guia in guias_nao_marcadas:
                    df_parc, tot_parc, _ = calc_parc_com_categoria(
                        st.session_state.get(f"dados_{guia}"), mes_n, ano_r
                    )
                    st.markdown(f"- **{guia}**: {formatar_moeda_br(tot_parc)} neste mês")
                st.caption("Marque a guia como paga em 'Cartões e Guias' – não afeta os cálculos.")

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("#### Fluxo do Dinheiro (Sankey)")
        labels_sankey = ["Renda", "Sobra", "Fixos", "Dia a Dia", "Guias"] + get_categorias()
        source, target, value = [], [], []

        if sobra > 0:
            source.append(0); target.append(1); value.append(sobra)
        if t_fix > 0:
            source.append(0); target.append(2); value.append(t_fix)
        if t_cas > 0:
            source.append(0); target.append(3); value.append(t_cas)
        if total_guias > 0:
            source.append(0); target.append(4); value.append(total_guias)

        def add_sankey_links(df_gastos, source_idx):
            if df_gastos is not None and not df_gastos.empty:
                for cat, group in df_gastos.groupby("Categoria"):
                    val = group["Valor (R$)"].sum()
                    if val > 0 and cat in labels_sankey:
                        source.append(source_idx)
                        target.append(labels_sankey.index(cat))
                        value.append(val)

        add_sankey_links(st.session_state.gastos_fixos, 2)
        add_sankey_links(st.session_state.gastos_casuais, 3)
        df_todas_guias_mes = pd.DataFrame()
        for guia in st.session_state.guias_extras:
            df_parc, _, _ = calc_parc_com_categoria(
                st.session_state.get(f"dados_{guia}"), mes_n, ano_r
            )
            if not df_parc.empty:
                df_todas_guias_mes = pd.concat([df_todas_guias_mes, df_parc])
        add_sankey_links(df_todas_guias_mes, 4)

        if sum(value) > 0:
            fig_sankey = go.Figure(data=[go.Sankey(
                node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=labels_sankey),
                link=dict(source=source, target=target, value=value)
            )])
            fig_sankey.update_layout(height=400, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sankey, use_container_width=True)
        else:
            st.info("Adicione renda e gastos para visualizar o fluxo do dinheiro.")

        st.markdown("---")
        st.markdown("#### Evolução Anual")
        historico_df_dados = []
        chaves_todas = set(
            list(st.session_state.historico_fixos.keys()) +
            list(st.session_state.historico_casuais.keys()) +
            list(st.session_state.renda_por_mes.keys())
        )
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
                        _, t_g, _ = calc_parc_com_categoria(
                            st.session_state.get(f"dados_{g}"), mes_idx, ano_num
                        )
                        tot_g += t_g
                    df_ren = pd.DataFrame(st.session_state.renda_por_mes.get(chave, []))
                    tot_r = df_ren['Valor (R$)'].sum() if not df_ren.empty and 'Valor (R$)' in df_ren.columns else 0.0
                    tot_d = tot_f + tot_c + tot_g
                    historico_df_dados.append({
                        "Data_Sort": datetime(ano_num, mes_idx, 1),
                        "Mês": f"{mes_str[:3]}/{str(ano_str)[2:]}",
                        "Renda": tot_r, "Despesas": tot_d, "Sobra": tot_r - tot_d
                    })
                except:
                    continue
            if historico_df_dados:
                df_hist = pd.DataFrame(historico_df_dados).sort_values("Data_Sort")
                fig_hist = px.line(
                    df_hist, x="Mês", y=["Renda", "Despesas", "Sobra"],
                    color_discrete_sequence=['#4D96FF', '#FF6B6B', '#6BCB77'],
                    markers=True
                )
                fig_hist.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=10, b=10, l=0, r=0), height=250,
                    xaxis=dict(showgrid=False), yaxis=dict(showgrid=False),
                    legend_title_text="Legenda"
                )
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
        ct, cb = st.columns([3, 1])
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
                if st.form_submit_button("Guardar Lançamento"):
                    if n_desc:
                        nova_linha = pd.DataFrame([{
                            "Descrição": n_desc, "Valor (R$)": n_val,
                            "Pago": False, "Categoria": n_cat, "Dia Venc.": 10
                        }])
                        st.session_state.gastos_fixos = pd.concat(
                            [st.session_state.gastos_fixos, nova_linha], ignore_index=True
                        )
                        salvar_dados_nuvem()
                        st.success("Adicionado!")
                        st.rerun()
                    else:
                        st.warning("Preencha a descrição.")

            st.divider()
            desc_temp = st.text_input("Não sabe a categoria? Digite a descrição aqui:", key="desc_sugestao_fixo")
            if st.button("✨ Sugerir categoria (IA)", key="sugerir_fixo"):
                if desc_temp and gemini_ok:
                    with st.spinner("Pensando..."):
                        sugestao = sugerir_categoria_gemini(desc_temp, get_categorias())
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
                "Dia Venc.": st.column_config.NumberColumn(min_value=1, max_value=31, help="Dia do mês que a conta vence")
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
                        nova_linha = pd.DataFrame([{
                            "Data": n_data, "Categoria": n_cat,
                            "Descrição": n_desc, "Valor (R$)": n_val
                        }])
                        st.session_state.gastos_casuais = pd.concat(
                            [st.session_state.gastos_casuais, nova_linha], ignore_index=True
                        )
                        salvar_dados_nuvem()
                        st.success("Registrado!")
                        st.rerun()
                    else:
                        st.warning("A descrição não pode estar vazia.")

            st.divider()
            desc_temp = st.text_input("Não sabe a categoria? Digite a descrição:", key="desc_sugestao_casual")
            if st.button("✨ Sugerir categoria (IA)", key="sugerir_casual"):
                if desc_temp and gemini_ok:
                    with st.spinner("Pensando..."):
                        sugestao = sugerir_categoria_gemini(desc_temp, get_categorias())
                        st.info(f"Categoria sugerida: **{sugestao}**")

        with st.expander("📸 Escanear Cupom Fiscal com IA", expanded=False):
            from PIL import Image
            imagem_up = st.file_uploader("Envie a foto do cupom", type=["png", "jpg", "jpeg"])
            if imagem_up is not None:
                img = Image.open(imagem_up)
                st.image(img, width=300)
                if st.button("🪄 Extrair Dados", use_container_width=True):
                    with st.spinner("Lendo cupom..."):
                        dados = extrair_dados_recibo_gemini(img, get_categorias())
                        if dados:
                            st.session_state["recibo_pendente"] = dados
                            st.success("Dados extraídos!")
            if "recibo_pendente" in st.session_state:
                dados = st.session_state["recibo_pendente"]
                st.info("Verifique os dados:")
                c1, c2 = st.columns(2)
                r_data = pd.to_datetime(dados.get('data', datetime.now().date())).date()
                r_desc = c1.text_input("Descrição (IA)", dados.get('descricao', ''))
                r_cat = c2.selectbox("Categoria (IA)", get_categorias(),
                                     index=get_categorias().index(dados.get('categoria')) if dados.get('categoria') in get_categorias() else 0)
                r_val = st.number_input("Valor (R$)", value=float(dados.get('valor', 0.0)), format="%.2f")
                col_conf, col_canc = st.columns(2)
                with col_conf:
                    if st.button("✅ Salvar"):
                        nova_linha = pd.DataFrame([{
                            "Data": r_data, "Categoria": r_cat,
                            "Descrição": r_desc, "Valor (R$)": r_val
                        }])
                        st.session_state.gastos_casuais = pd.concat(
                            [st.session_state.gastos_casuais, nova_linha], ignore_index=True
                        )
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
        CLASSES_INV = ["Renda Fixa (CDB/Tesouro)", "Ações (Bolsa)", "Fundos Imobiliários (FIIs)",
                       "Previdência Privada", "Criptomoedas", "Outros"]
        TIPOS_MOV = ["Aporte", "Rendimento", "Resgate"]
        df_inv = st.session_state.dados_investimentos

        patrimonio_total = 0.0
        patrimonio_por_classe = {c: 0.0 for c in CLASSES_INV}

        if not df_inv.empty:
            for _, row in df_inv.iterrows():
                val = safe_float(row.get("Valor (R$)", 0.0))
                tipo = row.get("Tipo", "")
                classe = row.get("Classe", "Outros")
                if classe not in patrimonio_por_classe:
                    patrimonio_por_classe[classe] = 0.0
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
                    fig_inv.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                          margin=dict(t=0, b=0, l=0, r=0), height=150)
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
                        nova_linha = pd.DataFrame([{
                            "Data": n_data, "Ativo": n_ativo, "Classe": n_classe,
                            "Tipo": n_tipo, "Valor (R$)": n_val, "Descrição": n_desc
                        }])
                        st.session_state.dados_investimentos = pd.concat(
                            [st.session_state.dados_investimentos, nova_linha], ignore_index=True
                        )
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
        metas_categorias = {k: v for k, v in st.session_state.metas_orcamento.items() if k != "META_POUPANCA_GLOBAL"}
        if not metas_categorias:
            st.info("Nenhuma meta definida para categorias.")
        else:
            for cat, limite in list(metas_categorias.items()):
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
                    with st.popover("🗑️"):
                        st.markdown(f"Excluir meta de **{cat}**?")
                        if st.button("Sim", key=f"del_meta_{cat}"):
                            del st.session_state.metas_orcamento[cat]
                            salvar_dados_nuvem()
                            st.rerun()
                st.divider()
    elif sel == "Projeção Futura":
        st.subheader("🔭 Projeção de Gastos (Próximos 6 Meses)")

        # Menu suspenso com três opções
        tipo_projecao = st.selectbox(
            "Tipo de visão:",
            ["Geral (Fixos + Guias)", "Por Guia (Todas)", "Por Guia (Individual)"]
        )

        lista_meses_nomes = list(MESES.keys())

        # ------------------------------------------------------------------
        # 1. VISÃO GERAL (Fixos + Guias empilhados)
        # ------------------------------------------------------------------
        if tipo_projecao == "Geral (Fixos + Guias)":
            st.write("Esta visão soma os seus gastos **Fixos** atuais (assumindo que se mantêm) com as parcelas já comprometidas dos seus **Cartões e Guias** para os próximos meses.")

            projecoes = []
            m_iter = mes_n
            a_iter = ano_r

            for i in range(6):
                nome_mes = lista_meses_nomes[m_iter - 1]
                label_mes = f"{nome_mes[:3]}/{str(a_iter)[2:]}"
                total_fixo_futuro = t_fix
                total_guias_futuro = 0.0
                for g in st.session_state.guias_extras:
                    _, tot_g_futuro, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), m_iter, a_iter)
                    total_guias_futuro += tot_g_futuro
                projecoes.append({"Mês": label_mes, "Tipo": "Gastos Fixos", "Valor (R$)": total_fixo_futuro})
                projecoes.append({"Mês": label_mes, "Tipo": "Cartões e Guias", "Valor (R$)": total_guias_futuro})
                m_iter += 1
                if m_iter > 12:
                    m_iter = 1
                    a_iter += 1

            df_proj = pd.DataFrame(projecoes)
            fig_proj = px.bar(df_proj, x="Mês", y="Valor (R$)", color="Tipo", text_auto='.2s',
                              color_discrete_sequence=['#FF6B6B', '#6BCB77'])
            fig_proj.update_layout(barmode='stack', plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_proj, use_container_width=True)

        # ------------------------------------------------------------------
        # 2. POR GUIA (TODAS)
        # ------------------------------------------------------------------
        elif tipo_projecao == "Por Guia (Todas)":
            st.write("Projeção individual de cada **Cartão/Guia** para os próximos meses.")

            if not st.session_state.guias_extras:
                st.info("Nenhuma guia cadastrada para projetar.")
            else:
                projecoes_guias = []
                m_iter = mes_n
                a_iter = ano_r

                for i in range(6):
                    nome_mes = lista_meses_nomes[m_iter - 1]
                    label_mes = f"{nome_mes[:3]}/{str(a_iter)[2:]}"
                    for g in st.session_state.guias_extras:
                        _, tot_g_futuro, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), m_iter, a_iter)
                        projecoes_guias.append({
                            "Mês": label_mes,
                            "Guia": g,
                            "Valor (R$)": tot_g_futuro
                        })
                    m_iter += 1
                    if m_iter > 12:
                        m_iter = 1
                        a_iter += 1

                df_proj_guias = pd.DataFrame(projecoes_guias)

                # Gráfico de barras agrupadas
                fig_guias = px.bar(
                    df_proj_guias,
                    x="Mês",
                    y="Valor (R$)",
                    color="Guia",
                    text_auto='.2s',
                    barmode='group'
                )
                fig_guias.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_guias, use_container_width=True)

                # Tabela detalhada
                with st.expander("📋 Ver tabela detalhada"):
                    pivot = df_proj_guias.pivot(index="Mês", columns="Guia", values="Valor (R$)")
                    pivot = pivot.fillna(0)
                    pivot["Total"] = pivot.sum(axis=1)
                    st.dataframe(pivot.style.format("R$ {:,.2f}"), use_container_width=True)

        # ------------------------------------------------------------------
        # 3. POR GUIA (INDIVIDUAL)
        # ------------------------------------------------------------------
        else:
            st.write("Selecione um cartão/guia para visualizar a projeção apenas dele.")

            if not st.session_state.guias_extras:
                st.info("Nenhuma guia cadastrada para projetar.")
            else:
                # Seleciona a guia
                guia_selecionada = st.selectbox("Escolha a guia:", st.session_state.guias_extras)

                proj_individual = []
                m_iter = mes_n
                a_iter = ano_r

                for i in range(6):
                    nome_mes = lista_meses_nomes[m_iter - 1]
                    label_mes = f"{nome_mes[:3]}/{str(a_iter)[2:]}"
                    _, tot_guia_futuro, _ = calc_parc_com_categoria(
                        st.session_state.get(f"dados_{guia_selecionada}"), m_iter, a_iter
                    )
                    proj_individual.append({
                        "Mês": label_mes,
                        "Valor (R$)": tot_guia_futuro
                    })
                    m_iter += 1
                    if m_iter > 12:
                        m_iter = 1
                        a_iter += 1

                df_ind = pd.DataFrame(proj_individual)

                # Gráfico de linha
                fig_ind = px.line(
                    df_ind,
                    x="Mês",
                    y="Valor (R$)",
                    markers=True,
                    title=f"Projeção – {guia_selecionada}"
                )
                fig_ind.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ind, use_container_width=True)

                # Tabela simples
                with st.expander("📋 Ver valores"):
                    st.dataframe(df_ind.style.format({"Valor (R$)": "R$ {:,.2f}"}), use_container_width=True)

    elif sel == "Pesquisa Global":
        st.subheader("🔍 Procurar no Histórico")
        termo = st.text_input("Escreva uma palavra:").strip().lower()
        if termo:
            resultados = []
            for chave, df_list in st.session_state.historico_fixos.items():
                for row in df_list:
                    if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                        resultados.append({
                            "Referência": chave, "Tipo": "Fixa", "Data": "-",
                            "Categoria": row.get('Categoria',''),
                            "Descrição": row.get('Descrição',''),
                            "Valor": formatar_moeda_br(row.get('Valor (R$)',0))
                        })
            for chave, df_list in st.session_state.historico_casuais.items():
                for row in df_list:
                    if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                        resultados.append({
                            "Referência": chave, "Tipo": "Casual",
                            "Data": row.get('Data','-'),
                            "Categoria": row.get('Categoria',''),
                            "Descrição": row.get('Descrição',''),
                            "Valor": formatar_moeda_br(row.get('Valor (R$)',0))
                        })
            for g in st.session_state.guias_extras:
                df_g = st.session_state.get(f"dados_{g}")
                if df_g is not None and not df_g.empty:
                    for _, row in df_g.iterrows():
                        if termo in str(row.get('Descrição','')).lower() or termo in str(row.get('Categoria','')).lower():
                            data_compra = row.get('Data da Compra')
                            data_str = data_compra.strftime("%d/%m/%Y") if hasattr(data_compra, 'strftime') and not pd.isna(data_compra) else str(data_compra) if data_compra else "-"
                            resultados.append({
                                "Referência": f"Guia: {g}", "Tipo": "Parcela",
                                "Data": data_str,
                                "Categoria": row.get('Categoria',''),
                                "Descrição": row.get('Descrição',''),
                                "Valor": formatar_moeda_br(row.get('Valor Parcela (R$)',0))
                            })
            if "dados_investimentos" in st.session_state and not st.session_state.dados_investimentos.empty:
                for _, row in st.session_state.dados_investimentos.iterrows():
                    if termo in str(row.get('Ativo','')).lower() or termo in str(row.get('Classe','')).lower() or termo in str(row.get('Descrição','')).lower():
                        d_str = row['Data'].strftime("%d/%m/%Y") if hasattr(row.get('Data'),'strftime') else str(row.get('Data'))
                        resultados.append({
                            "Referência": "Carteira", "Tipo": f"Invest ({row.get('Tipo','')})",
                            "Data": d_str,
                            "Categoria": row.get('Classe',''),
                            "Descrição": f"{row.get('Ativo','')} - {row.get('Descrição','')}",
                            "Valor": formatar_moeda_br(row.get('Valor (R$)',0))
                        })
            if resultados:
                st.success(f"{len(resultados)} encontrados!")
                st.dataframe(pd.DataFrame(resultados), use_container_width=True, hide_index=True)
            else:
                st.warning("Nenhum registro encontrado.")

    elif sel == "Visão Consolidada":  # <--- Nome novo da aba atualizado!
        st.subheader("📊 Composição de Despesas (Origem)")
        
        dados_fontes = []
        
        # 1. Adiciona Gastos Fixos
        if t_fix > 0:
            dados_fontes.append({"Origem": "📌 Gastos Fixos", "Custo (R$)": t_fix})
            
        # 2. Adiciona Gastos Casuais (Dia a Dia)
        if t_cas > 0:
            dados_fontes.append({"Origem": "🛍️ Dia a Dia", "Custo (R$)": t_cas})

        # 3. Adiciona as Guias/Cartões individualmente
        total_guias_grafico = 0.0
        for g in st.session_state.guias_extras:
            _, custo, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{g}"), mes_n, ano_r)
            if custo > 0:
                dados_fontes.append({"Origem": f"💳 {g}", "Custo (R$)": custo})
                total_guias_grafico += custo

        # 4. Renderiza o Gráfico Consolidado
        if dados_fontes:
            df_fontes = pd.DataFrame(dados_fontes)
            
            # Mostra um pequeno resumo em texto acima do gráfico para facilitar a leitura
            st.markdown(
                f"**Fixos:** {formatar_moeda_br(t_fix)} &nbsp;|&nbsp; "
                f"**Dia a Dia:** {formatar_moeda_br(t_cas)} &nbsp;|&nbsp; "
                f"**Total Guias:** {formatar_moeda_br(total_guias_grafico)}"
            )
            
            fig_fontes = px.bar(
                df_fontes, 
                x="Origem", 
                y="Custo (R$)", 
                color="Origem", 
                text_auto='.2s',
                title="Distribuição de onde o dinheiro está saindo"
            )
            fig_fontes.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", 
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis_title="",
                yaxis_title="Valor (R$)",
                showlegend=False # Esconde a legenda lateral pois os nomes já estão no eixo X
            )
            st.plotly_chart(fig_fontes, use_container_width=True)
        else:
            st.info("Nenhum gasto registrado neste mês.")

        st.divider()
        
        st.subheader("📊 Gastos por Categoria")
        if gastos_categoria:
            df_cat = pd.DataFrame(gastos_categoria.items(), columns=["Categoria","Valor (R$)"]).sort_values("Valor (R$)", ascending=False)
            fig_cat = px.bar(df_cat, x="Categoria", y="Valor (R$)", color="Categoria")
            fig_cat.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("Nenhum gasto registrado.")
            
        st.divider()
        st.subheader("🗓️ Gastos Diários (Fixos + Casuais + Guias)")

        # 1. Consolidar gastos casuais
        df_cas = st.session_state.gastos_casuais.copy()
        if not df_cas.empty:
            df_cas['Data'] = pd.to_datetime(df_cas['Data'])
            df_cas = df_cas.groupby('Data')['Valor (R$)'].sum().reset_index()
            df_cas.columns = ['Data', 'Valor']
            df_cas['Tipo'] = 'Dia a Dia'

        # 2. Consolidar parcelas das guias (usando a Data da Compra)
        df_guias_all = pd.DataFrame()
        for guia in st.session_state.guias_extras:
            df_g = st.session_state.get(f"dados_{guia}").copy()
            if not df_g.empty:
                df_g['Data'] = pd.to_datetime(df_g['Data da Compra'], errors='coerce')
                df_guias_all = pd.concat([df_guias_all, df_g[['Data', 'Valor Parcela (R$)']]])
        
        if not df_guias_all.empty:
            df_guias_all = df_guias_all.groupby('Data')['Valor Parcela (R$)'].sum().reset_index()
            df_guias_all.columns = ['Data', 'Valor']
            df_guias_all['Tipo'] = 'Cartões/Guias'

        # 3. Juntar tudo
        df_diario = pd.concat([df_cas, df_guias_all])
        
        if not df_diario.empty:
            df_diario = df_diario.groupby(['Data', 'Tipo'])['Valor'].sum().reset_index()
            fig_diario = px.bar(
                df_diario, x="Data", y="Valor", color="Tipo",
                title=f"Gastos Diários - {st.session_state.mes_atual}",
                labels={"Valor": "Gasto (R$)"}
            )
            fig_diario.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_diario, use_container_width=True)
        else:
            st.info("Não há dados de gastos com data para exibir no gráfico diário.")

        st.divider()
        st.subheader("🔎 Detalhamento por Categoria (Global)")
        st.write("Selecione uma categoria para ver todos os gastos associados a ela neste mês, consolidados de todas as fontes.")

        dados_consolidados = []
        categorias_presentes = set()

        # 1. Buscar nos Gastos Fixos
        if not st.session_state.gastos_fixos.empty:
            for _, row in st.session_state.gastos_fixos.iterrows():
                cat = row.get('Categoria', 'Outros')
                categorias_presentes.add(cat)
                dados_consolidados.append({
                    "Data": f"Dia {int(row.get('Dia Venc.', 10))}" if pd.notna(row.get('Dia Venc.')) else "-",
                    "Fonte/Guia": "📌 Gasto Fixo",
                    "Descrição": row.get('Descrição', ''),
                    "Categoria": cat,
                    "Valor (R$)": row.get('Valor (R$)', 0.0)
                })

        # 2. Buscar nos Gastos Casuais (Dia a Dia)
        if not st.session_state.gastos_casuais.empty:
            for _, row in st.session_state.gastos_casuais.iterrows():
                cat = row.get('Categoria', 'Outros')
                categorias_presentes.add(cat)
                d_str = row['Data'].strftime("%d/%m/%Y") if hasattr(row.get('Data'), 'strftime') else str(row.get('Data', '-'))
                dados_consolidados.append({
                    "Data": d_str,
                    "Fonte/Guia": "🛍️ Dia a Dia",
                    "Descrição": row.get('Descrição', ''),
                    "Categoria": cat,
                    "Valor (R$)": row.get('Valor (R$)', 0.0)
                })

        # 3. Buscar em TODAS as Guias/Cartões
        for guia in st.session_state.guias_extras:
            # Puxa apenas as parcelas que caem no mês atual
            df_parc, _, _ = calc_parc_com_categoria(st.session_state.get(f"dados_{guia}"), mes_n, ano_r)
            if not df_parc.empty:
                for _, row in df_parc.iterrows():
                    cat = row.get('Categoria', 'Outros')
                    categorias_presentes.add(cat)
                    
                    # CORREÇÃO DA DATA: Tenta buscar 'Data' primeiro, se não achar, busca 'Data da Compra'
                    data_compra = row.get('Data')
                    if pd.isna(data_compra) or data_compra is None:
                        data_compra = row.get('Data da Compra')
                        
                    d_str = data_compra.strftime("%d/%m/%Y") if hasattr(data_compra, 'strftime') and pd.notna(data_compra) else "-"
                    
                    # CORREÇÃO DO VALOR: Tenta 'Valor (R$)' primeiro, se não achar, busca 'Valor Parcela (R$)'
                    valor_gasto = row.get('Valor (R$)')
                    if pd.isna(valor_gasto) or valor_gasto is None:
                        valor_gasto = row.get('Valor Parcela (R$)', 0.0)
                        
                    dados_consolidados.append({
                        "Data": d_str,
                        "Fonte/Guia": f"💳 {guia}",
                        "Descrição": row.get('Descrição', ''),
                        "Categoria": cat,
                        "Valor (R$)": float(valor_gasto)
                    })

        # 4. Renderizar a Tabela Interativa
        if dados_consolidados:
            df_detalhe = pd.DataFrame(dados_consolidados)
            
            # Dropdown para escolher a categoria (mostra apenas categorias que tiveram gastos)
            cat_selecionada = st.selectbox("Selecione a Categoria:", sorted(list(categorias_presentes)))
            
            # Filtra o DataFrame
            df_filtrado = df_detalhe[df_detalhe['Categoria'] == cat_selecionada]
            
            if not df_filtrado.empty:
                total_cat = df_filtrado['Valor (R$)'].sum()
                st.markdown(f"**Total gasto com {cat_selecionada} neste mês:** <span style='color:#FF6B6B; font-size:18px; font-weight:bold;'>{formatar_moeda_br(total_cat)}</span>", unsafe_allow_html=True)
                
                # Formata a coluna de valor para exibição (R$ X.XXX,XX)
                df_display = df_filtrado.copy()
                df_display['Valor (R$)'] = df_display['Valor (R$)'].apply(formatar_moeda_br)
                
                # Exibe a tabela ocultando o índice e a coluna Categoria (pois já está selecionada)
                st.dataframe(
                    df_display[['Data', 'Fonte/Guia', 'Descrição', 'Valor (R$)']], 
                    use_container_width=True, 
                    hide_index=True
                )
            else:
                st.info(f"Nenhum detalhe encontrado para a categoria {cat_selecionada}.")
        else:
            st.info("Nenhum dado disponível para análise de categorias neste mês.")

    elif sel == "Cartões e Guias":
        st.subheader("💳 Cartões de Crédito e Guias Extras")
        if not st.session_state.guias_extras:
            st.info("Nenhum cartão cadastrado. Vá na barra lateral em 'Gerenciar Guias' para criar.")
        else:
            guia_ativa = st.selectbox("Selecione o cartão/guia para editar:", st.session_state.guias_extras, key="guia_ativa")

            chave_atual = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
            if chave_atual not in st.session_state.pagamento_guias:
                st.session_state.pagamento_guias[chave_atual] = {}

            pago_guia = st.session_state.pagamento_guias[chave_atual].get(guia_ativa, False)
            novo_status = st.checkbox("✅ Marcar como paga (apenas lembrete, não afeta os cálculos)", value=pago_guia)
            if novo_status != pago_guia:
                st.session_state.pagamento_guias[chave_atual][guia_ativa] = novo_status
                salvar_dados_nuvem()
                st.rerun()

            df_guia = st.session_state[f"dados_{guia_ativa}"]
            if "Data da Compra" not in df_guia.columns:
                df_guia["Data da Compra"] = None
            else:
                df_guia["Data da Compra"] = pd.to_datetime(df_guia["Data da Compra"], errors='coerce').apply(
                    lambda x: x.date() if isinstance(x, datetime) and not pd.isna(x) else None
                )

            df_parc, total_parc, _ = calc_parc_com_categoria(df_guia, mes_n, ano_r)

            st.markdown(f"**Parcelas neste mês:** {formatar_moeda_br(total_parc)}")
            if not df_parc.empty:
                df_parc_format = df_parc.copy()
                df_parc_format['Valor (R$)'] = df_parc_format['Valor (R$)'].apply(formatar_moeda_br)
                st.dataframe(df_parc_format, use_container_width=True, hide_index=True)
            else:
                st.caption("Nenhuma parcela prevista para este mês.")

            st.divider()

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
                                "Descrição": n_desc, "Valor Parcela (R$)": n_val,
                                "Data da Compra": n_data_compra,
                                "Mês Início (1-12)": n_mes_ini, "Ano Início": n_ano_ini,
                                "Qtd Parcelas": n_qtd, "Categoria": n_cat
                            }])
                            st.session_state[f"dados_{guia_ativa}"] = pd.concat(
                                [df_guia, nova_linha], ignore_index=True
                            )
                            salvar_dados_nuvem()
                            st.success("Despesa adicionada!")
                            st.rerun()
                        else:
                            st.warning("Preencha a descrição.")

            with st.expander(f"📥 Importar Fatura (PDF ou CSV) para {guia_ativa}", expanded=False):
                arquivo_extrato = st.file_uploader("Envie a fatura deste cartão", type=["pdf", "csv"], key=f"up_{guia_ativa}")
                if arquivo_extrato is not None:
                    if st.button("🪄 Processar Fatura"):
                        with st.spinner("A IA está a ler a fatura e a categorizar os gastos..."):
                            texto_completo = ""
                            if arquivo_extrato.name.endswith('.pdf'):
                                leitor = PyPDF2.PdfReader(arquivo_extrato)
                                for pagina in leitor.pages:
                                    texto_completo += pagina.extract_text() + "\n"
                            elif arquivo_extrato.name.endswith('.csv'):
                                texto_completo = arquivo_extrato.getvalue().decode("utf-8")
                            dados_lote = extrair_lote_extrato_gemini(texto_completo, get_categorias())
                            if dados_lote and isinstance(dados_lote, list):
                                st.session_state["fatura_pendente"] = pd.DataFrame(dados_lote)
                                st.success(f"{len(dados_lote)} despesas encontradas!")
                            else:
                                st.error("Não foi possível extrair dados estruturados desta fatura.")

                if "fatura_pendente" in st.session_state:
                    st.info("Reveja os dados importados. Pode editar as células antes de confirmar.")
                    df_lote = st.session_state["fatura_pendente"]
                    df_lote['Data'] = pd.to_datetime(df_lote['Data'], errors='coerce').dt.date
                    df_editado = st.data_editor(
                        df_lote,
                        num_rows="dynamic",
                        column_config={
                            "Data": st.column_config.DateColumn("Data da Compra", format="DD/MM/YYYY"),
                            "Categoria": st.column_config.SelectboxColumn(options=get_categorias()),
                            "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", min_value=0)
                        },
                        use_container_width=True,
                        key=f"editor_lote_{guia_ativa}"
                    )
                    col_sl, col_cl = st.columns(2)
                    with col_sl:
                        if st.button("✅ Guardar no Cartão"):
                            novas_linhas = []
                            for _, row in df_editado.iterrows():
                                novas_linhas.append({
                                    "Descrição": row.get("Descrição", ""),
                                    "Valor Parcela (R$)": row.get("Valor (R$)", 0.0),
                                    "Data da Compra": row.get("Data"),
                                    "Mês Início (1-12)": mes_n,
                                    "Ano Início": ano_r,
                                    "Qtd Parcelas": 1,
                                    "Categoria": row.get("Categoria", "Outros")
                                })
                            st.session_state[f"dados_{guia_ativa}"] = pd.concat(
                                [df_guia, pd.DataFrame(novas_linhas)], ignore_index=True
                            )
                            salvar_dados_nuvem()
                            del st.session_state["fatura_pendente"]
                            st.success("Fatura importada com sucesso!")
                            st.rerun()
                    with col_cl:
                        if st.button("❌ Cancelar Importação"):
                            del st.session_state["fatura_pendente"]
                            st.rerun()

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
