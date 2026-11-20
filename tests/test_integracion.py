import contextlib
import io
import tempfile
import unittest

import main
from dragon.errores import LEXICO, SEMANTICO, SINTACTICO
from tests.ayudas import EJEMPLOS, RAIZ, ejecutar, frente


def ejecutar_main(*argumentos):
    # La carpeta de salida debe estar dentro del proyecto (protección contra Path Traversal)
    with tempfile.TemporaryDirectory(dir=RAIZ) as carpeta, contextlib.redirect_stdout(io.StringIO()) as salida:
        codigo = main.main([*argumentos, "--sin-color", "--salida", carpeta])
    return codigo, salida.getvalue()


class PruebasIntegracion(unittest.TestCase):
    def test_programa_correcto_salida_esperada(self):
        salida = ejecutar((EJEMPLOS / "programa_correcto.drg").read_text(encoding="utf-8"))
        self.assertEqual(salida, [
            "Comienza la batalla de Aria",
            "1", "94", "2", "74", "¡Golpe crítico!", "37.5", "3", "24",
            "4", "4", "5", "0", "Aria derrotó al dragón", "24.0",
        ])

    def test_programa_correcto_compila_sin_errores(self):
        codigo, salida = ejecutar_main(str(EJEMPLOS / "programa_correcto.drg"))
        self.assertEqual(codigo, 0)
        for fase in range(1, 8):
            self.assertIn(f"FASE {fase}", salida)
        self.assertIn("la semántica se preservó", salida)

    def test_programa_estres_reporta_todos_los_errores(self):
        reporte = frente((EJEMPLOS / "programa_estres.drg").read_text(encoding="utf-8")).reporte
        self.assertEqual(len(reporte.de_fase(LEXICO)), 2)
        self.assertEqual(len(reporte.de_fase(SINTACTICO)), 2)
        self.assertEqual(len(reporte.de_fase(SEMANTICO)), 12)

    def test_programa_estres_no_se_detiene_abruptamente(self):
        codigo, salida = ejecutar_main(str(EJEMPLOS / "programa_estres.drg"))
        self.assertEqual(codigo, 1)
        self.assertIn("Compilación detenida: 16 error(es)", salida)
        self.assertNotIn("Traceback", salida)

    def test_ejemplos_de_errores(self):
        for nombre, fase in (("error_lexico", LEXICO), ("error_sintactico", SINTACTICO), ("error_semantico", SEMANTICO)):
            reporte = frente((EJEMPLOS / "errores" / f"{nombre}.drg").read_text(encoding="utf-8")).reporte
            self.assertTrue(reporte.errores, nombre)
            self.assertTrue(all(e.fase == fase for e in reporte.errores), nombre)

    def test_programa_registros(self):
        for n in ("2", "3", "6"):
            codigo, salida = ejecutar_main(str(EJEMPLOS / "programa_registros.drg"), "--registros", n)
            self.assertEqual(codigo, 0)
            self.assertIn("la semántica se preservó", salida)

    def test_rechaza_path_traversal_en_archivo(self):
        codigo, salida = ejecutar_main("../../etc/passwd.drg")
        self.assertEqual(codigo, 1)
        self.assertIn("Por seguridad", salida)

    def test_rechaza_path_traversal_en_carpeta_de_salida(self):
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            codigo = main.main([str(EJEMPLOS / "programa_correcto.drg"), "--sin-color", "--salida", "../../tmp/ataque"])
        self.assertEqual(codigo, 1)
        self.assertIn("Por seguridad", salida.getvalue())

    def test_rechaza_extension_distinta_de_drg(self):
        codigo, salida = ejecutar_main("README.md")
        self.assertEqual(codigo, 1)
        self.assertIn(".drg", salida)

    def test_archivo_inexistente(self):
        codigo, salida = ejecutar_main("no_existe.drg")
        self.assertEqual(codigo, 1)
        self.assertIn("No se encontró", salida)


if __name__ == "__main__":
    unittest.main()
