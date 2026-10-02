from datetime import date
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import polars as pl
import pytest

import cache_registry
import data_cache


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class ColumnResult:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, table_exists=True, row_count=1, columns=("cnpj", "nome")):
        self.table_exists = table_exists
        self.row_count = row_count
        self.columns = columns
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        sql = str(query)
        self.calls.append((sql, params))
        if "OBJECT_ID" in sql:
            return ScalarResult(1 if self.table_exists else None)
        if "COUNT_BIG" in sql or "COUNT(" in sql:
            return ScalarResult(self.row_count)
        return ColumnResult([(column,) for column in self.columns])


class FakeEngine:
    def __init__(self, **kwargs):
        self.connection = FakeConnection(**kwargs)

    def connect(self):
        return self.connection


def test_path_helpers_cover_frozen_desktop_layout_and_directory_creation(tmp_path, monkeypatch):
    cache = data_cache
    created = []
    executable = tmp_path / "Sentinela.exe"
    with monkeypatch.context() as scoped:
        scoped.setattr(cache.sys, "frozen", True, raising=False)
        scoped.setattr(cache.sys, "executable", str(executable))
        scoped.setattr(cache.os.path, "exists", lambda _path: False)
        scoped.setattr(cache.os, "makedirs", lambda path, exist_ok=True: created.append(path))
        importlib.reload(cache)

        assert cache.BASE_DIR == str(tmp_path)
        assert cache.get_modules_dir() == str(tmp_path / "modules")
        assert cache.get_cache_dir() == str(tmp_path / "modules" / "global")
        assert cache.get_cnpj_cache_root() == str(tmp_path / "modules" / "cnpjs")
        assert cache.get_user_preferences_dir() == str(tmp_path / "modules" / "user_preferences")
        assert created == [
            str(tmp_path / "modules"),
            str(tmp_path / "modules" / "global"),
            str(tmp_path / "modules" / "cnpjs"),
        ]

    importlib.reload(cache)


def test_matrix_cnpj_lookup_trims_identifiers_and_drops_null_rows():
    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return ColumnResult([(" 111 ",), (None,), ("222",)])

    class Engine:
        def connect(self):
            return Connection()

    assert data_cache._buscar_cnpjs_matriz(Engine()) == ["111", "222"]


@pytest.fixture
def isolated_cache_state(monkeypatch):
    tracked = [
        name
        for name in vars(data_cache)
        if name.startswith("_df_")
        or name
        in {
            "_cache_progress",
            "_cache_status",
            "_cache_error_message",
            "_cache_generation",
        }
    ]
    previous = {name: getattr(data_cache, name) for name in tracked}
    previous_ready = set(data_cache._ON_DEMAND_GLOBAL_CACHE_READY)
    yield data_cache
    for name, value in previous.items():
        monkeypatch.setattr(data_cache, name, value)
    data_cache._ON_DEMAND_GLOBAL_CACHE_READY.clear()
    data_cache._ON_DEMAND_GLOBAL_CACHE_READY.update(previous_ready)


