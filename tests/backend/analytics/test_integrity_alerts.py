from datetime import date, datetime
from types import SimpleNamespace

import polars as pl
import pytest

from api.services.analytics import geografico, integrity_alerts as alerts


CNPJ = "12345678000190"
REFERENCE = date(2024, 4, 1)


def _cadastro(**overrides):
    values = {
        "cnpj": CNPJ,
        "nome_fantasia": "Farmacia Referencia",
        "razao_social": "Razao Social",
        "data_processamento": datetime(2024, 4, 1, 12, 0),
        "is_cnae_farmacia_ausente": False,
        "is_dispersao_uf_nao_vizinha": False,
        "pct_dispersao_uf_nao_vizinha": 0.0,
        "valor_dispersao_uf_nao_vizinha": 0.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _socio(**overrides):
    values = {
        "indicador_socio": "PF",
        "cpf_cnpj_socio": "12345678901",
        "nome_socio": "Pessoa Socia",
        "data_nascimento_socio": date(1990, 1, 1),
        "data_exclusao_sociedade": None,
        "is_falecido": False,
        "is_cadunico": False,
        "is_esocial": False,
        "is_seguro_defeso": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _install_sources(monkeypatch, *, cadastro=None, socios=None, par_teia=None, semestres=None):
    cadastro = cadastro or _cadastro()
    socios = socios or []
    par_teia = par_teia if par_teia is not None else pl.DataFrame({"cnpj": [CNPJ], "has_par_n2": [False]})
    semestres = semestres if semestres is not None else []
    monkeypatch.setattr(alerts, "get_dados_farmacia", lambda _cnpj: cadastro)
    monkeypatch.setattr(
        alerts,
        "get_socios_farmacia",
        lambda _cnpj: SimpleNamespace(data_processamento=REFERENCE, socios=socios),
    )
    monkeypatch.setattr(alerts, "get_df_par_teia_alvos", lambda: par_teia)
    monkeypatch.setattr(alerts, "get_evolucao_financeira", lambda *_args, **_kwargs: SimpleNamespace(semestres=semestres))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (date(2024, 3, 31), date(2024, 3, 31)),
        (datetime(2024, 3, 31, 23, 59), date(2024, 3, 31)),
    ],
)
def test_date_normalization(value, expected):
    assert alerts._as_date(value) == expected


@pytest.mark.parametrize(
    ("birth", "expected"),
    [
        (date(2006, 4, 2), 17),
        (date(2006, 4, 1), 18),
        (date(2003, 4, 1), 21),
        (date(1943, 4, 1), 81),
    ],
)
def test_age_calculation_respects_whether_birthday_has_occurred(birth, expected):
    assert alerts._calcular_idade(birth, REFERENCE) == expected


@pytest.mark.parametrize(
    ("age", "expected_type"),
    [(17, "socio_menor_idade"), (18, "socio_menor_21"), (20, "socio_menor_21"),
     (21, None), (80, None), (81, "socio_maior_80")],
)
def test_age_alert_boundaries(age, expected_type):
    result = alerts._build_alerta_idade_socio(
        socio=_socio(), entidade_nome="Pessoa", idade=age, data_referencia=REFERENCE
    )

    assert (result.tipo if result else None) == expected_type


@pytest.mark.parametrize("semestres, expected", [([], False), ([SimpleNamespace(volume_atipico=False)], False),
                                                    ([SimpleNamespace(volume_atipico=True)], True)])
def test_atypical_volume_alert_requires_atypical_semester(monkeypatch, semestres, expected):
    _install_sources(monkeypatch, semestres=semestres)

    result = alerts._build_alerta_volume_atipico(
        cadastro=_cadastro(nome_fantasia="", data_processamento=None),
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 12, 31), volume_atipico_limite=0.5,
    )

    assert (result is not None) is expected
    if result:
        assert result.entidade_nome == "Razao Social"
        assert result.data_referencia is None
        assert result.aba_destino == "movimentacao"


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (pl.DataFrame({"cnpj": [CNPJ], "has_par_n2": [False]}), False),
        (pl.DataFrame({"cnpj": ["99999999000199"], "has_par_n2": [True]}), False),
        (pl.DataFrame({"cnpj": [CNPJ], "has_par_n2": [True]}), True),
    ],
)
def test_par_teia_alert_matches_target_and_true_flag(monkeypatch, frame, expected):
    monkeypatch.setattr(alerts, "get_df_par_teia_alvos", lambda: frame)

    result = alerts._build_alerta_par_teia_n2(cadastro=_cadastro(nome_fantasia=None))

    assert (result is not None) is expected
    if result:
        assert result.entidade_nome == "Razao Social"
        assert result.aba_destino == "teia"


@pytest.mark.parametrize("frame", [pl.DataFrame(), pl.DataFrame({"cnpj": [CNPJ]})])
def test_par_teia_rejects_missing_required_columns(monkeypatch, frame):
    monkeypatch.setattr(alerts, "get_df_par_teia_alvos", lambda: frame)

    with pytest.raises(RuntimeError, match="colunas obrigatorias para alerta PAR N2"):
        alerts._build_alerta_par_teia_n2(cadastro=_cadastro())


