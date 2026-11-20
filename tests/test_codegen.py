import re
import unittest

from tests.ayudas import EJEMPLOS, compilar, ejecutar

EXPRESION_PESADA = """
entero a = 7; entero b = 3; entero c = 10; entero d = 4;
entero e = 2; entero f = 9; entero g = 5; entero h = 1;
mientras (h < 2) {
    imprimir((a + b) * (c + d) - (e + f) * (g + h) + (a - b) * ((c - d) * (e - f) + (g - h) * (a + h)));
    h = h + 1;
}
"""


class PruebasGeneracionDeCodigo(unittest.TestCase):
    def test_nunca_dos_operandos_de_memoria(self):
        for archivo in ("programa_correcto.drg", "programa_registros.drg"):
            asm = compilar((EJEMPLOS / archivo).read_text(encoding="utf-8"), registros=2).asm
            for ins in asm.instrucciones:
                memorias = [o for o in ins.operandos if o.startswith("[")]
                self.assertLessEqual(len(memorias), 1, f"{archivo}: {ins}")

    def test_solo_usa_los_registros_disponibles(self):
        for n in (2, 3, 4):
            asm = compilar(EXPRESION_PESADA, registros=n).asm
            usados = set(re.findall(r"\bR(\d+)\b", asm.como_texto()))
            self.assertTrue(all(int(r) < n for r in usados))

    def test_spill_cuando_faltan_registros(self):
        con_2 = compilar(EXPRESION_PESADA, registros=2).asm
        con_8 = compilar(EXPRESION_PESADA, registros=8).asm
        self.assertGreater(con_2.spills, 0)
        self.assertEqual(con_8.spills, 0)
        self.assertIn("SPILL", con_2.como_texto())

    def test_resultado_correcto_con_cualquier_numero_de_registros(self):
        for n in (2, 3, 4, 6):
            self.assertEqual(ejecutar(EXPRESION_PESADA, registros=n), ["34"])

    def test_seleccion_de_instrucciones_por_tipo(self):
        texto = compilar("real r = 1.5; entero e = 2; mientras (e > 0) { r = r * 2.0; e = e - 1; } imprimir(r); imprimir(e);").asm.como_texto()
        self.assertIn("FMUL", texto)
        self.assertIn("SUB", texto)
        self.assertIn("real_0", texto)  # constantes reales van a .data

    def test_semantica_de_division_y_modulo_enteros(self):
        salida = ejecutar("entero a = -7; entero b = 2; mientras (b > 1) { imprimir(a / b); imprimir(a % b); b = 0; }")
        self.assertEqual(salida, ["-3", "-1"])  # truncamiento hacia cero, como en C


if __name__ == "__main__":
    unittest.main()