def test_global_path_signature_and_schema_validation_use_real_parquet(tmp_path, monkeypatch):
    path = tmp_path / "fixture.smod"
    pl.DataFrame({"id": pl.Series([7], dtype=pl.Int32), "label": ["sample"]}).write_parquet(path)
    monkeypatch.setattr(data_cache, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(data_cache, "_GLOBAL_PARQUETS", {"fixture": path.name})
    monkeypatch.setattr(
        data_cache,
        "_GLOBAL_PARQUET_SCHEMAS",
        {"fixture": {"id": pl.Int32, "label": pl.Utf8}},
    )

    assert data_cache._global_cache_path("fixture") == str(path)
    signature = data_cache.get_global_cache_signature("fixture")
    assert signature[0] == "fixture"
    assert signature[1] > 0
    assert signature[2] == path.stat().st_size
    data_cache._validate_parquet_schema("fixture", str(path))

    with pytest.raises(ValueError, match="schema antigo sem colunas obrigatorias: missing"):
        data_cache._validate_parquet_schema(
            "fixture",
            str(path),
            required={"missing"},
        )

    monkeypatch.setattr(
        data_cache,
        "_GLOBAL_PARQUET_SCHEMAS",
        {"fixture": {"id": pl.Int64}},
    )
    with pytest.raises(ValueError, match="schema antigo com tipos invalidos"):
        data_cache._validate_parquet_schema("fixture", str(path))


def test_on_demand_scan_validates_contract_and_records_readiness(tmp_path, monkeypatch):
    path = tmp_path / "on_demand.smod"
    expected = pl.DataFrame({"id": [4], "name": ["Ada"]})
    expected.write_parquet(path)
    monkeypatch.setattr(
        data_cache,
        "_GLOBAL_PARQUET_SCHEMAS",
        {"fixture": {"id": pl.Int64, "name": pl.Utf8}},
    )
    monkeypatch.setattr(
        data_cache,
        "_ON_DEMAND_GLOBAL_REQUIRED_COLUMNS",
        {"fixture": {"id", "name"}},
    )
    data_cache._ON_DEMAND_GLOBAL_CACHE_READY.discard("fixture")

    result = data_cache._scan_on_demand_global_parquet("fixture", str(path)).collect()

    assert result.equals(expected)
    assert data_cache._is_on_demand_global_cache_ready("fixture", str(path))

    stale = tmp_path / "stale.smod"
    pl.DataFrame({"id": [4]}).write_parquet(stale)
    data_cache._ON_DEMAND_GLOBAL_CACHE_READY.discard("fixture")
    with pytest.raises(ValueError, match="name"):
        data_cache._scan_on_demand_global_parquet("fixture", str(stale))
    assert not data_cache._is_on_demand_global_cache_ready("fixture", str(stale))


def test_schema_validation_and_signature_fail_for_absent_files(tmp_path, monkeypatch):
    missing = tmp_path / "missing.smod"
    monkeypatch.setattr(data_cache, "_GLOBAL_PARQUETS", {"missing": missing.name})
    monkeypatch.setattr(data_cache, "_CACHE_DIR", str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Parquet global missing nao encontrado"):
        data_cache._validate_parquet_schema("missing", str(missing))
    with pytest.raises(FileNotFoundError):
        data_cache.get_global_cache_signature("missing")


def test_fast_cache_boot_rejects_parquet_missing_required_columns(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    old_cache = tmp_path / "dados-par.parquet"
    pl.DataFrame({"cnpj": ["12345678000195"]}).write_parquet(old_cache)
    monkeypatch.setattr(cache, "_DADOS_PAR_PARQUET_PATH", str(old_cache))
    monkeypatch.setattr(
        cache.os.path,
        "exists",
        lambda path: str(path) == str(old_cache),
    )

    cache.load_cache(None)

    assert cache._df_dados_par is None
    assert cache._cache_status == "idle"


def test_source_table_contract_checks_existence_rows_and_columns():
    assert data_cache._assert_fp_source_table(
        FakeEngine(columns=("cnpj", "nome", "id")),
        "amostra",
        {"cnpj", "id"},
    ) == 1

    with pytest.raises(RuntimeError, match="Tabela fonte temp_CGUSC.fp.amostra nao encontrada"):
        data_cache._assert_fp_source_table(
            FakeEngine(table_exists=False),
            "amostra",
            {"cnpj"},
        )
    with pytest.raises(RuntimeError, match="Tabela fonte temp_CGUSC.fp.amostra esta vazia"):
        data_cache._assert_fp_source_table(
            FakeEngine(row_count=0),
            "amostra",
            {"cnpj"},
        )
    with pytest.raises(RuntimeError, match="sem colunas obrigatorias: ausente"):
        data_cache._assert_fp_source_table(
            FakeEngine(columns=("cnpj",)),
            "amostra",
            {"cnpj", "ausente"},
        )


def test_falecidos_sync_normalizes_identifiers_saves_rows_and_reports_progress(
    tmp_path, monkeypatch
):
    path = tmp_path / "falecidos.smod"
    progress = []
    monkeypatch.setattr(data_cache, "_FALECIDOS_PARQUET_PATH", str(path))
    monkeypatch.setattr(data_cache, "_assert_fp_source_table", lambda *args: 2)
    source = pd.DataFrame(
        {
            "cnpj": ["12.345.678/0001-95", "12345678000195"],
            "cpf": ["123.456.789-01", "98765432100"],
            "nome_falecido": ["A", "B"],
            "municipio_falecido": ["Campinas", "Santos"],
            "uf_falecido": ["SP", "SP"],
            "dt_nascimento": [pd.Timestamp("1940-01-01")] * 2,
            "dt_obito": [pd.Timestamp("2024-01-01")] * 2,
            "fonte_obito": ["fonte", "fonte"],
            "num_autorizacao": ["A1", "A2"],
            "data_autorizacao": [pd.Timestamp("2024-02-01"), pd.Timestamp("2024-03-01")],
            "qtd_itens_na_autorizacao": [1, 2],
            "valor_total_autorizacao": [10.0, 20.0],
            "dias_apos_obito": [31, 60],
        }
    )
    monkeypatch.setattr(data_cache.pd, "read_sql", lambda *args, **kwargs: iter([source]))

    data_cache._sync_falecidos(object(), progress.append)

    result = pl.read_parquet(path)
    assert result.height == 2
    assert result["cnpj"].to_list() == ["12345678000195"] * 2
    assert result["cpf"][0] == "12345678901"
    assert result["valor_total_autorizacao"].to_list() == [10.0, 20.0]
    assert progress == [100]
    assert data_cache._df_falecidos.equals(result)


def test_falecidos_sync_rejects_source_table_without_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(data_cache, "_FALECIDOS_PARQUET_PATH", str(tmp_path / "falecidos.smod"))
    monkeypatch.setattr(data_cache, "_assert_fp_source_table", lambda *args: 1)
    monkeypatch.setattr(data_cache.pd, "read_sql", lambda *args, **kwargs: iter([]))

    with pytest.raises(RuntimeError, match="nao retornou linhas"):
        data_cache._sync_falecidos(object())


def test_simple_global_sync_casts_schema_adds_constants_and_signals_completion(
    tmp_path, monkeypatch
):
    path = tmp_path / "simple.smod"
    monkeypatch.setattr(
        data_cache,
        "_GLOBAL_PARQUET_SCHEMAS",
        {"simple": {"id": pl.Int32, "name": pl.Utf8, "batch": pl.Int16}},
    )
    monkeypatch.setattr(
        data_cache.pd,
        "read_sql",
        lambda query, conn: pd.DataFrame({"id": [3], "name": ["record"]}),
    )
    progress = []

    data_cache._load_or_sync_global_cache_simple(
        "simple",
        str(path),
        "SELECT id, name",
        FakeEngine(),
        progress_callback=progress.append,
        extra_columns={"batch": 2026},
    )

    result = pl.read_parquet(path)
    assert result.schema == {"id": pl.Int32, "name": pl.Utf8, "batch": pl.Int16}
    assert result.to_dicts() == [{"id": 3, "name": "record", "batch": 2026}]
    assert not Path(str(path) + ".tmp").exists()
    assert progress == [100]
    assert data_cache._is_on_demand_global_cache_ready("simple", str(path))


def test_simple_global_sync_rejects_missing_required_sql_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_cache,
        "_GLOBAL_PARQUET_SCHEMAS",
        {"simple": {"id": pl.Int32, "required_value": pl.Utf8}},
    )
    monkeypatch.setattr(
        data_cache.pd,
        "read_sql",
        lambda query, conn: pd.DataFrame({"id": [1]}),
    )
    path = tmp_path / "simple.smod"

    with pytest.raises(ValueError, match="colunas obrigatorias ausentes no resultado SQL: required_value"):
        data_cache._load_or_sync_global_cache_simple(
            "simple",
            str(path),
            "SELECT id",
            FakeEngine(),
        )
    assert not path.exists()


def test_fast_boot_enters_degraded_mode_when_required_parquets_are_absent(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    monkeypatch.setattr(cache, "_CACHE_DIR", str(tmp_path))
    for name, value in vars(cache).items():
        if name.startswith("_") and name.endswith("_PATH") and isinstance(value, str):
            monkeypatch.setattr(cache, name, str(tmp_path / Path(value).name))
    cache._ON_DEMAND_GLOBAL_CACHE_READY.clear()

    cache.load_cache(engine=object(), force_refresh=False)

    status = cache.get_cache_status()
    assert status["status"] == "idle"
    assert status["progress"] == 0
    assert status["is_ready"] is False
    assert status["loaded_modules"] == 0
    assert status["modules"]["movimentacao"]["status"] == "missing"
    assert status["modules"]["crm_prescritores_global"]["optional"] is True


def test_fast_boot_loads_all_required_caches_and_marks_on_demand_modules_ready(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    loaded_names = []
    marked_names = []
    real_read_parquet = cache.pl.read_parquet
    matrix_path = tmp_path / "matriz_risco.parquet"
    matrix_schema = cache._GLOBAL_PARQUET_SCHEMAS["matriz_risco"]
    pl.DataFrame(schema=matrix_schema).write_parquet(matrix_path)
    monkeypatch.setattr(cache, "_MATRIZ_PARQUET_PATH", str(matrix_path))
    falecidos_path = tmp_path / "falecidos.parquet"
    pl.DataFrame(schema=cache._GLOBAL_PARQUET_SCHEMAS["falecidos"]).write_parquet(falecidos_path)
    monkeypatch.setattr(cache, "_FALECIDOS_PARQUET_PATH", str(falecidos_path))

    class FrameContract:
        def __init__(self, columns):
            self.columns = list(columns)

    def read_parquet(path):
        caller = inspect.currentframe().f_back
        load_frame = caller.f_back
        required_columns = load_frame.f_locals["required_columns"]
        cache_name = caller.f_locals["name"]
        loaded_names.append(cache_name)
        if cache_name == "matriz_risco" or cache_name == "falecidos":
            return real_read_parquet(path)
        return FrameContract(required_columns.get(cache_name, set()))

    monkeypatch.setattr(cache.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(cache.pl, "read_parquet", read_parquet)
    def mark_ready(name, _path):
        marked_names.append(name)
        cache._ON_DEMAND_GLOBAL_CACHE_READY.add(name)

    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", mark_ready)
    initial_generation = cache.get_cache_generation()
    cache.load_cache(engine=object(), force_refresh=False)

    status = cache.get_cache_status()
    assert status["status"] == "ready"
    assert status["progress"] == 100
    assert status["is_ready"] is True, [
        name for name, module in status["modules"].items()
        if not module["optional"] and not module["loaded"]
    ]
    assert status["unavailable_modules"] == 0
    assert status["error_message"] == ""
    assert status["cache_version"].endswith(f":{initial_generation + 1}")
    assert {"movimentacao", "perfil_estabelecimento", "dados_farmacia", "dados_par"}.issubset(loaded_names)
    assert {"teia_fonte_nivel2", "crm_prescritores_global", "esocial_cnpj_ano"}.issubset(marked_names)

    stale_matrix_schema = dict(matrix_schema)
    stale_matrix_schema["id_cnpj"] = pl.Utf8
    pl.DataFrame(schema=stale_matrix_schema).write_parquet(matrix_path)
    cache.load_cache(engine=object(), force_refresh=False)
    stale_status = cache.get_cache_status()
    assert stale_status["status"] == "idle"
    assert stale_status["modules"]["matriz_risco"]["loaded"] is False


def test_fast_boot_records_parquet_read_and_on_demand_validation_failures(
    monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state

    class FrameContract:
        def __init__(self, columns):
            self.columns = list(columns)

    def read_parquet(path):
        caller = inspect.currentframe().f_back
        load_frame = caller.f_back
        name = caller.f_locals["name"]
        if name == "movimentacao":
            raise OSError("arquivo bloqueado")
        return FrameContract(load_frame.f_locals["required_columns"].get(name, set()))

    def mark_ready(name, _path):
        if name == "crm_prescritores_global":
            raise ValueError("schema invalido")
        cache._ON_DEMAND_GLOBAL_CACHE_READY.add(name)

    monkeypatch.setattr(cache.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(cache.pl, "read_parquet", read_parquet)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", mark_ready)
    cache.load_cache(engine=object(), force_refresh=False)
    status = cache.get_cache_status()
    assert status["status"] == "idle"
    assert status["progress"] == 0
    assert status["is_ready"] is False
    assert status["modules"]["movimentacao"]["loaded"] is False


def test_fast_boot_attempts_modules_when_boot_exclusions_are_cleared(
    monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    monkeypatch.setattr(cache, "_DISABLED_BOOT_MODULES", frozenset())
    marked = []

    class FrameContract:
        def __init__(self, columns):
            self.columns = list(columns)

    def read_parquet(_path):
        caller = inspect.currentframe().f_back
        load_frame = caller.f_back
        required = load_frame.f_locals["required_columns"]
        name = caller.f_locals["name"]
        return FrameContract(required.get(name, set()))

    def mark_ready(name, _path):
        marked.append(name)

    monkeypatch.setattr(cache.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(cache.pl, "read_parquet", read_parquet)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", mark_ready)
    cache.load_cache(engine=object(), force_refresh=False)

    assert {
        "crm_medico_estabelecimento_mes", "crm_medico_brasil_mes",
        "crm_medico_territorio_mes", "crm_medico_brasil_ano",
        "crm_medico_territorio_ano", "crm_mapa_municipio_regiao_periodo",
        "crm_mapa_uf_periodo", "crm_limiar_p95_mes",
    }.issubset(marked)


def test_forced_cache_sync_runs_weighted_tasks_and_reports_progress(monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    calls = []

    def sync_stub(*args, **kwargs):
        callback = next((value for value in reversed(args) if callable(value)), None)
        if callback is None:
            callback = kwargs.get("progress_callback")
        if callback:
            callback(50)
            callback(100)
        calls.append(args[0] if args else "no-engine")

    for name, value in vars(cache).items():
        if name.startswith("_sync_") and callable(value):
            monkeypatch.setattr(cache, name, sync_stub)
    cache._cache_error_message = ""
    initial_generation = cache.get_cache_generation()
    cache.load_cache(engine="fake-engine", force_refresh=True)
    status = cache.get_cache_status()

    assert len(calls) >= 30
    assert status["status"] == "ready"
    assert status["progress"] == 100
    assert status["error_message"] == ""
    assert status["cache_version"].endswith(f":{initial_generation + 1}")


def test_forced_cache_sync_records_error_and_refresh_forces_reload(monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    monkeypatch.setattr(cache, "_sync_medicamentos", lambda *_args: (_ for _ in ()).throw(RuntimeError("fonte fora")))
    cache.load_cache(engine="fake-engine", force_refresh=True)
    status = cache.get_cache_status()
    assert status["status"] == "error"
    assert status["progress"] == 0
    assert status["error_message"] == "fonte fora"

    calls = []
    monkeypatch.setattr(cache, "load_cache", lambda engine, force_refresh=False: calls.append((engine, force_refresh)))
    cache.refresh_cache("engine")
    assert calls == [("engine", True)]


def test_locality_network_and_medicine_syncs_cast_write_and_report_progress(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    locality_path = tmp_path / "localities.parquet"
    network_path = tmp_path / "network.parquet"
    medicine_path = tmp_path / "medicines.parquet"
    monkeypatch.setattr(cache, "_LOCALIDADES_PARQUET_PATH", str(locality_path))
    monkeypatch.setattr(cache, "_REDE_PARQUET_PATH", str(network_path))
    monkeypatch.setattr(cache, "_MEDICAMENTOS_PARQUET_PATH", str(medicine_path))

    localities = pd.DataFrame({
        "sg_uf": ["SP"], "no_regiao_saude": ["Região A"], "id_regiao_saude": [123],
        "no_municipio": ["Campinas"], "id_ibge7": [3509502], "nu_populacao": [100],
        "unidade_pf": ["Unidade 1"],
    })
    network = pd.DataFrame({
        "cnpj_raiz": ["12345678"], "cnpj": ["12345678000195"], "razao_social": ["Farmácia"],
        "uf": ["SP"], "municipio": ["Campinas"], "is_matriz": [True],
        "qtd_estabelecimentos_rede": [2], "is_grande_rede": [False],
    })
    medicines = pd.DataFrame({
        "codigo_barra": ["1"], "principio_ativo": ["A"], "produto": ["B"],
        "descricao": ["C"], "laboratorio": ["D"], "patologia": ["E"],
    })
    reads = iter([localities, network, medicines])
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: next(reads))
    progress = []
    cache._sync_localidades(object(), progress.append)
    cache._sync_rede(object(), progress.append)
    cache._sync_medicamentos(object(), progress.append)

    assert progress == [100, 100, 100]
    assert pl.read_parquet(locality_path)["id_regiao_saude"].to_list() == [123]
    assert pl.read_parquet(network_path)["cnpj"].to_list() == ["12345678000195"]
    assert pl.read_parquet(medicine_path)["codigo_barra"].to_list() == ["1"]
    assert cache.get_localidades_df().height == cache.get_rede_df().height == cache.get_medicamentos_df().height == 1


def test_chunked_matrix_and_semester_sync_cast_and_sort_real_parquets(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    matrix_path = tmp_path / "risk.parquet"
    volume_path = tmp_path / "volume.parquet"
    monkeypatch.setattr(cache, "_MATRIZ_PARQUET_PATH", str(matrix_path))
    monkeypatch.setattr(cache, "_VOLUME_ATIPICO_SEMESTRAL_PARQUET_PATH", str(volume_path))
    schema = cache._GLOBAL_PARQUET_SCHEMAS["matriz_risco"]
    matrix_data = {column: [None] for column in schema}
    matrix_data.update({"id_cnpj": [2], "ano_base": [2024]})
    matrix = pd.DataFrame(matrix_data)
    volume_parts = [
        pd.DataFrame({
            "id_cnpj": [2], "chave_semestre": [202402], "status_semestre": [1],
            "qtd_meses_presentes": [6], "chave_semestre_anterior": [202401],
            "aumento_valor_semestre": [20.0], "taxa_crescimento_pct": [0.2],
        }),
        pd.DataFrame({
            "id_cnpj": [1], "chave_semestre": [202401], "status_semestre": [1],
            "qtd_meses_presentes": [6], "chave_semestre_anterior": [202302],
            "aumento_valor_semestre": [10.0], "taxa_crescimento_pct": [0.1],
        }),
    ]
    reads = iter([iter([matrix]), iter(volume_parts)])
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: next(reads))
    progress = []
    cache._sync_matriz_risco(FakeEngine(row_count=1), progress.append)
    cache._sync_volume_atipico_semestral(FakeEngine(row_count=2), progress.append)

    persisted_matrix = pl.read_parquet(matrix_path)
    persisted_volume = pl.read_parquet(volume_path)
    assert persisted_matrix.schema == schema
    assert persisted_matrix.select("id_cnpj", "ano_base").row(0) == (2, 2024)
    assert persisted_volume.select("id_cnpj", "chave_semestre").rows() == [(1, 202401), (2, 202402)]
    assert progress[-2:] == [50, 100]
    assert cache.get_df_matriz_risco().equals(persisted_matrix)
    assert cache.get_df_volume_atipico_semestral().equals(persisted_volume)

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
    with pytest.raises(RuntimeError, match="matriz_risco_consolidada nao retornou linhas"):
        cache._sync_matriz_risco(FakeEngine(row_count=0))


def test_geographic_and_demographic_cache_syncs_validate_sources_and_publish(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    geo_path = tmp_path / "geo.parquet"
    demo_path = tmp_path / "demographic.parquet"
    monkeypatch.setattr(cache, "_GEOGRAFICO_ORIGEM_UF_PARQUET_PATH", str(geo_path))
    monkeypatch.setattr(cache, "_DADOS_IBGE_DEMOGRAFIA_PARQUET_PATH", str(demo_path))
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)
    geo = pd.DataFrame({
        "id_cnpj": [3], "ano_base": [2024], "uf_farmacia": ["SP"], "uf_paciente": ["RJ"],
        "is_outra_uf": [True], "qtd_autorizacoes": [4], "valor_autorizado": [80.5],
    })
    demo = pd.DataFrame({
        "id_ibge7": ["3509502"], "grupo_idade": ["50 a 59"], "sexo": ["F"],
        "nu_populacao": [10], "ano_censo": [2022], "idade_min": [50], "idade_max": [59], "ordem": [5],
    })
    reads = iter([iter([geo]), iter([demo])])
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: next(reads))
    progress = []
    cache._sync_geografico_origem_uf(FakeEngine(row_count=1), progress.append)
    cache._sync_dados_ibge_demografia(FakeEngine(row_count=1), progress.append)

    assert pl.read_parquet(geo_path).to_dicts()[0]["valor_autorizado"] == 80.5
    assert cache._is_on_demand_global_cache_ready("geografico_origem_uf", str(geo_path))
    assert pl.read_parquet(demo_path)["id_ibge7"].to_list() == ["3509502"]
    assert cache.get_df_dados_ibge_demografia().height == 1
    assert progress == [100, 100]

    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: (_ for _ in ()).throw(RuntimeError("schema ausente")))
    with pytest.raises(RuntimeError, match="schema ausente"):
        cache._sync_geografico_origem_uf(FakeEngine())


def test_crm_benchmark_sync_deduplicates_scoped_rows_and_reports_all_phases(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    paths = [tmp_path / "br.parquet", tmp_path / "uf.parquet", tmp_path / "region.parquet"]
    monkeypatch.setattr(cache, "_BENCH_CRM_BR_PATH", str(paths[0]))
    monkeypatch.setattr(cache, "_BENCH_CRM_UF_PATH", str(paths[1]))
    monkeypatch.setattr(cache, "_BENCH_CRM_REGIAO_PATH", str(paths[2]))
    frame = pd.DataFrame({
        "competencia": [202401, 202401, 202402], "uf": ["SP", "SP", "RJ"],
        "id_regiao_saude": [123, 123, 456], "valor": [1, 2, 3],
    })
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: frame)
    progress = []
    cache._sync_crm_benchmarks(object(), progress.append)

    assert progress == [33, 66, 100, 100]
    for path in paths:
        result = pl.read_parquet(path)
        assert result.height == 2
        assert result.columns == ["competencia", "uf", "id_regiao_saude", "valor"]

    def read_with_one_failure(query, *_args, **_kwargs):
        if "bench_uf" in str(query):
            raise OSError("UF offline")
        return frame

    monkeypatch.setattr(cache.pd, "read_sql", read_with_one_failure)
    recovered_progress = []
    cache._sync_crm_benchmarks(object(), recovered_progress.append)
    assert recovered_progress == [33, 100, 100]


def test_clinical_indicator_cache_syncs_cast_all_three_granularities(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    modules = {
        "analise_gtin_inconsistencia_clinica": "_ANALISE_GTIN_INCONSISTENCIA_CLINICA_PARQUET_PATH",
        "analise_gtin_inconsistencia_clinica_municipio": "_ANALISE_GTIN_INCONSISTENCIA_CLINICA_MUNICIPIO_PARQUET_PATH",
        "analise_gtin_inconsistencia_clinica_regiao": "_ANALISE_GTIN_INCONSISTENCIA_CLINICA_REGIAO_PARQUET_PATH",
    }
    paths = {}
    for index, (module, path_name) in enumerate(modules.items()):
        path = tmp_path / f"clinical-{index}.parquet"
        paths[module] = path
        monkeypatch.setattr(cache, path_name, str(path))

    def source_frame(module):
        values = {}
        for column in cache._ON_DEMAND_GLOBAL_REQUIRED_COLUMNS[module]:
            if column in {"id_cnpj", "id_regiao_saude", "id_ibge7"}:
                values[column] = [7 if column != "id_ibge7" else "3509502"]
            elif column in {"patologia", "regra_clinica"}:
                values[column] = ["DIABETES" if column == "patologia" else "IDADE_MENOR_20"]
            elif column == "ano_base":
                values[column] = [2024]
            elif column == "dt_processamento":
                values[column] = [pd.Timestamp("2025-01-01")]
            elif column.startswith(("qtd_", "rank_")):
                values[column] = [1]
            else:
                values[column] = [1.0]
        return pd.DataFrame(values)

    frames = {module: source_frame(module) for module in modules}
    def read_sql(query, _engine, chunksize=None):
        assert chunksize == 50_000
        module = next(module for module in sorted(modules, key=len, reverse=True) if module in query)
        return iter([frames[module]])

    marked = []
    def mark_ready(name, path):
        marked.append((name, path))
        cache._ON_DEMAND_GLOBAL_CACHE_READY.add(name)

    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)
    monkeypatch.setattr(cache.pd, "read_sql", read_sql)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", mark_ready)
    progress = []
    cache._sync_analise_gtin_inconsistencia_clinica(FakeEngine(), progress.append)
    cache._sync_analise_gtin_inconsistencia_clinica_municipio(FakeEngine(), progress.append)
    cache._sync_analise_gtin_inconsistencia_clinica_regiao(FakeEngine(), progress.append)

    assert progress == [100, 100, 100]
    assert [name for name, _ in marked] == list(modules)
    for module, path in paths.items():
        frame = pl.read_parquet(path)
        assert cache._ON_DEMAND_GLOBAL_CACHE_READY.__contains__(module)
        assert frame.height == 1
        assert "ano_base" in frame.columns
        assert frame["ano_base"].to_list() == [2024]


def test_crm_timeline_dia_sync_builds_month_parts_manifest_and_global_parquet(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_path = cache_dir / "timeline-dia.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, "_CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH", str(final_path))

    class Bounds:
        def mappings(self):
            return self

        def first(self):
            return {"dt_min": date(2024, 12, 15), "dt_max": date(2024, 12, 31)}

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Bounds()

    class Engine:
        def connect(self):
            return Connection()

    schema = cache._GLOBAL_PARQUET_SCHEMAS["crm_timeline_dia_global"]
    source = {}
    for column, dtype in schema.items():
        if dtype == pl.Utf8:
            source[column] = ["2024-12-15" if column == "dt_janela" else "sample"]
        elif dtype == pl.Float64:
            source[column] = [2.5]
        elif dtype == pl.Int32:
            source[column] = [123]
        else:
            source[column] = [1]
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pd.DataFrame(source))
    marked = []
    def mark_ready(name, path):
        marked.append((name, path))
        cache._ON_DEMAND_GLOBAL_CACHE_READY.add(name)

    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", mark_ready)
    progress = []
    cache._sync_crm_timeline_dia_global(Engine(), progress.append)

    result = pl.read_parquet(final_path)
    manifest_path = cache_dir / ".parts" / "crm_timeline_dia_global" / "manifest.json"
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    assert result.height == 1
    assert result.columns == list(schema)
    assert manifest["status"] == "done"
    assert manifest["final_rows"] == 1
    assert manifest["parts"]["2024-12"]["status"] == "done"
    assert progress == [90, 100]
    assert marked == [("crm_timeline_dia_global", str(final_path))]

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pd.DataFrame())
    empty_progress = []
    cache._sync_crm_timeline_dia_global(Engine(), empty_progress.append)
    empty_result = pl.read_parquet(final_path)
    assert empty_result.height == 0
    assert dict(empty_result.schema) == schema
    assert empty_progress == [90, 100]


def test_crm_timeline_dia_resume_skips_done_part_and_rejects_invalid_manifest(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    parts_dir = cache_dir / ".parts" / "crm_timeline_dia_global"
    parts_dir.mkdir(parents=True)
    final_path = cache_dir / "timeline-dia.parquet"
    part_path = parts_dir / "2024-01.smod.part"
    schema = cache._GLOBAL_PARQUET_SCHEMAS["crm_timeline_dia_global"]
    part = pl.DataFrame(schema=schema)
    part_path.write_bytes(b"placeholder")
    part.write_parquet(part_path)
    manifest_path = parts_dir / "manifest.json"
    manifest_path.write_text(__import__("json").dumps({
        "cache_key": "crm_timeline_dia_global", "start_month": "2024-01", "end_month": "2024-01",
        "status": "running", "parts": {"2024-01": {"status": "done", "rows": 0, "file": part_path.name}},
    }), encoding="utf-8")
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, "_CRM_TIMELINE_DIA_GLOBAL_PARQUET_PATH", str(final_path))

    class Bounds:
        def mappings(self):
            return self

        def first(self):
            return {"dt_min": date(2024, 1, 15), "dt_max": date(2024, 1, 31)}

    class Connection(FakeConnection):
        def execute(self, *_args, **_kwargs):
            return Bounds()

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pytest.fail("completed month must be reused"))
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    cache._sync_crm_timeline_dia_global(Engine(), progress.append)
    assert pl.read_parquet(final_path).height == 0
    assert progress == [90, 100]
    assert __import__("json").loads(manifest_path.read_text(encoding="utf-8"))["status"] == "done"

    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")

    def remove_verified_month(_progress):
        part_path.unlink(missing_ok=True)

    with pytest.raises(
        RuntimeError,
        match="Partes pendentes para consolidar crm_timeline_dia_global: 2024-01.smod.part",
    ):
        cache._sync_crm_timeline_dia_global(Engine(), remove_verified_month)

    manifest_path.write_text(__import__("json").dumps({
        "cache_key": "crm_timeline_dia_global", "start_month": "2024-01", "end_month": "2024-01",
        "status": "running", "parts": [],
    }), encoding="utf-8")
    with pytest.raises(RuntimeError, match="campo parts invalido"):
        cache._sync_crm_timeline_dia_global(Engine())

    class EmptyBounds(Bounds):
        def first(self):
            return {"dt_min": None, "dt_max": None}

    class EmptyEngine:
        def connect(self):
            class EmptyConnection(Connection):
                def execute(self, *_args, **_kwargs):
                    return EmptyBounds()
            return EmptyConnection()

    with pytest.raises(RuntimeError, match="nao possui periodos"):
        cache._sync_crm_timeline_dia_global(EmptyEngine())


def test_global_crm_simple_sync_wrappers_apply_registered_schemas(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    wrappers = [
        ("_sync_geografico_global", "geografico_global", "_GEOGRAFICO_GLOBAL_PARQUET_PATH", None),
        ("_sync_crm_concentracao_unico_alertas_global", "crm_concentracao_unico_alertas_global", "_CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET_PATH", {"_crm_alerts_cache_version": 4}),
        ("_sync_crm_concentracao_multiplo_alertas_global", "crm_concentracao_multiplo_alertas_global", "_CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET_PATH", {"_crm_alerts_cache_version": 4}),
        ("_sync_crm_timeline_hora_global", "crm_timeline_hora_global", "_CRM_TIMELINE_HORA_GLOBAL_PARQUET_PATH", None),
        ("_sync_crm_timeline_eventos_global", "crm_timeline_eventos_global", "_CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET_PATH", None),
    ]
    ready = []
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda name, path: ready.append((name, path)))

    def dataframe_for(name, extra):
        values = {}
        for column, dtype in cache._GLOBAL_PARQUET_SCHEMAS[name].items():
            if extra and column in extra:
                continue
            if dtype == pl.Utf8:
                values[column] = ["2024-01-15" if column.startswith("dt_") else "value"]
            elif dtype == pl.Datetime:
                values[column] = [pd.Timestamp("2024-01-15 10:00")]
            elif dtype == pl.Float64:
                values[column] = [1.5]
            else:
                values[column] = [1]
        return pd.DataFrame(values)

    sources = []
    paths = {}
    for index, (function_name, name, path_name, extra) in enumerate(wrappers):
        path = tmp_path / f"{index}-{name}.parquet"
        paths[name] = path
        monkeypatch.setattr(cache, path_name, str(path))
        sources.append(dataframe_for(name, extra))

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: sources.pop(0))
    progress = []
    for function_name, _name, _path_name, _extra in wrappers:
        getattr(cache, function_name)(FakeEngine(), progress.append)

    assert len(ready) == len(wrappers)
    assert progress == [100] * len(wrappers)
    assert sources == []
    for _function_name, name, _path_name, _extra in wrappers:
        saved = pl.read_parquet(paths[name])
        assert saved.height == 1
        assert dict(saved.schema) == cache._GLOBAL_PARQUET_SCHEMAS[name]


def test_simple_sync_without_registered_schema_writes_extra_fields_and_propagates_source_error(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    path = tmp_path / "unregistered.parquet"
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pd.DataFrame({"payload": ["x"]}))
    progress = []
    cache._load_or_sync_global_cache_simple(
        "unregistered", str(path), "SELECT payload", FakeEngine(), progress.append,
        extra_columns={"batch": 2026},
    )
    assert pl.read_parquet(path).to_dicts() == [{"payload": "x", "batch": 2026}]
    assert progress == [100]

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("database offline")))
    with pytest.raises(OSError, match="database offline"):
        cache._load_or_sync_global_cache_simple(
            "unregistered", str(path), "SELECT payload", FakeEngine()
        )



def test_empty_dataframe_factories_and_module_status_are_typed():
    dados_par = data_cache._empty_dados_par_df()
    alvos = data_cache._empty_par_teia_alvos_df()

    assert dados_par.schema["cnpj"] == pl.Utf8
    assert dados_par.schema["is_par"] == pl.Boolean
    assert alvos.schema["has_par_qualquer"] == pl.Boolean
    assert alvos.schema["qtd_empresas_par_n4"] == pl.Int32
    assert data_cache._get_cache_module_status(loaded=True, exists=False) == "loaded"
    assert data_cache._get_cache_module_status(loaded=False, exists=True) == "error"
    assert data_cache._get_cache_module_status(loaded=False, exists=False) == "missing"


def test_global_dataframe_getters_return_loaded_frames_and_fail_when_missing(monkeypatch):
    getters = {
        "get_df": "_df_movimentacao",
        "get_rede_df": "_df_rede",
        "get_localidades_df": "_df_localidades",
        "get_df_matriz_risco": "_df_matriz_risco",
        "get_df_bench_crm_regiao": "_df_bench_crm_regiao",
        "get_df_bench_crm_br": "_df_bench_crm_br",
        "get_df_dados_farmacia": "_df_dados_farmacia",
        "get_df_dados_farmacia_cnaes_secundarios": "_df_dados_farmacia_cnaes_secundarios",
        "get_df_perfil_estabelecimento": "_df_perfil_estabelecimento",
        "get_df_dados_socios": "_df_dados_socios",
        "get_df_dados_ibge_demografia": "_df_dados_ibge_demografia",
        "get_df_volume_atipico_semestral": "_df_volume_atipico_semestral",
        "get_df_sentinela_metadados_base": "_df_sentinela_metadados_base",
        "get_df_falecidos": "_df_falecidos",
        "get_df_dados_par": "_df_dados_par",
        "get_df_par_teia_alvos": "_df_par_teia_alvos",
    }
    expected = pl.DataFrame({"id": [1]})
    for function_name, state_name in getters.items():
        getter = getattr(data_cache, function_name)
        monkeypatch.setattr(data_cache, state_name, None)
        with pytest.raises(RuntimeError):
            getter()
        monkeypatch.setattr(data_cache, state_name, expected)
        assert getter() is expected


def test_on_demand_scan_wrappers_use_the_registered_module_and_path(monkeypatch):
    calls = []
    result = pl.DataFrame({"id": [1]}).lazy()

    def scan(name, path):
        calls.append((name, path))
        return result

    monkeypatch.setattr(data_cache, "_scan_on_demand_global_parquet", scan)
    wrappers = [
        name for name, value in vars(data_cache).items()
        if name.startswith("scan_") and callable(value)
    ]
    assert wrappers
    for name in wrappers:
        assert getattr(data_cache, name)() is result
    assert len(calls) == len(wrappers)
    assert all(module and path for module, path in calls)


def test_lazy_doctor_catalog_cache_reuses_signature_then_reloads(monkeypatch):
    monkeypatch.setattr(data_cache, "_DADOS_MEDICO_MEMORIA", None)
    signatures = [("dados_medico", 1, 10), ("dados_medico", 2, 20)]
    monkeypatch.setattr(data_cache, "get_global_cache_signature", lambda _name: signatures[0])
    first = pl.DataFrame({"id_medico": ["A"]})
    second = pl.DataFrame({"id_medico": ["B"]})
    scans = []

    def scan():
        return scans.pop(0).lazy()

    scans.extend([first, second])
    monkeypatch.setattr(data_cache, "scan_dados_medico", scan)
    assert data_cache.get_dados_medico_df().equals(first)
    assert data_cache.get_dados_medico_df().equals(first)
    signatures[0] = signatures[1]
    assert data_cache.get_dados_medico_df().equals(second)
    assert scans == []


def test_doctor_catalog_double_checks_cache_after_waiting_for_lock(monkeypatch):
    signature = ("dados_medico", 1, 10)
    expected = pl.DataFrame({"id_medico": ["A"]})
    monkeypatch.setattr(data_cache, "_DADOS_MEDICO_MEMORIA", None)
    monkeypatch.setattr(data_cache, "get_global_cache_signature", lambda _name: signature)

    class PublishingLock:
        def __enter__(self):
            data_cache._DADOS_MEDICO_MEMORIA = (signature, expected)
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(data_cache, "_DADOS_MEDICO_MEMORIA_LOCK", PublishingLock())
    monkeypatch.setattr(data_cache, "scan_dados_medico", lambda: pytest.fail("cache foi carregado por outra thread"))
    assert data_cache.get_dados_medico_df() is expected


def test_medicine_getter_uses_cached_data_then_file_and_reports_read_failures(monkeypatch, tmp_path):
    expected = pl.DataFrame({"gtin": ["1"]})
    monkeypatch.setattr(data_cache, "_df_medicamentos", expected)
    assert data_cache.get_medicamentos_df() is expected

    path = tmp_path / "medicamentos.parquet"
    expected.write_parquet(path)
    monkeypatch.setattr(data_cache, "_df_medicamentos", None)
    monkeypatch.setattr(data_cache, "_MEDICAMENTOS_PARQUET_PATH", str(path))
    assert data_cache.get_medicamentos_df().equals(expected)

    monkeypatch.setattr(data_cache, "_df_medicamentos", None)
    monkeypatch.setattr(data_cache.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(data_cache.pl, "read_parquet", lambda _path: (_ for _ in ()).throw(ValueError("corrupt")))
    with pytest.raises(RuntimeError, match="Cache de Medicamentos"):
        data_cache.get_medicamentos_df()


def test_par_caches_sync_nonempty_and_empty_results(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    dados_par_path = tmp_path / "dados-par.parquet"
    alvos_path = tmp_path / "par-alvos.parquet"
    monkeypatch.setattr(cache, "_DADOS_PAR_PARQUET_PATH", str(dados_par_path))
    monkeypatch.setattr(cache, "_PAR_TEIA_ALVOS_PARQUET_PATH", str(alvos_path))

    class Transaction(FakeConnection):
        def exec_driver_sql(self, _sql):
            return None

    class TransactionEngine:
        def begin(self):
            return Transaction()

    par_frame = pd.DataFrame({
        "cnpj": ["12345678000195"], "is_par": [True], "qtd_processos_par": [2],
        "par_situacoes": ["Em andamento"],
        "par_primeira_instauracao": [pd.Timestamp("2020-01-01")],
        "par_ultima_instauracao": [pd.Timestamp("2023-01-01")],
        "par_ultima_conclusao": [pd.Timestamp("2024-01-01")],
    })
    alvos_frame = pd.DataFrame({
        "cnpj": ["12345678000195"], "has_par_alvo": [True], "has_par_n2": [False],
        "has_par_n4": [True], "has_par_qualquer": [True], "qtd_par_alvo": [1],
        "qtd_empresas_par_n2": [0], "qtd_empresas_par_n4": [2],
        "qtd_empresas_par_qualquer": [3],
    })
    frames = iter([par_frame, alvos_frame])
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: next(frames))
    progress = []
    cache._sync_dados_par(object(), progress.append)
    cache._sync_par_teia_alvos(TransactionEngine(), progress.append)

    assert progress == [100, 100]
    assert pl.read_parquet(dados_par_path)["par_situacoes"].to_list() == ["Em andamento"]
    assert pl.read_parquet(alvos_path)["qtd_empresas_par_n4"].to_list() == [2]
    assert cache.get_df_dados_par().height == cache.get_df_par_teia_alvos().height == 1

    empty_reads = iter([pd.DataFrame(), pd.DataFrame()])
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: next(empty_reads))
    cache._sync_dados_par(object())
    cache._sync_par_teia_alvos(TransactionEngine())
    assert pl.read_parquet(dados_par_path).schema["cnpj"] == pl.String
    assert pl.read_parquet(alvos_path).schema["has_par_qualquer"] == pl.Boolean


@pytest.mark.parametrize(
    ("level", "path_attribute"),
    [
        ("nivel2", "_TEIA_FONTE_NIVEL2_PARQUET_PATH"),
        ("nivel3", "_TEIA_FONTE_NIVEL3_PARQUET_PATH"),
        ("nivel4", "_TEIA_FONTE_NIVEL4_PARQUET_PATH"),
    ],
)
def test_network_cache_levels_sync_nonempty_and_empty_sources(
    level, path_attribute, tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    path = tmp_path / f"{level}.parquet"
    monkeypatch.setattr(cache, path_attribute, str(path))
    module_name = f"teia_fonte_{level}"
    columns = cache._ON_DEMAND_GLOBAL_REQUIRED_COLUMNS[module_name]
    values = {}
    for column in columns:
        if column in {"data_entrada_sociedade", "data_exclusao_sociedade"}:
            values[column] = [pd.Timestamp("2020-01-01")]
        elif column.startswith("is_"):
            values[column] = [1]
        else:
            values[column] = ["12345678000195"]
    source = pd.DataFrame(values)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([source]))
    progress = []
    getattr(cache, f"_sync_{module_name}")(FakeEngine(row_count=1), progress.append)

    saved = pl.read_parquet(path)
    assert saved.height == 1
    assert progress == [100]
    assert saved["cpf_cnpj_socio" if level != "nivel3" else "cnpj_empresa"].len() == 1

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
    getattr(cache, f"_sync_{module_name}")(FakeEngine(row_count=0), progress.append)
    assert pl.read_parquet(path).height == 0
    assert progress[-1] == 100


def test_geographic_boot_metadata_cache_sync_uses_required_source_contract(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    path = tmp_path / "metadata.parquet"
    monkeypatch.setattr(cache, "_SENTINELA_METADADOS_BASE_PARQUET_PATH", str(path))
    required = {
        "nome_base", "nome_artefato", "fonte_origem", "dt_referencia_min",
        "dt_referencia_max", "competencia_min", "competencia_max", "qtd_registros",
        "qtd_chaves", "schema_versao", "dt_processamento_inicio",
        "dt_processamento_fim", "observacao",
    }

    class MetadataConnection(FakeConnection):
        def execute(self, query, params=None):
            sql = str(query)
            self.calls.append((sql, params))
            if "OBJECT_ID" in sql:
                return ScalarResult(1)
            if "COUNT_BIG" in sql:
                return ScalarResult(1)
            return ColumnResult([(column,) for column in required])

    class MetadataEngine:
        def connect(self):
            return MetadataConnection()

    source = pd.DataFrame({
        "nome_base": ["base"], "nome_artefato": ["parquet"], "fonte_origem": ["SQL"],
        "dt_referencia_min": [pd.Timestamp("2024-01-01")],
        "dt_referencia_max": [pd.Timestamp("2024-12-31")], "competencia_min": [202401],
        "competencia_max": [202412], "qtd_registros": [10], "qtd_chaves": [8],
        "schema_versao": [1], "dt_processamento_inicio": [pd.Timestamp("2025-01-01")],
        "dt_processamento_fim": [pd.Timestamp("2025-01-02")], "observacao": ["ok"],
    })
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: source)
    progress = []
    cache._sync_sentinela_metadados_base(MetadataEngine(), progress.append)

    result = pl.read_parquet(path)
    assert result["nome_base"].to_list() == ["base"]
    assert result["qtd_registros"].to_list() == [10]
    assert cache.get_df_sentinela_metadados_base().height == 1
    assert progress == [100]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("missing-table", "nao encontrada"),
        ("empty-table", "esta vazia"),
        ("missing-columns", "sem colunas obrigatorias"),
    ],
)
def test_metadata_sync_rejects_missing_empty_or_incomplete_source(mode, expected, isolated_cache_state):
    cache = isolated_cache_state
    required = {
        "nome_base", "nome_artefato", "fonte_origem", "dt_referencia_min",
        "dt_referencia_max", "competencia_min", "competencia_max", "qtd_registros",
        "qtd_chaves", "schema_versao", "dt_processamento_inicio",
        "dt_processamento_fim", "observacao",
    }

    class MetadataConnection(FakeConnection):
        def execute(self, query, params=None):
            sql = str(query)
            if "OBJECT_ID" in sql:
                return ScalarResult(None if mode == "missing-table" else 1)
            if "COUNT_BIG" in sql:
                return ScalarResult(0 if mode == "empty-table" else 1)
            columns = required if mode != "missing-columns" else {"nome_base"}
            return ColumnResult([(column,) for column in columns])

    class MetadataEngine:
        def connect(self):
            return MetadataConnection()

    with pytest.raises(RuntimeError, match=expected):
        cache._sync_sentinela_metadados_base(MetadataEngine())


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("missing-table", "nao encontrada"),
        ("empty-table", "esta vazia"),
        ("missing-columns", "sem colunas obrigatorias"),
    ],
)
def test_esocial_sync_rejects_missing_empty_or_incomplete_source(mode, expected, isolated_cache_state):
    cache = isolated_cache_state

    class EsocialConnection(FakeConnection):
        def execute(self, query, params=None):
            sql = str(query)
            if "OBJECT_ID" in sql:
                return ScalarResult(None if mode == "missing-table" else 1)
            if "COUNT_BIG" in sql:
                return ScalarResult(0 if mode == "empty-table" else 1)
            columns = () if mode == "missing-columns" else ()
            return ColumnResult([(column,) for column in columns])

    class EsocialEngine:
        def connect(self):
            return EsocialConnection()

    with pytest.raises(RuntimeError, match=expected):
        cache._sync_esocial(EsocialEngine())


