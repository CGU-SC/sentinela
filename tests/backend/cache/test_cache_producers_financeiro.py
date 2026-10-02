import sys
from datetime import date
from types import SimpleNamespace

import pandas as pd
import polars as pl
import pytest

import data_cache
from cache_producers import financeiro


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Engine:
    def connect(self):
        return _Connection()


def _monthly_rows():
    return pl.DataFrame(
        {
            "codigo_barra": ["0001"],
            "periodo": [date(2024, 1, 1)],
            "qnt_caixas_vendidas": [3],
            "qnt_caixas_sem_comprovacao": [1],
            "num_autorizacoes": [2],
            "valor_vendas": [30.0],
            "valor_sem_comprovacao": [10.0],
        }
    )


def test_financial_cache_directory_and_path_are_created_under_configured_root(monkeypatch, tmp_path):
    monkeypatch.setattr(data_cache, "get_cnpj_cache_root", lambda: str(tmp_path))

    directory = financeiro._get_cnpj_cache_dir("12345678000190")
    path = financeiro._cache_path("12345678000190")

    assert directory == str(tmp_path / "12345678000190")
    assert (tmp_path / "12345678000190").is_dir()
    assert path == str(tmp_path / "12345678000190" / financeiro.MOVIMENTACAO_MENSAL_GTIN_PARQUET)


def test_financial_cache_recovers_from_corrupt_local_parquet_using_global_cache(monkeypatch, tmp_path):
    parquet_path = tmp_path / "monthly-gtin.smod"
    source = _monthly_rows()
    read_parquet = pl.read_parquet
    monkeypatch.setattr(financeiro, "_cache_path", lambda _cnpj: str(parquet_path))
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(
        financeiro.pl,
        "read_parquet",
        lambda _path: (_ for _ in ()).throw(ValueError("corrupt local parquet")),
    )
    monkeypatch.setattr(financeiro, "_load_from_global", lambda _cnpj: (source, 4.2))

    result = financeiro.load_or_sync_movimentacao_mensal_gtin("12345678000190")

    assert result.df.equals(source)
    assert result.from_cache is False
    assert result.read_time_ms == 4.2
    assert result.save_time_ms is not None
    assert read_parquet(parquet_path).equals(source)


def test_financial_cache_uses_database_when_global_module_is_unavailable(monkeypatch, tmp_path):
    parquet_path = tmp_path / "monthly-gtin.smod"
    monkeypatch.setattr(financeiro, "_cache_path", lambda _cnpj: str(parquet_path))
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(financeiro, "_load_from_global", lambda _cnpj: None)
    monkeypatch.setitem(sys.modules, "database", SimpleNamespace(engine=_Engine()))

    def read_sql(query, connection, *, params):
        assert "movimentacao_mensal_gtin" in str(query)
        assert params == {"cnpj": "12345678000190"}
        assert isinstance(connection, _Connection)
        return pd.DataFrame(
            {
                "codigo_barra": [1],
                "periodo": [pd.Timestamp("2024-01-01")],
                "qnt_caixas_vendidas": [3],
                "qnt_caixas_sem_comprovacao": [1],
                "num_autorizacoes": [2],
                "valor_vendas": [30.0],
                "valor_sem_comprovacao": [10.0],
            }
        )

    monkeypatch.setattr(financeiro.pd, "read_sql", read_sql)

    result = financeiro.load_or_sync_movimentacao_mensal_gtin("12345678000190")

    assert result.error is None
    assert result.from_cache is False
    assert result.df is not None
    assert result.df.schema["codigo_barra"] == pl.String
    assert result.df.schema["periodo"] == pl.Date
    assert result.df.to_dicts() == [{
        "codigo_barra": "1",
        "periodo": date(2024, 1, 1),
        "qnt_caixas_vendidas": 3,
        "qnt_caixas_sem_comprovacao": 1,
        "num_autorizacoes": 2,
        "valor_vendas": 30.0,
        "valor_sem_comprovacao": 10.0,
    }]
    assert result.query_time_ms is not None and result.save_time_ms is not None
    assert pl.read_parquet(parquet_path).equals(result.df)


