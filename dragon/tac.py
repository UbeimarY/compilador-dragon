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

Operandos: los nombres (str) son variables o temporales; las constantes se
representan con la clase Const para no confundir el texto "x" con la
variable x.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .ast_nodos import (Asignacion, Binaria, Bloque, Conversion, Declaracion,
                        Expresion, Imprimir, Literal, Mientras, Nodo, Programa,
                        Si, Unaria, Variable)
from .semantico import Simbolo
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

    def usos(self) -> list[str]:
        """Nombres (variables o temporales) que esta instrucción LEE."""
        return [a for a in (self.arg1, self.arg2) if isinstance(a, str)]

    def define(self) -> Optional[str]:
        """Nombre que esta instrucción ESCRIBE (None si no escribe)."""
        return self.res if (self.op in BINARIOS or self.op in UNARIOS or self.op == "=") else None

    def __str__(self) -> str:
        if self.op == "label":
            return f"{self.res}:"
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
        fmt = lambda x: "—" if x is None else str(x)
        return f"({self.op}, {fmt(self.arg1)}, {fmt(self.arg2)}, {fmt(self.res)})"


@dataclass
class ProgramaTAC:
    instrucciones: list[Cuadrupla]
    tipos: dict[str, str]                      # tipo de cada variable y temporal
    variables: list[Simbolo] = field(default_factory=list)

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
            f = lambda x: "—" if x is None else str(x)
            filas.append(f"{i:<5}{q.op:<10}{f(q.arg1):<16}{f(q.arg2):<16}{f(q.res):<10}")
        return "\n".join(filas)

    def copia(self) -> "ProgramaTAC":
        return ProgramaTAC([Cuadrupla(q.op, q.arg1, q.arg2, q.res) for q in self.instrucciones],
                           dict(self.tipos), list(self.variables))


class GeneradorTAC:
    def __init__(self):
        self.instrucciones: list[Cuadrupla] = []
        self.tipos: dict[str, str] = {}
        self._temporales = 0
        self._etiquetas = 0

    def nuevo_temporal(self, tipo: str) -> str:
        self._temporales += 1
        nombre = f"t{self._temporales}"
        self.tipos[nombre] = tipo
        return nombre

    def nueva_etiqueta(self) -> str:
        self._etiquetas += 1
        return f"L{self._etiquetas}"

    def emitir(self, op: str, arg1: Operando = None, arg2: Operando = None, res: Optional[str] = None) -> None:
        self.instrucciones.append(Cuadrupla(op, arg1, arg2, res))

    # ------------------------------------------------------------------ API
    def generar(self, programa: Programa, simbolos: list[Simbolo]) -> ProgramaTAC:
        for s in simbolos:
            self.tipos[s.nombre_unico] = s.tipo
        for instr in programa.instrucciones:
            self._instruccion(instr)
        return ProgramaTAC(self.instrucciones, self.tipos, list(simbolos))

    # -------------------------------------------------------- instrucciones
    def _instruccion(self, n: Nodo) -> None:
        if isinstance(n, Declaracion):
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


def generar_tac(programa: Programa, simbolos: list[Simbolo]) -> ProgramaTAC:
    return GeneradorTAC().generar(programa, simbolos)
