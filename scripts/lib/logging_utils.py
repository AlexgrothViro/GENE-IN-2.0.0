"""
logging_utils.py — Módulo de log padronizado para scripts Python do Gene-In.

Formato: [NÍVEL] [ETAPA] [AMOSTRA] — descrição — ação sugerida

Identificadores de etapa (sem acento):
    QC_PREFLIGHT, DATABASE_PREFLIGHT, QC_FASTP, HOST_FILTER, ASSEMBLY, RESCUE_READS,
    BLAST, CLASSIFICACAO, REPORT, DASHBOARD

Níveis: FATAL (interrompe), RECUPERADO (fallback), AVISO (não fatal), INFO

Uso:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
    from logging_utils import set_context, log_fatal, log_info, log_warning
    set_context(sample="DEMO", etapa="CLASSIFICACAO")
    log_info("Processando 42 hits")
"""
import os
import sys

SAMPLE_NAME = os.getenv("SAMPLE_NAME")
PIPELINE_ETAPA = os.getenv("PIPELINE_ETAPA")


def set_context(sample=None, etapa=None):
    """Define ou sobrescreve o contexto de log (amostra/etapa).

    Valores podem vir de variáveis de ambiente herdadas do bash chamador
    ou ser definidos explicitamente pelo script Python.
    """
    global SAMPLE_NAME, PIPELINE_ETAPA
    if sample:
        SAMPLE_NAME = sample
    if etapa:
        PIPELINE_ETAPA = etapa


def log_fatal(msg, action=None):
    """Emite mensagem FATAL e encerra o processo com exit code 1."""
    _emit("FATAL", msg, action)
    sys.exit(1)


def log_recovered(msg, action=None):
    """Emite mensagem de recuperação (fallback bem-sucedido)."""
    _emit("RECUPERADO", msg, action)


def log_warning(msg, action=None):
    """Emite aviso não fatal."""
    _emit("AVISO", msg, action)


def log_info(msg, action=None):
    """Emite mensagem informativa."""
    _emit("INFO", msg, action)


def _emit(level, msg, action):
    etapa = PIPELINE_ETAPA or "?"
    amostra = SAMPLE_NAME or "?"
    line = f"[{level}] [{etapa}] [{amostra}] — {msg}"
    if action:
        line += f" — {action}"
    # FATAL e AVISO vão para stderr; INFO e RECUPERADO vão para stdout
    print(line, file=sys.stderr if level in ("FATAL", "AVISO") else sys.stdout)