def test_pharmacy_cache_sync_casts_columns_and_maps_progress_to_secondary_cache(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    primary_path = tmp_path / "farmacias.parquet"
    cnae_path = tmp_path / "cnaes.parquet"
    monkeypatch.setattr(cache, "_DADOS_FARMACIA_PARQUET_PATH", str(primary_path))
    monkeypatch.setattr(cache, "_DADOS_FARMACIA_CNAES_SECUNDARIOS_PARQUET_PATH", str(cnae_path))
    source = pd.DataFrame({
        "id_cnpj": [7], "cnpj": ["12345678000195"], "is_matriz": ["M"],
        "razao_social": ["Farmacia Exemplo"], "nome_fantasia": ["Loja"],
        "tipo_logradouro": ["Rua"], "logradouro": ["A"], "numero": ["1"],
        "complemento": [""], "bairro": ["Centro"], "cep": ["01000000"],
        "latitude": [-23.5], "longitude": [-46.6], "id_ibge7": [3509502],
        "id_cnae_principal": ["4771701"], "cnae_principal": ["Farmacia"],
        "is_cnae_farmacia_ausente": [0], "data_abertura": [pd.Timestamp("2000-01-01")],
        "data_processamento": [pd.Timestamp("2025-01-01")], "natureza_juridica": ["2062"],
        "capital_social": [1000.0], "telefone_1": ["11999999999"],
        "telefone_2": [None], "email": ["exemplo@example.com"],
        "situacao_rf": ["ATIVA"], "porte_empresa": ["ME"], "uf": ["SP"],
        "municipio": ["Campinas"],
    })
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([source]))
    secondary_callbacks = []

    def sync_secondary(engine, callback):
        secondary_callbacks.append(engine)
        callback(50)
        callback(100)

    monkeypatch.setattr(cache, "_sync_dados_farmacia_cnaes_secundarios", sync_secondary)
    progress = []
    cache._sync_dados_farmacia(FakeEngine(row_count=1), progress.append)

    result = pl.read_parquet(primary_path)
    assert result["id_cnpj"].dtype == pl.Int32
    assert result["id_cnae_principal"].dtype == pl.String
    assert result["is_matriz"].to_list() == [True]
    assert result["cnpj"].to_list() == ["12345678000195"]
    assert progress == [85, 92, 100]
    assert len(secondary_callbacks) == 1
    assert cache.get_df_dados_farmacia().equals(result)


