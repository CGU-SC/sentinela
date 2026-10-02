from datetime import date
from decimal import Decimal
import json
import zlib

import polars as pl
import pytest

import cache_files
import cache_producers.farmacia as farmacia
import data_cache


def _payload():
    return zlib.compress(
        json.dumps(
            {
                "gtins": [
                    {
                        "gtin": "789123",
                        "estoque_inicial": {
                            "quantidade": 10,
                            "data_referencia": "2015-07-01",
                            "notas": [
                                {
                                    "numero_nfe": "EST-1",
                                    "data": "2015-06-30",
                                    "quantidade": 10,
                                }
                            ],
                        },
                        "eventos": [
                            {
                                "tipo": "venda",
                                "periodo_inicial": "2025-01-01",
                                "periodo_final": "2025-01-31",
                                "periodo_inicio_irregular": "2025-01-10",
                                "estoque_inicial": 10,
                                "estoque_final": 7,
                                "vendas": 3,
                                "vendas_sem_comprovacao": 1,
                                "valor": 12.345,
                                "valor_sem_comprovacao": 2.5,
                                "notas_referencia": [{"tipo": "estoque_inicial"}],
                            }
                        ],
                        "summary": {
                            "vendas": 3,
                            "vendas_sem_comprovacao": 1,
                            "valor": 12.345,
                            "valor_sem_comprovacao": 2.5,
                        },
                    }
                ]
            }
        ).encode("utf-8")
    )


def test_memory_value_formatters_and_medicine_mapping_cover_valid_and_bad_rows():
    assert farmacia._parse_memory_date(date(2025, 3, 4)) == date(2025, 3, 4)
    assert farmacia._parse_memory_date("2025-03-04T12:00:00") == date(2025, 3, 4)
    assert farmacia._parse_memory_date("bad-date") is None
    assert farmacia._fmt_memory_date("2025-03-04") == "04/03/2025"
    assert farmacia._fmt_memory_date(None) == "-"
    assert farmacia._as_decimal("2.50") == Decimal("2.50")
    assert farmacia._as_int("3.9") == 3

    medicine_map = farmacia._build_medicamentos_map_from_rows(
        [("789", "Ativo"), ("abc", None), (None, "Ignorado")]
    )
    assert medicine_map["789"] == "Ativo"
    assert medicine_map[789.0] == "Ativo"
    assert medicine_map["abc"] == "DESCONHECIDO"
    assert "None" not in medicine_map


def test_memory_cache_paths_reference_the_configured_data_cache_roots(monkeypatch, tmp_path):
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(tmp_path / "global"))
    monkeypatch.setattr(data_cache, "get_cnpj_cache_root", lambda: str(tmp_path / "cnpjs"))

    local_dir = farmacia._get_cnpj_cache_dir("123")

    assert local_dir == str(tmp_path / "cnpjs" / "123")
    assert (tmp_path / "cnpjs" / "123").is_dir()
    assert farmacia._cache_path("123") == str(
        tmp_path / "cnpjs" / "123" / cache_files.MEMORIA_CALCULO_PARQUET
    )
    assert farmacia._global_cache_path() == str(
        tmp_path / "global" / cache_files.MEMORIA_CALCULO_GLOBAL_PARQUET
    )


def test_memory_reference_formatter_distinguishes_transfer_from_purchase():
    reference = {"numero_nfe": "NFE-1", "data": "2025-03-04", "quantidade": "2.9"}

    assert farmacia._formatar_referencia_v2(
        {**reference, "tipo": "saida_estoque"}, {}
    ) == "NF Transferencia: NFE-1 - 04/03/2025 | Qtde: 2"
    assert farmacia._formatar_referencia_v2(
        {**reference, "tipo": "aquisicao"}, {}
    ) == "NF Aquisicao: NFE-1 - 04/03/2025 | Qtde: 2"


