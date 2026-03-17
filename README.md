# Portal da Transparência Bot

Robô de automação web para consulta de pessoas físicas no [Portal da Transparência](https://portaldatransparencia.gov.br), desenvolvido em Python com Playwright. Suporta busca por CPF, NIS ou Nome, coleta dados de benefícios sociais, executa consultas simultâneas e expõe uma API REST documentada via Swagger.

---

## Estrutura do Projeto

```
portal-transparencia-bot/
├── bot.py                    # Bot principal + API FastAPI
├── executar_simultaneo.py    # Runner de execuções paralelas
├── test_bot.py               # Testes automatizados (unitários + integração)
├── pytest.ini                # Configuração do pytest
├── requirements.txt          # Dependências do projeto
├── resultado.json            # Último resultado de consulta individual
└── resultados_simultaneos/   # JSONs gerados nas execuções paralelas
```

---

## Instalação

**Pré-requisitos:** Python 3.10+

```bash
# 1. Clone o repositório
git clone <url-do-repositorio>
cd portal-transparencia-bot

# 2. Crie e ative o ambiente virtual
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Instale o navegador Chromium
playwright install chromium
```

---

## Uso

### Via linha de comando (CLI)

```bash
# Busca por CPF
python bot.py --cpf 12345678900

# Busca por NIS
python bot.py --nis 12345678901

# Busca por Nome
python bot.py --nome "FULANO DE TAL"

# Com filtro de programa social
python bot.py --nome "SILVA" --filtro-beneficiario

# Salvar resultado em arquivo específico
python bot.py --cpf 12345678900 --output meu_resultado.json

# Abrir navegador visível (útil para debug)
python bot.py --cpf 12345678900 --no-headless
```

### Via API REST

```bash
uvicorn bot:app --host 0.0.0.0 --port 8000
```

Acesse a documentação interativa em: **http://localhost:8000/docs**

#### Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/consultar` | Consulta pessoa física por CPF, NIS ou Nome |
| `GET` | `/health` | Verifica status da API |

#### Exemplos de requisição

```bash
# Por CPF
curl "http://localhost:8000/consultar?cpf=12345678900"

# Por Nome com filtro social
curl "http://localhost:8000/consultar?nome=SILVA&filtro_beneficiario=true"
```

### Execuções simultâneas

```bash
# Roda 5 consultas em paralelo (3 simultâneas por padrão)
python executar_simultaneo.py

# Controlar número de execuções simultâneas
python executar_simultaneo.py --max-simultaneos 5
```

> Edite a lista `CONSULTAS` no topo do `executar_simultaneo.py` para definir suas próprias consultas.

---

## Formato de Saída (JSON)

```json
{
  "parametros": {
    "nome": null,
    "cpf": "12345678900",
    "nis": null,
    "filtro_beneficiario": false
  },
  "timestamp": "2025-01-01T12:00:00.000000",
  "status": "ok",
  "panorama": {
    "nome": "FULANO DE TAL",
    "cpf_mascarado": "***.456.789-**",
    "municipio_uf": "RECIFE - PE",
    "programas_listados": ["Bolsa Família"],
    "beneficios_encontrados": ["Bolsa Família"]
  },
  "beneficios_detalhes": [
    {
      "beneficio": "Bolsa Família",
      "cabecalho": ["Mês de disponibilização", "Parcela", "UF", "Município", "Enquadramento", "Valor (R$)", "Observação"],
      "dados": [["01/2024", "1", "PE", "RECIFE", "BOLSA FAMILIA", "600.00", "NÃO HÁ"]],
      "url_detalhe": "https://portaldatransparencia.gov.br/beneficios/bolsa-familia/...",
      "erro": null
    }
  ],
  "screenshot_base64": "<imagem em base64>",
  "url_consultada": "https://portaldatransparencia.gov.br/busca/pessoa-fisica/...",
  "erro": null
}
```

### Cenários de erro

| Situação | `status` | `erro` |
|----------|----------|--------|
| CPF/NIS inexistente | `"erro"` | `"Não foi possível retornar os dados no tempo de resposta solicitado."` |
| Nome inexistente | `"erro"` | `"Foram encontrados 0 resultados para o termo \"...\"."` |
| Nenhum parâmetro informado | `"erro"` | `"Informe ao menos um parâmetro: nome, cpf ou nis."` |

---

## Testes

```bash
# Instalar dependências de teste
pip install pytest pytest-asyncio

# Apenas testes unitários (rápido, ~2s, sem acesso ao portal)
pytest test_bot.py -v -m unitario

# Apenas testes de integração (lento, ~3-4 min, acessa o portal)
pytest test_bot.py -v -m integracao

# Todos os testes
pytest test_bot.py -v
```

| Grupo | Testes | Descrição |
|-------|--------|-----------|
| Unitário | 9 | Exceções, JSON de erro, validação de CPF — sem internet |
| Integração | 7 | 5 cenários do desafio + estrutura de dados + timestamp |

---

## Decisões Técnicas

### Playwright vs Selenium
Playwright foi escolhido por suporte nativo a `async/await`, execução headless mais estável, API moderna com seletores mais precisos e melhor suporte a múltiplos contextos isolados — essencial para execuções simultâneas.

### Execuções simultâneas com asyncio
Cada consulta roda em um browser completamente isolado (`BrowserContext` próprio). O `asyncio.Semaphore` controla a concorrência máxima, evitando sobrecarga de memória. Em testes, 3 execuções simultâneas reduziram o tempo total de ~163s para ~71s (2.3x mais rápido).

### Anti-detecção de bot (Cloudflare)
O portal usa Cloudflare Human Verification nas páginas de detalhe de benefícios. A solução combina duas camadas: `playwright-stealth` (patches no fingerprint do navegador) e `add_init_script` que remove `navigator.webdriver` e simula propriedades de um navegador humano.

### Validação de CPF/NIS
O portal retorna resultados aleatórios para CPFs inválidos em vez de exibir erro. O bot valida o resultado comparando os dígitos visíveis do CPF mascarado no perfil com os dígitos nas mesmas posições do CPF buscado. Se não correspondem, lança `ErroTempoResposta`.

### Exceções customizadas
Três exceções tipadas (`ErroSemResultados`, `ErroTempoResposta`, `ErroParametroAusente`) garantem mensagens exatas conforme especificação do desafio, independente do ponto onde o erro ocorre.

---

## Dependências

```
playwright
fastapi
uvicorn
python-multipart
playwright-stealth
pytest
pytest-asyncio
```

---

## Parte 2 — Hiperautomação (Make.com)

A Parte 2 implementa um workflow automatizado no **Make.com** que integra o bot com Google Drive e Google Sheets, acionado via API em produção.

### Fluxo do Workflow

```
[1] HTTP Request → [2] Google Drive → [3] Google Sheets
```

**Módulo 1 — HTTP Request**
Chama a API do bot em produção (`https://portal-transparencia-bot.onrender.com/consultar`) com o CPF desejado e recebe o JSON com os dados coletados.

**Módulo 2 — Google Drive**
Salva o JSON retornado como arquivo na pasta `portal-transparencia-consultas` no Google Drive, com nome no formato:
```
[CPF]_[DATA_HORA].json
```

**Módulo 3 — Google Sheets**
Adiciona uma linha na planilha centralizada com os metadados da consulta:

| ID | Nome | CPF | Data_Hora | Link_JSON |
|----|------|-----|-----------|-----------|
| 2026-03-17T23:16:07... | FULANO DE TAL | 12345678900 | 17/03/2026 20:18:11 | https://drive.google.com/... |

### API em Produção

A API está disponível publicamente em:

**`https://portal-transparencia-bot.onrender.com`**

| Rota | Descrição |
|------|-----------|
| `/consultar` | Consulta pessoa física |
| `/health` | Status da API |
| `/docs` | Documentação Swagger interativa |

### Decisão Técnica — Make.com vs Alternativas

Make.com foi escolhido pela interface visual intuitiva e integração nativa com Google Drive e Google Sheets sem configuração extra. A autenticação foi configurada via OAuth 2.0 com Google Cloud Console para funcionar com conta Gmail pessoal.

---

## Observações

- O bot acessa dados **públicos** do Portal da Transparência (gov.br).
- CPFs exibidos são **mascarados** pelo próprio portal — o bot não armazena CPFs completos.
- Recomenda-se respeitar os limites de requisições do portal em execuções em lote.