from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import polars as pl
import pytest

import cache_files
import cache_producers.crm as crm
import data_cache


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def connect(self):
        return FakeConnection()


def test_crm_integer_and_parquet_read_helpers_report_bad_input(tmp_path, capsys):
    assert crm._to_int("3.9") == 3
    assert crm._to_int(None, default=-1) == -1
    assert crm._to_int("not-a-number", default=7) == 7

    missing = tmp_path / "missing.smod"
    assert crm._read_parquet(str(missing)) == (None, None)

    corrupt = tmp_path / "corrupt.smod"
    corrupt.write_text("not parquet", encoding="utf-8")
    assert crm._read_parquet(str(corrupt)) == (None, None)
    assert "erro de leitura" in capsys.readouterr().out
    assert crm._empty_schema(cache_files.CRM_TIMELINE_DIA_PARQUET)["dt_janela"] == pl.Utf8


def test_generic_sql_cache_prefers_existing_parquet(tmp_path, monkeypatch):
    path = tmp_path / cache_files.CRM_TIMELINE_DIA_PARQUET
    expected = pl.DataFrame({"dt_janela": ["2025-01-01"], "competencia": [202501]})
    expected.write_parquet(path)
    monkeypatch.setattr(crm, "_path", lambda cnpj, filename: str(path))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("cache válido deve evitar SQL"),
    )

    result = crm._load_or_sync_sql_cache(
        "123",
        cache_files.CRM_TIMELINE_DIA_PARQUET,
        "SELECT 1",
        {"cnpj": "123"},
        engine=None,
    )

    assert result.from_cache is True
    assert result.df.to_dicts() == expected.to_dicts()
    assert result.read_time_ms is not None


def test_generic_sql_cache_materializes_rows_and_empty_results(tmp_path, monkeypatch):
    path = tmp_path / cache_files.CRM_TIMELINE_DIA_PARQUET
    monkeypatch.setattr(crm, "_path", lambda cnpj, filename: str(path))
    calls = []
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda query, conn, params: calls.append(params)
        or pd.DataFrame({"dt_janela": ["2025-02-03"], "competencia": [202502]}),
    )

    result = crm._load_or_sync_sql_cache(
        "123",
        cache_files.CRM_TIMELINE_DIA_PARQUET,
        "SELECT janela",
        {"cnpj": "123"},
        engine=FakeEngine(),
        read_existing=False,
    )

    assert result.error is None
    assert result.df.to_dicts() == [{"dt_janela": "2025-02-03", "competencia": 202502}]
    assert calls == [{"cnpj": "123"}]
    assert pl.read_parquet(path).equals(result.df)

    empty_path = tmp_path / "empty.smod"
    monkeypatch.setattr(crm, "_path", lambda cnpj, filename: str(empty_path))
    monkeypatch.setattr(crm.pd, "read_sql", lambda *args, **kwargs: pd.DataFrame())
    empty = crm._load_or_sync_sql_cache(
        "123",
        cache_files.CRM_TIMELINE_DIA_PARQUET,
        "SELECT janela",
        {"cnpj": "123"},
        engine=FakeEngine(),
        read_existing=False,
    )
    assert empty.error is None
    assert empty.df.is_empty()
    assert empty.df.schema == crm._empty_schema(cache_files.CRM_TIMELINE_DIA_PARQUET)


def test_generic_sql_cache_returns_empty_typed_result_on_database_error(tmp_path, monkeypatch):
    path = tmp_path / cache_files.CRM_TIMELINE_DIA_PARQUET
    monkeypatch.setattr(crm, "_path", lambda cnpj, filename: str(path))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    result = crm._load_or_sync_sql_cache(
        "123",
        cache_files.CRM_TIMELINE_DIA_PARQUET,
        "SELECT janela",
        {"cnpj": "123"},
        engine=FakeEngine(),
        read_existing=False,
    )

    assert result.error == "Banco Offline."
    assert result.df.is_empty()
    assert result.df.schema == crm._empty_schema(cache_files.CRM_TIMELINE_DIA_PARQUET)
    assert not path.exists()


def _default_for(dtype):
    if dtype == pl.Utf8:
        return "crm-1"
    if dtype == pl.Boolean:
        return False
    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8):
        return 1
    if dtype == pl.Float64:
        return 1.0
    return None