def test_v2_projection_skips_empty_gtins_and_maps_stock_purchase_transfer_and_sales():
    rows = farmacia._legacy_rows_from_memoria_v2(
        {
            "gtins": [
                {"gtin": "   ", "eventos": [{"tipo": "venda"}]},
                {
                    "gtin": " 789321 ",
                    "estoque_inicial": {"quantidade": 5, "data_referencia": "2015-07-01"},
                    "eventos": [
                        {"tipo": "estoque_inicial"},
                        {
                            "tipo": "aquisicao", "estoque_inicial": 5, "estoque_final": 8,
                            "data": "2025-01-02", "quantidade": 3, "numero_nfe": "COMPRA",
                        },
                        {
                            "tipo": "saida_estoque", "estoque_inicial": 8, "estoque_final": 6,
                            "data": "2025-01-03", "quantidade": 2, "numero_nfe": "TRANSF",
                        },
                        {
                            "tipo": "venda", "periodo_inicial": "2025-01-01",
                            "periodo_final": "2025-01-31", "periodo_inicio_irregular": "2025-01-10",
                            "estoque_inicial": 6, "estoque_final": 4, "vendas": 2,
                            "vendas_sem_comprovacao": 1, "valor": 8.5,
                            "valor_sem_comprovacao": 3.25,
                            "notas_referencia": [
                                {"tipo": "aquisicao", "numero_nfe": "COMPRA", "data": "2025-01-02", "quantidade": 3},
                                {"tipo": "saida_estoque", "numero_nfe": "TRANSF", "data": "2025-01-03", "quantidade": 2},
                            ],
                        },
                    ],
                    "summary": {"vendas": 2, "vendas_sem_comprovacao": 1, "valor": 8.5, "valor_sem_comprovacao": 3.25},
                },
            ]
        }
    )

    assert [row["tipo"] for row in rows] == ["h", "e", "c", "d", "v", "s"]
    assert rows[2]["numero_nfe"] == "COMPRA"
    assert rows[3]["numero_nfe"] == "TRANSF"
    assert "NF Aquisicao: COMPRA" in rows[4]["notas"]
    assert "NF Transferencia: TRANSF" in rows[4]["notas"]


def test_payload_byte_conversion_accepts_bytes_like_and_iterable_values():
    expected = b"compressed-payload"

    assert farmacia._payload_to_bytes(expected) == expected
    assert farmacia._payload_to_bytes(bytearray(expected)) == expected
    assert farmacia._payload_to_bytes(memoryview(expected)) == expected
    assert farmacia._payload_to_bytes(list(expected)) == expected


def test_v2_payload_decodes_to_legacy_rows_and_builds_auditable_lines():
    decoded = farmacia._decode_memoria_payload(memoryview(_payload()))

    assert [row["tipo"] for row in decoded] == ["h", "e", "v", "s"]
    assert decoded[2]["periodo_inicial"] == date(2025, 1, 1)
    assert decoded[2]["valor_movimentado"] == Decimal("12.345")

    medicines = farmacia._build_medicamentos_map_from_rows([("789123", "Ativo")])
    result = farmacia._build_memoria_calculo_df(decoded, medicines)
    venda = result.filter(pl.col("tipo_linha") == "venda_irregular").row(0, named=True)

    assert result.columns == [
        "tipo_linha",
        "gtin",
        "medicamento",
        "periodo_inicial",
        "periodo_inicio_irregular",
        "periodo_final",
        "estoque_inicial",
        "estoque_final",
        "vendas",
        "vendas_irregular",
        "valor",
        "valor_irregular",
        "notas",
    ]
    assert venda["medicamento"] == "Ativo"
    assert venda["vendas_irregular"] == 1
    assert venda["valor"] == 12.35
    assert "Estoque Inicial Estimado: 10 - 01/07/2015" in venda["notas"]
    assert result.filter(pl.col("tipo_linha") == "resumo_parcial").height == 1


def test_decoder_normalizes_raw_date_strings_and_leaves_invalid_text_visible(monkeypatch):
    monkeypatch.setattr(
        farmacia,
        "_legacy_rows_from_memoria_v2",
        lambda _payload: [
            {
                "periodo_inicial": "2025-02-03T12:30:00",
                "periodo_final": "2025-02-28",
                "periodo_inicial_nao_comprovacao": "not-a-date",
            }
        ],
    )

    decoded = farmacia._decode_memoria_payload(_payload())

    assert decoded[0]["periodo_inicial"] == date(2025, 2, 3)
    assert decoded[0]["periodo_final"] == date(2025, 2, 28)
    assert decoded[0]["periodo_inicial_nao_comprovacao"] == "not-a-date"


