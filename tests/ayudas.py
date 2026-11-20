"""Funciones de apoyo para las pruebas: ejecutan el pipeline completo."""

from dataclasses import dataclass
from pathlib import Path

from dragon.codegen import CodigoObjetivo, generar_codigo
from dragon.emulador import EmuladorASM, EmuladorTAC
from dragon.errores import ReporteErrores
from dragon.interprete import interpretar
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


def compilar(codigo: str, registros: int = 3, asignador: str = "belady") -> Compilacion:
    c = frente(codigo)
    if c.reporte.hay_errores():
        raise AssertionError("Errores inesperados:\n" + "\n".join(map(str, c.reporte.errores)))
    c.tac = generar_tac(c.ast, c.semantico.tabla.todos, c.semantico.funciones)
    c.optimizado, _ = optimizar(c.tac)
    c.asm = generar_codigo(c.optimizado, registros, asignador)
    return c


def ejecuciones(codigo: str, registros: int = 3, asignador: str = "belady"):
    """Las cuatro ejecuciones: intérprete del AST, TAC, TAC optimizado y ensamblador."""
    c = compilar(codigo, registros, asignador)
    return (interpretar(c.ast, c.semantico.tabla.todos, c.semantico.funciones),
            EmuladorTAC(c.tac).ejecutar(), EmuladorTAC(c.optimizado).ejecutar(), EmuladorASM(c.asm).ejecutar())


def ejecutar(codigo: str, registros: int = 3, asignador: str = "belady", permitir_error: bool = False) -> list[str]:
    """Compila y ejecuta; verifica que las cuatro ejecuciones coincidan."""
    resultados = ejecuciones(codigo, registros, asignador)
    salidas = [r.salida for r in resultados]
    assert all(s == salidas[-1] for s in salidas), "Las salidas difieren:\n" + "\n".join(map(str, salidas))
    assert len({bool(r.error) for r in resultados}) == 1, [r.error for r in resultados]
    if not permitir_error:
        assert resultados[-1].error is None, resultados[-1].error
    return resultados[-1].salida


def errores_de(codigo: str, fase: str | None = None) -> list:
    reporte = frente(codigo).reporte
    return reporte.de_fase(fase) if fase else reporte.errores
