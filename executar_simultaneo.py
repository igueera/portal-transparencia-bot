"""
Execuções Simultâneas — Portal da Transparência Bot
====================================================
Dispara múltiplas consultas em paralelo usando asyncio.gather().
Cada consulta roda em seu próprio browser isolado, permitindo
execuções verdadeiramente simultâneas sem conflito de estado.

Uso:
    python executar_simultaneo.py
    python executar_simultaneo.py --max-simultaneos 3

Requisitos:
    O arquivo teste.py (bot principal) deve estar na mesma pasta.
"""
import asyncio
import json
import argparse
from datetime import datetime
from pathlib import Path

# Importa a função principal do bot
from bot import executar_consulta

# ─────────────────────────────────────────────
# LISTA DE CONSULTAS PARA TESTE
# Edite aqui para adicionar suas próprias consultas.
# ─────────────────────────────────────────────
CONSULTAS = [
    {"cpf": "70628973453"},                                      # CPF válido
    {"cpf": "00000000000"},                                      # CPF inválido
    {"nome": "IGOR LIMA GABRIEL"},                               # Nome válido
    {"nome": "XYZXYZ INEXISTENTE TESTE"},                        # Nome inexistente
    {"nome": "FERREIRA", "filtro_beneficiario": True},           # Com filtro social
]

OUTPUT_DIR = Path("resultados_simultaneos")


async def executar_e_salvar(consulta: dict, indice: int, semaforo: asyncio.Semaphore) -> dict:
    """
    Executa uma consulta respeitando o semáforo de concorrência,
    salva o resultado em JSON e retorna um resumo.
    """
    async with semaforo:
        inicio = datetime.now()
        termo = consulta.get("cpf") or consulta.get("nis") or consulta.get("nome", "?")
        print(f"[{indice}] ▶ Iniciando consulta: {termo} | {inicio.strftime('%H:%M:%S')}")

        try:
            resultado = await executar_consulta(
                nome=consulta.get("nome"),
                cpf=consulta.get("cpf"),
                nis=consulta.get("nis"),
                filtro_beneficiario=consulta.get("filtro_beneficiario", False),
                headless=True,
            )
        except Exception as e:
            resultado = {
                "status": "erro",
                "erro": str(e),
                "parametros": consulta,
                "timestamp": inicio.isoformat(),
            }

        fim = datetime.now()
        duracao = (fim - inicio).total_seconds()

        # Salva JSON individual com nome único: INDEX_TERMO_DATAHORA.json
        termo_limpo = termo.replace(" ", "_").replace("/", "-")[:30]
        nome_arquivo = f"{indice:02d}_{termo_limpo}_{fim.strftime('%Y%m%d_%H%M%S')}.json"
        caminho = OUTPUT_DIR / nome_arquivo
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        status_icon = "✅" if resultado.get("status") == "ok" else "❌"
        print(
            f"[{indice}] {status_icon} Concluído: {termo} | "
            f"{duracao:.1f}s | {nome_arquivo}"
        )

        return {
            "indice": indice,
            "termo": termo,
            "status": resultado.get("status"),
            "erro": resultado.get("erro"),
            "duracao_segundos": round(duracao, 1),
            "arquivo": str(caminho),
        }


async def executar_simultaneamente(consultas: list, max_simultaneos: int = 3):
    """
    Dispara todas as consultas em paralelo, limitando a concorrência
    máxima pelo semáforo para não sobrecarregar o sistema.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Portal da Transparência — Execução Simultânea")
    print(f"{'='*60}")
    print(f"  Total de consultas : {len(consultas)}")
    print(f"  Máx. simultâneos   : {max_simultaneos}")
    print(f"  Início             : {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    inicio_total = datetime.now()
    semaforo = asyncio.Semaphore(max_simultaneos)

    # Dispara todas as tarefas ao mesmo tempo — o semáforo controla quantas
    # rodam de fato em paralelo
    tarefas = [
        executar_e_salvar(consulta, i + 1, semaforo)
        for i, consulta in enumerate(consultas)
    ]
    resumos = await asyncio.gather(*tarefas)

    fim_total = datetime.now()
    duracao_total = (fim_total - inicio_total).total_seconds()

    # ── Relatório final ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RELATÓRIO FINAL")
    print(f"{'='*60}")

    sucesso = sum(1 for r in resumos if r["status"] == "ok")
    erro = sum(1 for r in resumos if r["status"] != "ok")

    for r in sorted(resumos, key=lambda x: x["indice"]):
        icon = "✅" if r["status"] == "ok" else "❌"
        erro_msg = f" → {r['erro'][:60]}" if r["erro"] else ""
        print(f"  {icon} [{r['indice']:02d}] {r['termo'][:35]:<35} {r['duracao_segundos']}s{erro_msg}")

    print(f"\n  Sucesso  : {sucesso}/{len(consultas)}")
    print(f"  Erros    : {erro}/{len(consultas)}")
    print(f"  Duração  : {duracao_total:.1f}s (sequencial seria ~{sum(r['duracao_segundos'] for r in resumos):.0f}s)")
    print(f"  Arquivos : {OUTPUT_DIR}/")
    print(f"{'='*60}\n")

    # Salva relatório consolidado
    relatorio = {
        "timestamp": inicio_total.isoformat(),
        "total": len(consultas),
        "sucesso": sucesso,
        "erro": erro,
        "duracao_total_segundos": round(duracao_total, 1),
        "max_simultaneos": max_simultaneos,
        "consultas": resumos,
    }
    caminho_relatorio = OUTPUT_DIR / f"relatorio_{fim_total.strftime('%Y%m%d_%H%M%S')}.json"
    with open(caminho_relatorio, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
    print(f"  📊 Relatório consolidado: {caminho_relatorio}\n")

    return resumos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execução Simultânea — Portal Transparência Bot")
    parser.add_argument(
        "--max-simultaneos",
        type=int,
        default=3,
        help="Número máximo de consultas rodando ao mesmo tempo (padrão: 3)",
    )
    args = parser.parse_args()

    asyncio.run(executar_simultaneamente(CONSULTAS, max_simultaneos=args.max_simultaneos))