def test_integrity_response_contains_and_orders_all_applicable_alerts(monkeypatch):
    cadastro = _cadastro(
        is_cnae_farmacia_ausente=True,
        is_dispersao_uf_nao_vizinha=True,
        nome_fantasia=None,
    )
    socios = [
        _socio(cpf_cnpj_socio="1", nome_socio="Menor", data_nascimento_socio=date(2008, 5, 1),
               is_falecido=True, is_cadunico=True, is_esocial=True, is_seguro_defeso=True),
        _socio(cpf_cnpj_socio="2", nome_socio="Menor de 21", data_nascimento_socio=date(2005, 4, 1)),
        _socio(cpf_cnpj_socio="3", nome_socio="Idoso", data_nascimento_socio=date(1940, 1, 1)),
        _socio(cpf_cnpj_socio="4", nome_socio="Socio PJ", indicador_socio="PJ", is_falecido=True),
        _socio(cpf_cnpj_socio="5", nome_socio="Vinculo encerrado", data_nascimento_socio=date(2008, 1, 1),
               data_exclusao_sociedade=date(2020, 1, 1), is_falecido=True, is_cadunico=True,
               is_esocial=True, is_seguro_defeso=True),
    ]
    _install_sources(
        monkeypatch,
        cadastro=cadastro,
        socios=socios,
        par_teia=pl.DataFrame({"cnpj": [CNPJ], "has_par_n2": [True]}),
        semestres=[SimpleNamespace(volume_atipico=True)],
    )

    response = alerts.get_integrity_alerts(CNPJ, volume_atipico_limite=0.75)
    tipos = [item.tipo for item in response.alertas]

    assert set(tipos) == {
        "volume_atipico", "par_teia_n2", "cnpj_cnae_farmacia_ausente", "cnpj_dispersao_uf_nao_vizinha",
        "socio_menor_idade", "socio_falecido", "socio_cadunico", "socio_esocial", "socio_seguro_defeso",
        "socio_menor_21", "socio_maior_80",
    }
    assert response.total == len(tipos)
    assert response.total_criticos == 3
    assert response.total_atencao == response.total - 3
    assert response.alertas[0].severidade == "critico"
    assert all(item.data_referencia == date(2024, 4, 1) for item in response.alertas)


def test_inactive_or_unqualified_partner_flags_do_not_create_false_alerts(monkeypatch):
    _install_sources(
        monkeypatch,
        socios=[
            _socio(data_exclusao_sociedade=date(2020, 1, 1), is_falecido=True, is_cadunico=True, is_seguro_defeso=True),
            _socio(indicador_socio="PJ", is_falecido=True, is_cadunico=True, is_seguro_defeso=True),
            _socio(data_nascimento_socio=None),
        ],
    )

    response = alerts.get_integrity_alerts(CNPJ)

    assert response.alertas == []
    assert response.total == 0


def test_period_geography_alert_uses_profile_id_and_filters(monkeypatch):
    _install_sources(monkeypatch)
    profile = pl.DataFrame({"cnpj": [CNPJ], "id_cnpj": [23], "uf": ["SC"]})
    calls = []
    result = {
        "is_dispersao_uf_nao_vizinha": True,
        "pct_dispersao_uf_nao_vizinha": 0.4,
        "valor_dispersao_uf_nao_vizinha": 200.0,
    }
    monkeypatch.setattr(alerts, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(geografico, "calcular_alerta_uf_nao_vizinha", lambda **kwargs: calls.append(kwargs) or result)

    response = alerts.get_integrity_alerts(CNPJ, data_fim=date(2024, 3, 31))

    assert any(item.tipo == "cnpj_dispersao_uf_nao_vizinha" for item in response.alertas)
    assert calls == [{"id_cnpj": 23, "uf_farmacia": "SC", "data_inicio": None, "data_fim": date(2024, 3, 31)}]


@pytest.mark.parametrize("columns", [{"cnpj": [CNPJ], "id_cnpj": [23]}, {"cnpj": [CNPJ], "uf": ["SC"]}, {"id_cnpj": [23], "uf": ["SC"]}])
def test_period_geography_requires_each_profile_column(monkeypatch, columns):
    _install_sources(monkeypatch)
    monkeypatch.setattr(alerts, "get_df_perfil_estabelecimento", lambda: pl.DataFrame(columns))

    with pytest.raises(RuntimeError, match="Perfil consolidado sem coluna obrigatoria"):
        alerts.get_integrity_alerts(CNPJ, data_inicio=date(2024, 1, 1))


def test_period_geography_requires_profile_row_for_requested_pharmacy(monkeypatch):
    _install_sources(monkeypatch)
    monkeypatch.setattr(
        alerts, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["99999999000199"], "id_cnpj": [23], "uf": ["SC"]}),
    )

    with pytest.raises(RuntimeError, match="Perfil consolidado ausente"):
        alerts.get_integrity_alerts(CNPJ, data_fim=date(2024, 3, 31))


def test_period_geography_can_return_no_alert(monkeypatch):
    _install_sources(monkeypatch, cadastro=_cadastro(is_dispersao_uf_nao_vizinha=True))
    monkeypatch.setattr(
        alerts, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "id_cnpj": [23], "uf": ["SC"]}),
    )
    monkeypatch.setattr(
        geografico, "calcular_alerta_uf_nao_vizinha",
        lambda **_kwargs: {"is_dispersao_uf_nao_vizinha": False, "pct_dispersao_uf_nao_vizinha": 0.0,
                           "valor_dispersao_uf_nao_vizinha": 0.0},
    )

    response = alerts.get_integrity_alerts(CNPJ, data_inicio=date(2024, 1, 1))

    assert all(item.tipo != "cnpj_dispersao_uf_nao_vizinha" for item in response.alertas)
