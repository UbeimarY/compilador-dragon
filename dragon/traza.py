"""
Recorrido de una línea por las 7 fases y estado de cada fase
=============================================================

Ejecuta el compilador completo una sola vez y conserva el resultado de cada
fase, para poder responder dos preguntas:

* **¿Hasta dónde llegó la compilación?** `estado_fases()` dice, para cada una
  de las 7 fases, si pasó, si falló allí o si no se alcanzó.
* **¿Qué le pasó a esta línea?** `recorrido_linea()` sigue una línea del código
  fuente por todas las fases: sus tokens, su subárbol del AST, los símbolos que
  declara, las cuádruplas TAC que genera (antes y después de optimizar), las
  instrucciones de ensamblador que le corresponden y cuántas veces se ejecutó.

Es posible porque cada cuádrupla y cada instrucción de ensamblador recuerda la
línea fuente de la que proviene (`Cuadrupla.linea`, `InstruccionASM.linea`).

Lo usan la opción `--linea N` de la terminal y el playground web.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .ast_nodos import Bloque, Programa, _etiqueta, _hijos
from .codegen import CodigoObjetivo, generar_codigo
from .emulador import EmuladorASM, EmuladorTAC, ResultadoEjecucion
from .errores import ADVERTENCIA, LEXICO, SEMANTICO, SINTACTICO, ReporteErrores
from .interprete import interpretar
from .lexer import Lexer, Token
from .optimizador import optimizar
from .parser import Parser
from .semantico import AnalizadorSemantico
from .tac import ProgramaTAC, generar_tac

# (número, nombre, semanas del curso)
FASES = [
    (1, "Léxico", "Semana 2"),
    (2, "Sintáctico", "Semanas 3 y 4"),
    (3, "Semántico", "Semanas 5 y 6"),
    (4, "Código intermedio", "Semana 7"),
    (5, "Optimización", "Semana 9"),
    (6, "Código objetivo", "Semana 10"),
    (7, "Ejecución y memoria", "Semanas 1 y 8"),
]

ETIQUETA_ESTADO = {"ok": "Pasó", "fallo": "Falló aquí", "error": "Con errores", "omitida": "No se alcanzó"}
FASE_DE_ERROR = {LEXICO: 1, SINTACTICO: 2, SEMANTICO: 3, ADVERTENCIA: 3}

# Categoría de cada tipo de token, para colorearlos
CATEGORIAS = {
    "TIPO": "tipo",
    "SI": "clave", "SINO": "clave", "MIENTRAS": "clave", "IMPRIMIR": "clave", "FUNCION": "clave",
    "RETORNAR": "clave", "VACIO": "clave", "LIBERAR": "clave",
    "BOOLEANO": "booleano",
    "NUM_ENTERO": "numero", "NUM_REAL": "numero",
    "CADENA": "texto",
    "ID": "identificador",
    "PAR_IZQ": "puntuacion", "PAR_DER": "puntuacion", "LLAVE_IZQ": "puntuacion",
    "LLAVE_DER": "puntuacion", "PUNTO_COMA": "puntuacion", "COMA": "puntuacion",
}
NOMBRE_CATEGORIA = {
    "clave": "Palabra clave", "tipo": "Tipo", "identificador": "Identificador", "numero": "Número",
    "texto": "Texto", "booleano": "Booleano", "operador": "Operador", "puntuacion": "Puntuación",
    "error": "Error léxico",
}


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def categoria(tipo_token: str) -> str:
    return CATEGORIAS.get(tipo_token, "operador")


@dataclass
class Analisis:
    """Resultado de todas las fases para un programa."""
    fuente: str
    reporte: ReporteErrores
    tokens: list[Token]
    ast: Programa
    semantico: object
    optimizado: bool = True
    tac: Optional[ProgramaTAC] = None
    tac_optimizado: Optional[ProgramaTAC] = None
    registro_optimizador: list = field(default_factory=list)
    codigo: Optional[CodigoObjetivo] = None
    ejecuciones: dict[str, ResultadoEjecucion] = field(default_factory=dict)

    @property
    def lineas_fuente(self) -> list[str]:
        return self.fuente.splitlines()

    @property
    def compilo(self) -> bool:
        return self.codigo is not None

    @property
    def semantica_preservada(self) -> bool:
        if not self.ejecuciones:
            return False
        asm = self.ejecuciones["Ensamblador"]
        return all(r.salida == asm.salida and bool(r.error) == bool(asm.error)
                   for r in self.ejecuciones.values())

    @property
    def error_ejecucion(self) -> Optional[str]:
        asm = self.ejecuciones.get("Ensamblador")
        return asm.error if asm else None

    @property
    def codigo_salida(self) -> int:
        if not self.compilo:
            return 1
        return 2 if self.error_ejecucion else 0


def analizar(fuente: str, registros: int = 3, optimizar_codigo: bool = True,
             asignador: str = "belady") -> Analisis:
    """Ejecuta las 7 fases y guarda el resultado de cada una."""
    reporte = ReporteErrores()
    tokens = Lexer(fuente, reporte).tokenizar()
    ast = Parser(tokens, reporte).parsear()
    semantico = AnalizadorSemantico(reporte).analizar(ast)
    a = Analisis(fuente, reporte, tokens, ast, semantico, optimizado=optimizar_codigo)
    if reporte.hay_errores():
        return a

    a.tac = generar_tac(ast, semantico.tabla.todos, semantico.funciones)
    a.tac_optimizado, optimizador = optimizar(a.tac)
    a.registro_optimizador = list(optimizador.registro)
    a.codigo = generar_codigo(a.tac_optimizado if optimizar_codigo else a.tac, registros, asignador)
    a.ejecuciones = {
        "Intérprete AST": interpretar(ast, semantico.tabla.todos, semantico.funciones),
        "TAC original": EmuladorTAC(a.tac).ejecutar(),
        "TAC optimizado": EmuladorTAC(a.tac_optimizado).ejecutar(),
        "Ensamblador": EmuladorASM(a.codigo).ejecutar(),
    }
    return a


# ------------------------------------------------------------ estado de las fases
def _resumir_error(mensaje: str) -> str:
    """'Stack Overflow: más de 500…' → 'Stack Overflow'."""
    corto = mensaje.split(":")[0].split(" en 0x")[0]
    return corto if len(corto) <= 48 else corto[:45] + "…"


def estado_fases(a: Analisis) -> list[dict]:
    """Una entrada por fase: número, nombre, semanas, estado y un detalle corto."""
    errores = {f: len(a.reporte.de_fase(f)) for f in (LEXICO, SINTACTICO, SEMANTICO)}
    detalles_ok = {
        1: _plural(len(a.tokens) - 1, "token", "tokens"),
        2: _plural(len(a.ast.instrucciones), "instrucción", "instrucciones"),
        3: _plural(len(a.semantico.tabla.todos), "símbolo", "símbolos"),
    }
    nombres_error = {LEXICO: "léxico(s)", SINTACTICO: "sintáctico(s)", SEMANTICO: "semántico(s)"}
    resultado, ya_fallo = [], False
    for numero, nombre, semanas in FASES:
        fase = {"numero": numero, "nombre": nombre, "semanas": semanas, "detalle": "", "mensaje": ""}
        if numero <= 3:
            clave = (LEXICO, SINTACTICO, SEMANTICO)[numero - 1]
            if errores[clave]:
                fase["estado"] = "error" if ya_fallo else "fallo"
                fase["detalle"] = f"{errores[clave]} error(es) {nombres_error[clave]}"
                ya_fallo = True
            else:
                fase["estado"] = "ok"
                fase["detalle"] = detalles_ok[numero]
        elif not a.compilo:
            fase["estado"] = "omitida"
        elif numero == 4:
            fase["estado"], fase["detalle"] = "ok", f"{len(a.tac.instrucciones)} instrucciones"
        elif numero == 5:
            fase["estado"] = "ok"
            antes, despues = len(a.tac.instrucciones), len(a.tac_optimizado.instrucciones)
            fase["detalle"] = f"{antes} → {despues} instrucciones" if a.optimizado else "desactivada"
        elif numero == 6:
            fase["estado"] = "ok"
            fase["detalle"] = f"{len(a.codigo.instrucciones)} instrucciones · {a.codigo.spills} spills"
        else:
            if a.error_ejecucion:
                fase["estado"], fase["detalle"] = "fallo", _resumir_error(a.error_ejecucion)
                fase["mensaje"] = a.error_ejecucion
            elif not a.semantica_preservada:
                fase["estado"], fase["detalle"] = "fallo", "las ejecuciones difieren"
            else:
                heap = a.ejecuciones["Ensamblador"].heap
                fugas = len(heap.fugas()) if heap else 0
                fase["estado"] = "ok"
                fase["detalle"] = "4 ejecuciones iguales" + (f" · {fugas} fuga(s)" if fugas else "")
        fase["etiqueta"] = ETIQUETA_ESTADO[fase["estado"]]
        resultado.append(fase)
    return resultado


# ------------------------------------------------------------ tokens con categoría
def tokens_coloreados(a: Analisis) -> list[dict]:
    """Tokens y errores léxicos en orden, cada uno con su categoría para colorearlo."""
    lista = [{"linea": t.linea, "columna": t.columna, "tipo": t.tipo, "lexema": t.lexema,
              "categoria": categoria(t.tipo)} for t in a.tokens if t.tipo != "EOF"]
    for e in a.reporte.de_fase(LEXICO):
        lista.append({"linea": e.linea, "columna": e.columna, "tipo": "ERROR", "lexema": "✗",
                      "categoria": "error", "mensaje": e.mensaje})
    return sorted(lista, key=lambda t: (t["linea"], t["columna"]))


# ------------------------------------------------------------ recorrido de una línea
def _nodos_de_linea(raiz, n: int) -> list:
    """Nodos más externos del AST que empiezan en la línea n."""
    encontrados = []

    def visitar(nodo) -> None:
        if not isinstance(nodo, Programa) and getattr(nodo, "linea", None) == n:
            encontrados.append(nodo)
            return
        for _, hijo in _hijos(nodo):
            visitar(hijo)

    visitar(raiz)
    return encontrados


def _arbol_de_linea(nodo, n: int) -> str:
    """Como arbol_ascii, pero los hijos de otras líneas se muestran plegados."""
    lineas = [_etiqueta(nodo)]

    def recorrer(x, prefijo: str) -> None:
        hijos = _hijos(x)
        for i, (rotulo, hijo) in enumerate(hijos):
            ultimo = i == len(hijos) - 1
            rama = "└── " if ultimo else "├── "
            linea_hijo = getattr(hijo, "linea", n)
            if linea_hijo != n:
                lineas.append(f"{prefijo}{rama}{rotulo}{_etiqueta(hijo)}  … (línea {linea_hijo})")
                continue
            lineas.append(f"{prefijo}{rama}{rotulo}{_etiqueta(hijo)}")
            recorrer(hijo, prefijo + ("    " if ultimo else "│   "))

    recorrer(nodo, "")
    return "\n".join(lineas)


def recorrido_linea(a: Analisis, n: int) -> dict:
    """Lo que le pasa a la línea n en cada fase. Cada fase trae 'lineas' (texto
    para mostrar), 'nota' (explicación corta) y 'errores' de esa fase."""
    fuente = a.lineas_fuente
    texto = fuente[n - 1] if 1 <= n <= len(fuente) else ""
    errores = {i: [] for i in range(1, 8)}
    for e in a.reporte.errores + a.reporte.advertencias:
        if e.linea == n:
            errores[FASE_DE_ERROR[e.fase]].append(f"[{e.fase}] C:{e.columna} — {e.mensaje}")

    fases = {}
    # 1. Tokens
    toks = [t for t in tokens_coloreados(a) if t["linea"] == n]
    fases[1] = {"lineas": [f"{t['tipo']:<13} {t['lexema']}" for t in toks if t["categoria"] != "error"],
                "tokens": toks,
                "nota": f"{len([t for t in toks if t['categoria'] != 'error'])} token(s)" if toks
                else "Sin tokens: línea vacía o comentario"}
    # 2. AST
    nodos = _nodos_de_linea(a.ast, n)
    fases[2] = {"lineas": "\n\n".join(_arbol_de_linea(x, n) for x in nodos).splitlines(),
                "nota": "Subárbol que empieza en esta línea" if nodos else "Ningún nodo del AST empieza aquí"}
    # 3. Semántico
    sem = []
    for s in a.semantico.tabla.todos:
        if s.linea == n:
            rol = "parámetro" if s.es_parametro else ("local" if s.es_local else "global")
            sem.append(f"{s.nombre} → {s.nombre_unico} : {s.tipo} · {rol} · {s.ubicacion}")
    for f in a.semantico.funciones.values():
        if f.linea == n:
            sem.append(f"función {f.firma}")
    sem += [c for c in a.semantico.coerciones if c.startswith(f"L:{n} ")]
    fases[3] = {"lineas": sem,
                "nota": "Símbolos declarados y coerciones" if sem else "No declara símbolos; sus usos se verificaron"}

    if not a.compilo:
        for i in range(4, 8):
            fases[i] = {"lineas": [], "nota": "No se alcanzó: el programa tiene errores"}
    else:
        # 4. TAC
        tac = [(i, q) for i, q in enumerate(a.tac.instrucciones) if q.linea == n]
        fases[4] = {"lineas": [f"{i:03d} {q}" for i, q in tac],
                    "nota": f"{len(tac)} cuádrupla(s)" if tac else "No genera código"}
        # 5. Optimización
        opt = [(i, q) for i, q in enumerate(a.tac_optimizado.instrucciones) if q.linea == n]
        if not tac:
            nota = "No genera código"
        elif not opt:
            nota = "El optimizador eliminó todo su código (plegado, código muerto o inalcanzable)"
        else:
            nota = f"{len(tac)} → {len(opt)} cuádrupla(s)"
        if not a.optimizado:
            nota += " · el ensamblador usa el TAC sin optimizar"
        fases[5] = {"lineas": [f"{i:03d} {q}" for i, q in opt], "nota": nota}
        # 6. Ensamblador
        asm = [str(x) for x in a.codigo.instrucciones if x.linea == n]
        fases[6] = {"lineas": asm, "nota": f"{len(asm)} instrucción(es) de máquina" if asm else "Sin instrucciones de máquina"}
        # 7. Ejecución (en el emulador del TAC original)
        ej = a.ejecuciones["TAC original"]
        indices = [i for i, _ in tac]
        veces = max((ej.conteo.get(i, 0) for i in indices), default=0)
        funcion = next((q.res for _, q in tac if q.op == "func"), None)
        if funcion:  # una declaración de función "se ejecuta" cada vez que la llaman
            veces = sum(ej.conteo.get(j, 0) for j, c in enumerate(a.tac.instrucciones)
                        if c.op == "call" and c.arg1 == funcion)
        impresas = [ej.salida[k] for k, i in enumerate(ej.origen_salida) if a.tac.instrucciones[i].linea == n]
        if not tac:
            nota = "No se ejecuta nada en esta línea"
        elif veces == 0:
            nota = "Nunca se llamó" if funcion else "Nunca se ejecutó"
        elif funcion:
            nota = f"La función se llamó {veces} {'vez' if veces == 1 else 'veces'}"
        else:
            nota = f"Se ejecutó {veces} {'vez' if veces == 1 else 'veces'}" + (f" · imprimió {len(impresas)} línea(s)" if impresas else "")
        fases[7] = {"lineas": [f"> {x}" for x in impresas[:12]] + (["…"] if len(impresas) > 12 else []),
                    "nota": nota}

    for i in fases:
        fases[i]["errores"] = errores[i]
    return {"linea": n, "texto": texto, "total_lineas": len(fuente), "fases": fases,
            "estados": estado_fases(a)}


def recorrido_como_texto(a: Analisis, n: int) -> str:
    """Versión para la terminal (opción --linea N)."""
    total = len(a.lineas_fuente)
    if not 1 <= n <= total:
        return f"La línea {n} no existe: el programa tiene {total} líneas."
    r = recorrido_linea(a, n)
    simbolo = {"ok": "✓", "fallo": "✗", "error": "✗", "omitida": "·"}
    salida = ["Estado de las fases:"]
    for f in r["estados"]:
        detalle = f" ({f['detalle']})" if f["detalle"] else ""
        salida.append(f"  {simbolo[f['estado']]} {f['numero']} {f['nombre']:<20} {f['etiqueta']}{detalle}")
    salida += ["", f"Recorrido de la línea {n}:  {r['texto'].strip()}", ""]
    for numero, nombre, semanas in FASES:
        fase = r["fases"][numero]
        salida.append(f"── {numero}. {nombre} ({semanas}) " + "─" * max(4, 50 - len(nombre) - len(semanas)))
        salida.append(f"   {fase['nota']}")
        salida += [f"   {x}" for x in fase["lineas"]]
        salida += [f"   {x}" for x in fase["errores"]]
        salida.append("")
    return "\n".join(salida).rstrip()
