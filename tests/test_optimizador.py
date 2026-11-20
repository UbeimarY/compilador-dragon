import unittest

from tests.ayudas import compilar, ejecutar


def texto_optimizado(codigo):
    return compilar(codigo).optimizado.como_texto(numerado=False)


class PruebasOptimizador(unittest.TestCase):
    def test_plegado_de_constantes(self):
        self.assertIn("imprimir 35", texto_optimizado("imprimir(15 * 2 + 5);"))

    def test_propagacion_de_constantes(self):
        resultado = texto_optimizado("entero a = 5; entero b = a * 2; imprimir(b);")
        self.assertEqual(resultado.strip(), "imprimir 10")

    def test_simplificacion_algebraica(self):
        resultado = texto_optimizado("entero x = 0; mientras (x < 3) { imprimir(x * 1 + 0); x = x + 1; }")
        self.assertIn("imprimir x", resultado)

    def test_si_con_condicion_falsa_se_elimina(self):
        resultado = texto_optimizado('si (3 > 4) { imprimir("nunca"); } sino { imprimir("siempre"); }')
        self.assertNotIn("nunca", resultado)
        self.assertNotIn("goto", resultado)

    def test_mientras_falso_se_elimina(self):
        self.assertEqual(texto_optimizado('mientras (falso) { imprimir("x"); }').strip(), "")

    def test_fusion_de_temporales(self):
        resultado = texto_optimizado("entero v = 10; mientras (v > 0) { v = v - 3; imprimir(v); }")
        self.assertIn("v = v - 3", resultado)

    def test_no_se_pliega_division_por_cero_en_ejecucion(self):
        c = compilar("entero c = 0; entero x = 5; mientras (x > 0) { imprimir(10 / c); x = 0; }")
        self.assertTrue(any(q.op == "/" for q in c.optimizado.instrucciones))

    def test_la_optimizacion_reduce_instrucciones(self):
        c = compilar("entero a = 2 * 3; entero b = a + 4; si (b > 100) { imprimir(b); } imprimir(a);")
        self.assertLess(len(c.optimizado.instrucciones), len(c.tac.instrucciones))

    def test_la_optimizacion_preserva_la_semantica(self):
        salida = ejecutar("entero i = 0; entero s = 0; mientras (i < 5) { s = s + i * 2; i = i + 1; } imprimir(s);")
        self.assertEqual(salida, ["20"])


if __name__ == "__main__":
    unittest.main()
