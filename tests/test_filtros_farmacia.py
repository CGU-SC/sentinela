"""Filtros de farmacia: o objeto unico cobre todos os pontos que os recebem."""

import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backend.api.endpoints.analytics import filtros_farmacia
from backend.api.services.analytics import crm_analysis_filtrado, indicadores
from backend.api.services.analytics.alertas_alvos import build_perfil_filtrado
from backend.api.services.analytics.crm_analysis import montar_filtros_farmacia
from backend.api.services.analytics.filtros_farmacia import (
    CAMPOS_FILTROS_FARMACIA,
    SEM_FILTRO_FARMACIA,
    FiltrosFarmacia,
)


class FiltrosFarmaciaTests(unittest.TestCase):
    def test_dependencia_dos_endpoints_declara_todos_os_campos(self):
        self.assertEqual(tuple(inspect.signature(filtros_farmacia).parameters), CAMPOS_FILTROS_FARMACIA)

    def test_cache_dos_indicadores_cobre_todos_os_campos(self):
        """Campo fora da chave de cache: filtros diferentes devolveriam o mesmo resultado."""
        chave = {nome for nome, _normalizer in indicadores._INDICADOR_SCOPE_FILTER_FIELDS}
        self.assertEqual(set(CAMPOS_FILTROS_FARMACIA) - chave, set())

    def test_analise_de_crms_usa_os_mesmos_campos(self):
        self.assertEqual(set(crm_analysis_filtrado.FILTROS_FARMACIA), set(CAMPOS_FILTROS_FARMACIA))
        ativo, normalizados = montar_filtros_farmacia(SEM_FILTRO_FARMACIA)
        self.assertFalse(ativo)
        self.assertEqual(set(normalizados), set(CAMPOS_FILTROS_FARMACIA))
        ativo, _ = montar_filtros_farmacia(FiltrosFarmacia(populacao_max=50000))
        self.assertTrue(ativo)

    def test_build_perfil_filtrado_recebe_o_objeto(self):
        parametros = inspect.signature(build_perfil_filtrado).parameters
        self.assertIn("filtros", parametros)
        self.assertEqual(set(parametros) & set(CAMPOS_FILTROS_FARMACIA), set())

    def test_conversoes(self):
        filtros = FiltrosFarmacia(seq_tipo="unico", seq_severidade_min=4)
        self.assertEqual(FiltrosFarmacia.de_mapeamento({**filtros.como_dict(), "uf": "SC"}), filtros)
        with self.assertRaises(Exception):
            filtros.seq_tipo = "multiplo"  # imutavel


if __name__ == "__main__":
    unittest.main()
