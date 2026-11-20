"""
Compilador Dragon — interfaz de línea de comandos.

Uso (cualquiera de las tres formas):
    python main.py <archivo.drg> [opciones]      # desde la carpeta del repositorio
    python -m dragon <archivo.drg> [opciones]
    dragon <archivo.drg> [opciones]               # si se instaló con pip

Opciones:
    --registros N     Número de registros físicos de la CPU simulada (por defecto 3, mínimo 2)
    --sin-optimizar   Genera el ensamblador directamente desde el TAC sin optimizar
    --automatas       Muestra los autómatas del lexer: RegEx → NFA → DFA → DFA mínimo
    --interpretar     Ejecuta el programa con el intérprete del AST (sin compilarlo)
    --asignador X     Asignación de registros: belady (local, por defecto) o coloreo (Chaitin-Briggs)
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
import os
import sys
import traceback
from pathlib import Path

from .ast_nodos import arbol_ascii
from .automatas import construir_automatas, verificar_tokens
from .codegen import generar_codigo
from .emulador import EmuladorASM, EmuladorTAC
from .flujo import construir_grafo, grafo_como_texto, grafo_dot
from .interprete import interpretar
from .errores import LEXICO, SEMANTICO, SINTACTICO, ReporteErrores
from .lexer import Lexer
from .optimizador import optimizar
from .parser import Parser
from .semantico import AnalizadorSemantico
from .tac import generar_tac
from .traza import analizar, recorrido_como_texto
from .utilidades import Color, formatear_valor

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


def ruta_segura(relativa: str, base: str) -> str | None:
    """Resuelve una ruta recibida por línea de comandos y garantiza que quede
    DENTRO de la carpeta base. Evita ataques de Path Traversal (por ejemplo
    `../../etc/passwd`): si la ruta real sale de la base, se rechaza."""
    base_real = os.path.realpath(base)
    ruta_real = os.path.realpath(os.path.join(base_real, relativa))
    if ruta_real == base_real or ruta_real.startswith(base_real + os.sep):
        return ruta_real
    return None


def escribir_salida(carpeta: str, nombre: str, contenido: str) -> None:
    destino = ruta_segura(nombre, carpeta)
    if destino is None:
        raise ValueError(f"Nombre de archivo de salida no permitido: {nombre}")
    with open(destino, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)


def mostrar_automatas(tokens) -> None:
    a = construir_automatas()
    titulo(None, "AUTÓMATAS DEL LEXER (Semana 2): RegEx → NFA → DFA → DFA mínimo")
    subtitulo("1. Expresiones regulares (L = letra o _, D = dígito, . = punto)")
    for token, regex, _, _ in a.detalle:
        print(f"  {token:<8} {regex}")
    subtitulo("2. NFA por construcción de Thompson")
    for token, regex, estados, final in a.detalle:
        print(f"  {token:<8} {estados:>2} estados nuevos · estado de aceptación q{final}")
    print(f"  NFA combinado: {a.nfa.total} estados y {a.nfa.num_aristas()} transiciones "
          f"(q0 se une a los tres con ε)")
    subtitulo("3. DFA por construcción de subconjuntos")
    for nombre in a.dfa.estados:
        print(f"  {nombre} = ε-cerradura {{{', '.join(f'q{e}' for e in sorted(a.dfa.composicion[nombre]))}}}")
    print()
    print(a.dfa.matriz())
    subtitulo("4. Minimización de Hopcroft (∅ = estado muerto)")
    for paso in a.traza:
        print(f"  {paso}")
    print(f"\n  {len(a.dfa.estados)} estados → {len(a.minimo.estados)} estados en el DFA mínimo\n")
    print(a.minimo.matriz())
    subtitulo("5. Verificación: cada número e identificador del programa pasa por el DFA mínimo")
    revisados, diferencias = verificar_tokens(a.minimo, tokens)
    for d in diferencias:
        print(Color.error(f"  {d}"))
    if not diferencias:
        print(Color.ok(f"  ✓ {revisados} lexemas: el DFA mínimo los clasifica igual que el lexer"))


def compilar(ruta: Path, carpeta_salida: str, args: argparse.Namespace) -> int:
    fases = set(range(1, 8)) if not args.fases else {int(f) for f in args.fases.split(",")}
    ver = lambda n: n in fases

    fuente = ruta.read_text(encoding="utf-8")
    lineas_fuente = fuente.splitlines()
    reporte = ReporteErrores()

    print(Color.titulo(f"\n  COMPILADOR DRAGON — {ruta.name}  ({len(lineas_fuente)} líneas)"))

    if args.linea is not None:
        titulo(None, f"RECORRIDO DE LA LÍNEA {args.linea} POR LAS 7 FASES")
        analisis = analizar(fuente, args.registros, not args.sin_optimizar, args.asignador)
        print(recorrido_como_texto(analisis, args.linea))
        if not 1 <= args.linea <= len(lineas_fuente):
            return 1
        return analisis.codigo_salida

    # ------------------------------------------------------------ FASE 1
    tokens = Lexer(fuente, reporte).tokenizar()
    if ver(1):
        titulo(1, "ANÁLISIS LÉXICO (Tokens)")
        print(f"{'Línea':<7}{'Col':<6}{'Tipo':<14}Lexema")
        print("-" * 44)
        for t in tokens[:-1]:
            print(f"{t.linea:<7}{t.columna:<6}{t.tipo:<14}{t.lexema}")
        print(Color.tenue(f"\nTotal: {len(tokens) - 1} tokens · errores léxicos: {len(reporte.de_fase(LEXICO))}"))
    if args.automatas:
        mostrar_automatas(tokens)

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
        if semantico.funciones:
            subtitulo("Funciones declaradas (firmas)")
            print(semantico.funciones_como_texto())
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

    if args.interpretar:
        titulo(None, "INTÉRPRETE DEL AST (sin compilar: recorre el árbol y lo ejecuta)")
        resultado = interpretar(ast, semantico.tabla.todos, semantico.funciones)
        for linea in resultado.salida:
            print(f"  > {linea}")
        if resultado.error:
            print(Color.error(f"  [ERROR DE EJECUCIÓN] {resultado.error}"))
        if resultado.heap.reservas:
            print(f"\n  Heap: {resultado.heap.resumen()}")
        print(Color.tenue(f"\n  {resultado.pasos} nodos evaluados. Un intérprete no genera código: "
                          "vuelve a recorrer el árbol en cada ejecución."))
        return 0 if resultado.ok else 2

    # ------------------------------------------------------------ FASE 4
    tac = generar_tac(ast, semantico.tabla.todos, semantico.funciones)
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
        subtitulo("Grafo de flujo de control (bloques básicos del TAC optimizado)")
        print(grafo_como_texto(tac_optimizado, construir_grafo(tac_optimizado)))

    # ------------------------------------------------------------ FASE 6
    base_codigo = tac if args.sin_optimizar else tac_optimizado
    codigo = generar_codigo(base_codigo, args.registros, args.asignador)
    if ver(6):
        titulo(6, f"GENERACIÓN DE CÓDIGO OBJETIVO ({args.registros} registros: "
                  f"{', '.join(f'R{i}' for i in range(args.registros))})")
        subtitulo("Asignación de registros: coloreo de grafos (Chaitin-Briggs)" if args.asignador == "coloreo"
                  else "Asignación de registros (análisis de vida + spill, criterio de Belady)")
        print("\n".join(codigo.eventos) or "(no se necesitaron temporales en registros)")
        estado = Color.aviso(f"{codigo.spills} spill(s) → marco de pila de {codigo.tamanio_marco} bytes") \
            if codigo.spills else Color.ok("0 spills: todos los temporales cupieron en registros")
        print(f"\n  {estado}")
        if len(codigo.marcos) > 1:
            subtitulo("Marcos de pila (stack frames)")
            for nombre, locales, ranuras, bytes_marco in codigo.marcos:
                print(f"  {nombre:<20} {locales} local(es) + {ranuras} ranura(s) de spill = {bytes_marco} bytes")
        subtitulo("Ensamblador generado")
        print(codigo.como_texto())

    # ------------------------------------------------------------ FASE 7
    ejec_tac = EmuladorTAC(tac).ejecutar()
    ejec_opt = EmuladorTAC(tac_optimizado).ejecutar()
    ejec_asm = EmuladorASM(codigo).ejecutar()
    ejec_ast = interpretar(ast, semantico.tabla.todos, semantico.funciones)
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
            print(f"  {nombre:<18}= {ejec_asm.heap.mostrar(valor)}  ({tac.tipos.get(nombre)})")
        if ejec_asm.heap.reservas:
            subtitulo("Heap (memoria dinámica)")
            print(f"  {ejec_asm.heap.resumen()}")
            for direccion, contenido, tam in ejec_asm.heap.fugas():
                print(Color.aviso(f"  fuga: bloque 0x{direccion:04X} ({tam} bytes) con \"{contenido}\" nunca se liberó"))
        subtitulo("Comparación de las cuatro ejecuciones")
        ejecuciones = (("Intérprete AST", ejec_ast), ("TAC original", ejec_tac),
                       ("TAC optimizado", ejec_opt), ("Ensamblador", ejec_asm))
        for nombre, r in ejecuciones:
            print(f"  {nombre:<16}{len(r.salida):>3} líneas impresas · {r.pasos:>6} pasos"
                  + (f" · error: {r.error}" if r.error else ""))
        iguales = all(r.salida == ejec_asm.salida and bool(r.error) == bool(ejec_asm.error)
                      for _, r in ejecuciones)
        if iguales:
            print(Color.ok("\n  ✓ Las cuatro ejecuciones producen la misma salida: la semántica se preservó."))
        else:
            print(Color.error("\n  ✗ Las salidas difieren: revisar optimizador o generador de código."))

    # ------------------------------------------------------ archivos de salida
    os.makedirs(carpeta_salida, exist_ok=True)
    escribir_salida(carpeta_salida, f"{ruta.stem}.tac", tac.como_texto() + "\n")
    escribir_salida(carpeta_salida, f"{ruta.stem}.opt.tac", tac_optimizado.como_texto() + "\n")
    escribir_salida(carpeta_salida, f"{ruta.stem}.asm", codigo.como_texto() + "\n")
    escribir_salida(carpeta_salida, f"{ruta.stem}.cfg.dot",
                    grafo_dot(tac_optimizado, construir_grafo(tac_optimizado), ruta.stem) + "\n")
    if args.automatas:
        escribir_salida(carpeta_salida, "automata_lexer.dot", construir_automatas().minimo.dot("DFA mínimo") + "\n")
    carpeta = os.path.relpath(carpeta_salida)
    print(Color.ok(f"\n  Compilación exitosa. Archivos generados en {carpeta}/: "
                   f"{ruta.stem}.tac, {ruta.stem}.opt.tac, {ruta.stem}.asm, {ruta.stem}.cfg.dot"))
    return 0 if ejec_asm.ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compilador Dragon: Tokens → AST → Semántico → TAC → Optimización → Ensamblador",
    )
    parser.add_argument("archivo", help="programa fuente .drg")
    parser.add_argument("--registros", type=int, default=3, help="registros físicos disponibles (mínimo 2)")
    parser.add_argument("--sin-optimizar", action="store_true", help="no optimizar antes de generar ensamblador")
    parser.add_argument("--asignador", choices=["belady", "coloreo"], default="belady",
                        help="algoritmo de asignación de registros")
    parser.add_argument("--interpretar", action="store_true", help="ejecutar con el intérprete del AST, sin compilar")
    parser.add_argument("--automatas", action="store_true", help="mostrar los autómatas del lexer (NFA, DFA, DFA mínimo)")
    parser.add_argument("--fases", help="fases a mostrar, separadas por comas (1-7)")
    parser.add_argument("--linea", type=int, metavar="N",
                        help="seguir la línea N del programa por las 7 fases")
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

    # Seguridad: las rutas recibidas por consola deben quedar dentro de la
    # carpeta de trabajo actual (protección contra Path Traversal).
    base = os.getcwd()
    archivo_validado = ruta_segura(args.archivo, base)
    carpeta_salida = ruta_segura(args.salida, base)
    if archivo_validado is None or carpeta_salida is None:
        print(Color.error("Por seguridad, el archivo fuente y la carpeta de salida deben estar "
                          "dentro de la carpeta actual del proyecto."))
        return 1
    if not archivo_validado.endswith(".drg"):
        print(Color.error(f"El archivo '{args.archivo}' no tiene la extensión .drg de un programa Dragon."))
        return 1
    if not os.path.isfile(archivo_validado):
        print(Color.error(f"No se encontró el archivo '{args.archivo}'."))
        return 1

    try:
        return compilar(Path(archivo_validado), carpeta_salida, args)
    except Exception as e:  # Nunca se muestra un traceback crudo al usuario
        print(Color.error(f"\n[ERROR INTERNO DEL COMPILADOR] {type(e).__name__}: {e}"))
        if args.depurar:
            traceback.print_exc()
        return 3