def test_memoria_builder_reconstructs_unreferenced_sales_and_ignores_non_sales():
    from datetime import date

    rows = [
        {"tipo": "h", "codigo_barra": "789123", "estoque_inicial": 7},
        {"tipo": "e", "codigo_barra": "789123", "estoque_inicial": 7},
        {"tipo": "c", "codigo_barra": "789123", "estoque_final": 9,
         "data_aquis_dev_estoq": date(2025, 1, 2), "qnt_aquis_dev": 2, "numero_nfe": "C1"},
        {"tipo": "d", "codigo_barra": "789123", "estoque_final": 8,
         "data_aquis_dev_estoq": date(2025, 1, 3), "qnt_aquis_dev": 1, "numero_nfe": "D1"},
        {"tipo": "v", "codigo_barra": "789123", "periodo_inicial": date(2025, 1, 1),
         "periodo_final": date(2025, 1, 31), "periodo_inicial_nao_comprovacao": None,
         "estoque_inicial": 8, "estoque_final": 6, "vendas_periodo": 2,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("10"),
         "valor_sem_comprovacao": Decimal("0"), "notas": None},
        {"tipo": "s", "codigo_barra": "789123", "vendas_periodo": 2,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("10"),
         "valor_sem_comprovacao": Decimal("0")},
        {"tipo": "h", "codigo_barra": "789124", "estoque_inicial": 7},
        {"tipo": "e", "codigo_barra": "789124", "estoque_inicial": 7},
        {"tipo": "v", "codigo_barra": "789124", "periodo_inicial": date(2025, 1, 1),
         "periodo_final": date(2025, 1, 31), "periodo_inicial_nao_comprovacao": None,
         "estoque_inicial": 7, "estoque_final": 5, "vendas_periodo": 2,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("10"),
         "valor_sem_comprovacao": Decimal("0"), "notas": None},
        {"tipo": "s", "codigo_barra": "789124", "vendas_periodo": 2,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("10"),
         "valor_sem_comprovacao": Decimal("0")},
        {"tipo": "h", "codigo_barra": "789125", "estoque_inicial": 3},
        {"tipo": "c", "codigo_barra": "789125", "estoque_final": 4,
         "data_aquis_dev_estoq": date(2025, 1, 2), "qnt_aquis_dev": 1, "numero_nfe": "C2"},
        {"tipo": "e", "codigo_barra": "789125", "estoque_inicial": 4},
        {"tipo": "d", "codigo_barra": "789125", "estoque_final": 3,
         "data_aquis_dev_estoq": date(2025, 1, 3), "qnt_aquis_dev": 1, "numero_nfe": "D2"},
        {"tipo": "v", "codigo_barra": "789125", "periodo_inicial": date(2025, 1, 1),
         "periodo_final": date(2025, 1, 31), "periodo_inicial_nao_comprovacao": None,
         "estoque_inicial": 3, "estoque_final": 2, "vendas_periodo": 1,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("5"),
         "valor_sem_comprovacao": Decimal("0"), "notas": None},
        {"tipo": "s", "codigo_barra": "789125", "vendas_periodo": 1,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("5"),
         "valor_sem_comprovacao": Decimal("0")},
        {"tipo": "h", "codigo_barra": "789126", "estoque_inicial": 1},
        {"tipo": "v", "codigo_barra": "789126", "periodo_inicial": date(2025, 1, 1),
         "periodo_final": date(2025, 1, 31), "periodo_inicial_nao_comprovacao": None,
         "estoque_inicial": 1, "estoque_final": 0, "vendas_periodo": 1,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("2"),
         "valor_sem_comprovacao": Decimal("0"), "notas": None},
        {"tipo": "s", "codigo_barra": "789126", "vendas_periodo": 1,
         "vendas_sem_comprovacao": 0, "valor_movimentado": Decimal("2"),
         "valor_sem_comprovacao": Decimal("0")},
    ]

    result = farmacia._build_memoria_calculo_df(rows, {789123.0: "Ativo"})
    vendas = result.filter(pl.col("tipo_linha") == "venda_normal").to_dicts()

    assert vendas[0]["medicamento"] == "Ativo"
    assert "NF Transferencia: D1" in vendas[0]["notas"]
    assert "NF Aquisicao: C1" in vendas[0]["notas"]
    assert "Estoque Inicial Estimado: 7" in vendas[1]["notas"]
    assert "Estoque Inicial Estimado: 4" in vendas[2]["notas"]
    assert vendas[3]["notas"] == ""
    assert result.filter(pl.col("tipo_linha") == "resumo_parcial")["estoque_final"].to_list() == [6, 5, 2, 0]
    assert farmacia._build_memoria_calculo_df([], {}).is_empty()


