# Evellyn - Dashboard SLA

Dashboard de SLA para chamados Jira, em Python, com:

- `pandas` para normalizacao e consolidacao dos tickets
- `Streamlit` para a interface
- integracao direta com o Google Sheets via API oficial
- filtros, metricas, alertas operacionais e exportacao em CSV
- **media por empresa calculada automaticamente**: volume de tickets, resolvidos, em aberto, atrasados, SLA no prazo (%), tempo medio de resolucao e atraso medio em dias uteis, com graficos comparativos e exportacao em CSV

## Media por empresa

A secao `Media por empresa` do dashboard elimina a necessidade de calculos manuais:

- agrupa os tickets por empresa (area: Pluggy, S1NC, Winner, etc.) ou por cliente
- calcula automaticamente, em dias uteis: tempo medio de resolucao e atraso medio
- mostra o percentual de SLA cumprido no prazo por empresa
- respeita os filtros aplicados na barra lateral (area, cliente, status, busca e periodo)
- permite baixar a tabela de medias em CSV

> Importante: `credentials.json`, `service_account.json` e `token.json` NUNCA devem ser enviados ao GitHub. Eles ja estao bloqueados no `.gitignore`. No deploy, use `st.secrets`.

## Estrutura

- `app.py`: interface da aplicacao
- `dashboard_core.py`: regras de negocio, normalizacao e metricas
- `google_sheets.py`: autenticacao e leitura das planilhas
- `requirements.txt`: dependencias da v2

## Como rodar

### 1. Entrar na pasta da v2

No PowerShell:

```powershell
cd "C:\Users\Bedetti\Documents\ms pickles\evelyn\dashboard-sla\v2"
```

### 2. Criar um ambiente virtual

Se o comando `py` existir:

```powershell
py -m venv .venv
```

Se o seu Windows usa `python` no PATH:

```powershell
python -m venv .venv
```

### 3. Ativar o ambiente virtual

No PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativacao, rode antes:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

e tente de novo o `Activate.ps1`.

### 4. Instalar as dependencias

```bash
pip install -r requirements.txt
```

As dependencias usadas pela v2 estao em `requirements.txt`:

- `streamlit`
- `pandas`
- `numpy`
- `plotly`
- `google-api-python-client`
- `google-auth-httplib2`
- `google-auth-oauthlib`

### 5. Credenciais do Google

#### Opcao mais simples para deploy no Streamlit Cloud

Use uma **service account** e salve o JSON dela em `st.secrets`.

Passos:

1. Crie uma service account no Google Cloud.
2. Gere a chave JSON.
3. Compartilhe a planilha com o e-mail da service account, com permissao de leitura.
4. No Streamlit Cloud, abra o app e va em:
   `App settings > Secrets`
5. Cole algo assim:

```toml
[gcp_service_account]
type = "service_account"
project_id = "seu-projeto"
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----
SUA_CHAVE_AQUI
-----END PRIVATE KEY-----"""
client_email = "nome-da-service-account@seu-projeto.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
universe_domain = "googleapis.com"
```

Nesse caso, a app usa `st.secrets["gcp_service_account"]` automaticamente e voce nao precisa de `credentials.json` no repositório.

#### Opcao local para desenvolvimento

Localmente, voce ainda pode usar:

- `credentials.json` para OAuth Desktop App
- `service_account.json` como arquivo local

Quickstart oficial:

- https://developers.google.com/workspace/sheets/api/quickstart/python

### 6. Rodar a aplicacao

```bash
streamlit run app.py
```

Se o `streamlit` nao estiver no PATH, use:

```powershell
python -m streamlit run app.py
```

ou:

```powershell
py -m streamlit run app.py
```

### 7. Abrir no navegador

Quando o servidor subir, o terminal vai mostrar algo assim:

```text
Local URL: http://localhost:8501
```

Abra esse endereco no navegador.

### 8. Preencher os campos da sidebar

Na aplicacao, preencha:

1. `Arquivo de credenciais` e `Arquivo de token` apenas no uso local
2. `Links da planilha`

O `token.json` sera criado automaticamente na primeira autenticacao quando voce usar OAuth local.

### 9. Carregar as fontes

Clique em `Carregar dashboard`. Se estiver tudo certo, a v2 vai:

- ler os ranges das planilhas no Google Sheets
- normalizar as colunas com `pandas`
- calcular SLA, atrasos e alertas operacionais
- montar grafico, metricas e tabela consolidada

### Exemplo completo de execucao

```powershell
cd "C:\Users\Bedetti\Documents\ms pickles\evelyn\dashboard-sla\v2"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

### Problemas comuns

- `py` nao encontrado:
  tente `python` no lugar de `py`.
- `streamlit` nao encontrado:
  confirme se o ambiente virtual esta ativado antes de rodar.
- tela abre mas nao carrega dados:
  confira se a URL/ID da planilha e o `range` estao corretos.
- erro de permissao no Google Sheets:
  confirme se a conta autenticada, ou a service account, tem acesso a planilha.
- Streamlit Cloud nao encontra `credentials.json`:
  use `st.secrets` com `gcp_service_account` em vez de subir o JSON no GitHub.

## Formato das fontes

### Formato simples

Agora voce pode usar apenas o link da planilha:

```text
https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0
```

Nesse modo, a aplicacao:

- extrai o `spreadsheetId` automaticamente
- lista as abas visiveis da planilha
- tenta ler cada aba em `A:ZZ`
- consolida tudo no dashboard

Esse e o formato recomendado se voce vai apenas mandar o link da planilha com permissao de leitura.

### Formato avancado opcional

No painel lateral, informe uma fonte por linha neste formato:

```text
nome_da_fonte|url_ou_id_da_planilha|aba!A:Z
```

Exemplo:

```text
Pluggy|https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0|Tickets!A:Z
S1NC|1abcDEFghiJKLmnoPQRstuVWxyz1234567890|Backlog!A:Z
Winner|https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=0|Operacao!A:Z
```

Se a planilha nao tiver coluna `Area`, o sistema usa o nome da fonte como fallback.
No modo simples, o nome da aba vira a referencia principal da fonte.

## Autenticacao

Esta v2 suporta dois cenarios:

- `st.secrets["gcp_service_account"]` para deploy simples no Streamlit Cloud
- `credentials.json` do OAuth Desktop App para uso local

## Referencias oficiais

- Python quickstart do Google Sheets API:
  https://developers.google.com/workspace/sheets/api/quickstart/python
- Leitura de valores no Google Sheets API:
  https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/get
