"""Funciones de apoyo para las pruebas: ejecutan el pipeline completo."""

from dataclasses import dataclass
from pathlib import Path

from dragon.codegen import CodigoObjetivo, generar_codigo
from dragon.emulador import EmuladorASM, EmuladorTAC
from dragon.errores import ReporteErrores
from dragon.lexer import Lexer
from dragon.optimizador import optimizar
from dragon.parser import Parser
from dragon.semantico import AnalizadorSemantico
from dragon.tac import ProgramaTAC, generar_tac

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLOS = RAIZ / "ejemplos"


@dataclass
class Compilacion:
    reporte: ReporteErrores
    ast: object
    semantico: object
    tac: ProgramaTAC | None = None
    optimizado: ProgramaTAC | None = None
    asm: CodigoObjetivo | None = None


def frente(codigo: str) -> Compilacion:
    """Ejecuta solo las fases de análisis (léxico, sintáctico, semántico)."""
    reporte = ReporteErrores()
    tokens = Lexer(codigo, reporte).tokenizar()
    ast = Parser(tokens, reporte).parsear()
    semantico = AnalizadorSemantico(reporte).analizar(ast)
    return Compilacion(reporte, ast, semantico)


def compilar(codigo: str, registros: int = 3) -> Compilacion:
    c = frente(codigo)
    if c.reporte.hay_errores():
        raise AssertionError("Errores inesperados:\n" + "\n".join(map(str, c.reporte.errores)))
    c.tac = generar_tac(c.ast, c.semantico.tabla.todos)
    c.optimizado, _ = optimizar(c.tac)
    c.asm = generar_codigo(c.optimizado, registros)
    return c


def ejecutar(codigo: str, registros: int = 3) -> list[str]:
    """Compila y ejecuta; verifica que TAC, TAC optimizado y ASM coincidan."""
    c = compilar(codigo, registros)
    salida_tac = EmuladorTAC(c.tac).ejecutar()
    salida_opt = EmuladorTAC(c.optimizado).ejecutar()
    salida_asm = EmuladorASM(c.asm).ejecutar()
    assert salida_tac.salida == salida_opt.salida == salida_asm.salida, (
        f"Las salidas difieren:\nTAC: {salida_tac.salida}\nOPT: {salida_opt.salida}\nASM: {salida_asm.salida}")
    assert salida_asm.error is None, salida_asm.error
    return salida_asm.salida


def errores_de(codigo: str, fase: str | None = None) -> list:
    reporte = frente(codigo).reporte
    return reporte.de_fase(fase) if fase else reporte.errores
