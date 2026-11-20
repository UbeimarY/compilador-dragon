"""
GRAFO DE FLUJO DE CONTROL (Semana 7)
====================================

Divide el TAC en BLOQUES BÁSICOS y los une con aristas según los saltos.

Un bloque básico empieza en un LÍDER:
    1. la primera instrucción del programa o de una función,
    2. toda etiqueta (L1:), porque alguien puede saltar a ella,
    3. la instrucción siguiente a un salto (goto, if_false, return, fin).

Aristas que salen de cada bloque, según su última instrucción:
    goto L        → el bloque de L
    if_false c L  → el bloque de L (condición falsa) y el siguiente (verdadera)
    return / fin  → SALIDA
    otra          → el bloque siguiente (caída)

El optimizador ya trabaja por bloques básicos (la propagación de constantes
se reinicia en cada uno); este módulo los hace visibles y los exporta para
Graphviz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tac import ProgramaTAC

SALTOS = ("goto", "if_false", "return", "fin")


@dataclass
class BloqueBasico:
    numero: int
    inicio: int                     # índice de la primera instrucción
    fin: int                        # índice de la última (inclusive)
    funcion: str                    # "main" o el nombre de la función
    sucesores: list = field(default_factory=list)   # números de bloque o "SALIDA"

    @property
    def nombre(self) -> str:
        return f"B{self.numero}"


def construir_grafo(programa: ProgramaTAC) -> list[BloqueBasico]:
    instr = programa.instrucciones
    # Cada función se trata por separado: sus pseudo-instrucciones no forman bloques
    segmentos, funcion, actual = [], "main", []
    for i, q in enumerate(instr):
        if q.op == "func":
            if actual:
                segmentos.append((funcion, actual))
            funcion, actual = q.res, []
        elif q.op == "fin_func":
            segmentos.append((funcion, actual))
            funcion, actual = None, []
        else:
            actual.append(i)
    if actual and funcion is not None:
        segmentos.append((funcion, actual))

    bloques: list[BloqueBasico] = []
    for funcion, indices in segmentos:
        if not indices:
            continue
        lideres = {indices[0]}
        for pos, i in enumerate(indices):
            if instr[i].op == "label":
                lideres.add(i)
            if instr[i].op in SALTOS and pos + 1 < len(indices):
                lideres.add(indices[pos + 1])
        inicio = None
        for pos, i in enumerate(indices):
            if i in lideres:
                if inicio is not None:
                    bloques.append(BloqueBasico(len(bloques), inicio, indices[pos - 1], funcion))
                inicio = i
        bloques.append(BloqueBasico(len(bloques), inicio, indices[-1], funcion))

    bloque_de_etiqueta = {instr[b.inicio].res: b.numero for b in bloques if instr[b.inicio].op == "label"}
    for b in bloques:
        ultima = instr[b.fin]
        siguiente = bloques[b.numero + 1] if b.numero + 1 < len(bloques) else None
        cae = siguiente is not None and siguiente.funcion == b.funcion
        if ultima.op == "goto":
            b.sucesores = [bloque_de_etiqueta[ultima.res]]
        elif ultima.op == "if_false":
            b.sucesores = ([siguiente.numero] if cae else []) + [bloque_de_etiqueta[ultima.res]]
        elif ultima.op in ("return", "fin") or not cae:
            b.sucesores = ["SALIDA"]
        else:
            b.sucesores = [siguiente.numero]
    return bloques


def grafo_como_texto(programa: ProgramaTAC, bloques: list[BloqueBasico]) -> str:
    lineas, funcion = [], None
    for b in bloques:
        if b.funcion != funcion:
            funcion = b.funcion
            lineas.append(f"[{'programa principal' if funcion == 'main' else 'función ' + funcion}]")
        destinos = ", ".join(s if s == "SALIDA" else f"B{s}" for s in b.sucesores)
        rango = f"{b.inicio:03d}" if b.inicio == b.fin else f"{b.inicio:03d}–{b.fin:03d}"
        cuerpo = [str(programa.instrucciones[i]).strip() for i in range(b.inicio, b.fin + 1)]
        resumen = "; ".join(cuerpo) if len(cuerpo) <= 3 else f"{cuerpo[0]}; … ; {cuerpo[-1]}"
        lineas.append(f"  {b.nombre:<4} {'[' + rango + ']':<10} → {destinos:<12} {resumen}")
    aristas = sum(len(b.sucesores) for b in bloques)
    lineas.append(f"\n  {len(bloques)} bloques básicos · {aristas} aristas")
    return "\n".join(lineas)


def grafo_dot(programa: ProgramaTAC, bloques: list[BloqueBasico], titulo: str) -> str:
    lineas = [f'digraph "{titulo}" {{', '  node [shape=box, fontname="monospace"];',
              '  SALIDA [shape=doublecircle];']
    for b in bloques:
        cuerpo = "\\l".join(str(programa.instrucciones[i]).strip().replace('"', '\\"')
                            for i in range(b.inicio, b.fin + 1))
        lineas.append(f'  {b.nombre} [label="{b.nombre} ({b.funcion})\\l{cuerpo}\\l"];')
        for s in b.sucesores:
            lineas.append(f"  {b.nombre} -> {s if s == 'SALIDA' else 'B' + str(s)};")
    lineas.append("}")
    return "\n".join(lineas)
