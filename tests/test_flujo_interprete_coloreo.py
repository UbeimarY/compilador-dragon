import unittest

from dragon.flujo import construir_grafo
from dragon.interprete import interpretar
from tests.ayudas import EJEMPLOS, compilar, ejecutar, frente

CICLO = "entero i = 0; mientras (i < 3) { si (i == 1) { imprimir(i); } i = i + 1; } imprimir(i);"


class PruebasGrafoDeFlujo(unittest.TestCase):
    def test_bloques_y_aristas_de_un_ciclo(self):
        tac = compilar(CICLO).optimizado
        bloques = construir_grafo(tac)
        # Un ciclo produce una arista hacia atrás (de un bloque a otro anterior)
        hacia_atras = [(b.numero, s) for b in bloques for s in b.sucesores if s != "SALIDA" and s <= b.numero]
        self.assertTrue(hacia_atras)
        self.assertEqual(bloques[-1].sucesores, ["SALIDA"])
        # Todo bloque empieza en una etiqueta o justo después de un salto
        for b in bloques[1:]:
            anterior = tac.instrucciones[b.inicio - 1].op
            self.assertTrue(tac.instrucciones[b.inicio].op == "label"
                            or anterior in ("goto", "if_false", "return", "fin", "fin_func"))

    def test_cada_funcion_tiene_sus_bloques(self):
        tac = compilar((EJEMPLOS / "programa_funciones.drg").read_text(encoding="utf-8")).optimizado
        funciones = {b.funcion for b in construir_grafo(tac)}
        self.assertEqual(funciones, {"main", "factorial", "fibonacci", "mcd", "es_primo", "area_circulo", "anunciar"})


class PruebasInterprete(unittest.TestCase):
    def test_interprete_coincide_con_el_compilador(self):
        for archivo in ("programa_correcto.drg", "programa_funciones.drg", "programa_memoria.drg"):
            ejecutar((EJEMPLOS / archivo).read_text(encoding="utf-8"))  # compara las 4 ejecuciones

    def test_interprete_no_genera_codigo(self):
        c = frente(CICLO)
        r = interpretar(c.ast, c.semantico.tabla.todos, c.semantico.funciones)
        self.assertEqual(r.salida, ["1", "3"])
        self.assertGreater(r.pasos, 0)


class PruebasColoreo(unittest.TestCase):
    PESADO = (EJEMPLOS / "programa_registros.drg").read_text(encoding="utf-8")

    def test_coloreo_correcto_con_cualquier_numero_de_registros(self):
        esperado = ejecutar(self.PESADO)
        for n in (2, 3, 4, 6, 8):
            self.assertEqual(ejecutar(self.PESADO, registros=n, asignador="coloreo"), esperado)

    def test_vecinos_nunca_comparten_registro(self):
        gen = compilar(self.PESADO, registros=4, asignador="coloreo").asm
        from dragon.coloreo import GeneradorCodigoColoreo
        g = GeneradorCodigoColoreo(compilar(self.PESADO).optimizado, 4)
        g.generar()
        for _, grafo, ubicacion in g.grafos:
            for t, vecinos in grafo.items():
                for v in vecinos:
                    if ubicacion[t].startswith("R"):
                        self.assertNotEqual(ubicacion[t], ubicacion[v], f"{t} y {v}")
        self.assertIsNotNone(gen)

    def test_con_mas_registros_hay_menos_spill(self):
        pocos = compilar(self.PESADO, registros=2, asignador="coloreo").asm.spills
        muchos = compilar(self.PESADO, registros=8, asignador="coloreo").asm.spills
        self.assertGreater(pocos, muchos)
        self.assertEqual(muchos, 0)


if __name__ == "__main__":
    unittest.main()
