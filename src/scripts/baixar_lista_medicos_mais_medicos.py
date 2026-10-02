"""Baixa a relação nominal de profissionais ativos do Programa Mais Médicos.

Fonte oficial: API de Dados Abertos do SUS.

Uso:
    python src/scripts/baixar_lista_medicos_mais_medicos.py
    python src/scripts/baixar_lista_medicos_mais_medicos.py --uf SP
    python src/scripts/baixar_lista_medicos_mais_medicos.py --saida caminho/medicos.csv

A API permite no máximo 1.000 registros por página. O CSV é salvo em UTF-8
com BOM para abrir corretamente em ferramentas comuns, como o Excel.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path

# O download (paginacao e validacao do contrato) e o mesmo do modulo do cache.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from mais_medicos import DownloadError, baixar  # noqa: E402


def _write_csv(path: Path, header: list[str], records: list[list[str]]) -> None:
    if not path.parent.is_dir():
        raise DownloadError(f"A pasta de saída não existe: {path.parent}")
    if path.exists():
        raise DownloadError(
            f"O arquivo de saída já existe: {path}. Remova-o ou informe outro caminho."
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            writer = csv.writer(temp_file, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(records)

        if path.exists():
            raise DownloadError(
                f"O arquivo de saída surgiu durante o download: {path}."
            )
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Baixa a relação nominal oficial de médicos ativos do PMMB."
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=project_root / "mais_medicos_ativos.csv",
        help="Caminho do CSV de saída (padrão: mais_medicos_ativos.csv na raiz).",
    )
    parser.add_argument("--uf", help="Filtra pela sigla da UF, por exemplo SP.")
    parser.add_argument("--sexo", help="Filtra pelo sexo conforme os valores da API.")
    parser.add_argument(
        "--nacionalidade",
        help="Filtra pela nacionalidade conforme os valores da API.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        filtros = {"uf": args.uf, "sexo": args.sexo, "nacionalidade": args.nacionalidade}
        header, records, pages = baixar(filtros)
        _write_csv(args.saida.resolve(), header, records)
    except (DownloadError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print(
        f"Concluído: {len(records)} profissionais em {pages} página(s). "
        f"Arquivo: {args.saida.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