def test_financial_cache_returns_valid_local_parquet_without_syncing(monkeypatch, tmp_path):
    source = _monthly_rows()
    monkeypatch.setattr(financeiro, "_cache_path", lambda _cnpj: str(tmp_path / "cached.smod"))
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(financeiro.pl, "read_parquet", lambda _path: source)

    result = financeiro.load_or_sync_movimentacao_mensal_gtin("12345678000190")

    assert result.df is source
    assert result.from_cache is True
    assert result.read_time_ms is not None
    assert result.query_time_ms is None


def test_load_from_global_joins_profile_identity_and_selects_monthly_fields(monkeypatch):
    profile = pl.DataFrame({"cnpj": ["12345678000190", "98765432000110"], "id_cnpj": [7, 8]})
    source = pl.DataFrame(
        {
            "id_cnpj": [7, 8], "codigo_barra": ["0001", "0002"],
            "periodo": [date(2024, 1, 1), date(2024, 1, 1)],
            "qnt_caixas_vendidas": [3, 4], "qnt_caixas_sem_comprovacao": [1, 2],
            "num_autorizacoes": [2, 3], "valor_vendas": [30.0, 40.0],
            "valor_sem_comprovacao": [10.0, 20.0],
        }
    )
    monkeypatch.setattr(data_cache, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(data_cache, "scan_movimentacao_mensal_gtin_global", lambda: source.lazy())

    result, elapsed = financeiro._load_from_global("12345678000190")

    assert result.columns == [
        "codigo_barra", "periodo", "qnt_caixas_vendidas", "qnt_caixas_sem_comprovacao",
        "num_autorizacoes", "valor_vendas", "valor_sem_comprovacao",
    ]
    assert result.get_column("codigo_barra").to_list() == ["0001"]
    assert elapsed >= 0


@pytest.mark.parametrize(
    "profile",
    [
        pl.DataFrame({"cnpj": [], "id_cnpj": []}, schema={"cnpj": pl.String, "id_cnpj": pl.Int64}),
        pl.DataFrame({"cnpj": ["12345678000190", "12345678000190"], "id_cnpj": [7, 7]}),
    ],
)
def test_load_from_global_requires_exactly_one_profile_identity(monkeypatch, profile):
    monkeypatch.setattr(data_cache, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(data_cache, "scan_movimentacao_mensal_gtin_global", lambda: pytest.fail("scan must not run"))

    with pytest.raises(RuntimeError, match="id_cnpj unico"):
        financeiro._load_from_global("12345678000190")


def test_missing_global_file_error_is_preserved_when_database_is_offline(monkeypatch, tmp_path):
    class OfflineEngine:
        def connect(self):
            raise ConnectionError("database offline")

    monkeypatch.setattr(financeiro, "_cache_path", lambda _cnpj: str(tmp_path / "missing.smod"))
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(financeiro, "_load_from_global", lambda _cnpj: (_ for _ in ()).throw(FileNotFoundError("global parquet absent")))

    result = financeiro.load_or_sync_movimentacao_mensal_gtin("12345678000190", engine=OfflineEngine())

    assert result.error is not None
    assert "Detalhe do modulo global: global parquet absent" in result.error
    assert result.query_time_ms is None
    assert result.save_time_ms is None


def test_unexpected_global_error_is_reported_without_fallback_message(monkeypatch, tmp_path):
    monkeypatch.setattr(financeiro, "_cache_path", lambda _cnpj: str(tmp_path / "missing.smod"))
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(financeiro, "_load_from_global", lambda _cnpj: (_ for _ in ()).throw(RuntimeError("invalid profile schema")))

    result = financeiro.load_or_sync_movimentacao_mensal_gtin("12345678000190", engine=_Engine())

    assert result.error is not None
    assert "Detalhe do modulo global" not in result.error
    assert result.df.is_empty()
