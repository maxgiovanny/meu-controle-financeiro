import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modulos.utilidades import (
    formatar_moeda_br,
    moeda_para_float,
    safe_float,
    safe_int,
    safe_str,
    safe_bool,
    remover_acentos
)

def test_formatar_moeda_br():
    assert formatar_moeda_br(1234.56) == "R$ 1.234,56"
    assert formatar_moeda_br(0) == "R$ 0,00"
    assert formatar_moeda_br(None) == "R$ 0,00"

def test_moeda_para_float():
    assert moeda_para_float("R$ 1.234,56") == 1234.56
    assert moeda_para_float("1.234,56") == 1234.56
    assert moeda_para_float("0") == 0.0
    assert moeda_para_float("") == 0.0
    assert moeda_para_float(None) == 0.0

def test_safe_float():
    import math
    assert safe_float("123.45") == 123.45
    assert safe_float(float('nan')) == 0.0
    assert safe_float(float('inf')) == 0.0
    assert safe_float(None) == 0.0
    assert safe_float("abc", 99.9) == 99.9

def test_safe_int():
    assert safe_int("5") == 5
    assert safe_int("abc") == 1
    assert safe_int(float('nan')) == 1
    assert safe_int(None, 10) == 10

def test_safe_str():
    import pandas as pd
    assert safe_str("teste") == "teste"
    assert safe_str(pd.NA) == ""
    assert safe_str(123) == "123"

def test_safe_bool():
    assert safe_bool("true") == True
    assert safe_bool("1") == True
    assert safe_bool("yes") == True
    assert safe_bool("false") == False
    assert safe_bool(None) == False

def test_remover_acentos():
    assert remover_acentos("ação") == "acao"
    assert remover_acentos("coração") == "coracao"
    assert remover_acentos("São Paulo") == "Sao Paulo"
