import pandas as pd
import polars as pl

import cache_files
import cache_producers.socios as socios
import data_cache


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def connect(self):
        return FakeConnection()


def test_socios_reads_real_parquet_cache_before_sql(tmp_path, monkeypatch):
    cache_path = tmp_path / cache_files.SOCIOS_PARQUET
    expected = pl.DataFrame(
        {
            "cnpj": ["123"],
            "nome_socio": ["Pessoa Exemplo"],
            "is_falecido": [True],
        }
    )
    expected.write_parquet(cache_path)
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        socios.pd,
        "read_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQL nao deveria rodar")),
    )

    result = socios.load_socios("123", engine=FakeEngine())

    assert result.from_cache is True
    assert result.df.to_dicts() == expected.to_dicts()


def test_socios_query_returns_rows_from_explicit_fake_engine(monkeypatch):
    captured = {}

    def read_sql(query, conn, params):
        captured.update(params)
        assert "WHERE cnpj = :cnpj" in str(query)
        return pd.DataFrame(
            {
                "cnpj": ["123"],
                "cpf_cnpj_socio": ["98765432100"],
                "nome_socio": ["Pessoa Exemplo"],
                "is_falecido": [False],
            }
        )

    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: "unused-cache-dir")
    monkeypatch.setattr(socios.os.path, "exists", lambda path: False)
    monkeypatch.setattr(socios.pd, "read_sql", read_sql)

    result = socios.load_socios("123", engine=FakeEngine())

    assert result.error is None
    assert result.from_cache is False
    assert captured == {"cnpj": "123"}
    assert result.df.row(0, named=True)["cpf_cnpj_socio"] == "98765432100"


def test_socios_sql_failure_returns_error_without_fabricating_rows(monkeypatch):
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: "unused-cache-dir")
    monkeypatch.setattr(socios.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        socios.pd,
        "read_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    result = socios.load_socios("123", engine=FakeEngine())

    assert result.df is None
    assert result.error == "Cache ausente e Banco offline."
    assert result.from_cache is False
