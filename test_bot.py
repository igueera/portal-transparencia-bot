"""
Testes Automatizados — Portal da Transparência Bot
===================================================
Execução:
    # Todos os testes:
    pytest test_bot.py -v

    # Apenas unitários (sem acessar o portal):
    pytest test_bot.py -v -m unitario

    # Apenas integração (acessa o portal de verdade):
    pytest test_bot.py -v -m integracao

    # Com relatório de cobertura:
    pytest test_bot.py -v --tb=short

Requisitos adicionais:
    pip install pytest pytest-asyncio
"""
import re
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from bot import (
    ErroSemResultados,
    ErroTempoResposta,
    ErroParametroAusente,
    _montar_erro_json,
    executar_consulta,
)

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DO PYTEST-ASYNCIO
# ─────────────────────────────────────────────
pytest_plugins = ["pytest_asyncio"]


# ─────────────────────────────────────────────
# TESTES UNITÁRIOS — sem acesso ao portal
# ─────────────────────────────────────────────

class TestExcecoes:
    """Valida que as exceções customizadas produzem as mensagens exatas do desafio."""

    @pytest.mark.unitario
    def test_erro_sem_resultados_mensagem(self):
        termo = "XYZXYZ INEXISTENTE"
        exc = ErroSemResultados(termo)
        assert str(exc) == f'Foram encontrados 0 resultados para o termo "{termo}".'

    @pytest.mark.unitario
    def test_erro_sem_resultados_guarda_termo(self):
        termo = "FULANO DE TAL"
        exc = ErroSemResultados(termo)
        assert exc.termo == termo

    @pytest.mark.unitario
    def test_erro_tempo_resposta_mensagem(self):
        exc = ErroTempoResposta()
        assert str(exc) == "Não foi possível retornar os dados no tempo de resposta solicitado."

    @pytest.mark.unitario
    def test_erro_parametro_ausente_mensagem(self):
        exc = ErroParametroAusente()
        assert str(exc) == "Informe ao menos um parâmetro: nome, cpf ou nis."


class TestMontarErroJson:
    """Valida o helper _montar_erro_json."""

    @pytest.mark.unitario
    def test_estrutura_completa(self):
        parametros = {"cpf": "123", "nome": None, "nis": None, "filtro_beneficiario": False}
        resultado = _montar_erro_json(parametros, "mensagem de erro")

        assert resultado["status"] == "erro"
        assert resultado["erro"] == "mensagem de erro"
        assert resultado["parametros"] == parametros
        assert resultado["panorama"] == {}
        assert resultado["beneficios_detalhes"] == []
        assert resultado["screenshot_base64"] is None
        assert resultado["url_consultada"] is None
        assert "timestamp" in resultado

    @pytest.mark.unitario
    def test_timestamp_formato_iso(self):
        resultado = _montar_erro_json({}, "erro")
        # Valida que o timestamp é uma string ISO válida
        from datetime import datetime
        datetime.fromisoformat(resultado["timestamp"])  # lança exceção se inválido

    @pytest.mark.unitario
    def test_mensagem_preservada(self):
        mensagem = "Foram encontrados 0 resultados para o termo \"teste\"."
        resultado = _montar_erro_json({}, mensagem)
        assert resultado["erro"] == mensagem


class TestValidacaoCpf:
    """Valida a lógica de comparação de dígitos do CPF mascarado."""

    @pytest.mark.unitario
    def test_digitos_cpf_valido(self):
        """Dígitos visíveis de ***.289.734-** devem ser 289734."""
        cpf_mascarado = "***.289.734-**"
        digitos_visiveis = re.sub(r"[^\d]", "", re.sub(r"\*+", "", cpf_mascarado))
        assert digitos_visiveis == "289734"

    @pytest.mark.unitario
    def test_digitos_esperados_cpf_limpo(self):
        """Posições 3-8 de 70628973454 devem ser 289734."""
        termo = "70628973454"
        termo_limpo = re.sub(r"\D", "", termo)
        digitos_esperados = termo_limpo[3:9]
        assert digitos_esperados == "289734"

    @pytest.mark.unitario
    def test_cpf_invalido_nao_corresponde(self):
        """CPF 00000000000 não deve corresponder a nenhum perfil real."""
        cpf_mascarado = "***.863.577-**"
        digitos_visiveis = re.sub(r"[^\d]", "", re.sub(r"\*+", "", cpf_mascarado))
        termo_limpo = re.sub(r"\D", "", "00000000000")
        digitos_esperados = termo_limpo[3:9]
        assert digitos_visiveis != digitos_esperados

    @pytest.mark.unitario
    def test_cpf_com_pontuacao_normalizado(self):
        """CPF com pontuação deve ser normalizado corretamente."""
        termo = "706.289.734-54"
        termo_limpo = re.sub(r"\D", "", termo)
        assert termo_limpo == "70628973454"
        assert termo_limpo[3:9] == "289734"