def test_secondary_cnae_cache_handles_rows_and_empty_source(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    path = tmp_path / "cnaes.parquet"
    monkeypatch.setattr(cache, "_DADOS_FARMACIA_CNAES_SECUNDARIOS_PARQUET_PATH", str(path))
    source = pd.DataFrame({
        "id_cnpj": [2, 1], "id_cnae": [4771701, 4771702], "descricao": ["B", "A"],
    })
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([source]))
    progress = []
    cache._sync_dados_farmacia_cnaes_secundarios(FakeEngine(row_count=2), progress.append)
    result = pl.read_parquet(path)
    assert result.select("id_cnpj", "id_cnae").rows() == [(1, 4771702), (2, 4771701)]
    assert result["descricao"].dtype == pl.Categorical
    assert progress == [100, 100]

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
    cache._sync_dados_farmacia_cnaes_secundarios(FakeEngine(row_count=0))
    empty = pl.read_parquet(path)
    assert empty.height == 0
    assert empty.schema["id_cnae"] == pl.Int32
    assert empty.schema["descricao"] == pl.Categorical


def test_establishment_profile_cache_deduplicates_and_rejects_incomplete_contract(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    path = tmp_path / "perfil.parquet"
    monkeypatch.setattr(cache, "_PERFIL_ESTABELECIMENTO_PARQUET_PATH", str(path))
    frame = pd.DataFrame({
        "id_cnpj": [2, 2], "cnpj": ["12345678000195"] * 2, "uf": ["SP"] * 2,
        "id_regiao_saude": [123] * 2, "id_ibge7": [3509502] * 2,
        "no_municipio": ["Campinas"] * 2, "razao_social": ["Exemplo"] * 2,
        "situacao_rf": ["ATIVA"] * 2, "is_conexao_ativa": [True] * 2,
        "porte_empresa": ["ME"] * 2, "is_grande_rede": [False] * 2,
        "qtd_estabelecimentos_rede": [1] * 2, "is_matriz": [True] * 2,
        "unidade_pf": ["Unidade"] * 2, "is_cnae_incompativel_farmaceutico": [False] * 2,
        "has_cadunico_direto": [False] * 2, "has_cadunico_n3": [False] * 2,
        "qtd_cadunico_direto": [0] * 2, "qtd_cadunico_n3": [0] * 2,
        "has_seguro_defeso_direto": [False] * 2, "has_seguro_defeso_n3": [False] * 2,
        "qtd_seguro_defeso_direto": [0] * 2, "qtd_seguro_defeso_n3": [0] * 2,
        "has_esocial_direto": [False] * 2, "has_esocial_n3": [False] * 2,
        "qtd_esocial_direto": [0] * 2, "qtd_esocial_n3": [0] * 2,
    })
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 2)
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([frame]))
    progress = []
    cache._sync_perfil_estabelecimento(FakeEngine(row_count=2), progress.append)
    result = pl.read_parquet(path)
    assert result.height == 1
    assert result["id_regiao_saude"].to_list() == ["123"]
    assert result["is_cnae_incompativel_farmaceutico"].to_list() == [False]
    assert progress == [100]
    assert cache.get_df_perfil_estabelecimento().equals(result)

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
    with pytest.raises(RuntimeError, match="nao retornou registros"):
        cache._sync_perfil_estabelecimento(FakeEngine(row_count=2))

    invalid = frame.iloc[[0]].copy()
    invalid["has_esocial_n3"] = None
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([invalid]))
    with pytest.raises(RuntimeError, match="alertas societarios nulos: has_esocial_n3"):
        cache._sync_perfil_estabelecimento(FakeEngine(row_count=1))

    valid_single = frame.iloc[[0]].copy()
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([valid_single]))
    with pytest.raises(RuntimeError, match="nao cobre todas as farmacias"):
        cache._sync_perfil_estabelecimento(FakeEngine(row_count=2))


