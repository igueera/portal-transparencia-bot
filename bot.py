"""
Portal da Transparência - Web Scraping Bot
==========================================
Seletores validados via playwright codegen em 2025.
Requisitos:
    pip install playwright fastapi uvicorn python-multipart
    playwright install chromium
Uso direto:
    python portal_transparencia_bot.py --cpf 123.456.789-00
    python portal_transparencia_bot.py --nome "FULANO DE TAL"
    python portal_transparencia_bot.py --nis 12345678901
Como API:
    uvicorn portal_transparencia_bot:app --host 0.0.0.0 --port 8000
"""
import asyncio
import re
import base64
import json
import argparse
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext

# playwright-stealth: disfarça o Playwright como navegador humano
# Instalação: pip install playwright-stealth
try:
    # playwright-stealth 2.x usa Stealth como classe
    from playwright_stealth import Stealth
    async def stealth_async(page):
        await Stealth().apply_stealth_async(page)
    STEALTH_DISPONIVEL = True
except ImportError:
    STEALTH_DISPONIVEL = False
    print("[AVISO] playwright-stealth nao instalado. Execute: pip install playwright-stealth")

BASE_URL = "https://portaldatransparencia.gov.br"
BENEFICIOS_ALVO = ["Auxílio Brasil", "Auxílio Emergencial", "Bolsa Família"]
TIMEOUT_MS = 90_000

# ─────────────────────────────────────────────
# EXCEÇÕES CUSTOMIZADAS — cenários do desafio
# ─────────────────────────────────────────────

class ErroSemResultados(Exception):
    """
    Levantada quando a busca por nome não retorna nenhum registro.
    Mensagem padrão: "Foram encontrados 0 resultados para o termo …"
    """
    def __init__(self, termo: str):
        self.termo = termo
        super().__init__(f'Foram encontrados 0 resultados para o termo "{termo}".')


class ErroTempoResposta(Exception):
    """
    Levantada quando CPF/NIS não é encontrado ou o portal não retorna dados.
    Mensagem padrão do desafio.
    """
    def __init__(self):
        super().__init__(
            "Não foi possível retornar os dados no tempo de resposta solicitado."
        )


class ErroParametroAusente(Exception):
    """Levantada quando nenhum parâmetro de busca é informado."""
    def __init__(self):
        super().__init__("Informe ao menos um parâmetro: nome, cpf ou nis.")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _montar_erro_json(parametros: dict, mensagem: str) -> dict:
    """Monta o JSON de resposta de erro no formato padrão."""
    return {
        "parametros": parametros,
        "timestamp": datetime.now().isoformat(),
        "status": "erro",
        "panorama": {},
        "beneficios_detalhes": [],
        "screenshot_base64": None,
        "url_consultada": None,
        "erro": mensagem,
    }


