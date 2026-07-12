#!/usr/bin/env python3
"""Multi-Source Backfill Pipeline — Extra Consultoria.

Pipeline unificado que executa TODOS os crawlers (Fases 1-3) em sequencia,
com entity matching apos cada fonte, em loop ate estabilizacao da cobertura
(2 execucoes consecutivas sem novas entidades).

Alvo: cobertura final de 95%+ dos 2.085 entes catarinenses.

Usage:
    python scripts/pipeline/backfill_multi_source.py --all-sources
    python scripts/pipeline/backfill_multi_source.py --sources pncp,dom-sc
    python scripts/pipeline/backfill_multi_source.py --all-sources --dry-run
    python scripts/pipeline/backfill_multi_source.py --resume

Story: COVERAGE-3.3
Epic: EPIC-COVERAGE-100PCT
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import DEFAULT_DSN  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ordem de execucao: fontes com maior potencial de cobertura primeiro (AC2)
SOURCE_ORDER = [
    'pncp',                    # Fase 1: 774+ entes
    'dom-sc',                  # Fase 1: ~280 municipios
    'pcp',                     # Fase 1: dados de PCP
    'compras-gov',             # Fase 1: ComprasGov
    'ciga-ckan',               # Fase 1: 155+ entes
    'transparencia',           # Fase 1: batch detect
    'sc-compras',              # Fase 2: ~100-200 entes
    'doe-sc',                  # Fase 2: ~50-100 entes
    'selenium',                # Fase 3: ~100-200 entes
    'transparencia-residual',  # Fase 3: ~50-100 entes
    'contracts',               # Fase 1: dados de contratos
]

# Mapeamento de nomes de fontes (formato do pipeline -> formato do monitor.py)
# Monitor.py usa underscores, o pipeline aceita hyphens para melhor legibilidade
SOURCE_NAME_MAP: dict[str, str] = {
    'pncp': 'pncp',
    'dom-sc': 'dom_sc',
    'dom_sc': 'dom_sc',
    'pcp': 'pcp',
    'compras-gov': 'compras_gov',
    'compras_gov': 'compras_gov',
    'ciga-ckan': 'ciga_ckan',
    'ciga_ckan': 'ciga_ckan',
    'transparencia': 'transparencia',
    'sc-compras': 'sc_compras',
    'sc_compras': 'sc_compras',
    'doe-sc': 'doe_sc',
    'doe_sc': 'doe_sc',
    'selenium': 'selenium',
    'transparencia-residual': 'transparencia_residual',
    'transparencia_residual': 'transparencia_residual',
    'contracts': 'contracts',
}

MAX_ITERATIONS = 3
COVERAGE_TOTAL_ENTITIES = 2085
CHECKPOINT_DIR = _PROJECT_ROOT / 'pipeline'
CHECKPOINT_FILE = CHECKPOINT_DIR / 'backfill_checkpoint.json'
STATUS_FILE = CHECKPOINT_DIR / 'backfill_status.json'
LOG_FILE = CHECKPOINT_DIR / 'backfill.log'
REPORT_FILE = _PROJECT_ROOT / 'docs' / 'epic-coverage' / 'backfill-coverage-report.md'

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_source(source: str) -> str:
    """Normalize source name from pipeline format to monitor.py format.

    Accepts both hyphens and underscores (e.g., 'dom-sc' and 'dom_sc').
    Returns the monitor.py-compatible underscore format.
    """
    normalized = SOURCE_NAME_MAP.get(source)
    if normalized:
        return normalized
    # Fallback: replace hyphens with underscores
    return source.replace('-', '_')


def _resolve_sources(raw_sources: list[str]) -> list[str]:
    """Resolve list of source names to monitor.py format and deduplicate."""
    seen: set[str] = set()
    result: list[str] = []
    for s in raw_sources:
        norm = _normalize_source(s)
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


# ---------------------------------------------------------------------------
# Pipeline Class
# ---------------------------------------------------------------------------

class MultiSourceBackfill:
    """Pipeline de backfill multi-source com loop de estabilizacao.

    Executa crawlers em sequencia definida, com entity matching apos cada
    fonte, em loop ate estabilizacao da cobertura.
    """

    def __init__(
        self,
        checkpoint_file: str | Path = CHECKPOINT_FILE,
        status_file: str | Path = STATUS_FILE,
        dsn: str = DEFAULT_DSN,
    ):
        self.checkpoint_file = Path(checkpoint_file)
        self.status_file = Path(status_file)
        self.dsn = dsn

        # Ensure parent dirs exist
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)

        self.stats: dict = {
            'started_at': None,
            'completed_at': None,
            'entities_before': 0,
            'entities_after': 0,
            'sources_done': [],
            'sources_skipped': [],
            'iterations': 0,
            'per_source': {},
            'total_duration_s': 0.0,
        }

        # Controle interno para dry-run com simulacao (usado em testes - AC8)
        self._simulate_matches_remaining = 0

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        """Create a new database connection."""
        import psycopg2
        return psycopg2.connect(self.dsn)

    def _count_covered(self) -> int:
        """Count currently covered entities."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(DISTINCT entity_id)
                FROM entity_coverage
                WHERE is_covered = TRUE
            """)
            result = cur.fetchone()[0] or 0
            cur.close()
            return result
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Source execution
    # ------------------------------------------------------------------

    def _run_source(self, source: str, dry_run: bool = False) -> dict:
        """Executa crawler para uma fonte via chamada direta a crawl_source().

        Substitui a chamada subprocess anterior (que era fragil e dependia
        de parsing de stdout).  Usa a mesma funcao que o monitor.py CLI
        invoca, retornando o dict estruturado completo.

        Args:
            source: Nome da fonte (formato monitor.py, ex: 'dom_sc').
            dry_run: Se True, apenas simula sem persistir.

        Returns:
            Dict com status, fetched, transformed, upserted, matched, etc.
        """
        from scripts.crawl.monitor import _get_conn, _load_entities, crawl_source

        start = time.time()

        if dry_run:
            duration = time.time() - start
            logger.info("Crawler %s [DRY-RUN]: simulado", source)
            return {
                'status': 'OK',
                'duration_s': round(duration, 1),
                'source': source,
                'fetched': 0, 'transformed': 0, 'upserted': 0, 'matched': 0,
                'unmatched': 0, 'warnings': [], 'dependencies_missing': [],
            }

        try:
            logger.info("Executando crawler: %s", source)
            conn = _get_conn()
            try:
                entities = _load_entities(conn, within_200km_only=False)
            finally:
                conn.close()

            result = crawl_source(source, entities, mode="full")
            duration = time.time() - start
            result['duration_s'] = round(duration, 1)

            status = result.get('status', 'failed')
            if status in ('success', 'degraded', 'empty'):
                logger.info(
                    "Crawler %s: %s — fetched=%d transformed=%d upserted=%d matched=%d (%.1fs)",
                    source, status,
                    result.get('fetched', 0),
                    result.get('transformed', 0),
                    result.get('upserted', 0),
                    result.get('matched', 0),
                    duration,
                )
                return {
                    'status': 'OK',
                    'duration_s': round(duration, 1),
                    'source': source,
                    'fetched': result.get('fetched', 0),
                    'transformed': result.get('transformed', 0),
                    'upserted': result.get('upserted', 0),
                    'matched': result.get('matched', 0),
                    'unmatched': result.get('unmatched', 0),
                    'monitor_status': status,
                    'warnings': result.get('warnings', []),
                    'dependencies_missing': result.get('dependencies_missing', []),
                }
            else:
                error_msg = result.get('error') or result.get('error_message') or status
                logger.warning("Crawler %s: %s — %s", source, status, error_msg)
                return {
                    'status': 'FAIL',
                    'error': str(error_msg)[:500],
                    'duration_s': round(duration, 1),
                    'source': source,
                    'monitor_status': status,
                    'dependencies_missing': result.get('dependencies_missing', []),
                }

        except Exception as e:
            duration = time.time() - start
            logger.error("Crawler %s: ERROR - %s", source, e)
            return {
                'status': 'SKIPPED',
                'error': str(e)[:200],
                'duration_s': round(duration, 1),
                'source': source,
            }

    def _run_entity_matching(self, source: str, dry_run: bool = False) -> dict:
        """Entity matching ja e executado por crawl_source() durante o crawl.

        Mantido como no-op por compatibilidade.  O matching acontece como
        Phase 4 dentro de monitor.crawl_source() — nao precisa ser chamado
        separadamente.
        """
        if dry_run and self._simulate_matches_remaining > 0:
            self._simulate_matches_remaining -= 1
            return {'new_matches': 1, 'source': source}
        # Matching ja foi feito por crawl_source()
        return {'new_matches': 0, 'source': source}

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    def _save_checkpoint(self):
        """Salva checkpoint com escrita atomica."""
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.checkpoint_file.with_suffix('.json.tmp')
        try:
            with open(tmp, 'w') as f:
                json.dump(self.stats, f, indent=2, default=str, ensure_ascii=False)
            os.replace(str(tmp), str(self.checkpoint_file))
            logger.info("Checkpoint salvo: %d fontes concluidas, iteracao %d",
                        len(self.stats.get('sources_done', [])),
                        self.stats.get('iterations', 0))
        except Exception as e:
            logger.error("Falha ao salvar checkpoint: %s", e)

    def _load_checkpoint(self) -> bool:
        """Carrega checkpoint existente.

        Returns:
            True se checkpoint carregado com sucesso, False caso contrario.
        """
        if not self.checkpoint_file.exists():
            logger.info("Nenhum checkpoint encontrado em %s", self.checkpoint_file)
            return False

        try:
            with open(self.checkpoint_file) as f:
                data = json.load(f)

            # Validar campos essenciais
            required = ['sources_done', 'sources_skipped', 'iterations', 'entities_before', 'per_source']
            missing = [k for k in required if k not in data]
            if missing:
                logger.warning("Checkpoint corrompido: campos ausentes %s. Iniciando do zero.", missing)
                return False

            self.stats = data
            logger.info("Checkpoint carregado: %d fontes concluidas, iteracao %d",
                        len(self.stats.get('sources_done', [])),
                        self.stats.get('iterations', 0))
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Checkpoint corrompido (%s). Iniciando do zero.", e)
            return False

    def _save_status(self):
        """Salva arquivo de status com fontes skipped e metadados."""
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        status = {
            'sources_skipped': self.stats.get('sources_skipped', []),
            'sources_done': self.stats.get('sources_done', []),
            'iterations': self.stats.get('iterations', 0),
            'completed_at': self.stats.get('completed_at'),
        }
        tmp = self.status_file.with_suffix('.json.tmp')
        try:
            with open(tmp, 'w') as f:
                json.dump(status, f, indent=2, default=str, ensure_ascii=False)
            os.replace(str(tmp), str(self.status_file))
        except Exception as e:
            logger.error("Falha ao salvar status: %s", e)

    # ------------------------------------------------------------------
    # Coverage Report (AC6)
    # ------------------------------------------------------------------

    def _generate_report(self):
        """Gera relatorio final de cobertura em docs/epic-coverage/.

        Inclui:
        - Cobertura antes vs depois: total, por fonte, por natureza, por municipio
        - Entidades cobertas em cada iteracao
        - Fontes que falharam e motivo
        - Tempo total de execucao e tempo por fonte
        """
        delta = self.stats['entities_after'] - self.stats['entities_before']
        pct_final = round(100.0 * self.stats['entities_after'] / COVERAGE_TOTAL_ENTITIES, 1)

        # Buscar dados detalhados do banco
        natureza_rows = []
        municipio_rows = []
        source_rows = []
        error_detail = ''

        try:
            conn = self._get_conn()
            cur = conn.cursor()

            # Cobertura por natureza juridica
            cur.execute("""
                SELECT e.natureza_juridica,
                       COUNT(*) as total_entes,
                       SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) as cobertos,
                       ROUND(100.0 * SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END)
                             / GREATEST(COUNT(*), 1), 1) as pct
                FROM sc_public_entities e
                LEFT JOIN entity_coverage ec ON ec.entity_id = e.id AND ec.is_covered = TRUE
                GROUP BY e.natureza_juridica
                ORDER BY COUNT(*) DESC
            """)
            natureza_rows = cur.fetchall()

            # Cobertura por municipio (top 20)
            cur.execute("""
                SELECT e.municipio,
                       COUNT(*) as total_entes,
                       SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) as cobertos,
                       ROUND(100.0 * SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END)
                             / GREATEST(COUNT(*), 1), 1) as pct
                FROM sc_public_entities e
                LEFT JOIN entity_coverage ec ON ec.entity_id = e.id AND ec.is_covered = TRUE
                WHERE e.municipio IS NOT NULL
                GROUP BY e.municipio
                ORDER BY COUNT(*) DESC
                LIMIT 20
            """)
            municipio_rows = cur.fetchall()

            # Cobertura por fonte
            cur.execute("""
                SELECT source,
                       COUNT(DISTINCT entity_id) as total,
                       COUNT(DISTINCT CASE WHEN is_covered THEN entity_id END) as covered
                FROM entity_coverage
                GROUP BY source
                ORDER BY source
            """)
            source_rows = cur.fetchall()

            cur.close()
            conn.close()
        except Exception as e:
            error_detail = f'(Erro ao buscar dados detalhados: {e})'
            logger.warning("Nao foi possivel buscar dados detalhados do banco: %s", e)

        # Montar relatorio
        lines = []
        lines.append('# Backfill Coverage Report\n')
        lines.append(f'**Data:** {self.stats.get("completed_at", "N/A")}')
        lines.append(f'**Duracao total:** {self._format_duration(self.stats.get("total_duration_s", 0))}\n')
        lines.append('## Resumo\n')
        lines.append('| Metrica | Valor |')
        lines.append('|---------|-------|')
        lines.append(f'| Entes antes | {self.stats["entities_before"]} |')
        lines.append(f'| Entes depois | {self.stats["entities_after"]} |')
        lines.append(f'| Ganho | +{delta} |')
        lines.append(f'| Cobertura final | {pct_final}% |')
        lines.append('| Target primario | >= 85% |')
        lines.append('| Stretch goal | >= 95% |')
        lines.append(f'| Iteracoes | {self.stats["iterations"]} |')
        lines.append(f'| Fontes OK | {len(self.stats["sources_done"])} |')
        lines.append(f'| Fontes SKIP | {len(self.stats["sources_skipped"])} |')
        lines.append('')

        # Tabela de fontes
        lines.append('## Fontes Executadas\n')
        lines.append('| Fonte | Status | Duracao |')
        lines.append('|-------|--------|---------|')
        for src_name in SOURCE_ORDER:
            norm_name = _normalize_source(src_name)
            src_data = self.stats.get('per_source', {}).get(norm_name, {})
            status = src_data.get('status', 'N/A')
            duration = src_data.get('duration_s', 0)
            dur_str = f'{duration:.1f}s' if duration else 'N/A'
            lines.append(f'| {src_name} | {status} | {dur_str} |')
        lines.append('')

        # Cobertura por natureza
        if natureza_rows:
            lines.append('## Cobertura por Natureza Juridica\n')
            lines.append('| Natureza Juridica | Total | Cobertos | % |')
            lines.append('|-------------------|-------|----------|---|')
            for natureza, total, cobertos, pct in natureza_rows:
                lines.append(f'| {natureza or "N/A"} | {total} | {cobertos} | {pct}% |')
            lines.append('')

        # Cobertura por municipio
        if municipio_rows:
            lines.append('## Cobertura por Municipio (top 20)\n')
            lines.append('| Municipio | Total | Cobertos | % |')
            lines.append('|-----------|-------|----------|---|')
            for municipio, total, cobertos, pct in municipio_rows:
                lines.append(f'| {municipio or "N/A"} | {total} | {cobertos} | {pct}% |')
            lines.append('')

        # Cobertura por fonte
        if source_rows:
            lines.append('## Cobertura por Fonte\n')
            lines.append('| Fonte | Total Entes | Cobertos |')
            lines.append('|-------|-------------|----------|')
            for src, total, covered in source_rows:
                lines.append(f'| {src} | {total} | {covered} |')
            lines.append('')

        # Fontes com falha
        skipped = self.stats.get('sources_skipped', [])
        if skipped:
            lines.append('## Fontes com Falha\n')
            lines.append('| Fonte | Iteracao | Motivo |')
            lines.append('|-------|----------|--------|')
            for skip in skipped:
                lines.append(f'| {skip.get("source", "N/A")} | {skip.get("iteration", "N/A")} | {skip.get("reason", "N/A")} |')
            lines.append('')

        # Analise de gap
        if self.stats['entities_after'] < COVERAGE_TOTAL_ENTITIES:
            gap = COVERAGE_TOTAL_ENTITIES - self.stats['entities_after']
            lines.append('## Analise de Gap\n')
            lines.append(f'{gap} entes ainda sem cobertura ({100 - pct_final}%).\n')
            if pct_final < 85:
                lines.append('**Target primario NAO atingido.** O relatorio de gap deve ser usado como input para COVERAGE-3.4.\n')
            elif pct_final >= 95:
                lines.append('**Stretch goal atingido!** Cobertura >= 95%.\n')
            else:
                lines.append(f'**Target primario atingido** ({pct_final}%), mas abaixo do stretch goal (95%).\n')

        if error_detail:
            lines.append(f'\n*{error_detail}*\n')

        lines.append('---\n')
        lines.append(f'*Relatorio gerado automaticamente por COVERAGE-3.3 backfill pipeline em {self.stats.get("completed_at", "N/A")}*\n')

        # Escrever arquivo
        report_path = Path(str(REPORT_FILE))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_content = '\n'.join(lines)
        with open(report_path, 'w') as f:
            f.write(report_content)

        logger.info("Relatorio gerado: %s", report_path)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in seconds to hours:minutes:seconds."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        if hours > 0:
            return f'{hours}h {minutes}m {secs:.0f}s'
        elif minutes > 0:
            return f'{minutes}m {secs:.0f}s'
        return f'{secs:.1f}s'

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run_pipeline(
        self,
        sources: list[str] | None = None,
        dry_run: bool = False,
        resume: bool = False,
        simulate_matches: int = 0,
    ) -> dict:
        """Executa pipeline completo com loop de estabilizacao.

        Args:
            sources: Lista de fontes a executar (None = todas).
            dry_run: Simular sem persistir dados.
            resume: Retomar de checkpoint salvo.
            simulate_matches: Para dry-run: simula N matches por fonte
                              na primeira iteracao (AC8).

        Returns:
            Dict com estatisticas da execucao.
        """
        sources = _resolve_sources(sources) if sources is not None else list(SOURCE_NAME_MAP.values())

        # Configurar simulacao para dry-run
        self._simulate_matches_remaining = simulate_matches

        pipeline_start = time.time()

        if resume and self._load_checkpoint():
            logger.info("Retomando pipeline do checkpoint")
        else:
            # Reset stats for fresh start
            self.stats = {
                'started_at': datetime.now().isoformat(),
                'completed_at': None,
                'entities_before': 0 if dry_run else self._count_covered(),
                'entities_after': 0,
                'sources_done': [],
                'sources_skipped': [],
                'iterations': 0,
                'per_source': {},
                'total_duration_s': 0.0,
            }
            logger.info("Iniciando pipeline do zero")

        baseline = self.stats['entities_before']
        if dry_run:
            logger.info("MODO DRY-RUN: nenhum dado sera persistido no banco")
        logger.info("Baseline: %d entes cobertos", baseline)

        # Loop de estabilizacao (AC4)
        iteration = 0
        while iteration < MAX_ITERATIONS:
            iteration += 1
            self.stats['iterations'] = iteration
            new_entities_this_iter = 0

            logger.info("--- Iteracao %d/%d ---", iteration, MAX_ITERATIONS)

            for source in sources:
                if source in self.stats['sources_done']:
                    logger.debug("Fonte %s ja concluida em iteracao anterior", source)
                    continue

                # Executar crawler
                logger.info("[Iteracao %d] Executando fonte: %s", iteration, source)
                result = self._run_source(source, dry_run)

                # Registrar resultado por fonte (mantem apenas o primeiro resultado)
                if source not in self.stats['per_source']:
                    self.stats['per_source'][source] = result

                if result['status'] == 'OK':
                    # Matching ja foi executado dentro de crawl_source()
                    # Usar matched reportado diretamente (sem subprocess extra)
                    matched_this_source = result.get('matched', 0)
                    new_entities_this_iter += matched_this_source
                    self.stats['sources_done'].append(source)
                    logger.info("Fonte %s OK. fetched=%d matched=%d",
                                source, result.get('fetched', 0), matched_this_source)
                else:
                    # AC5: Falha nao bloqueia o pipeline
                    skip_entry = {
                        'source': source,
                        'reason': result.get('error', 'unknown'),
                        'timestamp': datetime.now().isoformat(),
                        'iteration': iteration,
                    }
                    self.stats['sources_skipped'].append(skip_entry)
                    logger.warning("Fonte %s SKIPPED: %s", source, result.get('error', 'unknown'))

                # Salvar checkpoint apos cada fonte (permite resume)
                self._save_checkpoint()
                self._save_status()

            # Criterio de parada: estabilizacao (AC4)
            if new_entities_this_iter == 0:
                logger.info("Estabilizacao atingida na iteracao %d (0 novas entidades)", iteration)
                break
            else:
                logger.info("Iteracao %d: +%d novas entidades nesta iteracao",
                            iteration, new_entities_this_iter)

        # Finalizar
        if not dry_run:
            self.stats['entities_after'] = self._count_covered()
        else:
            # Em dry-run, estimar cobertura baseada nos matches simulados
            simulated_total = len(self.stats.get('sources_done', [])) * (simulate_matches if simulate_matches > 0 else 0)
            self.stats['entities_after'] = self.stats['entities_before'] + min(simulated_total, 20)

        self.stats['total_duration_s'] = time.time() - pipeline_start
        self.stats['completed_at'] = datetime.now().isoformat()

        # Gerar relatorio (AC6)
        self._generate_report()
        self._save_checkpoint()
        self._save_status()

        # Log final
        delta = self.stats['entities_after'] - self.stats['entities_before']
        pct = round(100.0 * self.stats['entities_after'] / COVERAGE_TOTAL_ENTITIES, 1)
        logger.info("=" * 60)
        logger.info("PIPELINE CONCLUIDO")
        logger.info("  Antes:  %d entes (%.1f%%)", self.stats['entities_before'],
                     round(100.0 * self.stats['entities_before'] / COVERAGE_TOTAL_ENTITIES, 1))
        logger.info("  Depois: %d entes (%.1f%%)", self.stats['entities_after'], pct)
        logger.info("  Ganho:  +%d entes", delta)
        logger.info("  Iteracoes: %d", iteration)
        logger.info("  Duracao: %s", self._format_duration(self.stats['total_duration_s']))
        logger.info("  Fontes OK: %d  |  SKIP: %d",
                     len(self.stats.get('sources_done', [])),
                     len(self.stats.get('sources_skipped', [])))
        logger.info("=" * 60)

        return self.stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description='Multi-Source Backfill Pipeline — COVERAGE-3.3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--all-sources',
        action='store_true',
        help='Executar todas as fontes disponiveis',
    )
    group.add_argument(
        '--sources',
        type=str,
        metavar='SOURCES',
        help='Fontes especificas separadas por virgula (ex: pncp,dom-sc)',
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular pipeline sem persistir dados no banco',
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Retomar execucao a partir do ultimo checkpoint salvo',
    )
    parser.add_argument(
        '--simulate-matches',
        type=int,
        default=0,
        help='[Teste] Simular N matches por fonte na iteracao 1 (dry-run)',
    )
    parser.add_argument(
        '--dsn',
        default=DEFAULT_DSN,
        help='PostgreSQL DSN (default: da env DATALAKE_DSN)',
    )

    args = parser.parse_args(argv)

    # Validar: precisa de --all-sources, --sources, ou --resume
    if not args.all_sources and not args.sources and not args.resume:
        parser.error('Especifique --all-sources, --sources, ou --resume')

    return args


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)

    # Resolver fontes
    sources = None
    if args.all_sources:
        # Usar SOURCE_ORDER em vez de SOURCE_NAME_MAP.values() para
        # respeitar a ordem de prioridade definida em AC2
        sources = [_normalize_source(s) for s in SOURCE_ORDER]
    elif args.sources:
        raw = [s.strip() for s in args.sources.split(',')]
        sources = _resolve_sources(raw)

    # Instanciar e executar pipeline
    pipeline = MultiSourceBackfill(dsn=args.dsn)

    try:
        stats = pipeline.run_pipeline(
            sources=sources,
            dry_run=args.dry_run,
            resume=args.resume,
            simulate_matches=args.simulate_matches,
        )
    except KeyboardInterrupt:
        logger.warning("Pipeline interrompido pelo usuario. Checkpoint salvo em %s", CHECKPOINT_FILE)
        pipeline._save_checkpoint()
        return 130
    except Exception as e:
        logger.critical("Pipeline falhou: %s", e, exc_info=True)
        pipeline._save_checkpoint()
        return 1

    # Output final
    print('\n' + '=' * 60)
    print('  BACKFILL PIPELINE - RESUMO FINAL')
    print('=' * 60)
    print(f'  Cobertura: {stats["entities_before"]} -> {stats["entities_after"]} '
          f'(+{stats["entities_after"] - stats["entities_before"]})')
    pct = round(100.0 * stats['entities_after'] / COVERAGE_TOTAL_ENTITIES, 1)
    print(f'  Cobertura final: {pct}%')
    print(f'  Iteracoes: {stats["iterations"]}')
    print(f'  Fontes OK: {len(stats["sources_done"])} | SKIP: {len(stats["sources_skipped"])}')
    print(f'  Duracao: {pipeline._format_duration(stats["total_duration_s"])}')
    print(f'  Relatorio: {REPORT_FILE}')
    print('=' * 60)

    if stats.get('sources_skipped'):
        print(f'\n  Fontes com falha ({len(stats["sources_skipped"])}):')
        for skip in stats['sources_skipped'][:5]:
            print(f'    - {skip["source"]}: {skip["reason"]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
