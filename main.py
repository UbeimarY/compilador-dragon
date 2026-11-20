"""
Compilador Dragon — punto de entrada.

Uso:
    python main.py <archivo.drg> [opciones]

Opciones:
    --registros N     Número de registros físicos de la CPU simulada (por defecto 3, mínimo 2)
    --sin-optimizar   Genera el ensamblador directamente desde el TAC sin optimizar
    --fases 1,4,6     Muestra solo las fases indicadas (1 a 7)
    --sin-color       Desactiva los colores de la consola
    --salida DIR      Carpeta donde se guardan los archivos .tac y .asm (por defecto: salida/)

Ejemplos:
    python main.py ejemplos/programa_correcto.drg
    python main.py ejemplos/programa_estres.drg
    python main.py ejemplos/programa_registros.drg --registros 2
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from dragon.ast_nodos import arbol_ascii
from dragon.codegen import generar_codigo
from dragon.emulador import EmuladorASM, EmuladorTAC
from dragon.errores import LEXICO, SEMANTICO, SINTACTICO, ReporteErrores
from dragon.lexer import Lexer
from dragon.optimizador import optimizar
from dragon.parser import Parser
from dragon.semantico import AnalizadorSemantico
from dragon.tac import generar_tac
from dragon.utilidades import Color, formatear_valor

ANCHO = 78


def titulo(numero: int | None, texto: str) -> None:
    rotulo = f" FASE {numero} · {texto} " if numero else f" {texto} "
    print()
    print(Color.titulo("═" * ANCHO))
    print(Color.titulo(rotulo.center(ANCHO)))
    print(Color.titulo("═" * ANCHO))


def subtitulo(texto: str) -> None:
    print(Color.aviso(f"\n── {texto} " + "─" * max(0, ANCHO - len(texto) - 4)))


def mostrar_error_con_contexto(error, lineas_fuente: list[str]) -> None:
    color = Color.aviso if error.fase == "ADVERTENCIA" else Color.error
    print(color(str(error)))
    if 1 <= error.linea <= len(lineas_fuente):
        codigo = lineas_fuente[error.linea - 1].replace("\t", " ")
        print(Color.tenue(f"    {error.linea:>4} | ") + codigo)
        print(Color.tenue("         | ") + " " * max(0, error.columna - 1) + color("^"))


def compilar(ruta: Path, args: argparse.Namespace) -> int:
    fases = set(range(1, 8)) if not args.fases else {int(f) for f in args.fases.split(",")}
    ver = lambda n: n in fases

    fuente = ruta.read_text(encoding="utf-8")
    lineas_fuente = fuente.splitlines()
    reporte = ReporteErrores()

    print(Color.titulo(f"\n  COMPILADOR DRAGON — {ruta.name}  ({len(lineas_fuente)} líneas)"))

    # ------------------------------------------------------------ FASE 1
    tokens = Lexer(fuente, reporte).tokenizar()
    if ver(1):
        titulo(1, "ANÁLISIS LÉXICO (Tokens)")
        print(f"{'Línea':<7}{'Col':<6}{'Tipo':<14}Lexema")
        print("-" * 44)
        for t in tokens[:-1]:
            print(f"{t.linea:<7}{t.columna:<6}{t.tipo:<14}{t.lexema}")
        print(Color.tenue(f"\nTotal: {len(tokens) - 1} tokens · errores léxicos: {len(reporte.de_fase(LEXICO))}"))

    # ------------------------------------------------------------ FASE 2
    ast = Parser(tokens, reporte).parsear()
    if ver(2):
        titulo(2, "ANÁLISIS SINTÁCTICO (Árbol de Sintaxis Abstracta)")
        print(arbol_ascii(ast))
        print(Color.tenue(f"\nErrores sintácticos: {len(reporte.de_fase(SINTACTICO))}"))

    # ------------------------------------------------------------ FASE 3
    semantico = AnalizadorSemantico(reporte).analizar(ast)
    if ver(3):
        titulo(3, "ANÁLISIS SEMÁNTICO (Tabla de símbolos y tipos)")
        subtitulo("Tabla de símbolos")
        print(semantico.tabla.como_texto())
        subtitulo("Traza de ámbitos (pila de scopes)")
        print("\n".join(semantico.tabla.eventos) or "(sin declaraciones)")
        subtitulo("Coerciones implícitas insertadas")
        print("\n".join(semantico.coerciones) or "(ninguna)")
        print(Color.tenue(f"\nErrores semánticos: {len(reporte.de_fase(SEMANTICO))}"))

    if reporte.advertencias:
        subtitulo(f"Advertencias ({len(reporte.advertencias)})")
        for adv in sorted(reporte.advertencias, key=lambda e: (e.linea, e.columna)):
            mostrar_error_con_contexto(adv, lineas_fuente)

    if reporte.hay_errores():
        titulo(None, "REPORTE DE ERRORES")
        for error in reporte.ordenados():
            mostrar_error_con_contexto(error, lineas_fuente)
        conteo = {f: len(reporte.de_fase(f)) for f in (LEXICO, SINTACTICO, SEMANTICO)}
        print(Color.error(
            f"\nCompilación detenida: {len(reporte.errores)} error(es) — "
            f"léxicos: {conteo[LEXICO]}, sintácticos: {conteo[SINTACTICO]}, semánticos: {conteo[SEMANTICO]}."))
        print("No se genera código intermedio ni ensamblador para un programa con errores.")
        return 1

    # ------------------------------------------------------------ FASE 4
    tac = generar_tac(ast, semantico.tabla.todos)
    if ver(4):
        titulo(4, "CÓDIGO INTERMEDIO (TAC en cuádruplas)")
        print(tac.como_texto())
        subtitulo("Representación interna: cuádruplas (op, arg1, arg2, resultado)")
        print(tac.como_cuadruplas())

    # ------------------------------------------------------------ FASE 5
    tac_optimizado, optimizador = optimizar(tac)
    if ver(5):
        titulo(5, "OPTIMIZACIÓN DEL CÓDIGO INTERMEDIO")
        print(tac_optimizado.como_texto() or "(programa vacío)")
        subtitulo("Optimizaciones aplicadas")
        for categoria, detalle in optimizador.registro:
            print(f"  [{categoria}] {detalle}")
        if not optimizador.registro:
            print("  (ninguna: el código ya era óptimo)")
        subtitulo("Resumen")
        for categoria, cantidad in optimizador.resumen().most_common():
            print(f"  {categoria:<30}{cantidad:>4}")
        antes, despues = len(tac.instrucciones), len(tac_optimizado.instrucciones)
        reduccion = 100 * (antes - despues) / antes if antes else 0
        print(Color.ok(f"\n  Instrucciones TAC: {antes} → {despues}  ({reduccion:.1f}% menos)"))

    # ------------------------------------------------------------ FASE 6
    base_codigo = tac if args.sin_optimizar else tac_optimizado
    codigo = generar_codigo(base_codigo, args.registros)
    if ver(6):
        titulo(6, f"GENERACIÓN DE CÓDIGO OBJETIVO ({args.registros} registros: "
                  f"{', '.join(f'R{i}' for i in range(args.registros))})")
        subtitulo("Asignación de registros (análisis de vida + spill)")
        print("\n".join(codigo.eventos) or "(no se necesitaron temporales en registros)")
        estado = Color.aviso(f"{codigo.spills} spill(s) → marco de pila de {codigo.tamanio_marco} bytes") \
            if codigo.spills else Color.ok("0 spills: todos los temporales cupieron en registros")
        print(f"\n  {estado}")
        subtitulo("Ensamblador generado")
        print(codigo.como_texto())

    # ------------------------------------------------------------ FASE 7
    ejec_tac = EmuladorTAC(tac).ejecutar()
    ejec_opt = EmuladorTAC(tac_optimizado).ejecutar()
    ejec_asm = EmuladorASM(codigo).ejecutar()
    if ver(7):
        titulo(7, "VERIFICACIÓN: EJECUCIÓN Y PRESERVACIÓN DE LA SEMÁNTICA")
        subtitulo("Salida del programa (ejecutando el ensamblador)")
        for linea in ejec_asm.salida:
            print(f"  > {linea}")
        if ejec_asm.error:
            print(Color.error(f"  [ERROR DE EJECUCIÓN] {ejec_asm.error}"))
        subtitulo("Estado final de la memoria (.data)")
        for nombre, valor in ejec_asm.memoria.items():
            if tac.tipos.get(nombre) == "booleano":
                valor = bool(valor)  # en la máquina los booleanos son 1 / 0
            print(f"  {nombre:<18}= {formatear_valor(valor)}  ({tac.tipos.get(nombre)})")
        subtitulo("Comparación de las tres ejecuciones")
        for nombre, r in (("TAC original", ejec_tac), ("TAC optimizado", ejec_opt), ("Ensamblador", ejec_asm)):
            print(f"  {nombre:<16}{len(r.salida):>3} líneas impresas · {r.pasos:>6} pasos"
                  + (f" · error: {r.error}" if r.error else ""))
        iguales = ejec_tac.salida == ejec_opt.salida == ejec_asm.salida and \
            bool(ejec_tac.error) == bool(ejec_opt.error) == bool(ejec_asm.error)
        if iguales:
            print(Color.ok("\n  ✓ Las tres ejecuciones producen la misma salida: la semántica se preservó."))
        else:
            print(Color.error("\n  ✗ Las salidas difieren: revisar optimizador o generador de código."))

    # ------------------------------------------------------ archivos de salida
    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{ruta.stem}.tac").write_text(tac.como_texto() + "\n", encoding="utf-8")
    (carpeta / f"{ruta.stem}.opt.tac").write_text(tac_optimizado.como_texto() + "\n", encoding="utf-8")
    (carpeta / f"{ruta.stem}.asm").write_text(codigo.como_texto() + "\n", encoding="utf-8")
    print(Color.ok(f"\n  Compilación exitosa. Archivos generados en {carpeta}/: "
                   f"{ruta.stem}.tac, {ruta.stem}.opt.tac, {ruta.stem}.asm"))
    return 0 if ejec_asm.ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Compilador Dragon: Tokens → AST → Semántico → TAC → Optimización → Ensamblador",
    )
    parser.add_argument("archivo", help="programa fuente .drg")
    parser.add_argument("--registros", type=int, default=3, help="registros físicos disponibles (mínimo 2)")
    parser.add_argument("--sin-optimizar", action="store_true", help="no optimizar antes de generar ensamblador")
    parser.add_argument("--fases", help="fases a mostrar, separadas por comas (1-7)")
    parser.add_argument("--sin-color", action="store_true", help="desactiva colores ANSI")
    parser.add_argument("--salida", default="salida", help="carpeta para los archivos generados")
    parser.add_argument("--depurar", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.sin_color:
        Color.desactivar()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.registros < 2:
        print(Color.error("Se necesitan al menos 2 registros (--registros 2 o más)."))
        return 1

    ruta = Path(args.archivo)
    if not ruta.is_file():
        print(Color.error(f"No se encontró el archivo '{ruta}'."))
        return 1

    try:
        return compilar(ruta, args)
    except Exception as e:  # Nunca se muestra un traceback crudo al usuario
        print(Color.error(f"\n[ERROR INTERNO DEL COMPILADOR] {type(e).__name__}: {e}"))
        if args.depurar:
            traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