def _prescritor_frames():
    cnpj_schema = crm._empty_schema(cache_files.CRM_PRESCRITORES_PARQUET)
    global_schema = {
        "id_cnpj": pl.Int32,
        **{name: dtype for name, dtype in cnpj_schema.items() if name != "no_medico"},
    }
    row = {name: [_default_for(dtype)] for name, dtype in global_schema.items()}
    row.update({"id_cnpj": [5], "id_medico": ["med-1"], "competencia": [202501]})
    row["_crm_prescritores_cache_version"] = [cache_files.CRM_PRESCRITORES_CACHE_VERSION]
    source = pl.DataFrame(row, schema=global_schema)
    names = pl.DataFrame(
        {"id_medico": ["med-1"], "no_medico": ["Dra. Exemplo"]}
    )
    return cnpj_schema, source, names


def test_crm_prescritor_valid_local_parquet_is_reused(tmp_path, monkeypatch):
    cnpj = "123"
    cnpj_dir = tmp_path / cnpj
    cnpj_dir.mkdir()
    schema = crm._empty_schema(cache_files.CRM_PRESCRITORES_PARQUET)
    expected = pl.DataFrame(schema=schema)
    expected.write_parquet(cnpj_dir / cache_files.CRM_PRESCRITORES_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda value: str(cnpj_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(tmp_path / "global"))

    result = crm.load_or_sync_crm_data(cnpj, engine=object())

    assert result.from_cache is True
    assert result.error is None
    assert result.df.is_empty()
    assert result.df.schema == schema


def test_crm_prescritor_global_parquet_is_filtered_named_and_saved(tmp_path, monkeypatch):
    cnpj = "123"
    cnpj_dir = tmp_path / cnpj
    global_dir = tmp_path / "global"
    cnpj_dir.mkdir()
    global_dir.mkdir()
    global_path = global_dir / cache_files.CRM_PRESCRITORES_GLOBAL_PARQUET
    pl.DataFrame(
        {"_crm_prescritores_cache_version": [cache_files.CRM_PRESCRITORES_CACHE_VERSION]}
    ).write_parquet(global_path)
    _, global_rows, doctors = _prescritor_frames()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda value: str(cnpj_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        data_cache,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [cnpj], "id_cnpj": [5]}),
    )
    monkeypatch.setattr(
        data_cache,
        "scan_crm_prescritores_global",
        lambda: global_rows.lazy(),
    )
    monkeypatch.setattr(data_cache, "scan_dados_medico", lambda: doctors.lazy())

    result = crm.load_or_sync_crm_data(cnpj, engine=object())

    assert result.error is None
    assert result.from_cache is False
    assert result.df["no_medico"].to_list() == ["Dra. Exemplo"]
    assert result.df["competencia"].to_list() == [202501]
    saved = pl.read_parquet(cnpj_dir / cache_files.CRM_PRESCRITORES_PARQUET)
    assert saved.equals(result.df)


def test_crm_prescritor_invalid_global_is_reported_without_sql_fallback(tmp_path, monkeypatch):
    cnpj_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    cnpj_dir.mkdir()
    global_dir.mkdir()
    pl.DataFrame({"_crm_prescritores_cache_version": [0]}).write_parquet(
        global_dir / cache_files.CRM_PRESCRITORES_GLOBAL_PARQUET
    )
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda value: str(cnpj_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        data_cache,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["123"], "id_cnpj": [5]}),
    )
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("global existente e inválido deve falhar visivelmente"),
    )

    result = crm.load_or_sync_crm_data("123", engine=FakeEngine())

    assert result.df.is_empty()
    assert result.error is not None
    assert "versao do modulo global inferior" in result.error
    assert not (cnpj_dir / cache_files.CRM_PRESCRITORES_PARQUET).exists()


