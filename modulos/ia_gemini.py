import streamlit as st
import json

# --- INICIALIZAÇÃO DO GEMINI ---
try:
    from google import genai
    GEMINI_DISPONIVEL = True
except ImportError:
    GEMINI_DISPONIVEL = False

gemini_ok = False
client = None

if GEMINI_DISPONIVEL and "GEMINI_API_KEY" in st.secrets:
    try:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        gemini_ok = True
    except Exception:
        pass # Falha silenciosa, a interface avisa que a IA não está disponível

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
    Forneça um feedback (max 200 palavras) e uma dica prática.
    """
    try:
        return api_analise_gemini(prompt)
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower(): return "⚠️ Limite de IA atingido. Tente depois."
        if "503" in str(e): return "⏳ A IA está com alta demanda. Tente depois."
        return f"Erro na IA: {e}"

def sugerir_categoria_gemini(descricao, categorias_disponiveis):
    if not gemini_ok or client is None: return "Outros"
    prompt = f"Com base na descrição, sugira a categoria mais adequada.\nOpções: {', '.join(categorias_disponiveis)}.\nDescrição: \"{descricao}\"\nResponda APENAS com o nome."
    try:
        return api_sugestao_gemini(prompt)
    except: return "Outros"      

def extrair_dados_recibo_gemini(imagem_pil, categorias_disponiveis):
    if not gemini_ok or client is None: return None
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
        return json.loads(texto_limpo)
    except Exception as e:
        st.error(f"Erro ao extrair: {e}")
        return None

def extrair_lote_extrato_gemini(texto_extrato, categorias_disponiveis):
    if not gemini_ok or client is None: return None
    prompt = f"""
    Aqui está o texto de um extrato bancário. Sua tarefa é extrair APENAS as DESPESAS/SAÍDAS (ignore recebimentos, transferências de mesma titularidade, saldos ou resgates de investimento).
    Para cada despesa encontrada, classifique-a em uma destas categorias: {', '.join(categorias_disponiveis)}.
    
    Retorne EXATAMENTE um array JSON, sem formatação markdown (```json), neste formato:
    [
        {{"Data": "YYYY-MM-DD", "Descrição": "Nome do local/Gasto", "Categoria": "Nome da Categoria", "Valor (R$)": 150.50}},
        ...
    ]
    
    Texto do extrato:
    {texto_extrato}
    """
    try:
        resposta = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_limpo)
    except Exception as e:
        st.error(f"Erro na extração em lote: {e}")
        return None