def test_partner_cache_casts_person_attributes_dates_and_alert_flags(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    path = tmp_path / "socios.parquet"
    monkeypatch.setattr(cache, "_DADOS_SOCIOS_PARQUET_PATH", str(path))
    columns = {
        "cnpj": ["12345678000195"], "cpf_cnpj_socio": ["12345678901"],
        "nome_socio": ["Pessoa Exemplo"], "indicador_socio": ["PESSOA FISICA"],
        "municipio": ["Campinas"], "uf": ["SP"],
        "data_entrada_sociedade": [pd.Timestamp("2020-01-01")],
        "data_exclusao_sociedade": [pd.NaT], "percentual_qualificacao": [50.0],
        "descricao_qualificacao": ["SOCIO"], "cpf_representante": ["98765432100"],
        "id_qualificacao_representante": [10], "nome_representante": ["Representante"],
        "descricao_qualificacao_representante": ["REPRESENTANTE"],
        "data_nascimento_socio": [pd.Timestamp("1980-01-01")],
        "data_nascimento_representante": [pd.Timestamp("1970-01-01")],
        "data_processamento": [pd.Timestamp("2025-01-01")], "is_cadunico": [0],
        "is_esocial": [1], "is_seguro_defeso": [0], "is_falecido": [0],
    }
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([pd.DataFrame(columns)]))
    progress = []
    cache._sync_dados_socios(FakeEngine(row_count=1), progress.append)

    result = pl.read_parquet(path)
    assert result["cnpj"].dtype == pl.String
    assert result["municipio"].dtype == pl.Categorical
    assert result["data_entrada_sociedade"].to_list() == [date(2020, 1, 1)]
    assert result["is_esocial"].to_list() == [1]
    assert cache.get_df_dados_socios().equals(result)
    assert progress == [100]


def test_crm_prescriber_global_sync_writes_typed_parts_and_consolidates(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_path = cache_dir / "crm-prescritores.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, "_CRM_PRESCRITORES_GLOBAL_PARQUET_PATH", str(final_path))

    class Competencies:
        def fetchall(self):
            return [(202401,), (202402,)]

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Competencies()

    class Engine:
        def connect(self):
            return Connection()

    base = {
        "id_cnpj": 7, "id_medico": "CRM-SP-123", "competencia": 202401,
        "vl_total_prescricoes": 250.5, "nu_prescricoes_mes": 10,
        "nu_prescricoes_total_brasil": 100, "flag_crm_invalido": 0,
        "flag_prescricao_antes_registro": 0, "alerta_concentracao_multiplos_crms": 1,
        "flag_concentracao_mesmo_crm": 0, "flag_distancia_geografica": 1,
        "dt_inscricao_crm": pd.Timestamp("2010-01-01"), "nu_estabelecimentos": 2,
    }
    def read_part(_query, _conn, params):
        row = dict(base)
        row["competencia"] = params["competencia"]
        return pd.DataFrame([row])

    monkeypatch.setattr(cache.pd, "read_sql", read_part)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    cache._sync_crm_prescritores_global(Engine(), progress.append)

    import json
    manifest_path = cache_dir / ".parts" / "crm_prescritores_global" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = pl.read_parquet(final_path)
    assert result.select("competencia", "id_cnpj").rows() == [(202401, 7), (202402, 7)]
    assert result.schema == cache._GLOBAL_PARQUET_SCHEMAS["crm_prescritores_global"]
    assert manifest["status"] == "done"
    assert manifest["final_rows"] == 2
    assert progress == [45, 90, 100]

    manifest["status"] = "running"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pytest.fail("partes concluidas nao devem ser consultadas novamente"),
    )
    resume_progress = []
    cache._sync_crm_prescritores_global(Engine(), resume_progress.append)
    assert resume_progress == [45, 90, 100]

    class NoCompetencies:
        def fetchall(self):
            return []

    class EmptySourceConnection(Connection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return NoCompetencies()

    class EmptySourceEngine:
        def connect(self):
            return EmptySourceConnection()

    with pytest.raises(RuntimeError, match="nao possui competencias"):
        cache._sync_crm_prescritores_global(EmptySourceEngine())

    manifest["status"] = "running"
    manifest["parts"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="campo parts invalido"):
        cache._sync_crm_prescritores_global(Engine())

    manifest["status"] = "done"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pd.DataFrame(columns=base))
    cache._sync_crm_prescritores_global(Engine())
    empty_result = pl.read_parquet(final_path)
    assert empty_result.height == 0
    assert dict(empty_result.schema) == cache._GLOBAL_PARQUET_SCHEMAS["crm_prescritores_global"]

    part_paths = sorted(manifest_path.parent.glob("*.smod.part"))
    for part_path in part_paths:
        part_path.unlink()
    original_replace = cache.os.replace

    def replace_then_drop_part(source, destination):
        original_replace(source, destination)
        destination_path = Path(destination)
        if destination_path.suffixes[-2:] == [".smod", ".part"]:
            destination_path.unlink(missing_ok=True)

    with monkeypatch.context() as race:
        race.setattr(cache.os, "replace", replace_then_drop_part)
        with pytest.raises(RuntimeError, match="Partes pendentes para consolidar crm_prescritores_global"):
            cache._sync_crm_prescritores_global(Engine())


