"""
Gene-In Dashboard Configuration & Preflight Module
Gerenciamento de ambiente, preflight checks, variáveis .env e alvos.
"""

import ipaddress
import json
import os
import re
import shlex
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from subprocess import run

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "experimental" / "contig_comparison"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from genein.paths import user_config_env_path, user_log_dir
from input_validation import validate_sample_id
from analysis_profiles import load_profiles, resolve_profile

DASHBOARD_DIR = REPO_ROOT / "dashboard"
# Resolved at import from the environment already set for this process.
# Tests patch the name. Do not create the directory here.
LOG_DIR = user_log_dir()
RUNS_DIR = REPO_ROOT / "results" / "runs"
TARGETS_FILE = REPO_ROOT / "config" / "targets.json"
REPO_CONFIG_ENV = REPO_ROOT / "config" / "picornavirus.env"
# Write target. Tests and the facade patch this name; do not point it at the source tree.
CONFIG_ENV_PRIMARY = user_config_env_path()
CONFIG_ENV_EXAMPLE = REPO_ROOT / "config" / "picornavirus.env.example"
CONFIG_ENV_LEGACY = REPO_ROOT / "config.env"
ENVIRONMENT_YML = REPO_ROOT / "environment.yml"
INSTALL_WSL_SCRIPT = REPO_ROOT / "bundle" / "install_wsl.sh"
BUNDLE_ENV_BIN = Path(
    os.environ.get("GENEIN_ENV_BIN", "")
    or (Path.home() / ".gene-in-bundle" / "env" / "bin")
)

JAVASCRIPT_MODULES = frozenset({
    "adapters.js", "advanced.js", "analytics.js", "api.js", "charts.js",
    "components.js", "dom.js", "main.js", "operational.js", "router.js",
    "state.js",
})

PREFLIGHT_TOOLS = (
    ("python3", "Base", True),
    ("blastn", "Busca viral", True),
    ("makeblastdb", "Busca viral", True),
    ("bowtie2", "Filtro de hospedeiro", False),
    ("samtools", "Alinhamento", True),
    ("fastp", "Controle de qualidade", True),
    ("velveth", "Montagem", False),
    ("spades.py", "Montagem", False),
    ("metaspades.py", "Montagem", False),
    ("iqtree2", "Análise complementar", False),
    ("mafft", "Análise complementar", False),
)

ASSEMBLER_TOOLS = frozenset({"velveth", "spades.py", "metaspades.py"})

SUPPORTED_ENV_KEYS = frozenset({
    "THREADS", "ASSEMBLER", "VELVET_K", "MIN_CONTIG_LEN",
    "BLAST_EVALUE", "BLAST_MAX_TARGET_SEQS", "DB", "SAMPLE_NAME",
    "SAMPLE_ID", "HOST_FILTER_ENABLED", "READ_TRKG", "BIND_HOST",
    "PORT", "SPADES_MEMORY", "SPADES_PARAMS", "VELVET_PARAMS",
    "HOST_REF", "HOST_FILTER_MODE", "HOST_ACTION", "HOST_NAME",
    "HOST_INDEX_PREFIX",
    "QC_ADAPTER_R1", "QC_ADAPTER_R2",
})

_BASH_DEFAULT_RE = re.compile(r'^\s*:\s*"\$\{(\w+):=([^}]*)\}"\s*$')
_BASH_SELF_DEFAULT_RE = re.compile(r'^\$\{(\w+):-([^}]*)\}$')

_DB_ALIAS = {
    "teschovirus_a":          "ptv",
    "teschovirus":            "ptv",
    "enterovirus_g":          "evg",
    "sapelovirus_a":          "psv",
    "astrovirus_suino":       "astrovirus_suino",
    "picornaviridae_refseq":  "picornaviridae_refseq",
    "picornaviridae_complete": "picornaviridae_complete",
    "picornaviridae_all":     "picornaviridae_all",
    "ptv": "ptv",
    "evg": "evg",
    "psv": "psv",
}


def require_sample_id(value):
    return validate_sample_id(value)


def get_repo_root():
    """Return the repository root used by all dashboard modules."""
    return REPO_ROOT


def get_runs_dir():
    """Return the canonical directory for dashboard run metadata."""
    return RUNS_DIR


def iso_now(epoch=None):
    dt = datetime.fromtimestamp(epoch) if epoch else datetime.now()
    return dt.astimezone().isoformat()


def is_loopback_host(host):
    if not host:
        return False
    host = host.strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback
    except ValueError:
        return False