def test_raiox_cache_hit_requires_current_version_and_expected_columns(tmp_path, monkeypatch):
    cnpj_dir = tmp_path / "123"
    cnpj_dir.mkdir()
    schema = crm._empty_schema(cache_files.CRM_RAIOX_TX_PARQUET)
    row = {name: [_default_for(dtype)] for name, dtype in schema.items()}
    row.update(
        {
            "dt_janela": ["2025-03-01"],
            "hr_janela": [9],
            "data_hora": ["2025-03-01 09:00"],
            "num_autorizacao": ["A1"],
            "id_medico": ["M1"],
            "valor_pago": [9.5],
            "_crm_raiox_tx_cache_version": [cache_files.CRM_RAIOX_TX_CACHE_VERSION],
        }
    )
    expected = pl.DataFrame(row, schema=schema)
    expected.write_parquet(cnpj_dir / cache_files.CRM_RAIOX_TX_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda value: str(cnpj_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(tmp_path / "global"))

    result = crm.sync_crm_raiox_tx("123", engine=object())

    assert result.from_cache is True
    assert result.df.equals(expected)


def _schema_row(schema, *, id_cnpj=None):
    row = {name: [_default_for(dtype)] for name, dtype in schema.items()}
    if id_cnpj is not None:
        row["id_cnpj"] = [id_cnpj]
    return row


@pytest.mark.parametrize(
    ("function", "filename"),
    [
        (crm.load_or_sync_geografico, cache_files.GEOGRAFICO_PARQUET),
        (crm.load_or_sync_crm_timeline_dia, cache_files.CRM_TIMELINE_DIA_PARQUET),
        (crm.load_or_sync_crm_timeline_hora, cache_files.CRM_TIMELINE_HORA_PARQUET),
        (crm.load_or_sync_crm_timeline_eventos, cache_files.CRM_TIMELINE_EVENTOS_PARQUET),
        (crm.load_or_sync_crm_unico_alertas, cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET),
        (crm.load_or_sync_crm_multi_alertas, cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET),
    ],
)
def test_crm_module_loaders_reuse_valid_local_cache(
    function, filename, tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    schema = crm._empty_schema(filename)
    expected = pl.DataFrame(schema=schema)
    expected.write_parquet(local_dir / filename)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("cache local valido nao deve consultar o banco"),
    )

    result = function("123", engine=FakeEngine())

    assert result.from_cache is True
    assert result.df.equals(expected)


@pytest.mark.parametrize(
    ("function", "filename"),
    [
        (crm.load_or_sync_geografico, cache_files.GEOGRAFICO_PARQUET),
        (crm.load_or_sync_crm_timeline_dia, cache_files.CRM_TIMELINE_DIA_PARQUET),
        (crm.load_or_sync_crm_timeline_hora, cache_files.CRM_TIMELINE_HORA_PARQUET),
        (crm.load_or_sync_crm_timeline_eventos, cache_files.CRM_TIMELINE_EVENTOS_PARQUET),
        (crm.load_or_sync_crm_unico_alertas, cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET),
        (crm.load_or_sync_crm_multi_alertas, cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET),
    ],
)
def test_crm_module_loaders_generate_typed_cache_from_empty_sql_result(
    function, filename, tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    sql_calls = []
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda query, conn, params: sql_calls.append((str(query), params)) or pd.DataFrame(),
    )

    result = function("123", engine=FakeEngine())

    assert len(sql_calls) == 1
    assert sql_calls[0][1] == {"cnpj": "123"}
    assert result.error is None
    assert result.from_cache is False
    assert result.df.is_empty()
    assert (local_dir / filename).exists()


def test_geographic_loader_rejects_missing_sql_columns_without_writing_parquet(
    tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pd.DataFrame({"coluna_inesperada": ["valor"]}),
    )

    result = crm.load_or_sync_geografico("123", engine=FakeEngine())

    assert result.df is None
    assert "Contrato invalido" in result.error
    assert "cnpj_a" in result.error
    assert not (local_dir / cache_files.GEOGRAFICO_PARQUET).exists()


def test_raiox_loader_reports_missing_sql_columns_without_writing_parquet(
    tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    local_dir.mkdir()
    monkeypatch.setattr(crm, "_path", lambda _cnpj, filename: str(local_dir / filename))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(tmp_path / "global"))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pd.DataFrame({"dt_janela": ["2025-03-01"]}),
    )

    result = crm.sync_crm_raiox_tx("123", engine=FakeEngine())

    assert result.df.is_empty()
    assert "Erro ao gerar" in result.error
    assert not (local_dir / cache_files.CRM_RAIOX_TX_PARQUET).exists()


