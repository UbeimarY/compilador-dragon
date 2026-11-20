import unittest

from dragon.errores import LEXICO, ReporteErrores
from dragon.lexer import Lexer


def tokens(codigo):
    reporte = ReporteErrores()
    return Lexer(codigo, reporte).tokenizar(), reporte


class PruebasLexer(unittest.TestCase):
    def test_palabras_reservadas_e_identificadores(self):
        toks, _ = tokens("entero enteros si sino_x mientras")
        self.assertEqual([t.tipo for t in toks], ["TIPO", "ID", "SI", "ID", "MIENTRAS", "EOF"])

    def test_numeros_enteros_y_reales(self):
        toks, _ = tokens("42 3.14")
        self.assertEqual((toks[0].tipo, toks[0].valor), ("NUM_ENTERO", 42))
        self.assertEqual((toks[1].tipo, toks[1].valor), ("NUM_REAL", 3.14))

    def test_operadores_de_dos_caracteres_tienen_prioridad(self):
        toks, _ = tokens("<= >= == != && || < > = !")
        self.assertEqual([t.tipo for t in toks[:-1]],
                         ["MENOR_IGUAL", "MAYOR_IGUAL", "IGUAL", "DIFERENTE", "Y", "O",
                          "MENOR", "MAYOR", "ASIGNACION", "NO"])

    def test_booleanos_se_convierten_a_valor(self):
        toks, _ = tokens("verdadero falso")
        self.assertEqual([t.valor for t in toks[:-1]], [True, False])

    def test_cadenas_con_secuencias_de_escape(self):
        toks, _ = tokens(r'"hola \"mundo\"\n"')
        self.assertEqual(toks[0].valor, 'hola "mundo"\n')

    def test_coordenadas_despues_de_comentario_multilinea(self):
        toks, _ = tokens("entero a;\n/* uno\n dos */ real b;\n// fin\nimprimir(a);")
        reales = [t for t in toks if t.lexema == "real"]
        self.assertEqual((reales[0].linea, reales[0].columna), (3, 9))
        imprimir = [t for t in toks if t.tipo == "IMPRIMIR"][0]
        self.assertEqual((imprimir.linea, imprimir.columna), (5, 1))

    def test_errores_lexicos_no_detienen_el_analisis(self):
        toks, reporte = tokens('entero a = 5 @ 3;\nentero 2x = 1;\ntexto s = "abc\n/* abierto')
        errores = reporte.de_fase(LEXICO)
        self.assertEqual(len(errores), 4)
        self.assertEqual([e.linea for e in errores], [1, 2, 3, 4])
        self.assertIn("@", errores[0].mensaje)
        self.assertIn("2x", errores[1].mensaje)
        # El análisis continuó hasta el final
        self.assertEqual(toks[-1].tipo, "EOF")


if __name__ == "__main__":
    unittest.main()
