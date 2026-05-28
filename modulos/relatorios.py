import tempfile
import os
from fpdf import FPDF
from modulos.utilidades import remover_acentos

def formatar_moeda_pdf(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_pdf_mes(mes_nome, ano, renda_df, fixos_df, casuais_df,
                  guias_dados, total_renda, t_fix, t_cas, t_gui,
                  sobra, dados_categoria):
    pdf = FPDF()
    pdf.add_page()
    COR_TOPO = (46, 125, 50)
    COR_TITULO_SECAO = (225, 225, 225)
    COR_LINHA_DIVISORIA = (220, 220, 220)

    pdf.set_font('helvetica', 'B', 16)
    pdf.set_fill_color(*COR_TOPO)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, remover_acentos(f"EXTRATO FINANCEIRO - {mes_nome.upper()} {ano}"),
             ln=True, align="C", fill=True)
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
            if tipo == "renda":
                texto_esq = f"  {row['Fonte']}"
            elif tipo == "fixos":
                status = "(Pago)" if row.get("Pago", False) else "(Pendente)"
                texto_esq = f"  {row.get('Descrição', '')} [{row.get('Categoria', '')}] {status}"
            elif tipo == "casuais":
                d_str = row['Data'].strftime("%d/%m") if hasattr(row['Data'], 'strftime') else str(row['Data'])[:5]
                texto_esq = f"  {d_str} | {row.get('Categoria', '')} - {row.get('Descrição', '')}"
            if len(texto_esq) > 85:
                texto_esq = texto_esq[:82] + "..."
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
            if not parcelas:
                continue
            total_fatura = sum(row['Valor (R$)'] for row in parcelas)
            pdf.set_font('helvetica', 'B', 9)
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(140, 6, remover_acentos(f"    Fatura: {guia}"), border='B', fill=True)
            pdf.cell(50, 6, formatar_moeda_pdf(total_fatura), border='B', ln=True, align="R", fill=True)
            pdf.set_font('helvetica', '', 9)
            for row in parcelas:
                linha_texto = f"        - {row['Descrição']} ({row['Categoria']})"
                if len(linha_texto) > 75:
                    linha_texto = linha_texto[:72] + "..."
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
    pdf.set_text_color(0, 0, 0)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        temp_path = tmp.name
    pdf.output(temp_path)
    with open(temp_path, "rb") as f:
        pdf_data = f.read()
    os.remove(temp_path)
    return pdf_data