@pytest.mark.parametrize(
    ("function", "filename", "global_filename", "scanner"),
    [
        (
            crm.load_or_sync_crm_timeline_dia,
            cache_files.CRM_TIMELINE_DIA_PARQUET,
            cache_files.CRM_TIMELINE_DIA_GLOBAL_PARQUET,
            "scan_crm_timeline_dia_global",
        ),
        (
            crm.load_or_sync_crm_timeline_hora,
            cache_files.CRM_TIMELINE_HORA_PARQUET,
            cache_files.CRM_TIMELINE_HORA_GLOBAL_PARQUET,
            "scan_crm_timeline_hora_global",
        ),
        (
            crm.load_or_sync_crm_timeline_eventos,
            cache_files.CRM_TIMELINE_EVENTOS_PARQUET,
            cache_files.CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET,
            "scan_crm_timeline_eventos_global",
        ),
    ],
)
def test_crm_timeline_modules_derive_local_cache_from_global(
    function, filename, global_filename, scanner, tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    (global_dir / global_filename).write_bytes(b"global cache marker")
    schema = crm._empty_schema(filename)
    global_schema = {"id_cnpj": pl.Int32, **schema}
    expected_global = pl.DataFrame(
        _schema_row(schema, id_cnpj=5), schema=global_schema
    )
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        data_cache,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["123"], "id_cnpj": [5]}),
    )
    monkeypatch.setattr(data_cache, scanner, lambda: expected_global.lazy())
    monkeypatch.setattr(
        crm,
        "_load_or_sync_sql_cache",
        lambda *args, **kwargs: pytest.fail("cache global valido deve evitar SQL"),
    )

    result = function("123", engine=FakeEngine())

    assert result.error is None
    assert result.from_cache is False
    assert result.df.height == 1
    assert pl.read_parquet(local_dir / filename).equals(result.df)


