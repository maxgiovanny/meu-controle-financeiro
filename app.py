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
                
                # --- A MÁGICA ESTÁ AQUI EM BAIXO ---
                # Garante que é 'bytes' puro, pois o Streamlit odeia 'bytearray'
                if isinstance(pdf_bytes, str):
                    pdf_bytes = pdf_bytes.encode('latin-1')
                else:
                    pdf_bytes = bytes(pdf_bytes) 
                # -----------------------------------

                st.session_state.pdf_bytes = pdf_bytes
                st.session_state.pdf_nome = f"relatorio_{st.session_state.mes_atual}_{st.session_state.ano_atual}.pdf"
                st.rerun()
