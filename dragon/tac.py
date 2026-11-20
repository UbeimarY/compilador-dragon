"""
FASE 4 — CÓDIGO INTERMEDIO (TAC)
================================

Recorre el AST ya validado y lo "desenrolla" en una secuencia lineal de
instrucciones de tres direcciones, almacenadas como CUÁDRUPLAS
(operador, argumento1, argumento2, resultado) — Semana 7.

    x = a + b * c        ──►    t1 = b * c
                                t2 = a + t1
                                x = t2

Las estructuras de control se convierten en saltos con etiquetas:

    si (c) {A} sino {B}  ──►    if_false c goto L1
                                A
                                goto L2
                              L1:
                                B
                              L2:

    mientras (c) {A}     ──►  L1:
                                if_false c goto L2
                                A
                                goto L1
                              L2:

Funciones (convención de llamada):

    x = sumar(a, 2)      ──►    param a            el llamador apila los argumentos
                                param 2
                                t1 = call sumar, 2
                                x = t1
                                ...
                                fin                fin del programa principal
                              func sumar(p, q):    cuerpo de la función
                                t2 = p + q
                                return t2
                              fin_func sumar

Operandos: los nombres (str) son variables o temporales; las constantes se
representan con la clase Const para no confundir el texto "x" con la
variable x.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .ast_nodos import (Asignacion, Binaria, Bloque, Conversion, Declaracion,
                        Expresion, Funcion, Imprimir, InstruccionExpresion,
                        Liberar, Literal, Llamada, Mientras, Nodo, Programa,
                        Retornar, Si, Unaria, Variable)
from .semantico import InfoFuncion, Simbolo
from .utilidades import formatear_valor


@dataclass(frozen=True)
class Const:
    valor: Any
    tipo: str

    def __str__(self) -> str:
        if self.tipo == "texto":
            escapado = self.valor.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
            return f'"{escapado}"'
        return formatear_valor(self.valor)


Operando = Union[str, Const, None]

BINARIOS = {"+", "-", "*", "/", "%", "<", ">", "<=", ">=", "==", "!=", "&&", "||"}
UNARIOS = {"neg": "-", "not": "!", "itof": "(real) "}


@dataclass
class Cuadrupla:
    op: str
    arg1: Operando = None
    arg2: Operando = None
    res: Optional[str] = None
    linea: Optional[int] = field(default=None, compare=False, repr=False)  # línea del código fuente

    def usos(self) -> list[str]:
        """Nombres (variables o temporales) que esta instrucción LEE."""
        if self.op == "call":  # arg1 es el nombre de la función, no una variable
            return []
        return [a for a in (self.arg1, self.arg2) if isinstance(a, str)]

    def define(self) -> Optional[str]:
        """Nombre que esta instrucción ESCRIBE (None si no escribe)."""
        if self.op in BINARIOS or self.op in UNARIOS or self.op in ("=", "call"):
            return self.res
        return None

    def __str__(self) -> str:
        if self.op == "label":
            return f"{self.res}:"
        if self.op == "func":
            return f"func {self.res}({', '.join(self.arg1 or [])}):"
        if self.op == "fin_func":
            return f"fin_func {self.res}"
        if self.op == "fin":
            return "    fin"
        if self.op == "param":
            return f"    param {self.arg1}"
        if self.op == "call":
            llamada = f"call {self.arg1}, {self.arg2}"
            return f"    {self.res} = {llamada}" if self.res else f"    {llamada}"
        if self.op == "return":
            return "    return" if self.arg1 is None else f"    return {self.arg1}"
        if self.op == "free":
            return f"    liberar {self.arg1}"
        if self.op == "goto":
            return f"    goto {self.res}"
        if self.op == "if_false":
            return f"    if_false {self.arg1} goto {self.res}"
        if self.op == "print":
            return f"    imprimir {self.arg1}"
        if self.op == "=":
            return f"    {self.res} = {self.arg1}"
        if self.op in UNARIOS:
            return f"    {self.res} = {UNARIOS[self.op]}{self.arg1}"
        return f"    {self.res} = {self.arg1} {self.op} {self.arg2}"

    def como_tupla(self) -> str:
        fmt = lambda x: "—" if x is None else (", ".join(x) if isinstance(x, list) else str(x))
        return f"({self.op}, {fmt(self.arg1)}, {fmt(self.arg2)}, {fmt(self.res)})"


@dataclass
class ProgramaTAC:
    instrucciones: list[Cuadrupla]
    tipos: dict[str, str]                      # tipo de cada variable y temporal
    variables: list[Simbolo] = field(default_factory=list)       # solo las GLOBALES (.data)
    funciones: dict[str, InfoFuncion] = field(default_factory=dict)
    marco: dict[str, int] = field(default_factory=dict)          # local/parámetro → desplazamiento desde FP

    @property
    def globales(self) -> set[str]:
        return {s.nombre_unico for s in self.variables}

    def tipo_de(self, operando: Operando) -> str:
        if isinstance(operando, Const):
            return operando.tipo
        return self.tipos.get(operando, "entero")

    def como_texto(self, numerado: bool = True) -> str:
        lineas = []
        for i, q in enumerate(self.instrucciones):
            prefijo = f"{i:03d} " if numerado else ""
            lineas.append(f"{prefijo}{q}")
        return "\n".join(lineas)

    def como_cuadruplas(self) -> str:
        filas = [f"{'#':<5}{'Operador':<10}{'Arg1':<16}{'Arg2':<16}{'Resultado':<10}", "-" * 57]
        for i, q in enumerate(self.instrucciones):
            f = lambda x: "—" if x is None else (", ".join(x) if isinstance(x, list) else str(x))
            filas.append(f"{i:<5}{q.op:<10}{f(q.arg1):<16}{f(q.arg2):<16}{f(q.res):<10}")
        return "\n".join(filas)

    def copia(self) -> "ProgramaTAC":
        return ProgramaTAC([Cuadrupla(q.op, q.arg1, q.arg2, q.res, q.linea) for q in self.instrucciones],
                           dict(self.tipos), list(self.variables), dict(self.funciones), dict(self.marco))


class GeneradorTAC:
    def __init__(self):
        self.instrucciones: list[Cuadrupla] = []
        self.tipos: dict[str, str] = {}
        self._temporales = 0
        self._etiquetas = 0
        self._linea: Optional[int] = None   # línea fuente de la instrucción que se está traduciendo

    def nuevo_temporal(self, tipo: str) -> str:
        self._temporales += 1
        nombre = f"t{self._temporales}"
        self.tipos[nombre] = tipo
        return nombre

    def nueva_etiqueta(self) -> str:
        self._etiquetas += 1
        return f"L{self._etiquetas}"

    def emitir(self, op: str, arg1: Operando = None, arg2: Operando = None, res: Optional[str] = None) -> None:
        self.instrucciones.append(Cuadrupla(op, arg1, arg2, res, self._linea))

    # ------------------------------------------------------------------ API
    def generar(self, programa: Programa, simbolos: list[Simbolo],
                funciones: Optional[dict[str, InfoFuncion]] = None) -> ProgramaTAC:
        funciones = funciones or {}
        marco = {}
        for s in simbolos:
            self.tipos[s.nombre_unico] = s.tipo
            if s.es_local:
                marco[s.nombre_unico] = s.desplazamiento
        cuerpos = [n for n in programa.instrucciones if isinstance(n, Funcion)]
        for instr in programa.instrucciones:
            if not isinstance(instr, Funcion):
                self._instruccion(instr)
        if cuerpos:
            self._linea = None
            self.emitir("fin")  # el programa principal termina aquí; después van las funciones
            for f in cuerpos:
                self._funcion(f, funciones[f.nombre])
        globales = [s for s in simbolos if not s.es_local]
        return ProgramaTAC(self.instrucciones, self.tipos, globales, dict(funciones), marco)

    def _funcion(self, n: Funcion, info: InfoFuncion) -> None:
        self._linea = n.linea
        self.emitir("func", list(info.parametros), None, n.nombre)
        for instr in n.cuerpo.instrucciones:
            self._instruccion(instr)
        if not self.instrucciones or self.instrucciones[-1].op != "return":
            self._linea = n.linea
            self.emitir("return")  # retorno implícito al final de la función
        self._linea = n.linea
        self.emitir("fin_func", res=n.nombre)

    # -------------------------------------------------------- instrucciones
    def _instruccion(self, n: Nodo) -> None:
        anterior = self._linea
        if not isinstance(n, Bloque):
            self._linea = n.linea
        try:
            self._traducir_instruccion(n)
        finally:
            self._linea = anterior

    def _traducir_instruccion(self, n: Nodo) -> None:
        if isinstance(n, Retornar):
            self.emitir("return", self._expresion(n.valor) if n.valor is not None else None)
        elif isinstance(n, InstruccionExpresion):
            self._expresion(n.expresion)
        elif isinstance(n, Liberar):
            self.emitir("free", n.variable.nombre_unico)
        elif isinstance(n, Declaracion):
            if n.valor is not None:
                self.emitir("=", self._expresion(n.valor), None, n.nombre_unico)
        elif isinstance(n, Asignacion):
            self.emitir("=", self._expresion(n.valor), None, n.nombre_unico)
        elif isinstance(n, Imprimir):
            self.emitir("print", self._expresion(n.valor))
        elif isinstance(n, Bloque):
            for instr in n.instrucciones:
                self._instruccion(instr)
        elif isinstance(n, Si):
            self._si(n)
        elif isinstance(n, Mientras):
            self._mientras(n)

    def _si(self, n: Si) -> None:
        condicion = self._expresion(n.condicion)
        etiqueta_sino = self.nueva_etiqueta()
        self.emitir("if_false", condicion, None, etiqueta_sino)
        self._instruccion(n.entonces)
        if n.sino is None:
            self.emitir("label", res=etiqueta_sino)
            return
        etiqueta_fin = self.nueva_etiqueta()
        self.emitir("goto", res=etiqueta_fin)
        self.emitir("label", res=etiqueta_sino)
        self._instruccion(n.sino)
        self.emitir("label", res=etiqueta_fin)

    def _mientras(self, n: Mientras) -> None:
        etiqueta_inicio = self.nueva_etiqueta()
        etiqueta_fin = self.nueva_etiqueta()
        self.emitir("label", res=etiqueta_inicio)
        condicion = self._expresion(n.condicion)
        self.emitir("if_false", condicion, None, etiqueta_fin)
        self._instruccion(n.cuerpo)
        self.emitir("goto", res=etiqueta_inicio)
        self.emitir("label", res=etiqueta_fin)

    # ----------------------------------------------------------- expresiones
    def _expresion(self, n: Expresion) -> Operando:
        if isinstance(n, Literal):
            return Const(n.valor, n.tipo)
        if isinstance(n, Variable):
            return n.nombre_unico
        if isinstance(n, Llamada):
            argumentos = [self._expresion(a) for a in n.argumentos]
            for a in argumentos:
                self.emitir("param", a)
            t = self.nuevo_temporal(n.tipo) if n.tipo not in (None, "vacio", "error") else None
            self.emitir("call", n.nombre, len(argumentos), t)
            return t
        if isinstance(n, Conversion):
            interno = self._expresion(n.expresion)
            t = self.nuevo_temporal("real")
            self.emitir("itof", interno, None, t)
            return t
        if isinstance(n, Unaria):
            operando = self._expresion(n.operando)
            t = self.nuevo_temporal(n.tipo)
            self.emitir("neg" if n.operador == "-" else "not", operando, None, t)
            return t
        if isinstance(n, Binaria):
            izq = self._expresion(n.izquierda)
            der = self._expresion(n.derecha)
            t = self.nuevo_temporal(n.tipo)
            self.emitir(n.operador, izq, der, t)
            return t
        raise ValueError(f"Expresión no soportada: {n}")


def generar_tac(programa: Programa, simbolos: list[Simbolo],
                funciones: Optional[dict[str, InfoFuncion]] = None) -> ProgramaTAC:
    return GeneradorTAC().generar(programa, simbolos, funciones)
