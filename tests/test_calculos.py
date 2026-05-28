import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from modulos.calculos import obter_mes_anterior, calc_parc_com_categoria

def test_obter_mes_anterior():
    assert obter_mes_anterior("Fevereiro", 2025) == ("Janeiro", 2025)
    assert obter_mes_anterior("Janeiro", 2025) == ("Dezembro", 2024)

def test_calc_parc_com_categoria():
    # DataFrame de exemplo com uma compra parcelada em 3x começando em Jan/2025
    df = pd.DataFrame([{
        "Descrição": "TV",
        "Valor Parcela (R$)": 100.0,
        "Mês Início (1-12)": 1,
        "Ano Início": 2025,
        "Qtd Parcelas": 3,
        "Categoria": "Eletrônicos"
    }])
    # Mês 1 (Jan) deve ter parcela
    parcelas, total, cats = calc_parc_com_categoria(df, 1, 2025)
    assert total == 100.0
    assert len(parcelas) == 1
    assert cats == {"Eletrônicos": 100.0}

    # Mês 4 (Abr) não deve ter parcela
    parcelas, total, _ = calc_parc_com_categoria(df, 4, 2025)
    assert total == 0.0
    assert parcelas.empty

    # DataFrame vazio
    parcelas, total, _ = calc_parc_com_categoria(pd.DataFrame(), 1, 2025)
    assert total == 0.0
