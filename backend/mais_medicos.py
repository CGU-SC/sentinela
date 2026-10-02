"""Medicos ativos do Programa Mais Medicos (fonte externa, API de Dados Abertos do SUS).

O intercambista do programa atua com o registro do Ministerio da Saude (RMS),
nao com inscricao no CFM; por isso ele aparece como "nao localizado no CFM" na
analise de CRMs. Este modulo baixa a relacao nominal oficial dos profissionais
ativos e grava uma linha por medico, na mesma chave do cadastro do CFM
(id_medico = "{numero}/{UF}"), para identificar esses casos.

Regras da montagem:

* registros sem numero de CRM/RMS nao podem ser cruzados e sao descartados
  (a contagem aparece no log da sincronizacao);
* o mesmo medico (numero + UF) em mais de um municipio ou ciclo fica com os
  dados da atividade mais recente (maior inicio de atividade);
* o inicio da atividade nao entra: a fonte so traz a atividade atual (ciclos
  a partir de 2023), e o medico pode ter prescrito com o mesmo registro em
  ciclos anteriores do programa;
* o municipio nao entra: parte dos registros traz o codigo de um distrito
  sanitario indigena (DSEI), nao de um municipio.

A lista so traz quem esta ativo hoje: quem ja saiu do programa nao aparece.
"""

from __future__ import annotations

import csv
import io
import os
import time
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import polars as pl

API_URL = (
    "https://apidadosabertos.saude.gov.br/"
    "atencao-primaria/pmmb-relacao-nominal-ativo"
)
PAGE_SIZE = 1000
TIMEOUT_SECONDS = 60
CSV_DELIMITER = ";"
REQUIRED_COLUMNS = {
    "crm",
    "uf",
    "no_profissional",
    "perfil",
    "nacionalidade",
    "inicio_atividade",
    "dt_atualizacao",
}
SCHEMA = {
    "id_medico": pl.Utf8,
    "nu_crm": pl.Int64,
    "sg_uf": pl.Utf8,
    "no_medico": pl.Utf8,
    "tp_perfil": pl.Utf8,
    "no_nacionalidade": pl.Utf8,
    "dt_atualizacao": pl.Date,
}


class DownloadError(RuntimeError):
    """Erro visivel ao consultar ou validar a resposta da API."""


