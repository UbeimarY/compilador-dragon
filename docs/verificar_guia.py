"""
Ejecuta todos los pasos de la guía de estudio y comprueba cada resultado
========================================================================

Uso (desde la carpeta compilador-dragon):

    python docs/verificar_guia.py          # Windows, Mac o Linux
    python docs/verificar_guia.py --pip    # además prueba la instalación con pip (necesita internet)

Corre los pasos 2 a 12 de la guía, los ejemplos de errores, los ejercicios 9 y 10,
las opciones avanzadas y el guion de la sustentación. Compara cada resultado con
lo que la guía dice que debe salir, muestra un resumen con ✓ y ✗, y guarda la
salida completa de cada comando en registro_guia.txt.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
REGISTRO = REPO / "registro_guia.txt"
resultados: list[tuple[str, str, bool, str]] = []
registro: list[str] = []


def correr(*argumentos: str) -> tuple[int, str]:
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, *argumentos], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=entorno)
    salida = p.stdout + p.stderr
    registro.append(f"\n$ python {' '.join(argumentos)}\n(código de salida {p.returncode})\n{salida}")
    return p.returncode, salida


def compilar(*argumentos: str) -> tuple[int, str]:
    return correr("main.py", *argumentos, "--sin-color")


def chequear(paso: str, descripcion: str, ok: bool, real: str) -> None:
    resultados.append((paso, descripcion, bool(ok), real))
    print(f"  {'✓' if ok else '✗'} {paso:<9} {descripcion}")


def linea_con(texto: str, prefijo: str) -> str:
    return next((l.strip() for l in texto.splitlines() if l.strip().startswith(prefijo)), "")


def impresas(texto: str) -> list[str]:
    return re.findall(r"^  > (.*)$", texto, re.M)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"Ejecutando la guía de estudio en {REPO}\n")

    # Paso 2 — Python
    version = sys.version_info
    chequear("Paso 2", "Python 3.10 o superior", version >= (3, 10), sys.version.split()[0])

    # Paso 4 — pruebas
    c, s = correr("-m", "unittest")
    m = re.search(r"Ran (\d+) tests in ([\d.]+)s", s)
    chequear("Paso 4", "python -m unittest → Ran 113 tests … OK",
             c == 0 and m and m.group(1) == "113", f"Ran {m.group(1)} tests en {m.group(2)} s" if m else s[-200:])

    # Paso 5 — programa completo
    c, s = compilar("ejemplos/programa_correcto.drg")
    chequear("Paso 5", "la salida tiene unas 970 líneas", 900 <= len(s.splitlines()) <= 1000, f"{len(s.splitlines())} líneas")
    chequear("Paso 5", "✓ Las cuatro ejecuciones producen la misma salida", "la semántica se preservó" in s, "")
    chequear("Paso 5", "Compilación exitosa. Archivos generados en salida/",
             c == 0 and "Compilación exitosa. Archivos generados en salida/" in s, f"código {c}")
    (REPO / "resultado.txt").write_text(s, encoding="utf-8")
    chequear("Paso 5", "salida guardada en resultado.txt", (REPO / "resultado.txt").exists(), "resultado.txt")

    # Paso 6 — una fase a la vez
    for n in ["1", "2", "3", "4", "5", "6", "7", "4,5"]:
        c, s = compilar("ejemplos/programa_correcto.drg", "--fases", n)
        fases = re.findall(r"FASE (\d) ·", s)
        chequear("Paso 6", f"--fases {n} muestra solo esa(s) fase(s)", c == 0 and fases == n.split(","),
                 "fases " + ", ".join(fases))

    # Paso 7 — errores
    c, s = compilar("ejemplos/programa_estres.drg")
    detenida = linea_con(s, "Compilación detenida")
    chequear("Paso 7", "16 errores: léxicos 2, sintácticos 2, semánticos 12",
             c == 1 and "16 error(es) — léxicos: 2, sintácticos: 2, semánticos: 12." in detenida, detenida)
    for nombre, cuantos in [("error_lexico", 4), ("error_sintactico", 6), ("error_semantico", 5)]:
        c, s = compilar(f"ejemplos/errores/{nombre}.drg")
        detenida = linea_con(s, "Compilación detenida")
        chequear("Paso 7", f"{nombre}.drg reporta {cuantos} errores", c == 1 and f": {cuantos} error(es)" in detenida, detenida)

    # Paso 8 — registros y spill
    for registros, esperado in [("2", 5), ("3", 2), ("6", 0)]:
        c, s = compilar("ejemplos/programa_registros.drg", "--registros", registros, "--fases", "6")
        m = re.search(r"(\d+) spill\(s\)", s)
        spills = int(m.group(1)) if m else (0 if "0 spills" in s else -1)
        chequear("Paso 8", f"{esperado} spills con {registros} registros", spills == esperado, f"{spills} spills")

    # Paso 9 — con y sin optimización
    def contar_asm(texto: str) -> int:
        cuerpo = texto.split("Ensamblador generado", 1)[-1].split("section .text", 1)[-1]
        return sum(1 for l in cuerpo.splitlines() if re.match(r"^    [A-Z]", l))
    _, sin = compilar("ejemplos/programa_correcto.drg", "--sin-optimizar")
    _, con = compilar("ejemplos/programa_correcto.drg")
    chequear("Paso 9", "sin optimizar el ensamblador es más largo", contar_asm(sin) > contar_asm(con),
             f"{contar_asm(sin)} instrucciones sin optimizar, {contar_asm(con)} optimizado")
    chequear("Paso 9", "y sigue imprimiendo lo mismo", impresas(sin) == impresas(con) != [], "")

    # Paso 10 — archivos generados
    esperados = {f"programa_correcto{x}" for x in (".tac", ".opt.tac", ".asm", ".cfg.dot")}
    hay = {p.name for p in (REPO / "salida").glob("programa_correcto*")}
    chequear("Paso 10", "salida/ tiene .tac, .opt.tac, .asm y .cfg.dot", esperados <= hay, ", ".join(sorted(hay)))

    # Paso 11 — programa propio
    mio = "entero vida = 50;\nmientras (vida > 0) {\n    imprimir(vida);\n    vida = vida - 20;\n}\n"
    (REPO / "ejemplos" / "mio.drg").write_text(mio, encoding="utf-8")
    c, s = compilar("ejemplos/mio.drg", "--fases", "7")
    chequear("Paso 11", "ejemplos/mio.drg imprime 50, 30 y 10", impresas(s) == ["50", "30", "10"], ", ".join(impresas(s)))
    with tempfile.TemporaryDirectory(dir=REPO) as tmp:
        variantes = [("sin un ';'", mio.replace("imprimir(vida);", "imprimir(vida)"), "[SINTÁCTICO]"),
                     ('vida - "fuego"', mio.replace("vida - 20", 'vida - "fuego"'), "[SEMÁNTICO]")]
        for i, (nombre, codigo, fase) in enumerate(variantes):
            archivo = Path(tmp) / f"variante{i}.drg"
            archivo.write_text(codigo, encoding="utf-8")
            c, s = compilar(str(archivo.relative_to(REPO)))
            chequear("Paso 11", f"{nombre} → error {fase.strip('[]').lower()}", c == 1 and fase in s, linea_con(s, fase))

    # Paso 12 — otras formas de ejecutarlo
    c, s = correr("-m", "dragon", "ejemplos/programa_correcto.drg", "--sin-color", "--fases", "7")
    chequear("Paso 12", "python -m dragon", c == 0 and "se preservó" in s, f"código {c}")
    if "--pip" in sys.argv:
        with tempfile.TemporaryDirectory() as venv:
            subprocess.run([PY, "-m", "venv", venv], check=True)
            pip = Path(venv) / ("Scripts" if os.name == "nt" else "bin")
            subprocess.run([str(pip / "pip"), "install", "-q", "git+https://github.com/UbeimarY/compilador-dragon.git"])
            p = subprocess.run([str(pip / "dragon"), "ejemplos/programa_correcto.drg", "--sin-color", "--fases", "7"],
                               cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
            chequear("Paso 12", "pip install + comando dragon", p.returncode == 0 and "se preservó" in p.stdout, f"código {p.returncode}")

    # Errores con funciones y de ejecución
    for nombre, codigo in [("error_funciones", 1), ("error_memoria", 2), ("error_recursion", 2)]:
        c, s = compilar(f"ejemplos/errores/{nombre}.drg")
        chequear("Errores", f"{nombre}.drg termina con código {codigo}", c == codigo,
                 linea_con(s, "Compilación detenida") or linea_con(s, "[ERROR DE EJECUCIÓN]")[:100])

    # Ejercicios 9 y 10
    (REPO / "suma.drg").write_text("funcion entero suma(entero a, entero b) {\n    entero c = a + b;\n"
                                   "    retornar c;\n}\nimprimir(suma(2, 3));\n", encoding="utf-8")
    c, s = compilar("suma.drg", "--fases", "6,7")
    chequear("Ej. 9", "suma.drg: a en [FP+24], b en [FP+16], c en [FP-8], imprime 5",
             all(x in s for x in ("[FP+24]", "[FP+16]", "[FP-8]")) and impresas(s) == ["5"], "")
    c, s = compilar("ejemplos/programa_correcto.drg", "--automatas", "--fases", "1")
    chequear("Ej. 10", "Hopcroft: 7 estados → 5", "7 estados → 5 estados" in s, linea_con(s, "7 estados"))

    # Opciones avanzadas
    c, s = compilar("ejemplos/programa_correcto.drg", "--interpretar")
    chequear("Extra", "--interpretar (intérprete del AST)", c == 0 and "284 nodos evaluados" in s, "")
    c, s = compilar("ejemplos/programa_registros.drg", "--registros", "3", "--asignador", "coloreo", "--fases", "6")
    chequear("Extra", "--asignador coloreo (Chaitin-Briggs)", c == 0 and "Chaitin-Briggs" in s, "")
    c, s = compilar("ejemplos/programa_correcto.drg", "--linea", "9")
    chequear("Extra", "--linea 9: 3 cuádruplas → ataque_base = 25", c == 0 and "ataque_base = 25" in s, "")

    # Guion de la sustentación
    for argumentos, debe in [(("ejemplos/programa_correcto.drg", "--fases", "1,2"), "FASE 2"),
                             (("ejemplos/programa_correcto.drg", "--fases", "3"), "Tabla de símbolos"),
                             (("ejemplos/programa_correcto.drg", "--fases", "4,5"), "78 → 63"),
                             (("ejemplos/programa_registros.drg", "--registros", "2", "--fases", "6"), "SPILL"),
                             (("ejemplos/programa_correcto.drg", "--fases", "7"), "se preservó"),
                             (("ejemplos/programa_estres.drg",), "16 error(es)")]:
        c, s = compilar(*argumentos)
        chequear("Guion", f"{' '.join(argumentos)} → «{debe}»", debe in s, "")

    correctas = sum(1 for r in resultados if r[2])
    resumen = [f"Guía de estudio: {correctas} de {len(resultados)} comprobaciones correctas", ""]
    for paso, descripcion, ok, real in resultados:
        resumen.append(f"{'✓' if ok else '✗'} {paso:<9} {descripcion}" + (f"\n             → {real}" if real else ""))
    REGISTRO.write_text("\n".join(resumen) + "\n\n" + "=" * 78 + "\nSALIDA COMPLETA DE CADA COMANDO\n"
                        + "=" * 78 + "".join(registro), encoding="utf-8")
    print(f"\n{correctas} de {len(resultados)} comprobaciones correctas.")
    print(f"Salida completa de cada comando: {REGISTRO.name}")
    return 0 if correctas == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
