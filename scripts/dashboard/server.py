"""
Gene-In Dashboard Server Launcher Module
Inicialização do servidor HTTP multithreaded e tratamento de argumentos CLI.
"""

import argparse
import errno
import logging
import os
import shutil
import sys
import subprocess
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from dashboard.config import (
    CONFIG_ENV_PRIMARY, CONFIG_ENV_EXAMPLE, get_config_env_path,
    parse_env_file, is_loopback_host,
)
from dashboard.handler import DashboardHandler, logger


def _ensure_config_env():
    """Bootstrap config/picornavirus.env from the bundled example if it doesn't exist yet."""
    if not CONFIG_ENV_PRIMARY.exists():
        if CONFIG_ENV_EXAMPLE.exists():
            CONFIG_ENV_PRIMARY.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CONFIG_ENV_EXAMPLE, CONFIG_ENV_PRIMARY)
            logger.info(
                "config/picornavirus.env criado a partir do exemplo: %s", CONFIG_ENV_EXAMPLE.name
            )
        else:
            logger.warning(
                "config/picornavirus.env não encontrado e nenhum .example disponível; "
                "usando config.env como fallback."
            )


PORT_ATTEMPTS = 20


def _windows_listener_ports():
    """WSL can bind a port already occupied on the Windows browser host."""
    if not (os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")):
        return set()
    powershell = shutil.which("powershell.exe")
    if not powershell:
        candidate = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        powershell = str(candidate) if candidate.is_file() else None
    if powershell:
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command",
                 "[System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties()"
                 ".GetActiveTcpListeners() | ForEach-Object { $_.Port }"],
                capture_output=True, text=True, timeout=10, check=True,
            )
            return {int(line.strip()) for line in result.stdout.splitlines() if line.strip()}
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    print("[AVISO] Não foi possível verificar portas no Windows; verificando somente o WSL.", flush=True)
    return set()


def _bind_server(host, port, strict_port=False):
    windows_ports = _windows_listener_ports()
    attempts = 1 if strict_port else PORT_ATTEMPTS
    last_port = min(65535, port + attempts - 1)
    retry_errors = {errno.EADDRINUSE, errno.EACCES, errno.EPERM, 10048, 10013}
    for candidate in range(port, last_port + 1):
        if candidate in windows_ports:
            reason = "ocupada no Windows"
        else:
            try:
                return ThreadingHTTPServer((host, candidate), DashboardHandler)
            except OSError as exc:
                if exc.errno not in retry_errors and getattr(exc, "winerror", None) not in retry_errors:
                    raise
                reason = "ocupada ou sem permissão de uso"
        print(f"[AVISO] Porta {candidate} {reason}.", flush=True)
    print(f"[ERRO] Nenhuma porta disponível entre {port} e {last_port}. "
          "Escolha outra com --port (ou make ux PORT=8765).", flush=True)
    raise SystemExit(1)


def run_server(args_list=None):
    config_defaults = parse_env_file(get_config_env_path())
    default_host = os.environ.get("BIND_HOST") or config_defaults.get("BIND_HOST") or "127.0.0.1"
    try:
        default_port = int(os.environ.get("PORT") or config_defaults.get("PORT") or "8000")
    except ValueError:
        default_port = 8000

    parser = argparse.ArgumentParser(description="Painel local do Gene-In")
    parser.add_argument(
        "--host", default=default_host,
        help="Endereço de escuta. Padrão vem de BIND_HOST no config. "
             "Somente localhost e endereços loopback são aceitos."
    )
    parser.add_argument("--port", default=default_port, type=int)
    parser.add_argument("--ready-file", help="Arquivo novo que recebe a URL efetivamente aberta pelo servidor.")
    parser.add_argument(
        "--strict-port", action="store_true",
        help="Usar somente a porta solicitada, sem tentar as próximas 19 portas.",
    )
    args = parser.parse_args(args_list)

    if not is_loopback_host(args.host):
        print("[ERRO] O dashboard aceita somente enderecos loopback (127.0.0.1/localhost).")
        print("       A exposicao na rede exige uma modalidade autenticada futura.")
        raise SystemExit(2)
    if not 1 <= args.port <= 65535:
        print("[ERRO] A porta deve estar entre 1 e 65535.")
        raise SystemExit(2)

    _ensure_config_env()

    ThreadingHTTPServer.allow_reuse_address = True
    server = _bind_server(args.host, args.port, args.strict_port)
    actual_port = server.server_address[1]
    if actual_port != args.port:
        print(f"[INFO] Porta solicitada: {args.port}; porta escolhida: {actual_port}.", flush=True)
    print("Painel ativo em:", flush=True)
    print(f"  http://{args.host}:{actual_port}", flush=True)
    ready_file = Path(args.ready_file) if args.ready_file else None
    if ready_file:
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents a stale launcher receipt from being reused.
        try:
            with ready_file.open("x", encoding="utf-8") as receipt:
                receipt.write(f"http://{args.host}:{actual_port}/\n")
        except OSError:
            server.server_close()
            raise
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando painel...")
    finally:
        server.server_close()