def test_memory_calculation_sync_normalizes_payload_types_and_rejects_empty_source(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_path = cache_dir / "memoria.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, "_MEMORIA_CALCULO_GLOBAL_PARQUET_PATH", str(final_path))

    class Prefixes:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Connection(FakeConnection):
        def __init__(self, rows):
            super().__init__()
            self.rows = rows

        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Prefixes(self.rows)

    class Engine:
        def __init__(self, rows):
            self.rows = rows

        def connect(self):
            return Connection(self.rows)

    payloads = {
        "01": bytearray(b"one"), "12": memoryview(b"twelve"), "99": None,
        "04": b"four", "05": [65, 66],
    }
    def read_prefix(_query, _conn, params):
        prefix = params["prefixo"]
        return pd.DataFrame({
            "cnpj": [prefix + "3456789012"], "id_processamento": [10],
            "schema_version": [2], "memoria_calculo_payload": [payloads[prefix]],
        })

    monkeypatch.setattr(cache.pd, "read_sql", read_prefix)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    cache._sync_memoria_calculo_global(
        Engine([("1",), ("12",), ("99",), ("4",), ("5",)]), progress.append
    )

    import json
    manifest_path = cache_dir / ".parts" / "memoria_calculo_global" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = pl.read_parquet(final_path)
    assert result["cnpj"].to_list() == [
        "013456789012", "123456789012", "993456789012", "043456789012", "053456789012",
    ]
    assert result["memoria_calculo_payload"].to_list() == [b"one", b"twelve", None, b"four", b"AB"]
    assert result.schema == cache._GLOBAL_PARQUET_SCHEMAS["memoria_calculo_global"]
    assert manifest["status"] == "done"
    assert progress == [18, 36, 54, 72, 90, 100]

    manifest["status"] = "running"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pytest.fail("prefixos concluidos nao devem ser consultados novamente"),
    )
    resume_progress = []
    cache._sync_memoria_calculo_global(
        Engine([("1",), ("12",), ("99",), ("4",), ("5",)]), resume_progress.append
    )
    assert resume_progress == [18, 36, 54, 72, 90, 100]

    manifest["status"] = "running"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    part_removed_during_resume = cache_dir / ".parts" / "memoria_calculo_global" / "01.smod.part"

    def remove_verified_part(_progress):
        part_removed_during_resume.unlink(missing_ok=True)

    with pytest.raises(
        RuntimeError,
        match="Partes pendentes para consolidar memoria_calculo_global: 01.smod.part",
    ):
        cache._sync_memoria_calculo_global(
            Engine([("1",), ("12",), ("99",), ("4",), ("5",)]),
            remove_verified_part,
        )

    manifest["status"] = "done"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pd.DataFrame())
    cache._sync_memoria_calculo_global(Engine([("77",)]))
    empty_result = pl.read_parquet(final_path)
    assert empty_result.is_empty()
    assert empty_result.schema == cache._GLOBAL_PARQUET_SCHEMAS["memoria_calculo_global"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest["parts"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="campo parts invalido"):
        cache._sync_memoria_calculo_global(Engine([("77",)]))

    with pytest.raises(RuntimeError, match="nao possui dados"):
        cache._sync_memoria_calculo_global(Engine([]))


@pytest.mark.parametrize(
    ("sync_name", "cache_key", "path_attribute"),
    [
        ("_sync_crm_raiox_tx_global", "crm_raiox_tx_global", "_CRM_RAIOX_TX_GLOBAL_PARQUET_PATH"),
        (
            "_sync_pagamentos_consolidados_farmacia_popular",
            "pagamentos_consolidados_farmacia_popular",
            "_PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH",
        ),
        (
            "_sync_movimentacao_mensal_gtin_global",
            "movimentacao_mensal_gtin_global",
            "_MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH",
        ),
    ],
)
def test_monthly_global_parquet_syncs_create_manifest_and_consolidated_rows(
    sync_name, cache_key, path_attribute, tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_path = cache_dir / f"{cache_key}.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, path_attribute, str(final_path))

    class Bounds:
        def mappings(self):
            return self

        def first(self):
            return {"dt_min": date(2024, 12, 15), "dt_max": date(2024, 12, 31)}

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Bounds()

    class Engine:
        def connect(self):
            return Connection()

    frames = {
        "crm_raiox_tx_global": pd.DataFrame({
            "id_cnpj": [9], "dt_janela": [pd.Timestamp("2024-12-15")],
            "hr_janela": [10], "data_hora": [pd.Timestamp("2024-12-15 10:30")],
            "num_autorizacao": ["A1"], "id_medico": ["CRM-SP-1"], "valor_pago": [75.5],
        }),
        "pagamentos_consolidados_farmacia_popular": pd.DataFrame({
            "id_cnpj": [9], "data_pagamento": [pd.Timestamp("2024-12-15")],
            "programa_acao": ["PFPB"], "numero_ordem_bancaria": ["OB1"],
            "valor_pago": [75.5],
        }),
        "movimentacao_mensal_gtin_global": pd.DataFrame({
            "id_cnpj": [9], "codigo_barra": ["789"], "periodo": [pd.Timestamp("2024-12-01")],
            "qnt_caixas_vendidas": [4], "qnt_caixas_sem_comprovacao": [1],
            "num_autorizacoes": [3], "valor_vendas": [100.0],
            "valor_sem_comprovacao": [25.0],
        }),
    }
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: frames[cache_key])
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    getattr(cache, sync_name)(Engine(), progress.append)

    result = pl.read_parquet(final_path)
    expected_schema = cache._GLOBAL_PARQUET_SCHEMAS[cache_key]
    assert dict(result.schema) == expected_schema
    assert result.height == 1
    manifest_path = cache_dir / ".parts" / cache_key / "manifest.json"
    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "done"
    assert manifest["final_rows"] == 1
    assert progress == [90, 100]

    schema = cache._GLOBAL_PARQUET_SCHEMAS[cache_key]
    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pd.DataFrame(columns=list(schema)),
    )
    empty_progress = []
    getattr(cache, sync_name)(Engine(), empty_progress.append)
    empty_result = pl.read_parquet(final_path)
    assert empty_result.height == 0
    assert dict(empty_result.schema) == schema
    assert empty_progress == [90, 100]

    parts_dir = cache_dir / ".parts" / cache_key
    manifest_path = parts_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest["parts"]["2024-12"]["status"] = "done"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pytest.fail("parte pronta nao deve consultar a fonte"),
    )
    resume_progress = []
    getattr(cache, sync_name)(Engine(), resume_progress.append)
    assert resume_progress == [90, 100]

    if cache_key in {"crm_raiox_tx_global", "pagamentos_consolidados_farmacia_popular"}:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        resumed_part = parts_dir / "2024-12.smod.part"

        def remove_verified_month(_progress):
            resumed_part.unlink(missing_ok=True)

        with pytest.raises(
            RuntimeError,
            match=f"Partes pendentes para consolidar {cache_key}: 2024-12.smod.part",
        ):
            getattr(cache, sync_name)(Engine(), remove_verified_month)

    manifest["parts"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="campo parts invalido"):
        getattr(cache, sync_name)(Engine())

    class EmptyBounds(Bounds):
        def first(self):
            return {"dt_min": None, "dt_max": None}

    class EmptyConnection(Connection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return EmptyBounds()

    class EmptyEngine:
        def connect(self):
            return EmptyConnection()

    with pytest.raises(RuntimeError, match="nao possui periodos"):
        getattr(cache, sync_name)(EmptyEngine())

    if cache_key == "movimentacao_mensal_gtin_global":
        manifest_path = parts_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        manifest["parts"] = {
            "2024-12": {"status": "done", "rows": 1, "file": "2024-12.smod.part"}
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        part_path = parts_dir / "2024-12.smod.part"
        part_path.write_bytes(b"not a parquet file")
        monkeypatch.setattr(
            cache.pd,
            "read_sql",
            lambda *_args, **_kwargs: frames[cache_key],
        )
        getattr(cache, sync_name)(Engine())
        assert pl.read_parquet(part_path).height == 1

        part_path.unlink()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        manifest["parts"]["2024-12"]["status"] = "done"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: frames[cache_key])
        getattr(cache, sync_name)(Engine())
        assert part_path.exists() and pl.read_parquet(part_path).height == 1

        original_replace = cache.os.replace

        def replace_then_drop_part(source, destination):
            original_replace(source, destination)
            if Path(destination) == part_path:
                part_path.unlink(missing_ok=True)

        with monkeypatch.context() as race:
            race.setattr(cache.os, "replace", replace_then_drop_part)
            with pytest.raises(RuntimeError, match="Partes pendentes ou invalidas para consolidar"):
                getattr(cache, sync_name)(Engine())


@pytest.mark.parametrize(
    ("sync_name", "cache_key", "path_attribute"),
    [
        ("_sync_crm_raiox_tx_global", "crm_raiox_tx_global", "_CRM_RAIOX_TX_GLOBAL_PARQUET_PATH"),
        (
            "_sync_pagamentos_consolidados_farmacia_popular",
            "pagamentos_consolidados_farmacia_popular",
            "_PAGAMENTOS_CONSOLIDADOS_FARMACIA_POPULAR_PARQUET_PATH",
        ),
        (
            "_sync_movimentacao_mensal_gtin_global",
            "movimentacao_mensal_gtin_global",
            "_MOVIMENTACAO_MENSAL_GTIN_GLOBAL_PARQUET_PATH",
        ),
    ],
)
def test_monthly_global_parquets_advance_through_non_december_months(
    sync_name, cache_key, path_attribute, tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_path = cache_dir / f"{cache_key}.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, path_attribute, str(final_path))

    class Bounds:
        def mappings(self):
            return self

        def first(self):
            return {"dt_min": date(2024, 1, 15), "dt_max": date(2024, 2, 28)}

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            return Bounds()

    class Engine:
        def connect(self):
            return Connection()

    schema = cache._GLOBAL_PARQUET_SCHEMAS[cache_key]
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pd.DataFrame(columns=list(schema)))
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []

    getattr(cache, sync_name)(Engine(), progress.append)

    parts = cache_dir / ".parts" / cache_key
    assert (parts / "2024-01.smod.part").exists()
    assert (parts / "2024-02.smod.part").exists()
    assert pl.read_parquet(final_path).is_empty()
    assert progress == [45, 90, 100]


def test_movimentacao_sync_casts_monthly_facts_and_rejects_unmapped_cnpj(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    path = tmp_path / "movimentacao.parquet"
    monkeypatch.setattr(cache, "_PARQUET_PATH", str(path))
    chunks = [
        pd.DataFrame({
            "id_cnpj": [2], "periodo": [pd.Timestamp("2024-02-01")],
            "total_vendas": [30.0], "total_sem_comprovacao": [5.0],
            "total_qnt_caixas_vendidas": [3],
            "total_qnt_caixas_sem_comprovacao": [1], "total_num_autorizacoes": [2],
        }),
        pd.DataFrame({
            "id_cnpj": [1], "periodo": [pd.Timestamp("2024-01-01")],
            "total_vendas": [20.0], "total_sem_comprovacao": [2.0],
            "total_qnt_caixas_vendidas": [2],
            "total_qnt_caixas_sem_comprovacao": [0], "total_num_autorizacoes": [1],
        }),
    ]

    class MovementConnection(FakeConnection):
        def execute(self, query, params=None):
            sql = str(query)
            self.calls.append((sql, params))
            if "COUNT(" in sql:
                return ScalarResult(2)
            return ScalarResult(None)

    class MovementEngine:
        def connect(self):
            return MovementConnection()

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter(chunks))
    progress = []
    cache._sync_movimentacao(MovementEngine(), progress.append)
    result = pl.read_parquet(path)
    assert result.select("id_cnpj", "periodo").rows() == [
        (1, date(2024, 1, 1)), (2, date(2024, 2, 1)),
    ]
    assert result["total_num_autorizacoes"].dtype == pl.Int64
    assert progress == [50, 100]
    assert cache.get_df().equals(result)

    class InvalidMovementConnection(MovementConnection):
        def execute(self, query, params=None):
            if "COUNT(" in str(query):
                return ScalarResult(2)
            return ScalarResult(1)

    class InvalidMovementEngine:
        def connect(self):
            return InvalidMovementConnection()

    with pytest.raises(RuntimeError, match="CNPJs sem id correspondente"):
        cache._sync_movimentacao(InvalidMovementEngine(), progress.append)


def test_esocial_sync_writes_all_four_typed_caches(tmp_path, monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    path_names = {
        "esocial_cnpj_ano": "_ESOCIAL_CNPJ_ANO_PARQUET_PATH",
        "esocial_cnpj_trabalhador_ano": "_ESOCIAL_CNPJ_TRABALHADOR_ANO_PARQUET_PATH",
        "esocial_cnpj_movimentacao_ano": "_ESOCIAL_CNPJ_MOVIMENTACAO_ANO_PARQUET_PATH",
        "esocial_cnpj_ultima_movimentacao": "_ESOCIAL_CNPJ_ULTIMA_MOVIMENTACAO_PARQUET_PATH",
    }
    paths = {}
    for key, attribute in path_names.items():
        path = tmp_path / f"{key}.parquet"
        paths[key] = path
        monkeypatch.setattr(cache, attribute, str(path))

    table_columns = set().union(*(cache._ON_DEMAND_GLOBAL_REQUIRED_COLUMNS[key] for key in path_names))

    class SourceConnection(FakeConnection):
        def execute(self, query, params=None):
            sql = str(query)
            self.calls.append((sql, params))
            if "OBJECT_ID" in sql:
                return ScalarResult(1)
            if "COUNT_BIG" in sql:
                return ScalarResult(1)
            return ColumnResult([(column,) for column in table_columns])

    class SourceEngine:
        def connect(self):
            return SourceConnection()

    date_columns = {
        "dt_admissao", "dt_rescisao", "dt_carga_fonte", "dt_processamento",
        "periodo_min", "periodo_max", "ultimo_periodo_movimentacao",
        "ultimo_mes_trabalhador_ativo",
    }
    text_columns = {
        "cpf_trabalhador", "matricula", "titulo_cbo", "uf", "escopo_referencia",
        "classificacao_mov_trabalhista", "motivo_classificacao",
        "classificacao_mov_sem_funcionario", "motivo_mov_sem_funcionario",
    }

    def frame_for(columns):
        values = {}
        for column in columns:
            if column in date_columns or column.startswith("dt_"):
                values[column] = [pd.Timestamp("2024-01-15 08:30")]
            elif column in text_columns:
                values[column] = ["sample"]
            elif column.startswith(("valor_", "p90_", "p95_", "autorizacoes_por_", "caixas_por_")):
                values[column] = [1.5]
            elif column.startswith(("has_", "is_")):
                values[column] = [True]
            else:
                values[column] = [1]
        return pd.DataFrame(values)

    sources = {
        key: frame_for(cache._ON_DEMAND_GLOBAL_REQUIRED_COLUMNS[key])
        for key in path_names
    }

    def read_source(query, _connection_or_engine, chunksize=None):
        sql = str(query)
        key = next(
            key for key in (
                "esocial_cnpj_trabalhador_ano",
                "esocial_cnpj_movimentacao_ano",
                "esocial_cnpj_ultima_movimentacao",
                "esocial_cnpj_ano",
            )
            if f"[{key}]" in sql
        )
        frame = sources[key]
        return iter([frame]) if chunksize is not None else frame

    marked = []
    def mark_ready(key, path):
        marked.append((key, path))

    monkeypatch.setattr(cache.pd, "read_sql", read_source)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", mark_ready)
    progress = []
    cache._sync_esocial(SourceEngine(), progress.append)

    assert [key for key, _path in marked] == [
        "esocial_cnpj_trabalhador_ano",
        "esocial_cnpj_ano",
        "esocial_cnpj_movimentacao_ano",
        "esocial_cnpj_ultima_movimentacao",
    ]
    assert progress == [50, 100]
    for key, path in paths.items():
        result = pl.read_parquet(path)
        assert cache._ON_DEMAND_GLOBAL_REQUIRED_COLUMNS[key].issubset(result.columns)
        assert result.height == 1


def test_crm_semester_and_doctor_dimension_syncs_cast_and_publish(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    semester_path = tmp_path / "crm-semester.parquet"
    doctor_path = tmp_path / "doctors.parquet"
    monkeypatch.setattr(cache, "_CRM_PRESCRICOES_BRASIL_SEMESTRE_PATH", str(semester_path))
    monkeypatch.setattr(cache, "_DADOS_MEDICO_PARQUET_PATH", str(doctor_path))
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)
    semester = pd.DataFrame({
        "id_medico": ["CRM-SP-1"], "chave_semestre": [202401],
        "nu_prescricoes_total_brasil": [30], "dias_ativos_brasil": [12],
    })
    doctors = pd.DataFrame({
        "id_medico": ["CRM-SP-1"], "nu_crm": [1], "sg_uf": ["SP"],
        "no_medico": ["Medico Exemplo"],
        "dt_primeira_inscricao_uf": [pd.Timestamp("2010-01-01")],
    })
    frames = iter([iter([semester]), iter([doctors])])
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: next(frames))
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    cache._sync_crm_prescricoes_brasil_semestre(FakeEngine(row_count=1), progress.append)
    cache._sync_dados_medico(FakeEngine(row_count=1), progress.append)

    assert pl.read_parquet(semester_path)["dias_ativos_brasil"].dtype == pl.Int16
    saved_doctors = pl.read_parquet(doctor_path)
    assert saved_doctors["nu_crm"].dtype == pl.Int64
    assert saved_doctors["dt_primeira_inscricao_uf"].to_list() == [date(2010, 1, 1)]
    assert progress == [100, 100]

    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
    with pytest.raises(RuntimeError, match="sem registros para sincronizacao"):
        cache._sync_crm_prescricoes_brasil_semestre(FakeEngine(row_count=1))
    with pytest.raises(RuntimeError, match="sem registros para sincronizacao"):
        cache._sync_dados_medico(FakeEngine(row_count=1))


def test_crm_medico_brasil_month_sync_writes_competence_part_and_manifest(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_path = cache_dir / "crm-medico-brasil-mes.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, "_CRM_MEDICO_BRASIL_MES_PATH", str(final_path))
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)

    class Competencies:
        def fetchall(self):
            return [(202401,)]

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Competencies()

    class Engine:
        def connect(self):
            return Connection()

    source = pd.DataFrame({
        "id_medico": ["CRM-SP-1"], "competencia": [202401],
        "nu_prescricoes_mes": [20], "qtd_dias_com_prescricao_mes": [10],
    })
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([source]))
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    cache._sync_crm_medico_brasil_mes(Engine(), progress.append)

    import json
    manifest = json.loads(
        (cache_dir / ".parts" / "crm_medico_brasil_mes" / "manifest.json").read_text(encoding="utf-8")
    )
    result = pl.read_parquet(final_path)
    assert dict(result.schema) == cache._GLOBAL_PARQUET_SCHEMAS["crm_medico_brasil_mes"]
    assert result["nu_prescricoes_mes"].to_list() == [20]
    assert manifest["status"] == "done"
    assert progress == [90, 100]

    manifest_path = cache_dir / ".parts" / "crm_medico_brasil_mes" / "manifest.json"
    manifest["status"] = "running"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pytest.fail("competencia concluida nao deve ser consultada"),
    )
    resumed = []
    cache._sync_crm_medico_brasil_mes(Engine(), resumed.append)
    assert resumed == [90, 100]

    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    completed_part = cache_dir / ".parts" / "crm_medico_brasil_mes" / "202401.smod.part"

    def remove_verified_competence(_progress):
        completed_part.unlink(missing_ok=True)

    with pytest.raises(
        RuntimeError,
        match="Partes pendentes para consolidar crm_medico_brasil_mes: 202401.smod.part",
    ):
        cache._sync_crm_medico_brasil_mes(Engine(), remove_verified_competence)

    manifest["parts"] = []
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="campo parts invalido"):
        cache._sync_crm_medico_brasil_mes(Engine())

    manifest["parts"] = {}
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
    with pytest.raises(RuntimeError, match="sem registros para competencia 202401"):
        cache._sync_crm_medico_brasil_mes(Engine())

    class NoCompetenciesConnection(FakeConnection):
        def execute(self, query, params=None):
            return CompetenciesEmpty()

    class CompetenciesEmpty:
        def fetchall(self):
            return []

    class NoCompetenciesEngine:
        def connect(self):
            return NoCompetenciesConnection()

    with pytest.raises(RuntimeError, match="nao possui competencias"):
        cache._sync_crm_medico_brasil_mes(NoCompetenciesEngine())


