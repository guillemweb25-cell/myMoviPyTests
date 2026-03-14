#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def build_command(
    target: str,
    binary: str,
    profile: str | None,
    config_path: str | None,
    extra_args: str | None,
) -> list[str]:
    command = [binary, "manual"]

    if profile:
        command.extend(["--profile", profile])
    if config_path:
        command.extend(["--config", config_path])
    if extra_args:
        command.extend(shlex.split(extra_args))

    command.extend(["--url", target])
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description="Wrapper aislado para ejecutar OF-Scraper")
    parser.add_argument("--target", required=True, help="URL o target para OF-Scraper")
    parser.add_argument("--binary", default="ofscraper", help="Binario a ejecutar")
    parser.add_argument("--profile", default=None, help="Perfil de OF-Scraper")
    parser.add_argument("--config", dest="config_path", default=None, help="Ruta opcional a config.json")
    parser.add_argument("--extra-args", default=None, help="Argumentos extra en formato CLI")
    args = parser.parse_args()

    binary_path = shutil.which(args.binary)
    if not binary_path:
        print(f"No encuentro el binario '{args.binary}'.")
        print("Instala OF-Scraper dentro del entorno donde corre el backend y vuelve a intentarlo.")
        raise SystemExit(1)

    command = build_command(
        target=args.target,
        binary=binary_path,
        profile=args.profile,
        config_path=args.config_path,
        extra_args=args.extra_args,
    )

    print("Lanzando flujo aislado OF-Scraper")
    print(f"Target: {args.target}")
    if args.profile:
        print(f"Perfil: {args.profile}")
    if args.config_path:
        print(f"Config: {args.config_path}")
    if args.extra_args:
        print(f"Args extra: {args.extra_args}")
    print(f"Comando: {' '.join(shlex.quote(part) for part in command)}")
    print("Nota: este flujo requiere que OF-Scraper este configurado y autenticado por tu parte.")

    completed = subprocess.run(command, cwd=ROOT_DIR, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