def test_geographic_module_derives_local_cache_from_global(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    (global_dir / cache_files.GEOGRAFICO_GLOBAL_PARQUET).write_bytes(b"global cache marker")
    schema = crm._empty_schema(cache_files.GEOGRAFICO_PARQUET)
    row = _schema_row(schema)
    row["cnpj_a"] = ["123"]
    global_rows = pl.DataFrame(row, schema=schema)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(data_cache, "scan_geografico_global", lambda: global_rows.lazy())
    monkeypatch.setattr(
        crm,
        "_load_or_sync_sql_cache",
        lambda *args, **kwargs: pytest.fail("cache global valido deve evitar SQL"),
    )

    result = crm.load_or_sync_geografico("123", engine=FakeEngine())

    assert result.error is None
    assert result.from_cache is False
    assert result.df.height == 1
    assert result.df["cnpj_a"].to_list() == ["123"]
    assert pl.read_parquet(local_dir / cache_files.GEOGRAFICO_PARQUET).equals(result.df)


def test_cache_directory_creation_and_default_engine_resolution(tmp_path, monkeypatch):
    cache_root = tmp_path / "cnpjs"
    monkeypatch.setattr(data_cache, "get_cnpj_cache_root", lambda: str(cache_root))
    cache_dir = Path(crm._get_cnpj_cache_dir("123"))
    assert cache_dir == cache_root / "123"
    assert cache_dir.is_dir()

    engine = object()
    monkeypatch.setitem(sys.modules, "database", SimpleNamespace(engine=engine))
    assert crm._engine_or_default() is engine
    explicit_engine = object()
    assert crm._engine_or_default(explicit_engine) is explicit_engine


def _prescritor_sql_rows(*, omit=()):
    values = {
        "id_medico": "med-1",
        "competencia": 202501,
        "vl_total_prescricoes": 125.5,
        "nu_prescricoes_mes": 3,
        "nu_prescricoes_total_brasil": 12,
        "flag_crm_invalido": 0,
        "flag_prescricao_antes_registro": 0,
        "alerta_concentracao_multiplos_crms": 0,
        "flag_concentracao_mesmo_crm": 0,
        "flag_distancia_geografica": 0,
        "dt_inscricao_crm": "2020-01-02",
        "nu_estabelecimentos": 1,
    }
    return pd.DataFrame([{key: value for key, value in values.items() if key not in omit}])


def test_crm_prescritor_sql_generation_enriches_and_saves_rows(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    pl.DataFrame({"legacy": [1]}).write_parquet(
        local_dir / cache_files.CRM_PRESCRITORES_PARQUET
    )
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(crm.pd, "read_sql", lambda *args, **kwargs: _prescritor_sql_rows())
    monkeypatch.setattr(
        data_cache,
        "scan_dados_medico",
        lambda: pl.DataFrame({"id_medico": ["med-1"], "no_medico": ["Dra. Teste"]}).lazy(),
    )

    result = crm.load_or_sync_crm_data("123", engine=FakeEngine())

    assert result.error is None
    assert result.from_cache is False
    assert result.df["no_medico"].to_list() == ["Dra. Teste"]
    assert result.df["flag_crm_invalido"].dtype == pl.Int8
    assert result.df["dt_inscricao_crm"].to_list() == [pd.Timestamp("2020-01-02").date()]
    saved = pl.read_parquet(local_dir / cache_files.CRM_PRESCRITORES_PARQUET)
    expected_columns = list(crm._empty_schema(cache_files.CRM_PRESCRITORES_PARQUET))
    assert saved.equals(result.df.select(expected_columns))


@pytest.mark.parametrize(
    "profile",
    [
        pl.DataFrame({"cnpj": ["123"]}),
        pl.DataFrame({"cnpj": ["123", "123"], "id_cnpj": [5, 6]}),
    ],
    ids=["missing-required-profile-column", "non-unique-pharmacy-mapping"],
)
def test_crm_prescritor_global_derivation_rejects_invalid_profile(tmp_path, monkeypatch, profile):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    pl.DataFrame(
        {"_crm_prescritores_cache_version": [cache_files.CRM_PRESCRITORES_CACHE_VERSION]}
    ).write_parquet(global_dir / cache_files.CRM_PRESCRITORES_GLOBAL_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(data_cache, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("um global invalido deve falhar sem consulta SQL"),
    )

    result = crm.load_or_sync_crm_data("123", engine=FakeEngine())

    assert result.df.is_empty()
    assert result.error is not None
    assert "Modulo global" in result.error
    assert not (local_dir / cache_files.CRM_PRESCRITORES_PARQUET).exists()


def test_crm_prescritor_global_derivation_saves_empty_typed_result(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    pl.DataFrame(
        {"_crm_prescritores_cache_version": [cache_files.CRM_PRESCRITORES_CACHE_VERSION]}
    ).write_parquet(global_dir / cache_files.CRM_PRESCRITORES_GLOBAL_PARQUET)
    cnpj_schema, _, _ = _prescritor_frames()
    global_schema = {
        "id_cnpj": pl.Int32,
        **{name: dtype for name, dtype in cnpj_schema.items() if name != "no_medico"},
    }
    empty_global = pl.DataFrame(schema=global_schema)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        data_cache,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["123"], "id_cnpj": [5]}),
    )
    monkeypatch.setattr(data_cache, "scan_crm_prescritores_global", lambda: empty_global.lazy())
    monkeypatch.setattr(
        data_cache,
        "scan_dados_medico",
        lambda: pytest.fail("sem prescritores, nao deve consultar a dimensao de medicos"),
    )

    result = crm.load_or_sync_crm_data("123", engine=FakeEngine())

    assert result.error is None
    assert result.df.is_empty()
    assert result.df.schema == cnpj_schema
    saved = pl.read_parquet(local_dir / cache_files.CRM_PRESCRITORES_PARQUET)
    assert saved.equals(result.df.select(list(crm._empty_schema(cache_files.CRM_PRESCRITORES_PARQUET))))


@pytest.mark.parametrize(
    ("omitted", "expected_error"),
    [((), None), (("vl_total_prescricoes",), "Contrato invalido")],
)
def test_crm_prescritor_sql_generation_handles_contract_and_database_errors(
    tmp_path, monkeypatch, omitted, expected_error
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(crm.pd, "read_sql", lambda *args, **kwargs: _prescritor_sql_rows(omit=omitted))
    monkeypatch.setattr(
        data_cache,
        "scan_dados_medico",
        lambda: pl.DataFrame({"id_medico": ["med-1"], "no_medico": ["Dra. Teste"]}).lazy(),
    )

    result = crm.load_or_sync_crm_data("123", engine=FakeEngine())

    if expected_error:
        assert result.error is not None
        assert result.df.is_empty()
        assert not (local_dir / cache_files.CRM_PRESCRITORES_PARQUET).exists()
    else:
        assert result.error is None
        assert result.df.height == 1


def test_crm_prescritor_sql_generation_rejects_missing_doctor_registration_date(
    tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: _prescritor_sql_rows(omit=("dt_inscricao_crm",)),
    )
    monkeypatch.setattr(
        data_cache,
        "scan_dados_medico",
        lambda: pl.DataFrame({"id_medico": ["med-1"], "no_medico": ["Dra. Teste"]}).lazy(),
    )

    result = crm.load_or_sync_crm_data("123", engine=FakeEngine())

    assert result.error is not None
    assert result.error == "Arquivo Parquet local nao encontrado e Banco Offline."
    assert result.df.is_empty()
    assert result.df.is_empty()


@pytest.mark.parametrize(
    ("function", "filename", "global_filename", "scanner", "drop_id"),
    [
        (
            crm.load_or_sync_crm_unico_alertas,
            cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET,
            cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET,
            "scan_crm_concentracao_unico_alertas_global",
            True,
        ),
        (
            crm.load_or_sync_crm_multi_alertas,
            cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET,
            cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET,
            "scan_crm_concentracao_multiplo_alertas_global",
            False,
        ),
    ],
)
def test_crm_alert_modules_derive_local_cache_from_global(
    function, filename, global_filename, scanner, drop_id, tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    (global_dir / global_filename).write_bytes(b"global cache marker")
    schema = crm._empty_schema(filename)
    if function is crm.load_or_sync_crm_multi_alertas:
        old_cache = pl.DataFrame(
            {name: [0 if name == "_crm_alerts_cache_version" else _default_for(dtype)]
             for name, dtype in schema.items()},
            schema=schema,
        )
        old_cache.write_parquet(local_dir / filename)
    global_schema = schema if "id_cnpj" in schema else {"id_cnpj": pl.Int32, **schema}
    global_rows = pl.DataFrame(_schema_row(schema, id_cnpj=5), schema=global_schema)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        data_cache,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["123"], "id_cnpj": [5]}),
    )
    monkeypatch.setattr(data_cache, scanner, lambda: global_rows.lazy())
    monkeypatch.setattr(
        crm,
        "_load_or_sync_sql_cache",
        lambda *args, **kwargs: pytest.fail("cache global valido deve evitar SQL"),
    )

    result = function("123", engine=FakeEngine())

    assert result.error is None
    assert result.from_cache is False
    assert result.df.height == 1
    assert ("id_cnpj" not in result.df.columns) is drop_id
    assert pl.read_parquet(local_dir / filename).equals(result.df)