def test_medicine_map_requires_both_contract_columns(monkeypatch):
    monkeypatch.setattr(
        data_cache,
        "get_medicamentos_df",
        lambda: pl.DataFrame({"codigo_barra": ["789"]}),
    )

    with pytest.raises(RuntimeError, match="principio_ativo"):
        farmacia._load_medicamentos_map_from_cache()


def test_global_memory_requires_current_cache_version(tmp_path, monkeypatch):
    global_path = tmp_path / cache_files.MEMORIA_CALCULO_GLOBAL_PARQUET
    global_path.write_bytes(b"placeholder")
    monkeypatch.setattr(farmacia, "_global_cache_path", lambda: str(global_path))
    old_payload = pl.DataFrame(
        {
            "cnpj": ["123"],
            "memoria_calculo_payload": [_payload()],
            "_memoria_calculo_cache_version": [0],
        }
    )
    monkeypatch.setattr(data_cache, "scan_memoria_calculo_global", lambda: old_payload.lazy())

    with pytest.raises(RuntimeError, match="esperado 1"):
        farmacia._load_memoria_from_global("123")


def test_global_memory_loads_valid_payload_and_returns_empty_for_no_match(
    tmp_path, monkeypatch
):
    global_path = tmp_path / cache_files.MEMORIA_CALCULO_GLOBAL_PARQUET
    global_path.write_bytes(b"placeholder")
    monkeypatch.setattr(farmacia, "_global_cache_path", lambda: str(global_path))
    cached_rows = pl.DataFrame(
        {
            "cnpj": ["123"],
            "memoria_calculo_payload": [_payload()],
            "_memoria_calculo_cache_version": [cache_files.MEMORIA_CALCULO_CACHE_VERSION],
        }
    )
    monkeypatch.setattr(data_cache, "scan_memoria_calculo_global", lambda: cached_rows.lazy())
    monkeypatch.setattr(
        data_cache,
        "get_medicamentos_df",
        lambda: pl.DataFrame({"codigo_barra": ["789123"], "principio_ativo": ["Ativo"]}),
    )

    result, elapsed = farmacia._load_memoria_from_global("123")

    assert result.filter(pl.col("tipo_linha") == "venda_irregular").height == 1
    assert elapsed is not None

    empty_rows = cached_rows.filter(pl.col("cnpj") == "absent")
    monkeypatch.setattr(data_cache, "scan_memoria_calculo_global", lambda: empty_rows.lazy())
    empty_result, empty_elapsed = farmacia._load_memoria_from_global("absent")
    assert empty_result.is_empty()
    assert empty_elapsed is not None


def test_global_memory_reports_absent_cache_and_sql_without_rows(monkeypatch, tmp_path):
    global_path = tmp_path / "absent.parquet"
    monkeypatch.setattr(farmacia, "_global_cache_path", lambda: str(global_path))
    assert farmacia._load_memoria_from_global("123") == (None, None)

    class EmptyResult:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return EmptyResult()

    class Engine:
        def connect(self):
            return Connection()

    rows, medicines, elapsed = farmacia._load_memoria_sql("123", Engine())
    assert rows is None
    assert medicines == {}
    assert elapsed is not None


