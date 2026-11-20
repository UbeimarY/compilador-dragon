import unittest

from dragon.ast_nodos import Conversion
from dragon.errores import SEMANTICO
from tests.ayudas import errores_de, frente


def mensajes(codigo):
    return [e.mensaje for e in errores_de(codigo, SEMANTICO)]


class PruebasTablaDeSimbolos(unittest.TestCase):
    def test_variable_no_declarada(self):
        self.assertIn("no ha sido declarada", mensajes("imprimir(x);")[0])

    def test_redeclaracion_en_el_mismo_ambito(self):
        self.assertIn("ya fue declarada", mensajes("entero a = 1; entero a = 2;")[0])

    def test_variable_fuera_de_su_ambito(self):
        errores = mensajes("{ entero secreto = 1; imprimir(secreto); } imprimir(secreto);")
        self.assertEqual(len(errores), 1)
        self.assertIn("secreto", errores[0])

    def test_ambito_interno_ve_variables_externas(self):
        self.assertEqual(mensajes("entero g = 1; { { imprimir(g); } }"), [])

    def test_ocultamiento_es_valido_y_genera_advertencia(self):
        c = frente("entero x = 1; { entero x = 2; imprimir(x); } imprimir(x);")
        self.assertFalse(c.reporte.hay_errores())
        self.assertTrue(any("oculta" in a.mensaje for a in c.reporte.advertencias))
        unicos = [s.nombre_unico for s in c.semantico.tabla.todos]
        self.assertEqual(unicos, ["x", "x_1"])

    def test_direcciones_alineadas_y_distintas(self):
        tabla = frente("booleano b = verdadero; real r = 1.0; entero e = 1; imprimir(b); imprimir(r); imprimir(e);").semantico.tabla
        direcciones = {s.nombre: s.direccion for s in tabla.todos}
        self.assertEqual(direcciones["r"] % 8, 0)
        self.assertEqual(direcciones["e"] % 4, 0)
        self.assertEqual(len(set(direcciones.values())), 3)


class PruebasChequeoDeTipos(unittest.TestCase):
    def test_coercion_entero_a_real(self):
        c = frente("real r = 2;")
        self.assertFalse(c.reporte.hay_errores())
        self.assertIsInstance(c.ast.instrucciones[0].valor, Conversion)

    def test_real_a_entero_es_error(self):
        self.assertIn("pérdida de precisión", mensajes("entero e = 2.5;")[0])

    def test_texto_menos_entero(self):
        self.assertIn("No se puede aplicar '-'", mensajes('entero v = 100 - "Fuego";')[0])

    def test_concatenacion_de_texto_valida(self):
        self.assertEqual(mensajes('texto s = "a" + "b";'), [])

    def test_condicion_debe_ser_booleana(self):
        self.assertIn("booleana", mensajes("si (1) { }")[0])
        self.assertIn("booleana", mensajes("mientras (1.5) { }")[0])

    def test_division_por_cero_literal(self):
        self.assertIn("División por cero", mensajes("entero a = 5 / 0;")[0])

    def test_modulo_solo_enteros(self):
        self.assertIn("'%'", mensajes("real r = 5.0 % 2;")[0])

    def test_operadores_logicos_requieren_booleanos(self):
        self.assertTrue(mensajes("booleano b = verdadero && 1;"))
        self.assertTrue(mensajes("booleano b = !5;"))

    def test_sin_errores_en_cascada(self):
        # 'nada' no existe: solo se reporta una vez aunque participe en una expresión grande
        self.assertEqual(len(mensajes("entero a = nada + 1 * 2 - 3;")), 1)


if __name__ == "__main__":
    unittest.main()
