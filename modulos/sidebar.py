import streamlit as st
import pandas as pd
from modulos.utilidades import formatar_moeda_br, safe_float, safe_int, safe_str, safe_bool, MESES
from modulos.bd_google import salvar_dados_nuvem

def renderizar_sidebar(
    get_categorias_fn,
    carregar_dados_sessao_fn,
    gerar_pdf_mes_fn,
    calc_parc_com_categoria_fn
):
    """Renderiza a barra lateral e retorna a opção selecionada no menu."""
    with st.sidebar:
        st.markdown(f"<h3 style='text-align: center;'>👤 Olá, {str(st.session_state.get('usuario_logado', '')).title()}</h3>", unsafe_allow_html=True)
        st.markdown("---")
        
        st.subheader("📅 Mês de Referência")
        
        c_esq, c_meio, c_dir = st.columns([1, 2, 1])
        lista_meses = list(MESES.keys())
        idx_mes_atual = lista_meses.index(st.session_state.mes_atual)

        with c_esq:
            if st.button("◀", use_container_width=True, key="btn_mes_ant"):
                salvar_dados_nuvem()
                if idx_mes_atual == 0:
                    st.session_state.mes_atual = lista_meses[11]
                    st.session_state.ano_atual -= 1
                else:
                    st.session_state.mes_atual = lista_meses[idx_mes_atual - 1]
                carregar_dados_sessao_fn()
                st.session_state.pdf_ready = False
                st.rerun()

        with c_meio:
            st.markdown(f"<div style='text-align: center; font-weight: bold; margin-top: 5px; font-size: 16px;'>{st.session_state.mes_atual}<br><span style='font-size: 12px; color: #A0A0A0;'>{st.session_state.ano_atual}</span></div>", unsafe_allow_html=True)

        with c_dir:
            if st.button("▶", use_container_width=True, key="btn_mes_prox"):
                salvar_dados_nuvem()
                if idx_mes_atual == 11:
                    st.session_state.mes_atual = lista_meses[0]
                    st.session_state.ano_atual += 1
                else:
                    st.session_state.mes_atual = lista_meses[idx_mes_atual + 1]
                carregar_dados_sessao_fn()
                st.session_state.pdf_ready = False
                st.rerun()
                
        st.markdown("---")
        st.subheader("Navegação Principal")
        opcoes = ["Resumo Geral", "Renda", "Gastos Fixos", "Dia a Dia", "Cartões e Guias", "Visão Consolidada", "Investimentos", "Metas de Orçamento", "Projeção Futura", "Pesquisa Global"]
        sel = st.radio("", opcoes, label_visibility="collapsed")
        
        st.markdown("---")
        st.subheader("⚙️ Configurações")

        if st.button("🔄 Recarregar Nuvem", use_container_width=True):
            for key in ["dados_carregados", "historico_fixos", "historico_casuais", "guias_extras", 
                        "categorias_personalizadas", "categorias_padrao", "renda_por_mes", "metas_orcamento",
                        "dados_investimentos", "pagamento_guias"]:
                if key in st.session_state:
                    del st.session_state[key]
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
                    df_parc, tot, cats = calc_parc_com_categoria_fn(st.session_state.get(f"dados_{guia}"), mes_n, ano_r)
                    total_guias_p += tot
                    for cat, val in cats.items(): gastos_cat_p[cat] = gastos_cat_p.get(cat, 0.0) + val
                    guias_dados_p[guia] = df_parc.to_dict('records')
                total_renda_p = st.session_state.renda_detalhada["Valor (R$)"].sum()
                sobra_p = total_renda_p - (t_fix_p + t_cas_p + total_guias_p)

                st.session_state.pdf_data = gerar_pdf_mes_fn(
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

        # --- Gerenciar Categorias ---
        st.divider()
        st.subheader("🏷️ Gerenciar Categorias")
        with st.expander("Opções de categorias"):
            nova_cat = st.text_input("Nova categoria personalizada:", key="nova_cat_input")
            if st.button("➕ Adicionar", key="add_cat"):
                if nova_cat and nova_cat not in get_categorias_fn():
                    st.session_state.categorias_personalizadas.append(nova_cat)
                    salvar_dados_nuvem()
                    st.rerun()
                else: st.warning("Categoria já existe ou nome inválido.")
            
            st.markdown("---")
            st.write("✏️ **Editar categorias existentes**")
            cat_para_editar = st.selectbox("Selecione a categoria:", get_categorias_fn(), key="cat_edit_select")
            is_padrao = cat_para_editar in st.session_state.categorias_padrao
            is_personalizada = cat_para_editar in st.session_state.categorias_personalizadas
            
            novo_nome_cat = st.text_input("Novo nome:", key="novo_nome_cat")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✏️ Renomear", key="rename_cat"):
                    if novo_nome_cat and novo_nome_cat not in get_categorias_fn():
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
                    with st.popover("🗑️ Apagar"):
                        st.markdown(f"Excluir **{cat_para_editar}**?")
                        if st.button("Sim, apagar", key="delete_cat"):
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

        # --- Gerenciar Guias ---
        st.divider()
        st.subheader("🛠️ Gerenciar Guias")
        with st.expander("Opções de gerenciamento"):
            ng = st.text_input("Nova Guia/Cartão:")
            if st.button("➕ Criar", key="add_guia"):
                if ng and ng not in st.session_state.guias_extras:
                    st.session_state.guias_extras.append(ng)
                    colunas_guia = ["Descrição","Valor Parcela (R$)","Data da Compra","Mês Início (1-12)","Ano Início","Qtd Parcelas","Categoria"]
                    st.session_state[f"dados_{ng}"] = pd.DataFrame(columns=colunas_guia)
                    
                    chave_atual = f"{st.session_state.mes_atual}_{st.session_state.ano_atual}"
                    if chave_atual not in st.session_state.pagamento_guias:
                        st.session_state.pagamento_guias[chave_atual] = {}
                    st.session_state.pagamento_guias[chave_atual][ng] = False
                    
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
                            for mes_ano in st.session_state.pagamento_guias:
                                if g_ativa in st.session_state.pagamento_guias[mes_ano]:
                                    st.session_state.pagamento_guias[mes_ano][novo_nome] = st.session_state.pagamento_guias[mes_ano].pop(g_ativa)
                            salvar_dados_nuvem()
                            st.rerun()
                with col2:
                    with st.popover("🗑️ Apagar"):
                        st.markdown(f"Excluir **{g_ativa}**?")
                        if st.button("Sim, apagar", key="delete_guia"):
                            st.session_state.guias_extras.remove(g_ativa)
                            if f"dados_{g_ativa}" in st.session_state: del st.session_state[f"dados_{g_ativa}"]
                            for mes_ano in st.session_state.pagamento_guias:
                                st.session_state.pagamento_guias[mes_ano].pop(g_ativa, None)
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

    return sel