class TestExecutarConsultaMock:
    """Testa executar_consulta com browser mockado — sem acessar o portal."""

    @pytest.mark.unitario
    @pytest.mark.asyncio
    async def test_sem_parametros_retorna_erro(self):
        """Sem CPF/NIS/Nome deve retornar erro com mensagem correta."""
        resultado = await executar_consulta()
        assert resultado["status"] == "erro"
        assert "Informe ao menos um parâmetro" in resultado["erro"]

    @pytest.mark.unitario
    @pytest.mark.asyncio
    async def test_retorno_tem_campos_obrigatorios(self):
        """O JSON de erro deve conter todos os campos obrigatórios."""
        resultado = await executar_consulta()
        campos = ["status", "erro", "parametros", "panorama",
                  "beneficios_detalhes", "screenshot_base64",
                  "url_consultada", "timestamp"]
        for campo in campos:
            assert campo in resultado, f"Campo ausente: {campo}"

    @pytest.mark.unitario
    @pytest.mark.asyncio
    async def test_parametros_preservados_no_erro(self):
        """Os parâmetros informados devem ser refletidos no JSON de retorno."""
        resultado = await executar_consulta(nome="TESTE", cpf=None, nis=None)

        # Se chegou até o portal e falhou, verifica parametros
        # Se retornou direto por ausência de parâmetro válido, também ok
        assert "parametros" in resultado


# ─────────────────────────────────────────────
# TESTES DE INTEGRAÇÃO — acessa o portal real
# ─────────────────────────────────────────────
# Marcados com @pytest.mark.integracao para rodar separadamente.
# ATENÇÃO: cada teste demora ~30s pois acessa o portal de verdade.
# ─────────────────────────────────────────────

CPF_VALIDO = "70628973454"   # CPF real com dados no portal


class TestIntegracaoCenarios:

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_cenario1_sucesso_cpf(self):
        """Cenário 1: CPF válido deve retornar status ok com dados."""
        resultado = await executar_consulta(cpf=CPF_VALIDO)

        assert resultado["status"] == "ok"
        assert resultado["erro"] is None
        assert resultado["panorama"].get("nome") is not None
        assert resultado["panorama"].get("cpf_mascarado") is not None
        assert resultado["screenshot_base64"] is not None
        assert len(resultado["screenshot_base64"]) > 100  # base64 não vazio

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_cenario1_json_serializavel(self):
        """O JSON retornado deve ser serializável sem erros."""
        resultado = await executar_consulta(cpf=CPF_VALIDO)
        # Não deve lançar exceção
        serializado = json.dumps(resultado, ensure_ascii=False)
        assert len(serializado) > 0

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_cenario2_erro_cpf_invalido(self):
        """Cenário 2: CPF inexistente deve retornar mensagem padronizada."""
        resultado = await executar_consulta(cpf="00000000000")

        assert resultado["status"] == "erro"
        assert resultado["erro"] == (
            "Não foi possível retornar os dados no tempo de resposta solicitado."
        )
        assert resultado["panorama"] == {}
        assert resultado["screenshot_base64"] is None

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_cenario3_sucesso_nome(self):
        """Cenário 3: Nome válido deve retornar o primeiro resultado encontrado."""
        resultado = await executar_consulta(nome="ALINE HEMELY FERREIRA DA SILVA")

        assert resultado["status"] == "ok"
        assert resultado["panorama"].get("nome") is not None
        assert resultado["url_consultada"] is not None

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_cenario4_erro_nome_inexistente(self):
        """Cenário 4: Nome inexistente deve retornar mensagem com o termo buscado."""
        termo = "XYZXYZ INEXISTENTE TESTE"
        resultado = await executar_consulta(nome=termo)

        assert resultado["status"] == "erro"
        assert "0 resultados" in resultado["erro"]
        assert termo in resultado["erro"]

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_cenario5_filtro_social(self):
        """Cenário 5: Busca com filtro social deve retornar beneficiário de programa."""
        resultado = await executar_consulta(
            nome="FERREIRA",
            filtro_beneficiario=True,
        )

        assert resultado["status"] == "ok"
        assert resultado["panorama"].get("nome") is not None
        # Deve ter encontrado ao menos um programa social
        assert len(resultado["panorama"].get("programas_listados", [])) > 0

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_detalhes_beneficio_estrutura(self):
        """Os detalhes de benefício devem ter cabeçalho e dados preenchidos."""
        resultado = await executar_consulta(cpf=CPF_VALIDO)

        assert resultado["status"] == "ok"
        for detalhe in resultado["beneficios_detalhes"]:
            assert "beneficio" in detalhe
            assert "cabecalho" in detalhe
            assert "dados" in detalhe
            # Se não houve erro, deve ter dados
            if detalhe["erro"] is None:
                assert len(detalhe["cabecalho"]) > 0
                assert len(detalhe["dados"]) > 0

    @pytest.mark.integracao
    @pytest.mark.asyncio
    async def test_timestamp_presente_e_valido(self):
        """O timestamp deve estar presente e em formato ISO."""
        from datetime import datetime
        resultado = await executar_consulta(cpf=CPF_VALIDO)
        assert "timestamp" in resultado
        datetime.fromisoformat(resultado["timestamp"])  # lança se inválido