def test_cache_only_request_returns_empty_result_without_querying_database(tmp_path, monkeypatch):
    cnpj_dir = tmp_path / "123"
    monkeypatch.setattr(farmacia, "_cache_path", lambda cnpj: str(cnpj_dir / cache_files.MEMORIA_CALCULO_PARQUET))
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_from_global",
        lambda cnpj: pytest.fail("check_cache nao deve consultar a fonte global"),
    )
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_sql",
        lambda *args: pytest.fail("check_cache nao deve consultar SQL"),
    )

    result = farmacia.load_or_sync_memoria_calculo("123", engine=object(), check_cache=True)

    assert result.df.is_empty()
    assert result.from_cache is False
    assert result.error is None


def test_corrupt_local_parquet_in_cache_only_mode_returns_empty_result(tmp_path, monkeypatch):
    path = tmp_path / cache_files.MEMORIA_CALCULO_PARQUET
    path.write_bytes(b"not a parquet file")
    monkeypatch.setattr(farmacia, "_cache_path", lambda _cnpj: str(path))
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_from_global",
        lambda *_args: pytest.fail("cache-only nao pode consultar cache global"),
    )
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_sql",
        lambda *_args: pytest.fail("cache-only nao pode consultar SQL"),
    )

    result = farmacia.load_or_sync_memoria_calculo("123", engine=object(), check_cache=True)

    assert result.df.is_empty()
    assert result.from_cache is False
    assert result.error is None


def test_local_memory_parquet_is_reused(tmp_path, monkeypatch):
    path = tmp_path / cache_files.MEMORIA_CALCULO_PARQUET
    expected = pl.DataFrame({"tipo_linha": ["venda_irregular"], "valor": [12.5]})
    expected.write_parquet(path)
    monkeypatch.setattr(farmacia, "_cache_path", lambda cnpj: str(path))
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_from_global",
        lambda cnpj: pytest.fail("cache local válido deve ser reutilizado"),
    )

    result = farmacia.load_or_sync_memoria_calculo("123", engine=object())

    assert result.from_cache is True
    assert result.df.equals(expected)
    assert result.read_time_ms is not None


def test_global_memory_is_materialized_locally_and_empty_global_result_is_returned(
    tmp_path, monkeypatch
):
    path = tmp_path / "123" / cache_files.MEMORIA_CALCULO_PARQUET
    path.parent.mkdir()
    expected = pl.DataFrame({"tipo_linha": ["venda_irregular"], "valor": [12.5]})
    monkeypatch.setattr(farmacia, "_cache_path", lambda _cnpj: str(path))
    monkeypatch.setattr(farmacia, "_load_memoria_from_global", lambda _cnpj: (expected, 1.5))

    result = farmacia.load_or_sync_memoria_calculo("123", engine=object())

    assert result.from_cache is True
    assert result.read_time_ms == 1.5
    assert result.save_time_ms is not None
    assert pl.read_parquet(path).equals(expected)

    path.unlink()
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_from_global",
        lambda _cnpj: (pl.DataFrame([]), 2.5),
    )
    empty = farmacia.load_or_sync_memoria_calculo("123", engine=object())
    assert empty.df.is_empty()
    assert empty.from_cache is True
    assert empty.read_time_ms == 2.5