def _raiox_sql_rows():
    return pd.DataFrame(
        [
            {
                "dt_janela": "2025-03-01",
                "hr_janela": 9,
                "data_hora": "2025-03-01 09:15:00",
                "num_autorizacao": "A-2",
                "id_medico": "med-2",
                "valor_pago": 15.75,
            },
            {
                "dt_janela": "2025-03-01",
                "hr_janela": 9,
                "data_hora": "2025-03-01 09:05:00",
                "num_autorizacao": "A-1",
                "id_medico": "med-1",
                "valor_pago": 10.25,
            },
        ]
    )


def test_raiox_sql_generation_casts_orders_and_saves_rows(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(crm.pd, "read_sql", lambda *args, **kwargs: _raiox_sql_rows())

    result = crm.sync_crm_raiox_tx("123", engine=FakeEngine())

    assert result.error is None
    assert result.from_cache is False
    assert result.df["num_autorizacao"].to_list() == ["A-1", "A-2"]
    assert result.df["_crm_raiox_tx_cache_version"].to_list() == [
        cache_files.CRM_RAIOX_TX_CACHE_VERSION,
        cache_files.CRM_RAIOX_TX_CACHE_VERSION,
    ]
    assert pl.read_parquet(local_dir / cache_files.CRM_RAIOX_TX_PARQUET).equals(result.df)


def test_raiox_sql_generation_saves_typed_empty_cache(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(crm.pd, "read_sql", lambda *args, **kwargs: pd.DataFrame())

    result = crm.sync_crm_raiox_tx("123", engine=FakeEngine())

    assert result.error is None
    assert result.df.is_empty()
    assert result.df.schema == crm._empty_schema(cache_files.CRM_RAIOX_TX_PARQUET)
    assert pl.read_parquet(local_dir / cache_files.CRM_RAIOX_TX_PARQUET).equals(result.df)


def test_raiox_sql_failure_is_returned_with_typed_empty_data(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("SQL indisponivel")),
    )

    result = crm.sync_crm_raiox_tx("123", engine=FakeEngine())

    assert result.error is not None
    assert "SQL Server" in result.error
    assert result.df.is_empty()
    assert result.df.schema == crm._empty_schema(cache_files.CRM_RAIOX_TX_PARQUET)
    assert not (local_dir / cache_files.CRM_RAIOX_TX_PARQUET).exists()


def test_raiox_global_derivation_filters_sorts_and_saves_rows(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    schema = crm._empty_schema(cache_files.CRM_RAIOX_TX_PARQUET)
    global_schema = {"id_cnpj": pl.Int32, **schema}
    global_rows = pl.DataFrame(
        {
            "id_cnpj": [5, 5],
            "dt_janela": ["2025-03-01", "2025-03-01"],
            "hr_janela": [9, 9],
            "data_hora": ["2025-03-01 09:15", "2025-03-01 09:05"],
            "num_autorizacao": ["A-2", "A-1"],
            "id_medico": ["med-2", "med-1"],
            "valor_pago": [15.75, 10.25],
            "_crm_raiox_tx_cache_version": [
                cache_files.CRM_RAIOX_TX_CACHE_VERSION,
                cache_files.CRM_RAIOX_TX_CACHE_VERSION,
            ],
        },
        schema=global_schema,
    )
    version_marker = pl.DataFrame(
        {"_crm_raiox_tx_cache_version": [cache_files.CRM_RAIOX_TX_CACHE_VERSION]}
    )
    version_marker.write_parquet(global_dir / cache_files.CRM_RAIOX_TX_GLOBAL_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        data_cache,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["123"], "id_cnpj": [5]}),
    )
    monkeypatch.setattr(data_cache, "scan_crm_raiox_tx_global", lambda: global_rows.lazy())
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("cache global valido deve evitar SQL"),
    )

    result = crm.sync_crm_raiox_tx("123", engine=FakeEngine())

    assert result.error is None
    assert result.from_cache is False
    assert result.df["num_autorizacao"].to_list() == ["A-1", "A-2"]
    assert pl.read_parquet(local_dir / cache_files.CRM_RAIOX_TX_PARQUET).equals(result.df)