def get_preflight_status():
    """Inspect the runtime PATH used by the dashboard and its jobs.

    The dashboard is frequently started directly with the system Python,
    while the scientific tools live in the isolated micromamba environment.
    Include that environment when it exists so the preflight result reflects
    the runtime that pipeline jobs can actually use.
    """
    runtime_env = runtime_environment()
    effective_path = runtime_env.get("PATH", os.defpath)
    tools = []
    presence = {}
    for name, group, required in PREFLIGHT_TOOLS:
        resolved = shutil.which(name, path=effective_path)
        if name == "iqtree2" and not resolved:
            resolved = shutil.which("iqtree3", path=effective_path) or shutil.which("iqtree", path=effective_path)
        presence[name] = resolved is not None
        tools.append({
            "name": name,
            "group": group,
            "required": required,
            "present": resolved is not None,
            "path": resolved,
        })
    required_missing = [
        tool["name"] for tool in tools
        if tool["required"] and not tool["present"]
    ]
    assembler_available = any(presence.get(name) for name in ASSEMBLER_TOOLS)
    pending = list(required_missing)
    if not assembler_available:
        pending.append("nenhum montador (Velvet/SPAdes/metaSPAdes)")
    ok = not pending
    return {
        "ok": ok,
        "tools": tools,
        "required_missing": required_missing,
        "assembler_available": assembler_available,
        "path_source": "dashboard_job_environment",
        "runtime_env_bin": str(BUNDLE_ENV_BIN) if BUNDLE_ENV_BIN.is_dir() else None,
        "checked_at": iso_now(),
        "summary": "Ferramentas disponíveis: " + ", ".join(tool["name"] for tool in tools if tool["present"]) if ok else f"Ambiente com pendências: {', '.join(pending)}",
    }


