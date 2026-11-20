"""
Manejo centralizado de errores de compilación.

Ninguna fase lanza excepciones hacia el usuario: cada error se registra en un
ReporteErrores con su fase, línea y columna, y la compilación continúa para
encontrar la mayor cantidad posible de errores en una sola pasada.
"""

from dataclasses import dataclass, field

LEXICO = "LÉXICO"
SINTACTICO = "SINTÁCTICO"
SEMANTICO = "SEMÁNTICO"
ADVERTENCIA = "ADVERTENCIA"


@dataclass(frozen=True)
class ErrorCompilacion:
    fase: str
    mensaje: str
    linea: int
    columna: int

    def __str__(self) -> str:
        return f"[{self.fase}] L:{self.linea} C:{self.columna} — {self.mensaje}"


@dataclass
class ReporteErrores:
    errores: list[ErrorCompilacion] = field(default_factory=list)
    advertencias: list[ErrorCompilacion] = field(default_factory=list)

    def error(self, fase: str, mensaje: str, linea: int, columna: int) -> None:
        nuevo = ErrorCompilacion(fase, mensaje, linea, columna)
        # Evita reportar dos veces exactamente el mismo error
        if nuevo not in self.errores:
            self.errores.append(nuevo)

    def advertencia(self, mensaje: str, linea: int, columna: int) -> None:
        nueva = ErrorCompilacion(ADVERTENCIA, mensaje, linea, columna)
        if nueva not in self.advertencias:
            self.advertencias.append(nueva)

    def hay_errores(self) -> bool:
        return bool(self.errores)

    def de_fase(self, fase: str) -> list[ErrorCompilacion]:
        return [e for e in self.errores if e.fase == fase]

    def ordenados(self) -> list[ErrorCompilacion]:
        return sorted(self.errores, key=lambda e: (e.linea, e.columna))
