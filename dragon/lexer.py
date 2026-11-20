"""
FASE 1 — ANÁLISIS LÉXICO
========================

Convierte el texto fuente en una lista de tokens. Cada token guarda su tipo,
el lexema original, su valor ya convertido (int, float, str, bool) y las
coordenadas (línea, columna) del primer carácter en el archivo.

Técnica: un único patrón con grupos con nombre (?P<NOMBRE>...) evaluados en
orden de prioridad (visto en la Semana 2). Las palabras reservadas se
distinguen de los identificadores con una tabla de búsqueda, lo que evita
que `enteros` se confunda con la palabra clave `entero`.

Errores léxicos que se detectan (sin detener el análisis):
    * Carácter fuera del alfabeto del lenguaje (ej. @, #, $).
    * Identificador que empieza con dígito (ej. 2vida).
    * Cadena de texto sin cerrar.
    * Comentario de bloque /* ... sin cerrar.
"""

import re
from dataclasses import dataclass
from typing import Any

from .errores import LEXICO, ReporteErrores

PALABRAS_RESERVADAS = {
    "entero": "TIPO",
    "real": "TIPO",
    "texto": "TIPO",
    "booleano": "TIPO",
    "si": "SI",
    "sino": "SINO",
    "mientras": "MIENTRAS",
    "imprimir": "IMPRIMIR",
    "verdadero": "BOOLEANO",
    "falso": "BOOLEANO",
}

OPERADORES = {
    "==": "IGUAL", "!=": "DIFERENTE", "<=": "MENOR_IGUAL", ">=": "MAYOR_IGUAL",
    "&&": "Y", "||": "O", "<": "MENOR", ">": "MAYOR", "=": "ASIGNACION",
    "!": "NO", "+": "MAS", "-": "MENOS", "*": "POR", "/": "DIV", "%": "MOD",
    "(": "PAR_IZQ", ")": "PAR_DER", "{": "LLAVE_IZQ", "}": "LLAVE_DER",
    ";": "PUNTO_COMA", ",": "COMA",
}

# El orden importa: las alternativas más específicas van primero.
PATRON_LEXICO = re.compile(
    r"(?P<COMENTARIO_BLOQUE>/\*[\s\S]*?\*/)"
    r"|(?P<COMENTARIO_ABIERTO>/\*[\s\S]*)"
    r"|(?P<COMENTARIO_LINEA>//[^\n]*)"
    r'|(?P<CADENA>"(?:[^"\\\n]|\\.)*")'
    r'|(?P<CADENA_ABIERTA>"(?:[^"\\\n]|\\.)*)'
    r"|(?P<NUM_REAL>\d+\.\d+)"
    r"|(?P<NUMERO_MAL_FORMADO>\d+[^\W\d]\w*)"
    r"|(?P<NUM_ENTERO>\d+)"
    r"|(?P<ID>[^\W\d]\w*)"
    r"|(?P<OPERADOR>==|!=|<=|>=|&&|\|\||[<>=!+\-*/%(){};,])"
    r"|(?P<NUEVA_LINEA>\n)"
    r"|(?P<ESPACIO>[ \t\r]+)"
    r"|(?P<ERROR>.)"
)

ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


@dataclass
class Token:
    tipo: str
    lexema: str
    valor: Any
    linea: int
    columna: int

    def __repr__(self) -> str:
        return f"Token({self.tipo}, {self.lexema!r}, L:{self.linea}, C:{self.columna})"


def _desescapar(contenido: str) -> str:
    resultado, i = [], 0
    while i < len(contenido):
        c = contenido[i]
        if c == "\\" and i + 1 < len(contenido):
            resultado.append(ESCAPES.get(contenido[i + 1], contenido[i + 1]))
            i += 2
        else:
            resultado.append(c)
            i += 1
    return "".join(resultado)


class Lexer:
    def __init__(self, codigo_fuente: str, reporte: ReporteErrores):
        self.codigo = codigo_fuente
        self.reporte = reporte

    def tokenizar(self) -> list[Token]:
        tokens: list[Token] = []
        linea, inicio_linea = 1, 0

        for m in PATRON_LEXICO.finditer(self.codigo):
            clase = m.lastgroup
            lexema = m.group()
            columna = m.start() - inicio_linea + 1

            if clase == "NUEVA_LINEA":
                linea += 1
                inicio_linea = m.end()
                continue
            if clase == "ESPACIO" or clase == "COMENTARIO_LINEA":
                continue
            if clase in ("COMENTARIO_BLOQUE", "COMENTARIO_ABIERTO"):
                if clase == "COMENTARIO_ABIERTO":
                    self.reporte.error(LEXICO, "Comentario de bloque '/*' sin cerrar", linea, columna)
                # El comentario puede ocupar varias líneas: se actualiza el contador
                saltos = lexema.count("\n")
                if saltos:
                    linea += saltos
                    inicio_linea = m.start() + lexema.rfind("\n") + 1
                continue

            if clase == "CADENA":
                tokens.append(Token("CADENA", lexema, _desescapar(lexema[1:-1]), linea, columna))
            elif clase == "CADENA_ABIERTA":
                self.reporte.error(LEXICO, "Cadena de texto sin cerrar (falta la comilla \")", linea, columna)
                # Recuperación: se asume que la cadena termina al final de la línea
                tokens.append(Token("CADENA", lexema, _desescapar(lexema[1:]), linea, columna))
            elif clase == "NUM_REAL":
                tokens.append(Token("NUM_REAL", lexema, float(lexema), linea, columna))
            elif clase == "NUM_ENTERO":
                tokens.append(Token("NUM_ENTERO", lexema, int(lexema), linea, columna))
            elif clase == "NUMERO_MAL_FORMADO":
                self.reporte.error(
                    LEXICO,
                    f"'{lexema}' no es válido: un identificador no puede empezar con un dígito",
                    linea, columna,
                )
            elif clase == "ID":
                tipo = PALABRAS_RESERVADAS.get(lexema, "ID")
                valor = (lexema == "verdadero") if tipo == "BOOLEANO" else lexema
                tokens.append(Token(tipo, lexema, valor, linea, columna))
            elif clase == "OPERADOR":
                tokens.append(Token(OPERADORES[lexema], lexema, lexema, linea, columna))
            else:  # ERROR
                self.reporte.error(LEXICO, f"Carácter no permitido '{lexema}'", linea, columna)

        tokens.append(Token("EOF", "", None, linea, len(self.codigo) - inicio_linea + 1))
        return tokens


def tokenizar(codigo_fuente: str, reporte: ReporteErrores | None = None) -> list[Token]:
    """Atajo para tokenizar sin crear explícitamente el Lexer."""
    return Lexer(codigo_fuente, reporte or ReporteErrores()).tokenizar()