@pytest.mark.parametrize(
    "global_version",
    [None, cache_files.CRM_RAIOX_TX_CACHE_VERSION - 1],
    ids=["empty-global", "outdated-global"],
)
def test_raiox_rejects_empty_or_outdated_global_cache(
    global_version, tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    if global_version is None:
        marker = pl.DataFrame(schema={"_crm_raiox_tx_cache_version": pl.Int32})
    else:
        marker = pl.DataFrame({"_crm_raiox_tx_cache_version": [global_version]})
    marker.write_parquet(global_dir / cache_files.CRM_RAIOX_TX_GLOBAL_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("global invalido deve falhar sem SQL alternativo"),
    )

    result = crm.sync_crm_raiox_tx("123", engine=FakeEngine())

    assert result.error is not None
    assert "mas invalido" in result.error
    assert result.df.is_empty()
    assert not (local_dir / cache_files.CRM_RAIOX_TX_PARQUET).exists()


def test_crm_prescritor_rejects_empty_global_module(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    pl.DataFrame(schema={"_crm_prescritores_cache_version": pl.Int32}).write_parquet(
        global_dir / cache_files.CRM_PRESCRITORES_GLOBAL_PARQUET
    )
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("modulo global vazio nao deve acionar SQL"),
    )

    result = crm.load_or_sync_crm_data("123", engine=FakeEngine())

    assert result.error is not None
    assert "o modulo global esta vazio" in result.error
    assert result.df.is_empty()


@pytest.mark.parametrize(
    ("function", "filename", "global_filename", "scanner"),
    [
        (
            crm.load_or_sync_geografico,
            cache_files.GEOGRAFICO_PARQUET,
            cache_files.GEOGRAFICO_GLOBAL_PARQUET,
            "scan_geografico_global",
        ),
        (
            crm.load_or_sync_crm_timeline_dia,
            cache_files.CRM_TIMELINE_DIA_PARQUET,
            cache_files.CRM_TIMELINE_DIA_GLOBAL_PARQUET,
            "scan_crm_timeline_dia_global",
        ),
        (
            crm.load_or_sync_crm_timeline_hora,
            cache_files.CRM_TIMELINE_HORA_PARQUET,
            cache_files.CRM_TIMELINE_HORA_GLOBAL_PARQUET,
            "scan_crm_timeline_hora_global",
        ),
        (
            crm.load_or_sync_crm_timeline_eventos,
            cache_files.CRM_TIMELINE_EVENTOS_PARQUET,
            cache_files.CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET,
            "scan_crm_timeline_eventos_global",
        ),
    ],
)
def test_crm_geographic_and_timeline_global_scan_errors_are_reported_and_fall_back_to_sql(
    function, filename, global_filename, scanner, tmp_path, monkeypatch, capsys
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    (global_dir / global_filename).write_bytes(b"global cache marker")
    schema = crm._empty_schema(filename)
    local_path = local_dir / filename
    pl.DataFrame(schema=schema).write_parquet(local_path)
    # Make the global cache newer so the local cache is deliberately rebuilt.
    import os
    os.utime(local_path, (1, 1))
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    if function is not crm.load_or_sync_geografico:
        monkeypatch.setattr(
            data_cache,
            "get_df_perfil_estabelecimento",
            lambda: pl.DataFrame({"cnpj": ["123"], "id_cnpj": [5]}),
        )
    monkeypatch.setattr(
        data_cache,
        scanner,
        lambda: (_ for _ in ()).throw(RuntimeError("global corrompido")),
    )
    empty = pl.DataFrame(schema=schema)
    monkeypatch.setattr(
        crm,
        "_load_or_sync_sql_cache",
        lambda *args, **kwargs: crm.CacheLoadResult(empty, from_cache=False),
    )

    result = function("123", engine=FakeEngine())

    assert result.error is None
    assert result.df.is_empty()
    assert "global corrompido" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("function", "filename", "global_filename", "scanner"),
    [
        (
            crm.load_or_sync_crm_unico_alertas,
            cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET,
            cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET,
            "scan_crm_concentracao_unico_alertas_global",
        ),
        (
            crm.load_or_sync_crm_multi_alertas,
            cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET,
            cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET,
            "scan_crm_concentracao_multiplo_alertas_global",
        ),
    ],
)
def test_crm_alert_global_scan_errors_are_reported_and_sql_errors_are_preserved(
    function, filename, global_filename, scanner, tmp_path, monkeypatch, capsys
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    (global_dir / global_filename).write_bytes(b"global cache marker")
    schema = crm._empty_schema(filename)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(
        data_cache,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["123"], "id_cnpj": [5]}),
    )
    monkeypatch.setattr(
        data_cache,
        scanner,
        lambda: (_ for _ in ()).throw(RuntimeError("global corrompido")),
    )
    monkeypatch.setattr(
        crm,
        "_load_or_sync_sql_cache",
        lambda *args, **kwargs: crm.CacheLoadResult(
            pl.DataFrame(schema=schema), from_cache=False, error="Banco Offline."
        ),
    )

    result = function("123", engine=FakeEngine())

    assert result.error == "Banco Offline."
    assert "global corrompido" in capsys.readouterr().out