@pytest.mark.parametrize(
    ("sync_name", "cache_key", "path_attribute"),
    [
        ("_sync_crm_medico_brasil_ano", "crm_medico_brasil_ano", "_CRM_MEDICO_BRASIL_ANO_PATH"),
        (
            "_sync_crm_medico_territorio_ano",
            "crm_medico_territorio_ano",
            "_CRM_MEDICO_TERRITORIO_ANO_PATH",
        ),
    ],
)
def test_crm_annual_sync_wrappers_write_ordered_typed_parts(
    sync_name, cache_key, path_attribute, tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_path = cache_dir / f"{cache_key}.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, path_attribute, str(final_path))
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)

    class Years:
        def fetchall(self):
            return [(2024,)]

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Years()

    class Engine:
        def connect(self):
            return Connection()

    schema = cache._GLOBAL_PARQUET_SCHEMAS[cache_key]
    values = {}
    for column, dtype in schema.items():
        if dtype == pl.String:
            values[column] = ["CRM-SP-1" if column == "id_medico" else "SP"]
        else:
            values[column] = [2024 if column == "ano" else 1]
    source = pd.DataFrame(values)
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([source]))
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    getattr(cache, sync_name)(Engine(), progress.append)

    result = pl.read_parquet(final_path)
    assert dict(result.schema) == schema
    assert result.height == 1
    assert progress == [90, 100]

    import json
    manifest_path = cache_dir / ".parts" / cache_key / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pytest.fail("ano concluido nao deve ser consultado"),
    )
    resumed = []
    getattr(cache, sync_name)(Engine(), resumed.append)
    assert resumed == [90, 100]

    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    completed_year = manifest_path.parent / "2024.smod.part"

    def remove_verified_year(_progress):
        completed_year.unlink(missing_ok=True)

    with pytest.raises(
        RuntimeError,
        match=f"Partes pendentes para consolidar {cache_key}: 2024.smod.part",
    ):
        getattr(cache, sync_name)(Engine(), remove_verified_year)

    manifest["parts"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="campo parts invalido"):
        getattr(cache, sync_name)(Engine())

    manifest["parts"] = {}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
    with pytest.raises(RuntimeError, match=f"sem registros para o ano 2024"):
        getattr(cache, sync_name)(Engine())

    class NoYears:
        def fetchall(self):
            return []

    class NoYearsConnection(FakeConnection):
        def execute(self, query, params=None):
            return NoYears()

    class NoYearsEngine:
        def connect(self):
            return NoYearsConnection()

    with pytest.raises(RuntimeError, match="nao possui anos"):
        getattr(cache, sync_name)(NoYearsEngine())


def test_crm_doctor_dimension_simple_sync_and_bitmap_index_delegate(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    path = tmp_path / "crm-medico-dim.parquet"
    monkeypatch.setattr(cache, "_CRM_MEDICO_DIM_PATH", str(path))
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)
    source = pd.DataFrame({"id_medico_num": [1], "id_medico": ["CRM-SP-1"]})
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: source)
    monkeypatch.setattr(cache, "_mark_on_demand_global_cache_ready", lambda *_args: None)
    progress = []
    cache._sync_crm_medico_dim(FakeEngine(row_count=1), progress.append)
    assert pl.read_parquet(path).to_dicts() == [{"id_medico_num": 1, "id_medico": "CRM-SP-1"}]
    assert progress == [100]

    import sys
    calls = []
    fake_indexer = SimpleNamespace(
        construir_indice=lambda output, progress_callback: calls.append((output, progress_callback))
    )
    monkeypatch.setitem(sys.modules, "crm_indice_bitmaps", fake_indexer)
    monkeypatch.setattr(cache, "_CRM_INDICE_BITMAPS_PATH", str(tmp_path / "bitmap.parquet"))
    cache._sync_crm_indice_bitmaps(progress_callback=progress.append)
    assert calls == [(str(tmp_path / "bitmap.parquet"), progress.append)]

    # Ponte medico x janela de multiplos CRMs: tambem montada localmente.
    bridge_calls = []
    fake_bridge = SimpleNamespace(
        construir=lambda output, progress_callback: bridge_calls.append((output, progress_callback)),
        conferir_fontes=lambda path: bridge_calls.append(("conferir", path)),
    )
    bridge_path = str(tmp_path / "ponte.parquet")
    monkeypatch.setitem(sys.modules, "crm_multiplo_medico", fake_bridge)
    monkeypatch.setattr(cache, "_CRM_CONCENTRACAO_MULTIPLO_MEDICO_GLOBAL_PARQUET_PATH", bridge_path)
    cache._sync_crm_concentracao_multiplo_medico_global(progress_callback=progress.append)
    cache.conferir_crm_concentracao_multiplo_medico_global()
    assert bridge_calls == [(bridge_path, progress.append), ("conferir", bridge_path)]


def test_sync_orchestrators_forward_identifiers_and_progress(monkeypatch, isolated_cache_state):
    cache = isolated_cache_state
    calls = []
    monkeypatch.setattr(cache, "_sync_dados_par", lambda engine: calls.append(("par", engine)))
    monkeypatch.setattr(cache, "_buscar_cnpjs_matriz", lambda engine: ["111", "222"])

    import cache_manager
    monkeypatch.setattr(
        cache_manager,
        "sync_cnpj_caches",
        lambda engine, cnpjs, callback: calls.append(("cnpj-caches", engine, cnpjs, callback)),
    )
    cache._sync_cnpj_parquets("engine")
    cache._sync_cnpj_parquets("engine", cnpjs=["333"])
    assert calls[:4] == [
        ("par", "engine"),
        ("cnpj-caches", "engine", ["111", "222"], None),
        ("par", "engine"),
        ("cnpj-caches", "engine", ["333"], None),
    ]

    calls.clear()
    def sync_level(name):
        def run(engine, callback):
            calls.append((name, engine))
            callback(100)
        return run

    monkeypatch.setattr(cache, "_sync_teia_fonte_nivel2", sync_level("n2"))
    monkeypatch.setattr(cache, "_sync_teia_fonte_nivel3", sync_level("n3"))
    monkeypatch.setattr(cache, "_sync_teia_fonte_nivel4", sync_level("n4"))
    progress = []
    cache._sync_teia_expansao_completa("engine", progress.append)
    assert calls == [("n2", "engine"), ("n3", "engine"), ("n4", "engine")]
    assert progress == [33, 66, 100, 100]