def _baixar_pagina(offset: int, filtros: dict[str, str]) -> tuple[list[str], list[list[str]]]:
    params: dict[str, str | int] = {"limit": PAGE_SIZE, "offset": offset, **filtros}
    request = Request(
        f"{API_URL}?{urlencode(params)}",
        headers={"Accept": "text/csv", "User-Agent": "Sentinela-dados-abertos/1.0"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            if content_type != "text/csv":
                raise DownloadError(
                    f"A API retornou Content-Type inesperado: {content_type!r}; era esperado 'text/csv'."
                )
            body = response.read().decode("utf-8-sig")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise DownloadError(f"A API respondeu HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise DownloadError(f"Nao foi possivel acessar a API: {exc.reason}") from exc
    except UnicodeDecodeError as exc:
        raise DownloadError("A resposta CSV nao esta codificada em UTF-8.") from exc

    rows = [row for row in csv.reader(io.StringIO(body, newline=""), delimiter=CSV_DELIMITER) if row]
    if not rows:
        raise DownloadError(f"A API retornou CSV vazio na posicao {offset}.")
    header = rows[0]
    if any(not column.strip() for column in header):
        raise DownloadError("O cabecalho retornado pela API esta vazio ou incompleto.")
    faltantes = REQUIRED_COLUMNS.difference(header)
    if faltantes:
        raise DownloadError(
            f"A API nao retornou as colunas obrigatorias: {', '.join(sorted(faltantes))}. "
            "O contrato da fonte pode ter mudado."
        )
    records = rows[1:]
    for row_number, row in enumerate(records, start=2):
        if len(row) != len(header):
            raise DownloadError(
                f"Registro invalido na pagina iniciada em {offset}: linha {row_number} "
                f"tem {len(row)} campos, mas o cabecalho tem {len(header)}."
            )
    return header, records


def baixar(
    filtros: Optional[dict[str, str]] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> tuple[list[str], list[list[str]], int]:
    """Baixa todas as paginas da relacao nominal de profissionais ativos.

    Args:
        filtros: filtros aceitos pela API (uf, sexo, nacionalidade).
        progress_callback: recebe um percentual aproximado (a API nao informa o total).

    Returns:
        Cabecalho, registros e quantidade de paginas.

    Raises:
        DownloadError: falha de rede, contrato diferente ou resposta vazia.
    """
    filtros = {chave: valor for chave, valor in (filtros or {}).items() if valor}
    todos: list[list[str]] = []
    cabecalho: Optional[list[str]] = None
    offset = 0
    paginas = 0
    while True:
        header, records = _baixar_pagina(offset, filtros)
        if cabecalho is None:
            cabecalho = header
        elif header != cabecalho:
            raise DownloadError("O cabecalho da API mudou entre paginas; o arquivo nao sera salvo.")
        paginas += 1
        todos.extend(records)
        print(f"   Pagina {paginas}: {len(records)} registros recebidos.")
        if progress_callback:
            progress_callback(min(80, paginas * 3))
        if len(records) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if cabecalho is None or not todos:
        raise DownloadError("A API nao retornou nenhum profissional ativo.")
    return cabecalho, todos, paginas


def montar(header: list[str], records: list[list[str]]) -> tuple[pl.DataFrame, int]:
    """Converte a relacao da API em uma linha por medico (chave do cadastro do CFM).

    Returns:
        O modulo montado e a quantidade de registros descartados por nao terem CRM.

    Raises:
        RuntimeError: CRM nao numerico, UF/nome/perfil vazio ou data invalida.
    """
    bruto = pl.DataFrame(records, schema=[(coluna, pl.Utf8) for coluna in header], orient="row")
    bruto = bruto.with_columns(pl.col(pl.Utf8).str.strip_chars().replace("", None))
    sem_crm = bruto.get_column("crm").null_count()
    bruto = bruto.filter(pl.col("crm").is_not_null())
    if bruto.is_empty():
        raise RuntimeError("Mais Medicos: nenhum registro com numero de CRM.")
    if not bruto.get_column("crm").str.contains(r"^\d+$").all():
        raise RuntimeError("Mais Medicos: numero de CRM com caracteres nao numericos.")
    for coluna in ("uf", "no_profissional", "perfil", "inicio_atividade", "dt_atualizacao"):
        if bruto.get_column(coluna).null_count():
            raise RuntimeError(f"Mais Medicos: registro com CRM e sem '{coluna}'.")

    # O inicio da atividade so escolhe o registro mais recente; nao e gravado.
    datas = {
        "_inicio_atividade": pl.col("inicio_atividade").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
        "dt_atualizacao": pl.col("dt_atualizacao").str.strptime(pl.Date, "%Y-%m-%d", strict=False),
    }
    convertido = bruto.select(
        pl.col("crm").cast(pl.Int64).alias("nu_crm"),
        pl.col("uf").str.to_uppercase().alias("sg_uf"),
        pl.col("no_profissional").alias("no_medico"),
        pl.col("perfil").alias("tp_perfil"),
        pl.col("nacionalidade").alias("no_nacionalidade"),
        **datas,
    )
    for coluna in datas:
        if convertido.get_column(coluna).null_count():
            raise RuntimeError(f"Mais Medicos: data invalida em '{coluna}' (esperado AAAA-MM-DD).")

    # Mesmo medico em mais de um municipio ou ciclo: fica a atividade mais recente.
    modulo = (
        convertido
        .with_columns(pl.format("{}/{}", "nu_crm", "sg_uf").alias("id_medico"))
        .sort(["id_medico", "_inicio_atividade", "dt_atualizacao", "tp_perfil"], descending=[False, True, True, False])
        .unique("id_medico", keep="first", maintain_order=True)
        .select(list(SCHEMA))
        .cast(SCHEMA)
    )
    return modulo, sem_crm


def construir(destino: str, progress_callback: Optional[Callable[[int], None]] = None) -> None:
    """Baixa a relacao da API e grava o modulo (substituido de forma atomica).

    Raises:
        DownloadError: falha ao baixar ou validar a resposta da API.
        RuntimeError: dado obrigatorio ausente ou invalido na relacao.
    """
    t0 = time.perf_counter()
    print("Baixando a relacao de medicos ativos do Mais Medicos (API de Dados Abertos do SUS)...")
    header, records, paginas = baixar(progress_callback=progress_callback)
    modulo, sem_crm = montar(header, records)
    if progress_callback:
        progress_callback(90)
    tmp = destino + ".tmp"
    modulo.write_parquet(tmp, compression="zstd")
    os.replace(tmp, destino)
    if progress_callback:
        progress_callback(100)
    print(
        f"   {len(records):,} registros em {paginas} pagina(s); {sem_crm:,} sem CRM descartados; "
        f"{modulo.height:,} medicos gravados em {time.perf_counter() - t0:.0f}s."
    )
