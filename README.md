# 💰 Controle Financeiro Pessoal

Aplicativo **Streamlit** completo para gestão de finanças pessoais.  
Permite registrar rendas, gastos fixos, compras do dia a dia, cartões de crédito, investimentos e gerar relatórios em PDF – tudo sincronizado com o Google Sheets.

---

## 📋 Funcionalidades

- 🔒 **Login multi‑usuário** com credenciais separadas.
- 📅 **Navegação por meses** (com setas) e comparação com o mês anterior.
- 💵 **Rendas** – fontes personalizáveis.
- 📌 **Gastos Fixos** – com lembretes de vencimento e auto‑preenchimento mensal.
- 🛍️ **Compras do Dia a Dia** – registro rápido, inclusive via foto do cupom fiscal (IA Gemini).
- 💳 **Cartões de Crédito e Guias** – controle de parcelas, importação de faturas em PDF/CSV e lembrete de pagamento.
- 📈 **Carteira de Investimentos** – acompanhamento de aportes, rendimentos e resgates.
- 🎯 **Metas de Orçamento** por categoria.
- 📊 **Gráficos interativos** – pizza, linha, Sankey, projeção futura.
- 📄 **Relatório mensal em PDF**.
- 🤖 **Inteligência Artificial (Gemini)** – análise financeira, sugestão de categoria e extração de dados de extratos.
- 🔍 **Pesquisa global** no histórico.

---

## 📁 Estrutura do Projeto
meu-controle-financeiro/
├── app.py # Arquivo principal da aplicação
├── modulos/
│ ├── utilidades.py # Constantes e funções de formatação/limpeza
│ ├── bd_google.py # Conexão, leitura e escrita no Google Sheets
│ ├── sidebar.py # Barra lateral (navegação e configurações)
│ ├── inicializacao.py # Carregamento inicial da sessão
│ ├── sessao.py # Lógica de carregamento dos dados mensais
│ ├── calculos.py # Cálculo de parcelas e datas
│ ├── relatorios.py # Geração do PDF
│ ├── ia_gemini.py # Integração com a API Gemini
├── tests/
│ ├── init.py
│ ├── test_utilidades.py # Testes das funções utilitárias
│ └── test_calculos.py # Testes das funções de cálculo
├── requirements.txt # Dependências do projeto
└── README.md


---

## ⚙️ Pré‑requisitos

- Python 3.10+
- Uma conta Google com acesso ao **Google Sheets** e ao **Google Cloud Console**.
- Uma **chave de API do Gemini** (opcional, mas recomendada para as funções de IA).
- As seguintes bibliotecas (listadas em `requirements.txt`):
```bash
streamlit
pandas
gspread
google-auth
plotly
fpdf
google-genai
Pillow
PyPDF2
pytest
````
---

## 🔧 Configuração

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/meu-controle-financeiro.git
cd meu-controle-financeiro
```

2. Crie e ative um ambiente virtual (recomendado)
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
````
3. Instale as dependências
```bash
pip install -r requirements.txt
```
4. Configure os segredos (secrets.toml)
```bash
# Usuários e senhas para login
[usuarios]
[usuarios.usuario1]
senha = "senha123"
url_planilha = "https://docs.google.com/spreadsheets/d/.../edit"

[usuarios.usuario2]
senha = "outrasenha"
url_planilha = "https://docs.google.com/spreadsheets/d/.../edit"

# Credenciais da conta de serviço do Google Sheets
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."

# Chave da API Gemini (opcional)
GEMINI_API_KEY = "sua-chave-aqui"
```
5. Prepare a planilha do Google Sheets

Sua planilha deve conter, pelo menos, as seguintes abas:

    Casuais – colunas: Mes_Ano, Data, Categoria, Descrição, Valor

    Fixos – colunas: Mes_Ano, Descrição, Categoria, Valor, Pago, Dia Venc.

    Guias – colunas: Guia, Descrição, Categoria, Valor Parcela, Data Compra, Mês Início, Ano Início, Qtd Parcelas

    Configuracoes – célula A1 com um JSON de configuração (gerado automaticamente pelo app)

🚀 Executando a aplicação

Com o ambiente virtual ativado, execute:
bash

streamlit run app.py5. Prepare a planilha do Google Sheets

Sua planilha deve conter, pelo menos, as seguintes abas:

    Casuais – colunas: Mes_Ano, Data, Categoria, Descrição, Valor

    Fixos – colunas: Mes_Ano, Descrição, Categoria, Valor, Pago, Dia Venc.

    Guias – colunas: Guia, Descrição, Categoria, Valor Parcela, Data Compra, Mês Início, Ano Início, Qtd Parcelas

    Configuracoes – célula A1 com um JSON de configuração (gerado automaticamente pelo app)

🚀 Executando a aplicação

Com o ambiente virtual ativado, execute:

streamlit run app.py

🧪 Executando os testes

O projeto inclui testes unitários usando pytest. Para executá‑los, na raiz do projeto digite:

pytest tests/

Os testes verificam as funções de formatação, conversão de moeda, cálculos de parcelas e outras utilidades.

☁️ Deploy no Streamlit Cloud

    Faça o push do repositório para o GitHub.

    Acesse Streamlit Cloud.

    Conecte seu repositório e aponte para app.py.

    Adicione os mesmos segredos (secrets.toml) diretamente na interface de configuração do app.

📄 Licença

Este projeto está sob a licença MIT – veja o arquivo LICENSE para detalhes.

🤝 Contribuições

Contribuições são bem‑vindas! Sinta‑se à vontade para abrir issues ou pull requests.

✨ Créditos - Max Giovanny

Desenvolvido com ❤️ utilizando Streamlit, Google Sheets API e Google Gemini.
