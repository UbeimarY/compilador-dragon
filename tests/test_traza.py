import io
import os
import unittest
from contextlib import redirect_stdout

from dragon.cli import main
from dragon.traza import (analizar, estado_fases, recorrido_como_texto, recorrido_linea,
                          tokens_coloreados)
from tests.ayudas import EJEMPLOS, RAIZ

PROGRAMAS = ["programa_correcto.drg", "programa_estres.drg", "programa_registros.drg",
             "programa_funciones.drg", "programa_memoria.drg"]


def leer(nombre: str) -> str:
    return (EJEMPLOS / nombre).read_text(encoding="utf-8")


def estados(nombre: str) -> list[str]:
    return [f["estado"] for f in estado_fases(analizar(leer(nombre)))]


class PruebasOrigenDeLinea(unittest.TestCase):
    def test_cada_cuadrupla_recuerda_su_linea(self):
        for nombre in PROGRAMAS:
            a = analizar(leer(nombre))
            if not a.compilo:
                continue
            for programa in (a.tac, a.tac_optimizado):
                sin_linea = [str(q) for q in programa.instrucciones if q.linea is None and q.op != "fin"]
                self.assertEqual(sin_linea, [], nombre)

    def test_solo_el_prologo_y_epilogo_de_main_no_tienen_linea(self):
        a = analizar(leer("programa_correcto.drg"))
        sin_linea = [i.opcode for i in a.codigo.instrucciones if i.linea is None]
        self.assertEqual(sin_linea, ["PUSH", "MOV", "MOV", "POP", "HLT"])

    def test_la_linea_no_cambia_la_igualdad_de_cuadruplas(self):
        from dragon.tac import Cuadrupla
        self.assertEqual(Cuadrupla("=", 1, None, "x", 3), Cuadrupla("=", 1, None, "x", 9))


class PruebasEstadoDeFases(unittest.TestCase):
    def test_programa_correcto_pasa_las_siete(self):
        self.assertEqual(estados("programa_correcto.drg"), ["ok"] * 7)

    def test_error_lexico_falla_en_la_fase_1(self):
        self.assertEqual(estados("errores/error_lexico.drg"),
                         ["fallo", "ok", "ok", "omitida", "omitida", "omitida", "omitida"])

    def test_error_sintactico_falla_en_la_fase_2(self):
        e = estados("errores/error_sintactico.drg")
        self.assertEqual(e[1], "fallo")
        self.assertEqual(e[3:], ["omitida"] * 4)

    def test_error_semantico_falla_en_la_fase_3(self):
        self.assertEqual(estados("errores/error_funciones.drg")[:3], ["ok", "ok", "fallo"])

    def test_error_de_ejecucion_falla_en_la_fase_7(self):
        for nombre in ("errores/error_memoria.drg", "errores/error_recursion.drg"):
            self.assertEqual(estados(nombre), ["ok"] * 6 + ["fallo"], nombre)


class PruebasTokensColoreados(unittest.TestCase):
    def test_categorias(self):
        toks = tokens_coloreados(analizar('entero x = 5; si (x > 2) { imprimir("hola"); }'))
        cat = {t["lexema"]: t["categoria"] for t in toks}
        self.assertEqual(cat["entero"], "tipo")
        self.assertEqual(cat["si"], "clave")
        self.assertEqual(cat["x"], "identificador")
        self.assertEqual(cat["5"], "numero")
        self.assertEqual(cat['"hola"'], "texto")
        self.assertEqual(cat[">"], "operador")
        self.assertEqual(cat[";"], "puntuacion")

    def test_los_errores_lexicos_aparecen_en_su_posicion(self):
        toks = tokens_coloreados(analizar("entero x = 1 # 2;"))
        errores = [t for t in toks if t["categoria"] == "error"]
        self.assertEqual(len(errores), 1)
        self.assertEqual(errores[0]["columna"], 14)
        self.assertLess(toks.index(errores[0]), [t["lexema"] for t in toks].index("2"))


class PruebasRecorridoDeLinea(unittest.TestCase):
    def setUp(self):
        self.a = analizar(leer("programa_correcto.drg"))

    def test_plegado_de_constantes(self):
        r = recorrido_linea(self.a, 9)["fases"]   # entero ataque_base = 10 * 2 + 5;
        self.assertEqual(len(r[4]["lineas"]), 3)
        self.assertEqual(len(r[5]["lineas"]), 1)
        self.assertIn("ataque_base = 25", r[5]["lineas"][0])
        self.assertIn("MOV", r[6]["lineas"][0])
        self.assertEqual(r[7]["nota"], "Se ejecutó 1 vez")

    def test_codigo_inalcanzable_desaparece_y_no_se_ejecuta(self):
        r = recorrido_linea(self.a, 31)["fases"]  # dentro de si (modo_depuracion)
        self.assertTrue(r[4]["lineas"])
        self.assertEqual(r[5]["lineas"], [])
        self.assertEqual(r[6]["lineas"], [])
        self.assertEqual(r[7]["nota"], "Nunca se ejecutó")

    def test_funcion_cuenta_sus_llamadas(self):
        r = recorrido_linea(self.a, 16)["fases"]  # funcion entero calcular_dano(...)
        self.assertIn("parámetro", "\n".join(r[3]["lineas"]))
        self.assertIn("fn_calcular_dano:", "\n".join(r[6]["lineas"]))
        self.assertEqual(r[7]["nota"], "La función se llamó 5 veces")

    def test_lineas_impresas_por_una_instruccion(self):
        a = analizar("entero i = 0;\nmientras (i < 3) {\n    imprimir(i);\n    i = i + 1;\n}")
        r = recorrido_linea(a, 3)["fases"]
        self.assertEqual(r[7]["lineas"], ["> 0", "> 1", "> 2"])
        self.assertIn("3 veces", r[7]["nota"])

    def test_errores_en_su_fase_y_fases_no_alcanzadas(self):
        a = analizar(leer("errores/error_lexico.drg"))
        r = recorrido_linea(a, 4)["fases"]       # vida = vida # 3;
        self.assertTrue(any("Carácter no permitido" in e for e in r[1]["errores"]))
        self.assertIn("No se alcanzó", r[4]["nota"])

    def test_linea_inexistente(self):
        self.assertIn("no existe", recorrido_como_texto(self.a, 999))


class PruebasOpcionLinea(unittest.TestCase):
    def ejecutar(self, *argumentos) -> tuple[int, str]:
        anterior = os.getcwd()
        os.chdir(RAIZ)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                codigo = main(list(argumentos) + ["--sin-color"])
            return codigo, buf.getvalue()
        finally:
            os.chdir(anterior)

    def test_codigos_de_salida(self):
        self.assertEqual(self.ejecutar("ejemplos/programa_correcto.drg", "--linea", "9")[0], 0)
        self.assertEqual(self.ejecutar("ejemplos/errores/error_lexico.drg", "--linea", "4")[0], 1)
        self.assertEqual(self.ejecutar("ejemplos/errores/error_recursion.drg", "--linea", "4")[0], 2)
        self.assertEqual(self.ejecutar("ejemplos/programa_correcto.drg", "--linea", "999")[0], 1)

    def test_muestra_las_siete_fases(self):
        _, texto = self.ejecutar("ejemplos/programa_correcto.drg", "--linea", "9")
        for n in range(1, 8):
            self.assertIn(f"── {n}.", texto)


if __name__ == "__main__":
    unittest.main()