def test_global_memory_write_failure_keeps_the_data_and_reports_save_error(
    monkeypatch, capsys
):
    expected = pl.DataFrame({"tipo_linha": ["venda_irregular"], "valor": [12.5]})
    monkeypatch.setattr(farmacia, "_cache_path", lambda _cnpj: "cache/memoria.parquet")
    monkeypatch.setattr(farmacia.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(farmacia, "_load_memoria_from_global", lambda _cnpj: (expected, 1.5))

    def fail_write(_frame, *_args, **_kwargs):
        raise OSError("disco sem espaco")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", fail_write)
    result = farmacia.load_or_sync_memoria_calculo("123", engine=object())

    assert result.df.equals(expected)
    assert result.from_cache is True
    assert result.save_time_ms is None
    assert "disco sem espaco" in capsys.readouterr().out


def test_sql_memory_rows_are_decoded_and_medicine_names_are_loaded(monkeypatch):
    payload = _payload()

    class Result:
        def __init__(self, row=None, rows=()):
            self.row = row
            self.rows = rows

        def fetchone(self):
            return self.row

        def fetchall(self):
            return list(self.rows)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            if "memoria_calculo_consolidada" in str(query):
                assert params == {"cnpj": "123"}
                return Result((payload, 1, 88))
            return Result(rows=[("789123", "Ativo")])

    class Engine:
        def connect(self):
            return Connection()

    rows, medicines, query_ms = farmacia._load_memoria_sql("123", Engine())

    assert [row["tipo"] for row in rows] == ["h", "e", "v", "s"]
    assert medicines["789123"] == "Ativo"
    assert query_ms >= 0


def test_sql_materialization_writes_rows_and_exposes_database_error(tmp_path, monkeypatch):
    path = tmp_path / "123" / cache_files.MEMORIA_CALCULO_PARQUET
    path.parent.mkdir()
    monkeypatch.setattr(farmacia, "_cache_path", lambda cnpj: str(path))
    monkeypatch.setattr(farmacia, "_load_memoria_from_global", lambda cnpj: (None, None))
    decoded = farmacia._decode_memoria_payload(_payload())
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_sql",
        lambda cnpj, engine: (decoded, {"789123": "Ativo"}, 4.2),
    )

    result = farmacia.load_or_sync_memoria_calculo("123", engine=object())

    assert result.error is None
    assert result.from_cache is False
    assert result.query_time_ms == 4.2
    assert result.df.filter(pl.col("tipo_linha") == "venda_irregular").height == 1
    assert pl.read_parquet(path).equals(result.df)

    monkeypatch.setattr(
        farmacia,
        "_load_memoria_sql",
        lambda *args: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    path.unlink()
    unavailable = farmacia.load_or_sync_memoria_calculo("123", engine=object())
    assert unavailable.error == "Arquivo Parquet local nao encontrado e Banco Offline."
    assert unavailable.df.is_empty()


def test_sql_absence_returns_empty_result_with_query_timing(monkeypatch):
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_sql",
        lambda cnpj, engine: (None, {}, 2.0),
    )
    monkeypatch.setattr(farmacia, "_cache_path", lambda cnpj: "not-created/memoria.smod")
    monkeypatch.setattr(farmacia.os.path, "exists", lambda path: False)
    monkeypatch.setattr(farmacia, "_load_memoria_from_global", lambda cnpj: (None, None))

    result = farmacia.load_or_sync_memoria_calculo("123", engine=object())

    assert result.df.is_empty()
    assert result.query_time_ms == 2.0
    assert result.error is None


def test_missing_global_cache_falls_through_to_sql_and_handles_local_write_failure(
    monkeypatch, capsys
):
    decoded = farmacia._decode_memoria_payload(_payload())
    monkeypatch.setattr(farmacia, "_cache_path", lambda _cnpj: "cache/memoria.parquet")
    monkeypatch.setattr(farmacia.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_from_global",
        lambda _cnpj: (_ for _ in ()).throw(FileNotFoundError("global cache ausente")),
    )
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_sql",
        lambda _cnpj, _engine: (decoded, {"789123": "Ativo"}, 3.5),
    )

    def fail_write(_frame, *_args, **_kwargs):
        raise OSError("sem permissao de escrita")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", fail_write)
    result = farmacia.load_or_sync_memoria_calculo("123", engine=object())

    assert result.df.filter(pl.col("tipo_linha") == "venda_irregular").height == 1
    assert result.from_cache is False
    assert result.query_time_ms == 3.5
    assert result.save_time_ms is None
    assert "sem permissao de escrita" in capsys.readouterr().out


def test_global_memory_load_failure_is_reported_without_falling_through_to_sql(
    monkeypatch
):
    monkeypatch.setattr(
        farmacia,
        "_cache_path",
        lambda _cnpj: "cache/memoria_calculo.parquet",
    )
    monkeypatch.setattr(farmacia.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_from_global",
        lambda _cnpj: (_ for _ in ()).throw(RuntimeError("schema invalido")),
    )
    monkeypatch.setattr(
        farmacia,
        "_load_memoria_sql",
        lambda *_args: pytest.fail("erro estrutural do cache global deve ser propagado"),
    )

    result = farmacia.load_or_sync_memoria_calculo("123", engine=object())

    assert result.error == (
        f"Modulo global {cache_files.MEMORIA_CALCULO_GLOBAL_PARQUET} invalido: schema invalido"
    )
    assert result.from_cache is False