def test_crm_cnpj_parquet_orchestrator_calls_all_producers_and_propagates_failures(
    monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    import cache_manager
    calls = []
    monkeypatch.setattr(
        cache_manager,
        "sync_cnpj_cache",
        lambda module, cnpj, engine: calls.append((module, cnpj, engine)),
    )
    progress = []
    cache._sync_crm_parquets("engine", progress_callback=progress.append, cnpjs=["111", "222"])
    expected_modules = [
        "geografico", "crm_concentracao_unico_alertas", "crm_concentracao_multiplo_alertas",
        "crm_timeline_dia", "crm_timeline_hora", "crm_timeline_eventos", "crm_raiox_tx",
    ]
    assert calls == [
        (module, cnpj, "engine")
        for cnpj in ("111", "222")
        for module in expected_modules
    ]
    assert progress == [50, 100, 100]

    class CandidateConnection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return ColumnResult([("333",), ("444",)])

    class CandidateEngine:
        def connect(self):
            return CandidateConnection()

    calls.clear()
    candidate_engine = CandidateEngine()
    cache._sync_crm_parquets(candidate_engine)
    assert calls == [
        (module, cnpj, candidate_engine)
        for cnpj in ("333", "444")
        for module in expected_modules
    ]

    calls.clear()
    monkeypatch.setattr(
        cache_manager,
        "sync_cnpj_cache",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("cache CNPJ falhou")),
    )
    with pytest.raises(RuntimeError, match="cache CNPJ falhou"):
        cache._sync_crm_parquets("engine", cnpjs=["111"])

    class BrokenEngine:
        def connect(self):
            raise OSError("banco indisponivel")

    cache._sync_crm_parquets(BrokenEngine())


def test_crm_monthly_establishment_and_territory_syncs_validate_and_publish(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    final_establishment = cache_dir / "establishment-month.parquet"
    final_territory = cache_dir / "territory-month.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, "_CRM_MEDICO_ESTABELECIMENTO_MES_PATH", str(final_establishment))
    monkeypatch.setattr(cache, "_CRM_MEDICO_TERRITORIO_MES_PATH", str(final_territory))
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)

    class Competencies:
        def fetchall(self):
            return [(202401,)]

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Competencies()

    class Engine:
        def connect(self):
            return Connection()

    sources = {
        "estabelecimento_mes": pd.DataFrame({
            "id_cnpj": [3], "id_medico": ["CRM-SP-1"], "competencia": [202401],
            "nu_prescricoes_mes": [5], "qtd_dias_com_prescricao_mes": [3],
        }),
        "territorio_mes": pd.DataFrame({
            "nivel": ["UF"], "id_geografico": ["SP"], "id_medico": ["CRM-SP-1"],
            "competencia": [202401], "nu_prescricoes_mes": [5],
            "qtd_dias_com_prescricao_mes": [3],
        }),
    }

    def read_sql(query, _conn, params=None, chunksize=None):
        assert chunksize == 100_000
        table = "estabelecimento_mes" if "app_crm_medico_estabelecimento_mes" in str(query) else "territorio_mes"
        return iter([sources[table]])

    monkeypatch.setattr(cache.pd, "read_sql", read_sql)
    progress = []
    cache._sync_crm_medico_estabelecimento_mes(Engine(), progress.append)
    cache._sync_crm_medico_territorio_mes(Engine(), progress.append)

    assert dict(pl.read_parquet(final_establishment).schema) == cache._GLOBAL_PARQUET_SCHEMAS[
        "crm_medico_estabelecimento_mes"
    ]
    assert pl.read_parquet(final_establishment)["id_cnpj"].to_list() == [3]
    assert dict(pl.read_parquet(final_territory).schema) == cache._GLOBAL_PARQUET_SCHEMAS[
        "crm_medico_territorio_mes"
    ]
    assert progress == [90, 100, 90, 100]

    invalid = sources["estabelecimento_mes"].copy()
    invalid["qtd_dias_com_prescricao_mes"] = [6]
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([invalid]))
    with pytest.raises(RuntimeError, match="valores invalidos na competencia 202401"):
        cache._sync_crm_medico_estabelecimento_mes(Engine())

    import json
    module_specs = [
        (
            "crm_medico_estabelecimento_mes",
            "_sync_crm_medico_estabelecimento_mes",
            "crm_medico_estabelecimento_mes",
        ),
        (
            "crm_medico_territorio_mes",
            "_sync_crm_medico_territorio_mes",
            "crm_medico_territorio_mes",
        ),
    ]
    for cache_key, sync_name, error_fragment in module_specs:
        manifest_path = cache_dir / ".parts" / cache_key / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        manifest["parts"]["202401"] = {
            "status": "done", "rows": 1, "file": "202401.smod.part",
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pytest.fail("competencias concluidas nao devem ser consultadas"),
    )
    resumed = []
    cache._sync_crm_medico_estabelecimento_mes(Engine(), resumed.append)
    cache._sync_crm_medico_territorio_mes(Engine(), resumed.append)
    assert resumed == [90, 100, 90, 100]

    for cache_key, sync_name, _error_fragment in module_specs:
        manifest_path = cache_dir / ".parts" / cache_key / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        completed_part = manifest_path.parent / "202401.smod.part"

        def remove_verified_competence(_progress):
            completed_part.unlink(missing_ok=True)

        with pytest.raises(
            RuntimeError,
            match=f"Partes pendentes para consolidar {cache_key}: 202401.smod.part",
        ):
            getattr(cache, sync_name)(Engine(), remove_verified_competence)

    for cache_key, sync_name, error_fragment in module_specs:
        manifest_path = cache_dir / ".parts" / cache_key / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        manifest["parts"] = []
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(RuntimeError, match="campo parts invalido"):
            getattr(cache, sync_name)(Engine())

    for cache_key, sync_name, error_fragment in module_specs:
        manifest_path = cache_dir / ".parts" / cache_key / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        manifest["parts"] = {}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: iter([]))
        with pytest.raises(RuntimeError, match="sem registros para competencia 202401"):
            getattr(cache, sync_name)(Engine())

    class NoCompetencies:
        def fetchall(self):
            return []

    class NoCompetenciesConnection(FakeConnection):
        def execute(self, query, params=None):
            return NoCompetencies()

    class NoCompetenciesEngine:
        def connect(self):
            return NoCompetenciesConnection()

    for _cache_key, sync_name, _error_fragment in module_specs:
        with pytest.raises(RuntimeError, match="nao possui competencias"):
            getattr(cache, sync_name)(NoCompetenciesEngine())


def test_establishment_month_consolidation_detects_part_changed_during_count(
    tmp_path, monkeypatch
):
    cache = data_cache
    cache_key = "crm_medico_estabelecimento_mes"
    schema = cache._GLOBAL_PARQUET_SCHEMAS[cache_key]
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    monthly_part = parts_dir / "202401.smod.part"
    first_row = {
        "id_cnpj": 3,
        "id_medico": "CRM-SP-1",
        "competencia": 202401,
        "nu_prescricoes_mes": 5,
        "qtd_dias_com_prescricao_mes": 3,
    }
    pl.DataFrame([first_row], schema=schema).write_parquet(monthly_part)
    final_path = tmp_path / "crm-medico-estabelecimento-mes.parquet"
    real_scan_parquet = cache.pl.scan_parquet
    scan_count = 0

    def scan_after_concurrent_refresh(paths, *args, **kwargs):
        nonlocal scan_count
        scan_count += 1
        if scan_count == 3:
            second_row = {**first_row, "id_cnpj": 4}
            pl.DataFrame([first_row, second_row], schema=schema).write_parquet(monthly_part)
        return real_scan_parquet(paths, *args, **kwargs)

    monkeypatch.setattr(cache.pl, "scan_parquet", scan_after_concurrent_refresh)

    with pytest.raises(
        RuntimeError,
        match=(
            r"Consolidacao de crm_medico_estabelecimento_mes com 1 linhas; "
            r"as partes mensais somam 2\."
        ),
    ):
        cache._consolidar_estabelecimento_mes_por_medico(
            {202401: monthly_part},
            parts_dir,
            str(final_path),
            list(schema.keys()),
        )

    assert scan_count == 4
    assert not final_path.exists()


def test_crm_map_period_syncs_write_registered_schemas_and_handle_empty_sources(
    tmp_path, monkeypatch, isolated_cache_state
):
    cache = isolated_cache_state
    cache_dir = tmp_path / "global"
    cache_dir.mkdir()
    regional_path = cache_dir / "crm-map-region.parquet"
    uf_path = cache_dir / "crm-map-uf.parquet"
    p95_path = cache_dir / "crm-p95.parquet"
    monkeypatch.setattr(cache, "_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(cache, "_CRM_MAPA_MUNICIPIO_REGIAO_PERIODO_PATH", str(regional_path))
    monkeypatch.setattr(cache, "_CRM_MAPA_UF_PERIODO_PATH", str(uf_path))
    monkeypatch.setattr(cache, "_CRM_LIMIAR_P95_MES_PATH", str(p95_path))
    monkeypatch.setattr(cache, "_assert_fp_source_table", lambda *_args: 1)

    class Competencies:
        def fetchall(self):
            return [(202401,)]

    class Connection(FakeConnection):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            return Competencies()

    class Engine:
        def connect(self):
            return Connection()

    regional = pd.DataFrame({
        "nivel": ["REGIAO"], "id_geografico": ["123"], "competencia_inicio": [202401],
        "competencia_fim": [202412], "qtd_medicos_ativos": [10],
        "qtd_medicos_alta_intensidade": [2],
    })
    uf = regional.assign(nivel="UF", id_geografico="SP")
    p95 = pd.DataFrame({"competencia": [202401], "qtd_medicos_ativos": [10], "p95_taxa_dia": [4.5]})
    def read_sql(query, _connection, **_kwargs):
        sql = str(query)
        if "app_crm_mapa_municipio_regiao_periodo" in sql:
            return regional
        if "app_crm_mapa_uf_periodo" in sql:
            return uf
        return p95

    monkeypatch.setattr(cache.pd, "read_sql", read_sql)
    progress = []
    cache._sync_crm_mapa_municipio_regiao_periodo(Engine(), progress.append)
    cache._sync_crm_mapa_uf_periodo(FakeEngine(row_count=1), progress.append)
    cache._sync_crm_limiar_p95_mes(FakeEngine(row_count=1), progress.append)

    assert dict(pl.read_parquet(regional_path).schema) == cache._GLOBAL_PARQUET_SCHEMAS[
        "crm_mapa_municipio_regiao_periodo"
    ]
    assert pl.read_parquet(uf_path)["id_geografico"].to_list() == ["SP"]
    assert pl.read_parquet(p95_path)["p95_taxa_dia"].to_list() == [4.5]
    assert progress == [90, 100, 100, 100]

    import json
    parts_dir = cache_dir / ".parts" / "crm_mapa_municipio_regiao_periodo"
    manifest_path = parts_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        cache.pd,
        "read_sql",
        lambda *_args, **_kwargs: pytest.fail("competencia concluida nao deve ser consultada"),
    )
    resumed = []
    cache._sync_crm_mapa_municipio_regiao_periodo(Engine(), resumed.append)
    assert resumed == [90, 100]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    completed_competence = parts_dir / "202401.smod.part"

    def remove_verified_competence(_progress):
        completed_competence.unlink(missing_ok=True)

    with pytest.raises(
        RuntimeError,
        match="Partes pendentes para consolidar crm_mapa_municipio_regiao_periodo: 202401.smod.part",
    ):
        cache._sync_crm_mapa_municipio_regiao_periodo(Engine(), remove_verified_competence)

    manifest["parts"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="campo parts invalido"):
        cache._sync_crm_mapa_municipio_regiao_periodo(Engine())

    manifest["parts"] = {}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cache.pd, "read_sql", lambda *_args, **_kwargs: pd.DataFrame())
    with pytest.raises(RuntimeError, match="sem registros para competencia inicial 202401"):
        cache._sync_crm_mapa_municipio_regiao_periodo(Engine())

    class NoCompetencies:
        def fetchall(self):
            return []

    class NoCompetenciesConnection(FakeConnection):
        def execute(self, query, params=None):
            return NoCompetencies()

    class NoCompetenciesEngine:
        def connect(self):
            return NoCompetenciesConnection()

    with pytest.raises(RuntimeError, match="nao possui competencias iniciais"):
        cache._sync_crm_mapa_municipio_regiao_periodo(NoCompetenciesEngine())


def test_crm_farmacia_doctor_year_sync_delegates_typed_cache_contract(monkeypatch):
    engine = object()
    progress_callback = object()
    calls = []
    monkeypatch.setattr(
        data_cache,
        "_sync_crm_medico_ano",
        lambda received_engine, **kwargs: calls.append((received_engine, kwargs)),
    )

    data_cache._sync_crm_farmacia_medico_ano(engine, progress_callback)

    assert calls == [(engine, {
        "cache_key": "crm_farmacia_medico_ano",
        "source_table": "app_crm_farmacia_medico_ano",
        "final_path": data_cache._CRM_FARMACIA_MEDICO_ANO_PATH,
        "casts": data_cache._GLOBAL_PARQUET_SCHEMAS["crm_farmacia_medico_ano"],
        "order_by": "id_medico_num, id_cnpj",
        "progress_callback": progress_callback,
    })]