async def criar_browser(headless: bool = True):
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="pt-BR",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        permissions=["geolocation"],
        extra_http_headers={
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    # Remove navigator.webdriver que delata o Playwright ao Cloudflare
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en'] });
        window.chrome = { runtime: {} };
    """)
    return pw, browser, context


async def aplicar_stealth(page: Page):
    """Aplica playwright-stealth na pagina se a lib estiver disponivel."""
    if STEALTH_DISPONIVEL:
        await stealth_async(page)
        print("[STEALTH] Patches aplicados na pagina")


async def fechar_cookies(page: Page, origem: str = ""):
    """Fecha o banner de cookies se estiver visível."""
    try:
        btn = page.get_by_role("button", name="Aceitar todos")
        visivel = await btn.is_visible()
        print(f"[COOKIE] Banner visível em '{origem}': {visivel}")
        if visivel:
            await btn.click()
            await page.wait_for_timeout(500)
            print(f"[COOKIE] Banner fechado em '{origem}'")
    except Exception:
        print(f"[COOKIE] Banner não encontrado em '{origem}'")


# ─────────────────────────────────────────────
# FLUXO PRINCIPAL
# ─────────────────────────────────────────────

async def buscar_pessoa(
    page: Page,
    nome: Optional[str] = None,
    cpf: Optional[str] = None,
    nis: Optional[str] = None,
    filtro_beneficiario: bool = False,
) -> dict:
    """
    Fluxo de navegação até o perfil da pessoa.
    Levanta exceções tipadas para cada cenário de erro do desafio.
    """
    if not any([nome, cpf, nis]):
        raise ErroParametroAusente()

    # Termo de busca: CPF ou NIS têm prioridade sobre nome
    termo = cpf or nis or nome
    busca_por_identificador = bool(cpf or nis)  # True = CPF/NIS; False = Nome

    # 1. Home
    print("[DEBUG] Acessando home...")
    await page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT_MS)
    await fechar_cookies(page, "home")

    # 2. Expandir menu Consultas
    print("[DEBUG] Expandindo menu de consultas...")
    await page.get_by_role("button", name="Expandir Consultas ").click()
    await page.wait_for_timeout(600)

    # 3. Clicar no flipcard de Pessoas (posição 10 no grid)
    print("[DEBUG] Clicando no flipcard...")
    await page.locator("div:nth-child(10) > .flipcard").click()
    await page.wait_for_timeout(800)

    # 4. Link "Busca de Pessoa Física"
    print("[DEBUG] Clicando em Busca de Pessoa Física...")
    await page.get_by_role("link", name="Busca de Pessoa Física").click()
    await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    print(f"[DEBUG] URL da busca: {page.url}")

    # 5. Filtro opcional
    if filtro_beneficiario:
        try:
            await page.get_by_role("button", name="Refine a Busca").click()
            await page.wait_for_timeout(400)
            await page.locator("#box-busca-refinada").get_by_text(
                "Beneficiário de Programa"
            ).click()
            print("[DEBUG] Filtro de programa social aplicado.")
        except Exception as e:
            print(f"[DEBUG] Filtro não aplicado (opcional): {e}")

    # 6. Preencher campo de busca
    print(f"[DEBUG] Preenchendo busca com: {termo}")
    campo = page.get_by_role("searchbox", name="Busque por Nome, Nis ou CPF (")
    await campo.click()
    await campo.fill(termo)
    await campo.press("Enter")

    # 7. Enviar formulário
    await page.get_by_role("button", name="Enviar dados do formulário de").click()
    await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    print(f"[DEBUG] URL após busca: {page.url}")

    # 8. Detectar e tratar resultados
    print("[DEBUG] Aguardando resultados da busca carregarem...")
    try:
        await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

        # ── Cenário: 0 resultados para nome ──────────────────────────────────
        # O portal exibe "Foram encontrados 0 resultados para o termo X"
        zero_result_locator = page.get_by_text(
            re.compile(r"Foram encontrados 0 resultados", re.IGNORECASE)
        )
        if await zero_result_locator.is_visible():
            raise ErroSemResultados(termo)

        # ── Cenário: CPF/NIS não encontrado (portal não retorna perfil) ───────
        # O portal pode exibir mensagem de "nenhum resultado" ou redirecionar
        # para página de erro ao buscar por CPF/NIS inválido.
        sem_resultado_locator = page.get_by_text(
            re.compile(r"nenhum resultado|não encontrado|0 registros", re.IGNORECASE)
        )
        if busca_por_identificador and await sem_resultado_locator.is_visible():
            raise ErroTempoResposta()

        # ── Aguarda os cards de resultado aparecerem ──────────────────────────
        await page.wait_for_selector(
            "text=Foram encontrados",
            state="visible",
            timeout=TIMEOUT_MS,
        )
        print("[DEBUG] Resultados carregados!")

        await fechar_cookies(page, "sobre resultados")
        await page.wait_for_timeout(500)

        await page.wait_for_selector(
            "a[href*='/busca/pessoa-fisica/']",
            state="visible",
            timeout=TIMEOUT_MS,
        )

        todos_links = await page.locator("a[href*='/busca/pessoa-fisica/']").all()
        print(f"[DEBUG] Total links encontrados: {len(todos_links)}")

        primeiro_link = todos_links[0]
        href = await primeiro_link.get_attribute("href")
        txt = await primeiro_link.inner_text()
        print(f"  [0] href={href} | texto={txt.strip()[:40]}")

        if not todos_links:
            # Nenhum card renderizado — comportamento de CPF/NIS inexistente
            if busca_por_identificador:
                raise ErroTempoResposta()
            raise ErroSemResultados(termo)

        primeiro = todos_links[0]
        texto = await primeiro.inner_text()
        print(f"[DEBUG] Clicando no resultado: {texto.strip()}")
        await primeiro.click()

        # ── Validação de CPF/NIS: confirma que o perfil retornado pertence
        # ao identificador buscado, comparando os dígitos visíveis do CPF
        # mascarado com os dígitos centrais do CPF/NIS informado.
        # O portal retorna resultados aleatórios para CPFs inválidos, então
        # precisamos rejeitar esses casos explicitamente.
        if busca_por_identificador:
            await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
            cpf_mascarado_el = page.get_by_text(re.compile(r"\*+\.\d+\.\d+-\*+")).first
            try:
                cpf_mascarado = (await cpf_mascarado_el.inner_text(timeout=5000)).strip()
                # Extrai dígitos visíveis do CPF mascarado (ex: ***.289.734-** → 289734)
                digitos_visiveis = re.sub(r"[^\d]", "", re.sub(r"\*+", "", cpf_mascarado))
                # Extrai os mesmos dígitos do termo buscado (posições 3-8 do CPF limpo)
                termo_limpo = re.sub(r"\D", "", termo)
                digitos_esperados = termo_limpo[3:9] if len(termo_limpo) >= 9 else ""
                print(f"[DEBUG] CPF mascarado: {cpf_mascarado} | visíveis: {digitos_visiveis} | esperados: {digitos_esperados}")
                if digitos_esperados and digitos_visiveis != digitos_esperados:
                    print("[DEBUG] CPF do perfil não corresponde ao buscado → ErroTempoResposta")
                    raise ErroTempoResposta()
            except ErroTempoResposta:
                raise
            except Exception as e:
                print(f"[DEBUG] Não foi possível validar CPF no perfil: {e}")

    except (ErroSemResultados, ErroTempoResposta):
        # Re-lança as exceções tipadas sem capturar
        raise

    except Exception as e:
        # Qualquer falha inesperada ao buscar por CPF/NIS vira ErroTempoResposta
        # (comportamento exigido pelo desafio); para nome, ErroSemResultados.
        print(f"[DEBUG] Falha inesperada na busca: {e}")
        await page.screenshot(path="debug_sem_resultado.png")
        if busca_por_identificador:
            raise ErroTempoResposta()
        raise ErroSemResultados(termo)

    await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    print(f"[DEBUG] URL do perfil: {page.url}")
    return {"url_perfil": page.url}


# ─────────────────────────────────────────────
# COLETA DE DADOS
# ─────────────────────────────────────────────

async def coletar_panorama(page: Page) -> dict:
    """
    Coleta dados da tela Panorama.
    Seletores validados via codegen na URL /busca/pessoa-fisica/ID-nome
    """
    dados = {}

    # Nome
    try:
        await page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
        spans = await page.locator("span").all()
        dados["nome"] = None
        for span in spans:
            txt = (await span.inner_text()).strip()
            if txt and txt.isupper() and len(txt) > 3 and not any(c.isdigit() for c in txt):
                dados["nome"] = txt
                print(f"[DEBUG] Nome coletado: {txt}")
                break
        if not dados["nome"]:
            print("[DEBUG] Nome não encontrado nos spans")
    except Exception as e:
        dados["nome"] = None
        print(f"[DEBUG] Nome não coletado: {e}")

    # CPF mascarado
    try:
        cpf_el = page.get_by_text(re.compile(r"\*+\.\d+\.\d+-\*+")).first
        dados["cpf_mascarado"] = (await cpf_el.inner_text()).strip()
        print(f"[DEBUG] CPF coletado: {dados['cpf_mascarado']}")
    except Exception as e:
        dados["cpf_mascarado"] = None
        print(f"[DEBUG] CPF não coletado: {e}")

    # Município-UF
    try:
        dados["municipio_uf"] = None
        bloco = page.get_by_text("Localidade", exact=True).first
        pai = bloco.locator("xpath=..")
        txt = (await pai.inner_text(timeout=5000)).strip()
        for linha in txt.splitlines():
            linha = linha.strip()
            partes = linha.split(" - ")
            if len(partes) == 2 and len(partes[1].strip()) == 2 and partes[1].strip().isupper():
                dados["municipio_uf"] = linha
                print(f"[DEBUG] Município coletado: {linha}")
                break
        if not dados["municipio_uf"]:
            print("[DEBUG] Município não encontrado no bloco Localidade")
    except Exception as e:
        dados["municipio_uf"] = None
        print(f"[DEBUG] Município não coletado: {e}")

    # Expandir "Recebimentos de recursos"
    try:
        btn = page.get_by_role("button", name="Recebimentos de recursos")
        await btn.click()
        await page.wait_for_timeout(1000)
        print("[DEBUG] Seção Recebimentos expandida")

        programas = []
        items = await page.locator("#accordion-recebimentos-recursos strong").all()
        for item in items:
            t = (await item.inner_text()).strip()
            if t and t not in programas:
                programas.append(t)
        print(f"[DEBUG] Programas coletados: {programas}")
        dados["programas_listados"] = programas
    except Exception as e:
        dados["programas_listados"] = []
        print(f"[DEBUG] Programas não coletados: {e}")

    # Benefícios visíveis
    beneficios_encontrados = []
    for b in BENEFICIOS_ALVO:
        try:
            el = page.get_by_text(b).first
            if await el.is_visible():
                beneficios_encontrados.append(b)
                print(f"[DEBUG] Benefício encontrado: {b}")
        except Exception:
            pass
    dados["beneficios_encontrados"] = beneficios_encontrados

    return dados


async def capturar_screenshot_base64(page: Page) -> str:
    screenshot_bytes = await page.screenshot(full_page=True)
    return base64.b64encode(screenshot_bytes).decode("utf-8")


async def coletar_detalhes_beneficio(
    page: Page, context: BrowserContext, beneficio: str
) -> dict:
    """
    Coleta detalhes de um benefício específico em nova aba.
    """
    detalhes = {
        "beneficio": beneficio,
        "cabecalho": [],
        "dados": [],
        "url_detalhe": None,
        "erro": None,
    }
    try:
        strong_beneficio = page.locator(
            "#accordion-recebimentos-recursos strong"
        ).filter(has_text=beneficio).first

        container = strong_beneficio.locator(
            "xpath=ancestor::div[.//a[contains(text(),'Detalhar')]]"
        ).first
        btn_detalhar = container.get_by_role("link", name="Detalhar").first
        href = await btn_detalhar.get_attribute("href")

        if not href:
            detalhes["erro"] = f"Link Detalhar não encontrado para {beneficio}"
            return detalhes

        url_detalhe = href if href.startswith("http") else f"{BASE_URL}{href}"
        detalhes["url_detalhe"] = url_detalhe
        print(f"[DEBUG] Abrindo detalhe: {url_detalhe}")

        nova_pagina = await context.new_page()
        # Opção A: aplica stealth antes de qualquer navegação (anti-Cloudflare)
        await aplicar_stealth(nova_pagina)
        # Opção B: reutiliza cookies da sessão principal (já passou pela verificação)
        cookies = await context.cookies()
        await context.add_cookies(cookies)
        await nova_pagina.goto(url_detalhe, wait_until="networkidle", timeout=TIMEOUT_MS)
        await fechar_cookies(nova_pagina, f"detalhe {beneficio}")

        # Aguarda a página carregar completamente
        await nova_pagina.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

        # Aguarda a tabela de detalhe pelo seu ID direto
        # ID confirmado via DevTools: tabelaDetalheDisponibilizado
        await nova_pagina.wait_for_selector(
            "#tabelaDetalheDisponibilizado", state="attached", timeout=TIMEOUT_MS
        )
        await nova_pagina.wait_for_selector(
            "#tabelaDetalheDisponibilizado tbody tr", state="attached", timeout=TIMEOUT_MS
        )
        print("[DEBUG] Tabela de detalhe localizada!")

        cabecalhos = await nova_pagina.locator(
            "#tabelaDetalheDisponibilizado thead th"
        ).all()
        if cabecalhos:
            header = [(await th.inner_text()).strip() for th in cabecalhos]
            detalhes["cabecalho"] = header
            print(f"[DEBUG] Cabeçalho: {header}")

        linhas = await nova_pagina.locator(
            "#tabelaDetalheDisponibilizado tbody tr"
        ).all()
        for linha in linhas:
            colunas = await linha.locator("td").all()
            valores = [(await col.inner_text()).strip() for col in colunas]
            if any(v for v in valores if v):
                detalhes["dados"].append(valores)

        print(f"[DEBUG] {beneficio}: {len(detalhes['dados'])} linhas coletadas")
        await nova_pagina.close()

    except Exception as e:
        detalhes["erro"] = str(e)
        print(f"[DEBUG] Erro ao coletar {beneficio}: {e}")

    return detalhes


# ─────────────────────────────────────────────
# ORQUESTRADOR
# ─────────────────────────────────────────────

async def executar_consulta(
    nome: Optional[str] = None,
    cpf: Optional[str] = None,
    nis: Optional[str] = None,
    filtro_beneficiario: bool = False,
    headless: bool = True,
) -> dict:
    """
    Orquestra o fluxo completo de consulta.
    Retorna sempre um dict com status 'ok' ou 'erro' e a mensagem padronizada.
    """
    parametros = {
        "nome": nome, "cpf": cpf, "nis": nis,
        "filtro_beneficiario": filtro_beneficiario,
    }

    resultado = {
        "parametros": parametros,
        "timestamp": datetime.now().isoformat(),
        "status": "ok",
        "panorama": {},
        "beneficios_detalhes": [],
        "screenshot_base64": None,
        "url_consultada": None,
        "erro": None,
    }

    pw, browser, context = await criar_browser(headless=headless)
    try:
        page = await context.new_page()
        nav = await buscar_pessoa(
            page, nome=nome, cpf=cpf, nis=nis,
            filtro_beneficiario=filtro_beneficiario,
        )
        resultado["url_consultada"] = nav["url_perfil"]
        resultado["panorama"] = await coletar_panorama(page)
        resultado["screenshot_base64"] = await capturar_screenshot_base64(page)

        programas_encontrados = resultado["panorama"].get("programas_listados", [])
        print(f"[DEBUG] Coletando detalhes de: {programas_encontrados}")
        for beneficio in programas_encontrados:
            try:
                detalhe = await coletar_detalhes_beneficio(page, context, beneficio)
                resultado["beneficios_detalhes"].append(detalhe)
            except Exception as e:
                resultado["beneficios_detalhes"].append(
                    {"beneficio": beneficio, "cabecalho": [], "dados": [], "erro": str(e)}
                )

    # ── Tratamento de erros tipados (mensagens padronizadas do desafio) ────────
    except ErroParametroAusente as e:
        return _montar_erro_json(parametros, str(e))

    except ErroSemResultados as e:
        return _montar_erro_json(parametros, str(e))

    except ErroTempoResposta as e:
        return _montar_erro_json(parametros, str(e))

    except Exception as e:
        # Fallback para erros inesperados — mantém rastreabilidade
        resultado["status"] = "erro"
        resultado["erro"] = str(e)

    finally:
        await browser.close()
        await pw.stop()

    return resultado


# ─────────────────────────────────────────────
# API FASTAPI + SWAGGER
# ─────────────────────────────────────────────

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse

    app = FastAPI(
        title="Portal Transparência Bot",
        description="Robô de consulta ao Portal da Transparência - Pessoas Físicas",
        version="1.0.0",
    )

    @app.get("/consultar", summary="Consulta pessoa física", tags=["Consulta"])
    async def consultar(
        cpf: Optional[str] = Query(None, description="CPF (ex: 123.456.789-00)"),
        nis: Optional[str] = Query(None, description="NIS/PIS/PASEP"),
        nome: Optional[str] = Query(None, description="Nome completo"),
        filtro_beneficiario: bool = Query(False, description="Filtrar por programa social"),
    ):
        if not any([cpf, nis, nome]):
            return JSONResponse(
                status_code=422,
                content=_montar_erro_json(
                    {"cpf": cpf, "nis": nis, "nome": nome, "filtro_beneficiario": filtro_beneficiario},
                    "Informe ao menos um parâmetro: cpf, nis ou nome.",
                ),
            )
        return await executar_consulta(
            nome=nome, cpf=cpf, nis=nis,
            filtro_beneficiario=filtro_beneficiario,
        )

    @app.get("/health", tags=["Status"])
    async def health():
        return {"status": "online", "timestamp": datetime.now().isoformat()}

except ImportError:
    app = None


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portal Transparência Bot")
    parser.add_argument("--cpf", help="CPF da pessoa")
    parser.add_argument("--nis", help="NIS da pessoa")
    parser.add_argument("--nome", help="Nome da pessoa")
    parser.add_argument("--filtro-beneficiario", action="store_true")
    parser.add_argument("--no-headless", action="store_true", help="Abrir navegador visível")
    parser.add_argument("--output", default="resultado.json")
    args = parser.parse_args()

    resultado = asyncio.run(
        executar_consulta(
            nome=args.nome,
            cpf=args.cpf,
            nis=args.nis,
            filtro_beneficiario=args.filtro_beneficiario,
            headless=not args.no_headless,
        )
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Resultado salvo em: {args.output}")
    print(f"   Status  : {resultado['status']}")
    print(f"   Nome    : {resultado['panorama'].get('nome', 'N/A')}")
    print(f"   URL     : {resultado['url_consultada']}")
    if resultado["erro"]:
        print(f"   ⚠ Erro  : {resultado['erro']}")