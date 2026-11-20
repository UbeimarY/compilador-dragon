"""Funciones de apoyo compartidas por varias fases."""

import os
import sys

TIPOS = ("entero", "real", "texto", "booleano")


def formatear_valor(valor) -> str:
    """Representación de un valor tal como lo imprime `imprimir(...)`."""
    if isinstance(valor, bool):
        return "verdadero" if valor else "falso"
    if isinstance(valor, float):
        if valor == int(valor) and abs(valor) < 1e15:
            return f"{valor:.1f}"
        return f"{valor:.6g}"
    return str(valor)


def division_entera(a: int, b: int) -> int:
    """División entera truncada hacia cero (como en C y Java)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def modulo_entero(a: int, b: int) -> int:
    """Residuo con el signo del dividendo (como en C y Java)."""
    return a - b * division_entera(a, b)


# ----------------------------------------------------------------------
# Colores ANSI para la consola (se desactivan si la salida no es terminal)
# ----------------------------------------------------------------------
class Color:
    activo = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    @classmethod
    def desactivar(cls) -> None:
        cls.activo = False

    @classmethod
    def _c(cls, codigo: str, texto: str) -> str:
        return f"\033[{codigo}m{texto}\033[0m" if cls.activo else texto

    @classmethod
    def titulo(cls, t: str) -> str:
        return cls._c("1;36", t)

    @classmethod
    def ok(cls, t: str) -> str:
        return cls._c("1;32", t)

    @classmethod
    def error(cls, t: str) -> str:
        return cls._c("1;31", t)

    @classmethod
    def aviso(cls, t: str) -> str:
        return cls._c("1;33", t)

    @classmethod
    def tenue(cls, t: str) -> str:
        return cls._c("2", t)


if os.name == "nt":  # Habilita secuencias ANSI en consolas de Windows
    os.system("")
