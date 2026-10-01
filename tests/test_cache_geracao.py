"""Cache por geracao compartilhado pelos servicos de analise."""

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backend.api.services.analytics import cache_geracao
from backend.api.services.analytics.cache_geracao import CacheGeracao


class CacheGeracaoTests(unittest.TestCase):
    def setUp(self):
        self.geracao = 1
        self.patcher = patch.object(cache_geracao, "get_cache_generation", side_effect=lambda: self.geracao)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_reaproveita_e_descarta_geracao_antiga(self):
        cache, chamadas = CacheGeracao(max_itens=4), []
        calcular = lambda: chamadas.append(1) or len(chamadas)
        self.assertEqual(cache.obter(("a",), calcular), 1)
        self.assertEqual(cache.obter(("a",), calcular), 1)
        self.geracao = 2  # dados recarregados
        self.assertEqual(cache.obter(("a",), calcular), 2)

    def test_lru_remove_o_menos_usado(self):
        cache, chamadas = CacheGeracao(max_itens=2), []

        def calcular(nome):
            return lambda: chamadas.append(nome) or nome

        cache.obter(("a",), calcular("a"))
        cache.obter(("b",), calcular("b"))
        cache.obter(("a",), calcular("a"))  # a passa a ser o mais recente
        cache.obter(("c",), calcular("c"))  # sai b
        cache.obter(("a",), calcular("a"))
        cache.obter(("b",), calcular("b"))
        self.assertEqual(chamadas, ["a", "b", "c", "b"])

    def test_expiracao(self):
        cache, chamadas = CacheGeracao(max_itens=4, ttl_segundos=10), []
        agora = [100.0]
        with patch.object(cache_geracao.time, "monotonic", side_effect=lambda: agora[0]):
            cache.obter(("a",), lambda: chamadas.append(1))
            agora[0] = 109.0
            cache.obter(("a",), lambda: chamadas.append(1))
            agora[0] = 111.0
            cache.obter(("a",), lambda: chamadas.append(1))
        self.assertEqual(len(chamadas), 2)

    def test_erro_nao_entra_no_cache(self):
        cache = CacheGeracao(max_itens=4)

        def falhar():
            raise RuntimeError("fonte indisponivel")

        with self.assertRaises(RuntimeError):
            cache.obter(("a",), falhar)
        self.assertEqual(cache.obter(("a",), lambda: "ok"), "ok")

    def test_requisicoes_simultaneas_calculam_uma_vez(self):
        cache, chamadas, resultados = CacheGeracao(max_itens=4), [], []
        inicio = threading.Barrier(6)

        def calcular():
            chamadas.append(1)
            time.sleep(0.2)
            return "valor"

        def pedir():
            inicio.wait()
            resultados.append(cache.obter(("a",), calcular))

        threads = [threading.Thread(target=pedir) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(resultados, ["valor"] * 6)


if __name__ == "__main__":
    unittest.main()