def runtime_environment(base=None):
    """Return an environment with the bundled Gene-In tools on ``PATH``.

    This keeps direct dashboard launches consistent with ``bundle/run.sh``.
    An explicitly configured ``GENEIN_ENV_BIN`` takes precedence; otherwise
    the default per-user micromamba environment is used when present.
    """
    env = dict(os.environ if base is None else base)
    env_bin = Path(env.get("GENEIN_ENV_BIN", "") or BUNDLE_ENV_BIN)
    if env_bin.is_dir():
        old_path = env.get("PATH", os.defpath)
        path_parts = [str(env_bin)] + [part for part in old_path.split(os.pathsep) if part]
        env["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))
        env["GENEIN_ENV_BIN"] = str(env_bin)
    return env


def list_targets():
    if not TARGETS_FILE.exists():
        return []
    try:
        data = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def list_db_profiles():
    try:
        completed = run(
            ["bash", "-lc", "scripts/ops/db_manager.sh list --json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return []
        data = json.loads(completed.stdout or "[]")
        if not isinstance(data, list):
            return []
        for item in data:
            prefix = REPO_ROOT / "blastdb" / item["id"]
            manifest = Path(str(prefix) + ".db-manifest.json")
            item["prepared"] = manifest.is_file() and manifest.stat().st_size > 0
            item["prefix"] = str(prefix)
            reference = REPO_ROOT / "data/ref" / f'{item["id"]}.fa'
            item["reference_size_bytes"] = reference.stat().st_size if reference.is_file() else None
        return data
    except Exception:
        return []


def get_config_env_path():
    """User file first, then a config that already exists in the source, then config.env."""
    if CONFIG_ENV_PRIMARY.is_file():
        return CONFIG_ENV_PRIMARY
    if REPO_CONFIG_ENV.is_file():
        return REPO_CONFIG_ENV
    if CONFIG_ENV_LEGACY.is_file():
        return CONFIG_ENV_LEGACY
    return CONFIG_ENV_PRIMARY


def ensure_user_config_env():
    """Copy the example into the user path. Never create config/picornavirus.env in the source."""
    if CONFIG_ENV_PRIMARY.exists() or REPO_CONFIG_ENV.exists() or CONFIG_ENV_LEGACY.exists():
        return False
    if not CONFIG_ENV_EXAMPLE.is_file():
        return False
    CONFIG_ENV_PRIMARY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG_ENV_EXAMPLE, CONFIG_ENV_PRIMARY)
    return True


def _readonly_config_seed():
    """Lines already stored in the source, copied only as the starting text of a new user file."""
    for source in (REPO_CONFIG_ENV, CONFIG_ENV_LEGACY):
        if source.is_file():
            return source.read_text(encoding="utf-8")
    return ""


def parse_env_file(filepath):
    """Parse a simple KEY=VALUE env file, ignoring comments and blank lines."""
    config = {}
    if not filepath.exists():
        return config

    try:
        content = filepath.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            bash_match = _BASH_DEFAULT_RE.match(line)
            if bash_match:
                key = bash_match.group(1)
                value = bash_match.group(2).strip('"').strip("'")
                config[key] = value
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                try:
                    parsed_value = shlex.split(value, posix=True)
                    if len(parsed_value) == 1:
                        value = parsed_value[0]
                except ValueError:
                    pass
                self_default = _BASH_SELF_DEFAULT_RE.match(value)
                if self_default and self_default.group(1) == key:
                    value = self_default.group(2)
                config[key] = value
    except Exception as e:
        print(f"[WARN] Error parsing env file {filepath}: {e}")

    return config


def load_config_env():
    """Load configuration from picornavirus.env (or config.env as fallback)"""
    env_path = get_config_env_path()
    config = parse_env_file(env_path)

    result = {}
    for key in SUPPORTED_ENV_KEYS:
        if key in config:
            result[key] = config[key]

    return result


def validate_config_updates(updates):
    if not isinstance(updates, dict):
        raise ValueError("config deve ser um objeto JSON")
    numeric_ranges = {
        "THREADS": (1, 256), "PORT": (1, 65535), "VELVET_K": (15, 127),
        "MIN_CONTIG_LEN": (1, 10_000_000), "BLAST_MAX_TARGET_SEQS": (1, 1000),
        "SPADES_MEMORY": (1, 4096),
    }
    for key, value in updates.items():
        if key not in SUPPORTED_ENV_KEYS:
            raise ValueError(f"Chave nao suportada: {key}")
        if isinstance(value, bool):
            value = str(value).lower()
        if not isinstance(value, (str, int, float)):
            raise ValueError(f"Valor invalido para {key}")
        text = str(value)
        if key in {"QC_ADAPTER_R1", "QC_ADAPTER_R2"}:
            if text and not re.fullmatch(r"[ACGTNacgtn]{1,500}", text):
                raise ValueError("Adaptadores devem conter somente A/C/G/T/N (ate 500 bases).")
            continue
        if not text or len(text) > 4096 or "\x00" in text or "\n" in text or "\r" in text:
            raise ValueError(f"Valor invalido para {key}: vazio, grande ou com quebra de linha")
        if key == "ASSEMBLER" and text.lower() not in {"velvet", "spades", "metaspades"}:
            raise ValueError("ASSEMBLER deve ser velvet, spades ou metaspades")
        if key == "BIND_HOST" and not is_loopback_host(text):
            raise ValueError("BIND_HOST deve ser localhost ou um endereco loopback")
        if key in numeric_ranges:
            try:
                number = int(text)
            except ValueError as exc:
                raise ValueError(f"{key} deve ser numerico") from exc
            low, high = numeric_ranges[key]
            if not low <= number <= high:
                raise ValueError(f"{key} fora do intervalo permitido ({low}-{high})")
        if key in {"DB", "SAMPLE_NAME", "SAMPLE_ID"}:
            if key != "DB":
                require_sample_id(text)
            if key == "DB" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", text):
                raise ValueError("DB contem caracteres invalidos")
        if key in {"HOST_FILTER_ENABLED", "READ_TRKG"} and text.lower() not in {"true", "false", "0", "1", "yes", "no", "sim", "nao"}:
            raise ValueError(f"{key} deve ser booleano")
    return {key: str(value) for key, value in updates.items()}


def quote_config_value(key, value):
    """Preserve the documented memory reference without executing arbitrary shell text."""
    if key != "SPADES_PARAMS" or "${SPADES_MEMORY}" not in str(value):
        return shlex.quote(str(value))
    parts = str(value).split("${SPADES_MEMORY}")
    def literal(part):
        for char in ("\\", '"', "$", "`"):
            part = part.replace(char, "\\" + char)
        return part
    return '"' + "${SPADES_MEMORY}".join(literal(part) for part in parts) + '"'


def save_config_env(updates):
    updates = validate_config_updates(updates)
    env_path = CONFIG_ENV_PRIMARY

    env_path.parent.mkdir(parents=True, exist_ok=True)

    if env_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = env_path.parent / f"{env_path.name}.bak-{timestamp}-{uuid.uuid4().hex[:8]}"
        shutil.copy2(env_path, backup_path)

    existing_lines = []
    existing_keys = set()

    if env_path.is_file():
        content = env_path.read_text(encoding="utf-8")
    else:
        content = _readonly_config_seed()
    if content:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                key = None
                bash_match = _BASH_DEFAULT_RE.match(stripped)
                if bash_match:
                    key = bash_match.group(1)
                elif "=" in stripped:
                    key = stripped.split("=")[0].strip()

                if key:
                    existing_keys.add(key)
                    if key in updates:
                        line = f"{key}={quote_config_value(key, updates[key])}"

            existing_lines.append(line)

    for key in SUPPORTED_ENV_KEYS:
        if key in updates and key not in existing_keys:
            existing_lines.append(f"{key}={quote_config_value(key, updates[key])}")

    env_path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")
    return load_config_env()


def validate_host_index(prefix):
    if not prefix:
        return {"valid": False, "reason": "Caminho do indice nao especificado"}
    for extension in ("bt2", "bt2l"):
        components = [Path(f"{prefix}.{part}.{extension}") for part in ("1", "2", "3", "4", "rev.1", "rev.2")]
        if all(path.is_file() and path.stat().st_size > 0 for path in components):
            try:
                checked = run(["bowtie2-inspect", "-s", str(prefix)], env=runtime_environment(), capture_output=True, text=True, check=False)
            except OSError:
                return {"valid": False, "reason": "bowtie2-inspect indisponível. Verifique o ambiente instalado."}
            if checked.returncode == 0:
                return {"valid": True, "path": str(components[0])}
            return {"valid": False, "reason": "Índice Bowtie2 completo, mas ilegível. Prepare novamente com bowtie2-build."}
    return {"valid": False, "reason": f"Índice Bowtie2 incompleto em {prefix}. Prepare com bowtie2-build e informe o prefixo sem .1.bt2; veja docs/HOSPEDEIRO_BETA.md."}


def host_env_from_params(params):
    env = dict(os.environ)

    host_ref = (params.get("host_reference") or "").strip()
    if host_ref:
        res = validate_host_index(host_ref)
        if not res["valid"]:
            raise ValueError(f"Indice de hospedeiro invalido: {res['reason']}")
        env["HOST_REF"] = host_ref
        env["GENEIN_HOST_REF"] = host_ref

    # This field identifies the host-reference selection made by the
    # dashboard.  It is not an alignment-policy knob.  In particular, "none"
    # is the canonical opt-out when the biological host is unknown.
    host_selection = str(params.get("host_filter_mode") or "none").strip().lower()
    if host_selection not in {"none", "sus_scrofa", "custom"}:
        raise ValueError(
            "Modo de filtro de hospedeiro invalido; use none, sus_scrofa ou custom"
        )

    host_action = (params.get("host_action") or "").strip()
    if host_action:
        if host_action not in {"remove", "keep_unmapped", "flag_only"}:
            raise ValueError("Acao de filtro de hospedeiro invalida")
        env["HOST_ACTION"] = host_action

    return env


def get_environment_status():
    preflight = get_preflight_status()

    python_version = sys.version.split()[0]
    in_wsl = False
    wsl_distro = None
    try:
        if Path("/proc/version").exists():
            proc_ver = Path("/proc/version").read_text(encoding="utf-8", errors="replace")
            in_wsl = "microsoft" in proc_ver.lower() or "wsl" in proc_ver.lower()
            wsl_distro = os.environ.get("WSL_DISTRO_NAME", "Desconhecido")
    except Exception:
        pass

    environment_yml_exists = ENVIRONMENT_YML.is_file()
    environment_yml_mtime = None
    if environment_yml_exists:
        try:
            environment_yml_mtime = iso_now(ENVIRONMENT_YML.stat().st_mtime)
        except OSError:
            environment_yml_mtime = None

    return {
        "ok": preflight["ok"],
        "preflight": preflight,
        "has_environment_yml": environment_yml_exists,
        "environment_yml_path": str(ENVIRONMENT_YML) if environment_yml_exists else None,
        "environment_yml_mtime": environment_yml_mtime,
        "running_on_windows_mount": bool(in_wsl and str(REPO_ROOT).startswith("/mnt/")),
        "system": {
            "python_version": python_version,
            "in_wsl": in_wsl,
            "wsl_distro": wsl_distro,
            "platform": sys.platform,
        },
        "checked_at": iso_now(),
    }


def tool_versions():
    versions = {}
    runtime_env = runtime_environment()
    for cmd, name in (
        ("blastn -version", "blast"),
        ("bowtie2 --version", "bowtie2"),
        ("samtools --version", "samtools"),
        ("fastp --version", "fastp"),
        ("spades.py --version", "spades"),
    ):
        try:
            res = run(cmd.split(), env=runtime_env, capture_output=True, text=True, check=False)
            output = (res.stdout or res.stderr or "").strip().splitlines()
            versions[name] = output[0] if output else "Desconhecido"
        except Exception:
            versions[name] = "Nao instalado"
    return versions
