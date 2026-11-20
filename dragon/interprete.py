"""
INTÉRPRETE DEL AST (Semanas 1 y 4)
=================================

Ejecuta el programa RECORRIENDO EL ÁRBOL, sin traducirlo: cada nodo se evalúa
en post-orden (primero los hijos, después el operador), como el evaluador de
la Semana 4, ampliado con variables, ámbitos, funciones y el heap.

Sirve para mostrar la diferencia de la Semana 1:

    Compilador  → traduce TODO antes de ejecutar (TAC → ensamblador) y luego
                  la máquina ejecuta instrucciones simples muy rápido.
    Intérprete  → lee y ejecuta el árbol directamente; no produce código.

En la fase 7 el intérprete es una cuarta ejecución que debe coincidir con
las otras tres: así el árbol anotado por el análisis semántico queda
verificado contra el código generado.
"""

from __future__ import annotations

import sys

from .ast_nodos import (Asignacion, Binaria, Bloque, Conversion, Declaracion,
                        Expresion, Funcion, Imprimir, InstruccionExpresion,
                        Liberar, Literal, Llamada, Mientras, Nodo, Programa,
                        Retornar, Si, Unaria, Variable)
from .emulador import LIMITE_PASOS, ResultadoEjecucion
from .utilidades import (ErrorEjecucion, Heap, formatear_valor,
                         operar_con_heap, operar_unaria, valor_por_defecto)

LIMITE_LLAMADAS = 500


class _Retorno(Exception):
    """Uso interno: desenrolla la recursión de Python al ejecutar 'retornar'."""

    def __init__(self, valor):
        self.valor = valor


class Interprete:
    def __init__(self, programa: Programa, simbolos, funciones):
        self.programa = programa
        self.heap = Heap()
        self.tipos = {s.nombre_unico: s.tipo for s in simbolos}
        self.globales = {s.nombre_unico for s in simbolos if not s.es_local}
        self.memoria = {}
        self.marcos: list[dict] = [{}]
        self.cuerpos = {n.nombre: n for n in programa.instrucciones if isinstance(n, Funcion)}
        self.funciones = funciones
        self.salida: list[str] = []
        self.pasos = 0

    # ----------------------------------------------------------- memoria
    def _inicial(self, tipo: str):
        return self.heap.vacia if tipo == "texto" else valor_por_defecto(tipo)

    def _leer(self, nombre: str):
        lugar = self.memoria if nombre in self.globales else self.marcos[-1]
        if nombre not in lugar:
            return self._inicial(self.tipos.get(nombre, "entero"))
        return lugar[nombre]

    def _escribir(self, nombre: str, valor) -> None:
        (self.memoria if nombre in self.globales else self.marcos[-1])[nombre] = valor

    def _contar(self) -> None:
        self.pasos += 1
        if self.pasos > LIMITE_PASOS:
            raise ErrorEjecucion(f"Se superaron {LIMITE_PASOS} pasos: posible ciclo infinito")

    # ------------------------------------------------------------ ejecución
    def ejecutar(self) -> ResultadoEjecucion:
        r = ResultadoEjecucion()
        limite_anterior = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limite_anterior, 20000))
        try:
            for n in self.programa.instrucciones:
                if not isinstance(n, Funcion):
                    self._instruccion(n)
        except ErrorEjecucion as e:
            r.error = str(e)
        except RecursionError:
            r.error = "Stack Overflow: demasiadas llamadas anidadas"
        finally:
            sys.setrecursionlimit(limite_anterior)
        r.salida, r.pasos, r.heap = self.salida, self.pasos, self.heap
        r.memoria = {n: self.memoria.get(n, self._inicial(self.tipos[n])) for n in self.globales}
        return r

    def _instruccion(self, n: Nodo) -> None:
        self._contar()
        if isinstance(n, Declaracion):
            valor = self._evaluar(n.valor) if n.valor is not None else self._inicial(n.tipo_declarado)
            self._escribir(n.nombre_unico, valor)
        elif isinstance(n, Asignacion):
            self._escribir(n.nombre_unico, self._evaluar(n.valor))
        elif isinstance(n, Imprimir):
            valor = self._evaluar(n.valor)
            self.salida.append(formatear_valor(self.heap.leer(valor) if n.valor.tipo == "texto" else valor))
        elif isinstance(n, Bloque):
            for i in n.instrucciones:
                self._instruccion(i)
        elif isinstance(n, Si):
            if self._evaluar(n.condicion):
                self._instruccion(n.entonces)
            elif n.sino is not None:
                self._instruccion(n.sino)
        elif isinstance(n, Mientras):
            while self._evaluar(n.condicion):
                self._instruccion(n.cuerpo)
                self._contar()
        elif isinstance(n, Retornar):
            raise _Retorno(self._evaluar(n.valor) if n.valor is not None else None)
        elif isinstance(n, Liberar):
            self.heap.liberar(self._evaluar(n.variable))
        elif isinstance(n, InstruccionExpresion):
            self._evaluar(n.expresion)

    def _evaluar(self, n: Expresion):
        self._contar()
        if isinstance(n, Literal):
            return self.heap.estatico(n.valor) if n.tipo == "texto" else n.valor
        if isinstance(n, Variable):
            return self._leer(n.nombre_unico)
        if isinstance(n, Conversion):
            return float(self._evaluar(n.expresion))
        if isinstance(n, Unaria):
            return operar_unaria("neg" if n.operador == "-" else "not", self._evaluar(n.operando))
        if isinstance(n, Binaria):  # post-orden: hijos primero, después el operador
            izquierda = self._evaluar(n.izquierda)
            derecha = self._evaluar(n.derecha)
            return operar_con_heap(self.heap, n.operador, izquierda, derecha)
        if isinstance(n, Llamada):
            return self._llamar(n)
        raise ErrorEjecucion(f"Expresión no soportada: {type(n).__name__}")

    def _llamar(self, n: Llamada):
        argumentos = [self._evaluar(a) for a in n.argumentos]
        if len(self.marcos) > LIMITE_LLAMADAS:
            raise ErrorEjecucion(f"Stack Overflow: más de {LIMITE_LLAMADAS} llamadas anidadas "
                                 f"(¿recursión infinita en '{n.nombre}'?)")
        info = self.funciones[n.nombre]
        self.marcos.append(dict(zip(info.parametros, argumentos)))
        try:
            for i in self.cuerpos[n.nombre].cuerpo.instrucciones:
                self._instruccion(i)
            valor = None
        except _Retorno as r:
            valor = r.valor
        finally:
            self.marcos.pop()
        if valor is None and info.tipo_retorno != "vacio":
            valor = self._inicial(info.tipo_retorno)
        return valor


def interpretar(programa: Programa, simbolos, funciones) -> ResultadoEjecucion:
    return Interprete(programa, simbolos, funciones).ejecutar()
