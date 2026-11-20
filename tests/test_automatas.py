import unittest

from dragon.automatas import (EPSILON, NFA, ParserRegex, construir_automatas,
                              verificar_tokens)
from dragon.lexer import tokenizar
from tests.ayudas import EJEMPLOS


class PruebasAutomatas(unittest.TestCase):
    def setUp(self):
        self.a = construir_automatas()

    def test_thompson_crea_transiciones_epsilon(self):
        nfa = NFA()
        ParserRegex("D+", nfa).construir()
        self.assertTrue(any(EPSILON in t for t in nfa.transiciones.values()))

    def test_el_dfa_no_tiene_transiciones_epsilon(self):
        for transiciones in self.a.dfa.transiciones.values():
            self.assertNotIn(EPSILON, transiciones)

    def test_hopcroft_minimiza_a_cinco_estados(self):
        # Igual a la matriz de la Semana 2: inicio, ID, entero, "entero.", real
        self.assertEqual(len(self.a.dfa.estados), 7)
        self.assertEqual(len(self.a.minimo.estados), 5)

    def test_reconocimiento(self):
        casos = {"vida": "ID", "_x9": "ID", "ñandú": "ID", "123": "ENTERO", "3.14": "REAL",
                 "3.": None, ".5": None, "9a": None}
        for lexema, token in casos.items():
            self.assertEqual(self.a.minimo.reconocer(lexema), token, lexema)

    def test_dfa_y_minimo_son_equivalentes(self):
        for lexema in ["a", "a1", "_", "0", "007", "1.5", "12.34", "1.", "1..2", "a.b"]:
            self.assertEqual(self.a.dfa.reconocer(lexema), self.a.minimo.reconocer(lexema), lexema)

    def test_verificacion_contra_el_lexer(self):
        tokens = tokenizar((EJEMPLOS / "programa_correcto.drg").read_text(encoding="utf-8"))
        revisados, diferencias = verificar_tokens(self.a.minimo, tokens)
        self.assertGreater(revisados, 50)
        self.assertEqual(diferencias, [])


if __name__ == "__main__":
    unittest.main()
