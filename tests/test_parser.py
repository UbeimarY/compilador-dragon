import unittest

from dragon.ast_nodos import Binaria, Declaracion, Literal, Si, Unaria
from dragon.errores import SINTACTICO
from tests.ayudas import errores_de, frente


def expresion(codigo):
    return frente(f"entero x = {codigo};").ast.instrucciones[0].valor


class PruebasParser(unittest.TestCase):
    def test_precedencia_multiplicacion_antes_que_suma(self):
        e = expresion("2 + 3 * 4")
        self.assertIsInstance(e, Binaria)
        self.assertEqual(e.operador, "+")
        self.assertEqual(e.derecha.operador, "*")

    def test_asociatividad_izquierda(self):
        e = expresion("10 - 4 - 3")  # (10 - 4) - 3
        self.assertEqual(e.operador, "-")
        self.assertEqual(e.izquierda.operador, "-")
        self.assertIsInstance(e.derecha, Literal)

    def test_parentesis_cambian_la_precedencia(self):
        e = expresion("(2 + 3) * 4")
        self.assertEqual(e.operador, "*")
        self.assertEqual(e.izquierda.operador, "+")

    def test_menos_unario(self):
        e = expresion("-5 + 3")
        self.assertIsInstance(e.izquierda, Unaria)

    def test_cadena_si_sino_si_sino(self):
        programa = frente("entero a = 1; si (a > 0) { a = 1; } sino si (a < 0) { a = 2; } sino { a = 3; }").ast
        si = programa.instrucciones[1]
        self.assertIsInstance(si, Si)
        self.assertIsInstance(si.sino, Si)
        self.assertIsNotNone(si.sino.sino)

    def test_recuperacion_reporta_varios_errores(self):
        codigo = "entero a = 5\nentero b = ;\nb 3;\nimprimir(a;\n"
        errores = errores_de(codigo, SINTACTICO)
        self.assertEqual([e.linea for e in errores], [1, 2, 3, 4])

    def test_punto_y_coma_faltante_no_descarta_la_linea_siguiente(self):
        c = frente("entero a = 5\nentero b = 6;")
        declaraciones = [n for n in c.ast.instrucciones if isinstance(n, Declaracion)]
        self.assertEqual([d.nombre for d in declaraciones], ["a", "b"])
        self.assertEqual(len(c.reporte.de_fase(SINTACTICO)), 1)

    def test_bloque_sin_cerrar(self):
        errores = errores_de("{ entero a = 1;", SINTACTICO)
        self.assertEqual(len(errores), 1)
        self.assertIn("nunca se cerró", errores[0].mensaje)


if __name__ == "__main__":
    unittest.main()
