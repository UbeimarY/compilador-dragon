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


class ErrorEjecucion(Exception):
    """Error en tiempo de ejecución detectado por los emuladores."""


def operar(op: str, a, b):
    """Semántica única de los operadores binarios del lenguaje Dragon.

    La usan el optimizador (plegado de constantes) y los dos emuladores, lo
    que garantiza que todos calculen exactamente lo mismo.
    """
    if op in ("/", "%") and b == 0:
        raise ErrorEjecucion("División por cero")
    enteros = isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool) and not isinstance(b, bool)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return division_entera(a, b) if enteros else a / b
    if op == "%":
        return modulo_entero(a, b)
    if op == "<":
        return a < b
    if op == ">":
        return a > b
    if op == "<=":
        return a <= b
    if op == ">=":
        return a >= b
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == "&&":
        return bool(a) and bool(b)
    if op == "||":
        return bool(a) or bool(b)
    raise ErrorEjecucion(f"Operador desconocido '{op}'")


def operar_unaria(op: str, a):
    if op == "neg":
        return -a
    if op == "not":
        return not a
    if op == "itof":
        return float(a)
    raise ErrorEjecucion(f"Operador unario desconocido '{op}'")


# ----------------------------------------------------------------------
# HEAP (Semana 8): memoria dinámica para los textos
# ----------------------------------------------------------------------
class Puntero:
    """Un valor de tipo texto en ejecución: la DIRECCIÓN de su cadena."""
    __slots__ = ("direccion",)

    def __init__(self, direccion: int):
        self.direccion = direccion

    def __eq__(self, otro) -> bool:
        return isinstance(otro, Puntero) and otro.direccion == self.direccion

    def __hash__(self) -> int:
        return hash(self.direccion)

    def __repr__(self) -> str:
        return f"0x{self.direccion:04X}"


class Heap:
    """Simula la memoria dinámica de un programa en ejecución.

    * Las cadenas literales ("Aria") viven en una zona ESTÁTICA (como .rodata).
    * Cada concatenación reserva un bloque nuevo en el HEAP (malloc).
    * `liberar(s)` devuelve el bloque (free). Detecta los errores clásicos:
      usar memoria ya liberada (dangling pointer), liberar dos veces
      (double free) y liberar algo que no está en el heap.
    * Al terminar, los bloques que nunca se liberaron son FUGAS DE MEMORIA.
    """

    BASE_ESTATICA = 0x4000
    BASE_HEAP = 0x8000

    def __init__(self):
        self.bloques: dict[int, list] = {}      # dirección → [contenido, estado, bytes]
        self._estaticos: dict[str, Puntero] = {}
        self._sig_estatica = self.BASE_ESTATICA
        self._sig_heap = self.BASE_HEAP
        self.reservas = 0
        self.liberaciones = 0
        self.vacia = self.estatico("")

    @staticmethod
    def _tamanio(contenido: str) -> int:
        bruto = len(contenido.encode("utf-8")) + 1          # + el '\0' final
        return (bruto + 7) // 8 * 8                          # alineado a 8 bytes

    def estatico(self, contenido: str) -> Puntero:
        if contenido not in self._estaticos:
            p = Puntero(self._sig_estatica)
            tam = self._tamanio(contenido)
            self.bloques[p.direccion] = [contenido, "estatico", tam]
            self._sig_estatica += tam
            self._estaticos[contenido] = p
        return self._estaticos[contenido]

    def reservar(self, contenido: str) -> Puntero:          # malloc
        p = Puntero(self._sig_heap)
        tam = self._tamanio(contenido)
        self.bloques[p.direccion] = [contenido, "vivo", tam]
        self._sig_heap += tam
        self.reservas += 1
        return p

    def leer(self, p) -> str:
        if not isinstance(p, Puntero):
            return str(p)
        bloque = self.bloques.get(p.direccion)
        if bloque is None:
            raise ErrorEjecucion(f"Puntero inválido {p}")
        if bloque[1] == "liberado":
            raise ErrorEjecucion(f"Uso de memoria ya liberada (dangling pointer) en {p}")
        return bloque[0]

    def concatenar(self, a, b) -> Puntero:
        return self.reservar(self.leer(a) + self.leer(b))

    def liberar(self, p) -> None:                            # free
        bloque = self.bloques.get(p.direccion) if isinstance(p, Puntero) else None
        if bloque is None:
            raise ErrorEjecucion(f"Puntero inválido {p}")
        if bloque[1] == "estatico":
            raise ErrorEjecucion(f"Solo se puede liberar memoria del heap: {p} es una cadena constante")
        if bloque[1] == "liberado":
            raise ErrorEjecucion(f"Doble liberación (double free) de {p}")
        bloque[1] = "liberado"
        self.liberaciones += 1

    def fugas(self) -> list[tuple[int, str, int]]:
        return [(d, b[0], b[2]) for d, b in self.bloques.items() if b[1] == "vivo"]

    def resumen(self) -> str:
        fugas = self.fugas()
        texto = f"{self.reservas} reserva(s) (malloc) · {self.liberaciones} liberación(es) (free)"
        if fugas:
            texto += f" · {len(fugas)} bloque(s) sin liberar = fuga de {sum(f[2] for f in fugas)} bytes"
        elif self.reservas:
            texto += " · sin fugas de memoria"
        return texto

    def mostrar(self, valor) -> str:
        """Representación segura de un valor para los reportes (no falla con punteros colgantes)."""
        if isinstance(valor, Puntero):
            bloque = self.bloques.get(valor.direccion)
            if bloque is None or bloque[1] == "liberado":
                return f"{valor} (memoria liberada)"
            return f'"{bloque[0]}" @{valor}' + (" (heap)" if bloque[1] == "vivo" else "")
        return formatear_valor(valor)


def operar_con_heap(heap: Heap, op: str, a, b):
    """operar() para valores de ejecución: los textos son punteros al heap."""
    if isinstance(a, Puntero) or isinstance(b, Puntero):
        if op == "+":
            return heap.concatenar(a, b)
        return operar(op, heap.leer(a), heap.leer(b))
    return operar(op, a, b)


def valor_por_defecto(tipo: str):
    return {"entero": 0, "real": 0.0, "texto": "", "booleano": False}.get(tipo, 0)


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
