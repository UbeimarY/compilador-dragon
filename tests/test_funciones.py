import unittest

from dragon.errores import SEMANTICO, SINTACTICO
from tests.ayudas import EJEMPLOS, compilar, ejecuciones, ejecutar, errores_de, frente


def mensajes(codigo):
    return [e.mensaje for e in errores_de(codigo, SEMANTICO)]


class PruebasFuncionesSemantica(unittest.TestCase):
    def test_numero_de_argumentos(self):
        self.assertIn("espera 1 argumento(s), pero recibió 2",
                      mensajes("funcion entero f(entero x) { retornar x; } imprimir(f(1, 2));")[0])

    def test_tipo_de_argumento(self):
        self.assertIn("El argumento 1 de 'f' debe ser entero",
                      mensajes('funcion entero f(entero x) { retornar x; } imprimir(f("a"));')[0])

    def test_coercion_en_argumento(self):
        c = frente("funcion real f(real x) { retornar x; } imprimir(f(2));")
        self.assertFalse(c.reporte.hay_errores())
        self.assertTrue(any("argumento 1" in x for x in c.semantico.coerciones))

    def test_tipo_de_retorno(self):
        self.assertIn("El valor retornado por 'f' debe ser texto",
                      mensajes("funcion texto f() { retornar 1; }")[0])

    def test_funcion_sin_retornar(self):
        self.assertIn("debe retornar un valor", mensajes("funcion entero f() { imprimir(1); }")[0])

    def test_vacio_no_se_usa_como_valor(self):
        self.assertIn("es vacio", mensajes("funcion vacio f() { } entero x = f();")[0])

    def test_retornar_fuera_de_funcion(self):
        self.assertIn("solo puede usarse dentro de una función", mensajes("retornar 1;")[0])

    def test_funcion_no_declarada_y_duplicada(self):
        self.assertIn("no ha sido declarada", mensajes("imprimir(g(1));")[0])
        self.assertIn("ya fue declarada", mensajes("funcion vacio f() { } funcion vacio f() { }")[0])

    def test_funcion_dentro_de_bloque_es_error_sintactico(self):
        errores = errores_de("{ funcion vacio f() { } }", SINTACTICO)
        self.assertIn("nivel global", errores[0].mensaje)

    def test_parametros_y_locales_viven_en_el_marco(self):
        c = frente("funcion entero f(entero a, entero b) { entero c = a + b; retornar c; } imprimir(f(1, 2));")
        ubicacion = {s.nombre: s.ubicacion for s in c.semantico.tabla.todos}
        self.assertEqual(ubicacion, {"a": "FP+24", "b": "FP+16", "c": "FP-8"})

    def test_llamar_funcion_declarada_mas_abajo(self):
        self.assertEqual(ejecutar("imprimir(f()); funcion entero f() { retornar 7; }"), ["7"])


class PruebasFuncionesEjecucion(unittest.TestCase):
    def test_recursion(self):
        codigo = ("funcion entero fact(entero n) { si (n <= 1) { retornar 1; } retornar n * fact(n - 1); }"
                  "funcion entero fib(entero n) { si (n < 2) { retornar n; } retornar fib(n - 1) + fib(n - 2); }"
                  "imprimir(fact(6)); imprimir(fib(12));")
        for n in (2, 3, 6):
            self.assertEqual(ejecutar(codigo, registros=n), ["720", "144"])

    def test_temporales_vivos_a_traves_de_una_llamada(self):
        codigo = ("funcion entero doble(entero x) { retornar x * 2; } entero a = 3; entero b = 4;"
                  "mientras (a < 4) { imprimir(a * 2 + doble(a) * (b + doble(b))); a = a + 1; }")
        for asignador in ("belady", "coloreo"):
            self.assertEqual(ejecutar(codigo, registros=2, asignador=asignador), ["78"])

    def test_funcion_modifica_una_global(self):
        codigo = ("entero c = 10; funcion entero inc() { c = c + 1; retornar c; }"
                  "imprimir(inc() + c); imprimir(c);")
        self.assertEqual(ejecutar(codigo), ["22", "11"])

    def test_programa_funciones(self):
        salida = ejecutar((EJEMPLOS / "programa_funciones.drg").read_text(encoding="utf-8"))
        self.assertEqual(salida, ["720", "6", "144", "12", "verdadero", "falso", "12.5664",
                                  "Aria obtiene puntos:", "8"])

    def test_convencion_de_llamada_en_ensamblador(self):
        texto = compilar("funcion entero f(entero x) { retornar x + 1; } imprimir(f(2));").asm.como_texto()
        for fragmento in ("PUSH     2", "CALL     fn_f", "ADD      SP, 8", "fn_f:", "MOV      RV", "RET"):
            self.assertIn(fragmento, texto)

    def test_stack_overflow(self):
        resultados = ejecuciones("funcion entero f(entero n) { retornar f(n + 1); } imprimir(f(0));")
        for r in resultados:
            self.assertIn("Stack Overflow", r.error)


if __name__ == "__main__":
    unittest.main()