@pytest.mark.parametrize(
    "profile",
    [
        pl.DataFrame({"cnpj": ["123"]}),
        pl.DataFrame({"cnpj": ["123", "123"], "id_cnpj": [5, 6]}),
    ],
    ids=["missing-required-profile-column", "non-unique-pharmacy-mapping"],
)
def test_raiox_global_derivation_rejects_invalid_pharmacy_profile(
    profile, tmp_path, monkeypatch
):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    pl.DataFrame(
        {"_crm_raiox_tx_cache_version": [cache_files.CRM_RAIOX_TX_CACHE_VERSION]}
    ).write_parquet(global_dir / cache_files.CRM_RAIOX_TX_GLOBAL_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(data_cache, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(
        data_cache,
        "scan_crm_raiox_tx_global",
        lambda: pytest.fail("perfil invalido deve impedir a leitura do cache global"),
    )
    monkeypatch.setattr(
        crm.pd,
        "read_sql",
        lambda *args, **kwargs: pytest.fail("global existente invalido deve falhar sem SQL"),
    )

    result = crm.sync_crm_raiox_tx("123", engine=FakeEngine())

    assert result.error is not None
    assert "perfil_estabelecimento" in result.error
    assert result.df.is_empty()


def test_crm_unico_alerts_rebuilds_invalid_local_cache_from_sql(tmp_path, monkeypatch):
    local_dir = tmp_path / "123"
    global_dir = tmp_path / "global"
    local_dir.mkdir()
    global_dir.mkdir()
    pl.DataFrame({"legacy": [1]}).write_parquet(
        local_dir / cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET
    )
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _cnpj: str(local_dir))
    monkeypatch.setattr(data_cache, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(crm.pd, "read_sql", lambda *args, **kwargs: pd.DataFrame())

    result = crm.load_or_sync_crm_unico_alertas("123", engine=FakeEngine())

    assert result.error is None
    assert result.df.is_empty()
    assert result.df["_crm_alerts_cache_version"].to_list() == []
    assert pl.read_parquet(local_dir / cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET).equals(
        result.df
    )
