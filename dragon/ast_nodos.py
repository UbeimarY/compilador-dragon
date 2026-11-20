"""
Nodos del Árbol de Sintaxis Abstracta (AST).

Cada nodo guarda la línea y columna de origen para que las fases siguientes
puedan reportar errores precisos. Los nodos de expresión tienen además el
atributo `tipo`, que inicialmente es None y lo completa el analizador
semántico (inferencia de tipos).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class Nodo:
    linea: int
    columna: int


class Expresion(Nodo):
    tipo: Optional[str]


# ---------------------------------------------------------------- Instrucciones
@dataclass
class Programa(Nodo):
    instrucciones: list[Nodo]
    linea: int = 1
    columna: int = 1


@dataclass
class Bloque(Nodo):
    instrucciones: list[Nodo]
    linea: int
    columna: int


@dataclass
class Declaracion(Nodo):
    tipo_declarado: str
    nombre: str
    valor: Optional[Expresion]
    linea: int
    columna: int
    nombre_unico: Optional[str] = field(default=None, repr=False)


@dataclass
class Asignacion(Nodo):
    nombre: str
    valor: Expresion
    linea: int
    columna: int
    nombre_unico: Optional[str] = field(default=None, repr=False)


@dataclass
class Si(Nodo):
    condicion: Expresion
    entonces: Bloque
    sino: Optional[Nodo]  # Bloque, otro Si (sino si ...) o None
    linea: int
    columna: int


@dataclass
class Mientras(Nodo):
    condicion: Expresion
    cuerpo: Bloque
    linea: int
    columna: int


@dataclass
class Imprimir(Nodo):
    valor: Expresion
    linea: int
    columna: int


@dataclass
class Parametro(Nodo):
    tipo: str
    nombre: str
    linea: int
    columna: int
    nombre_unico: Optional[str] = field(default=None, repr=False)


@dataclass
class Funcion(Nodo):
    tipo_retorno: str          # entero | real | texto | booleano | vacio
    nombre: str
    parametros: list[Parametro]
    cuerpo: Bloque
    linea: int
    columna: int


@dataclass
class Retornar(Nodo):
    valor: Optional[Expresion]
    linea: int
    columna: int


@dataclass
class Liberar(Nodo):
    """liberar(variable): devuelve al heap la memoria de un texto (free)."""
    variable: "Variable"
    linea: int
    columna: int


@dataclass
class InstruccionExpresion(Nodo):
    """Una llamada usada como instrucción: saludar("Aria");"""
    expresion: Expresion
    linea: int
    columna: int


# ------------------------------------------------------------------ Expresiones
@dataclass
class Literal(Expresion):
    valor: Any
    tipo: Optional[str]
    linea: int
    columna: int


@dataclass
class Variable(Expresion):
    nombre: str
    linea: int
    columna: int
    tipo: Optional[str] = None
    nombre_unico: Optional[str] = field(default=None, repr=False)


@dataclass
class Binaria(Expresion):
    operador: str
    izquierda: Expresion
    derecha: Expresion
    linea: int
    columna: int
    tipo: Optional[str] = None


@dataclass
class Unaria(Expresion):
    operador: str
    operando: Expresion
    linea: int
    columna: int
    tipo: Optional[str] = None


@dataclass
class Llamada(Expresion):
    nombre: str
    argumentos: list[Expresion]
    linea: int
    columna: int
    tipo: Optional[str] = None


@dataclass
class Conversion(Expresion):
    """Coerción implícita insertada por el analizador semántico (entero → real)."""
    expresion: Expresion
    linea: int
    columna: int
    tipo: Optional[str] = "real"


# ------------------------------------------------------------ Visualización
def _etiqueta(n: Nodo) -> str:
    t = f" : {n.tipo}" if isinstance(n, Expresion) and getattr(n, "tipo", None) else ""
    if isinstance(n, Programa):
        return "Programa"
    if isinstance(n, Funcion):
        params = ", ".join(f"{p.tipo} {p.nombre}" for p in n.parametros)
        return f"Función {n.tipo_retorno} {n.nombre}({params})"
    if isinstance(n, Retornar):
        return "Retornar"
    if isinstance(n, Liberar):
        return f"Liberar {n.variable.nombre}"
    if isinstance(n, InstruccionExpresion):
        return "Instrucción"
    if isinstance(n, Llamada):
        return f"Llamada {n.nombre}(){t}"
    if isinstance(n, Bloque):
        return "Bloque { }"
    if isinstance(n, Declaracion):
        return f"Declaración {n.tipo_declarado} {n.nombre}"
    if isinstance(n, Asignacion):
        return f"Asignación {n.nombre} ="
    if isinstance(n, Si):
        return "Si"
    if isinstance(n, Mientras):
        return "Mientras"
    if isinstance(n, Imprimir):
        return "Imprimir"
    if isinstance(n, Literal):
        v = f'"{n.valor}"' if n.tipo == "texto" else (
            ("verdadero" if n.valor else "falso") if n.tipo == "booleano" else n.valor)
        return f"Literal {v}{t}"
    if isinstance(n, Variable):
        return f"Variable {n.nombre}{t}"
    if isinstance(n, Binaria):
        return f"Operación '{n.operador}'{t}"
    if isinstance(n, Unaria):
        return f"Unaria '{n.operador}'{t}"
    if isinstance(n, Conversion):
        return f"Conversión implícita → real"
    return type(n).__name__


def _hijos(n: Nodo) -> list[tuple[str, Nodo]]:
    if isinstance(n, (Programa, Bloque)):
        return [("", i) for i in n.instrucciones]
    if isinstance(n, Funcion):
        return [("cuerpo: ", n.cuerpo)]
    if isinstance(n, Retornar):
        return [("", n.valor)] if n.valor else []
    if isinstance(n, Liberar):
        return []
    if isinstance(n, InstruccionExpresion):
        return [("", n.expresion)]
    if isinstance(n, Llamada):
        return [(f"arg {i + 1}: ", a) for i, a in enumerate(n.argumentos)]
    if isinstance(n, Declaracion):
        return [("valor: ", n.valor)] if n.valor else []
    if isinstance(n, Asignacion):
        return [("valor: ", n.valor)]
    if isinstance(n, Si):
        h = [("condición: ", n.condicion), ("entonces: ", n.entonces)]
        if n.sino:
            h.append(("sino: ", n.sino))
        return h
    if isinstance(n, Mientras):
        return [("condición: ", n.condicion), ("cuerpo: ", n.cuerpo)]
    if isinstance(n, Imprimir):
        return [("", n.valor)]
    if isinstance(n, Binaria):
        return [("", n.izquierda), ("", n.derecha)]
    if isinstance(n, Unaria):
        return [("", n.operando)]
    if isinstance(n, Conversion):
        return [("", n.expresion)]
    return []


def arbol_ascii(nodo: Nodo) -> str:
    """Dibuja el AST como un árbol de texto (├── └──)."""
    lineas = [_etiqueta(nodo)]

    def recorrer(n: Nodo, prefijo: str) -> None:
        hijos = _hijos(n)
        for i, (rotulo, hijo) in enumerate(hijos):
            ultimo = i == len(hijos) - 1
            lineas.append(f"{prefijo}{'└── ' if ultimo else '├── '}{rotulo}{_etiqueta(hijo)}")
            recorrer(hijo, prefijo + ("    " if ultimo else "│   "))

    recorrer(nodo, "")
    return "\n".join(lineas)
