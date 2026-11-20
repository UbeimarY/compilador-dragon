import unittest

from tests.ayudas import EJEMPLOS, compilar, ejecuciones, ejecutar


class PruebasHeap(unittest.TestCase):
    def test_concatenar_reserva_y_liberar_devuelve(self):
        resultados = ejecuciones('texto a = "x" + "y"; imprimir(a); liberar(a);')
        for r in resultados:
            self.assertEqual(r.salida, ["xy"])
            self.assertEqual((r.heap.reservas, r.heap.liberaciones, len(r.heap.fugas())), (1, 1, 0))

    def test_fuga_de_memoria(self):
        r = ejecuciones('texto a = "x" + "y"; imprimir(a);')[-1]
        self.assertEqual(len(r.heap.fugas()), 1)
        self.assertIn("fuga de", r.heap.resumen())

    def test_dangling_pointer(self):
        for r in ejecuciones('texto a = "x" + "y"; liberar(a); imprimir(a);'):
            self.assertIn("dangling pointer", r.error)

    def test_double_free(self):
        for r in ejecuciones('texto a = "x" + "y"; liberar(a); liberar(a);'):
            self.assertIn("double free", r.error)

    def test_no_se_libera_una_constante(self):
        for r in ejecuciones('texto a = "constante"; liberar(a);'):
            self.assertIn("Solo se puede liberar memoria del heap", r.error)

    def test_la_concatenacion_no_se_pliega_en_compilacion(self):
        c = compilar('texto a = "x" + "y"; imprimir(a); liberar(a);')
        self.assertTrue(any(q.op == "+" for q in c.optimizado.instrucciones))

    def test_comparar_textos_compara_contenido(self):
        self.assertEqual(ejecutar('texto a = "ab" + "c"; imprimir(a == "abc"); liberar(a);'), ["verdadero"])

    def test_programa_memoria(self):
        resultados = ejecuciones((EJEMPLOS / "programa_memoria.drg").read_text(encoding="utf-8"))
        asm = resultados[-1]
        self.assertEqual(asm.salida[-1], "fin")
        self.assertEqual((asm.heap.reservas, asm.heap.liberaciones, len(asm.heap.fugas())), (5, 4, 1))


if __name__ == "__main__":
    unittest.main()
