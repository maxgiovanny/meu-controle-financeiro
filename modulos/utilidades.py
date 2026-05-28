import pandas as pd
import math
import re

MESES = {"Janeiro":1,"Fevereiro":2,"Março":3,"Abril":4,"Maio":5,"Junho":6,
         "Julho":7,"Agosto":8,"Setembro":9,"Outubro":10,"Novembro":11,"Dezembro":12}
CATEGORIAS_PADRAO_BASE = ["Alimentação","Transporte","Lazer","Saúde","Casa","Trabalho","Outros"]

def formatar_moeda_br(valor):
    if valor is None: valor = 0.0
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def moeda_para_float(valor_str):
    if valor_str is None or valor_str == "": return 0.0
    if isinstance(valor_str, (int, float)): return float(valor_str)
    s = str(valor_str).strip()
    s = re.sub(r'^R\$', '', s)
    s = s.replace(" ", "").replace(",", ".")
    s = re.sub(r'[^\d.-]', '', s)
    if s.count('.') > 1:
        partes = s.split('.')
        s = ''.join(partes[:-1]) + '.' + partes[-1]
    try: return float(s)
    except: return 0.0

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
