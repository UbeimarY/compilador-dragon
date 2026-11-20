"""
FASE 2 — ANÁLISIS SINTÁCTICO
============================

Parser descendente recursivo (Top-Down, Semanas 3 y 4): cada regla de la
gramática es un método. La gramática no tiene recursión izquierda y codifica
la precedencia de operadores por niveles (de menor a mayor):

    programa     → ( funcion | instruccion )* EOF
    funcion      → 'funcion' ( TIPO | 'vacio' ) ID '(' [ parametro { ',' parametro } ] ')' bloque
    parametro    → TIPO ID
    instruccion  → declaracion | asignacion | si | mientras | imprimir | bloque
                 | retornar | liberar | llamada ';'
    retornar     → 'retornar' [ expresion ] ';'
    liberar      → 'liberar' '(' ID ')' ';'
    llamada      → ID '(' [ expresion { ',' expresion } ] ')'
    declaracion  → TIPO ID ( '=' expresion )? ';'
    asignacion   → ID '=' expresion ';'
    si           → 'si' '(' expresion ')' bloque ( 'sino' ( si | bloque ) )?
    mientras     → 'mientras' '(' expresion ')' bloque
    imprimir     → 'imprimir' '(' expresion ')' ';'
    bloque       → '{' instruccion* '}'

    expresion    → o_logico
    o_logico     → y_logico ( '||' y_logico )*
    y_logico     → igualdad ( '&&' igualdad )*
    igualdad     → relacional ( ( '==' | '!=' ) relacional )*
    relacional   → aditiva ( ( '<' | '>' | '<=' | '>=' ) aditiva )*
    aditiva      → multiplicativa ( ( '+' | '-' ) multiplicativa )*
    multiplicativa → unaria ( ( '*' | '/' | '%' ) unaria )*
    unaria       → ( '-' | '!' ) unaria | primaria
    primaria     → NUM_ENTERO | NUM_REAL | CADENA | BOOLEANO | llamada | ID | '(' expresion ')'

Recuperación de errores en MODO PÁNICO: cuando una instrucción está mal
formada se registra el error y se descartan tokens hasta un punto seguro
(';', '}' o el inicio de otra instrucción). Así el parser sigue analizando y
puede reportar varios errores sintácticos en una sola compilación.
"""

from .ast_nodos import (Asignacion, Binaria, Bloque, Declaracion, Expresion,
                        Funcion, Imprimir, InstruccionExpresion, Liberar,
                        Literal, Llamada, Mientras, Nodo, Parametro, Programa,
                        Retornar, Si, Unaria, Variable)
from .errores import LEXICO, SINTACTICO, ReporteErrores
from .lexer import Token

NOMBRES_LEGIBLES = {
    "PUNTO_COMA": "';'", "PAR_IZQ": "'('", "PAR_DER": "')'",
    "LLAVE_IZQ": "'{'", "LLAVE_DER": "'}'", "ASIGNACION": "'='",
    "ID": "un identificador", "EOF": "el fin del archivo", "TIPO": "un tipo",
}

INICIO_INSTRUCCION = {"TIPO", "ID", "SI", "MIENTRAS", "IMPRIMIR", "LLAVE_IZQ",
                      "FUNCION", "RETORNAR", "LIBERAR"}

NIVELES_BINARIOS = [
    {"O": "||"},
    {"Y": "&&"},
    {"IGUAL": "==", "DIFERENTE": "!="},
    {"MENOR": "<", "MAYOR": ">", "MENOR_IGUAL": "<=", "MAYOR_IGUAL": ">="},
    {"MAS": "+", "MENOS": "-"},
    {"POR": "*", "DIV": "/", "MOD": "%"},
]


class ErrorSintactico(Exception):
    """Uso interno: dispara la recuperación en modo pánico."""


def _describir(token: Token) -> str:
    return "el fin del archivo" if token.tipo == "EOF" else f"'{token.lexema}'"


class Parser:
    def __init__(self, tokens: list[Token], reporte: ReporteErrores):
        self.tokens = tokens
        self.reporte = reporte
        self.pos = 0
        # Líneas con errores léxicos: allí el error sintáctico es solo una
        # consecuencia (el lexer descartó caracteres), así que no se repite.
        self._lineas_con_error_lexico = {e.linea for e in reporte.de_fase(LEXICO)}

    def _reportar(self, mensaje: str, linea: int, columna: int) -> None:
        if linea not in self._lineas_con_error_lexico:
            self.reporte.error(SINTACTICO, mensaje, linea, columna)

    # ------------------------------------------------------------ utilidades
    @property
    def actual(self) -> Token:
        return self.tokens[self.pos]

    def _anterior(self) -> Token:
        return self.tokens[self.pos - 1] if self.pos > 0 else self.tokens[0]

    def _avanzar(self) -> Token:
        token = self.actual
        if token.tipo != "EOF":
            self.pos += 1
        return token

    def _siguiente_es(self, tipo: str) -> bool:
        return self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].tipo == tipo

    def _es(self, *tipos: str) -> bool:
        return self.actual.tipo in tipos

    def _error(self, mensaje: str, token: Token | None = None) -> ErrorSintactico:
        token = token or self.actual
        self._reportar(mensaje, token.linea, token.columna)
        return ErrorSintactico(mensaje)

    def _consumir(self, tipo: str, contexto: str) -> Token:
        if self.actual.tipo == tipo:
            return self._avanzar()
        esperado = NOMBRES_LEGIBLES.get(tipo, tipo)
        # Recuperación a nivel de frase: un ';' o ')' olvidado se "inserta"
        # virtualmente y el análisis continúa sin descartar la línea siguiente.
        if tipo == "PUNTO_COMA" or (tipo == "PAR_DER" and self._es("LLAVE_IZQ", "PUNTO_COMA")):
            previo = self._anterior()
            self._reportar(
                f"Falta {esperado} {contexto}",
                previo.linea, previo.columna + len(previo.lexema),
            )
            return Token(tipo, "", None, previo.linea, previo.columna + len(previo.lexema))
        raise self._error(f"Se esperaba {esperado} {contexto}, pero se encontró {_describir(self.actual)}")

    def _sincronizar(self) -> None:
        """Modo pánico: descarta tokens hasta un punto seguro para continuar."""
        inicio = self.pos
        while not self._es("EOF"):
            if self._es("PUNTO_COMA"):
                self._avanzar()
                return
            if self._es("LLAVE_DER"):
                return
            if self.pos > inicio and self.actual.tipo in INICIO_INSTRUCCION - {"ID"}:
                return
            self._avanzar()

    # ---------------------------------------------------------- instrucciones
    def parsear(self) -> Programa:
        instrucciones = []
        while not self._es("EOF"):
            if self._es("LLAVE_DER"):
                self._error("Llave '}' de cierre sin su '{' de apertura")
                self._avanzar()
                continue
            if self._es("FUNCION"):
                instr = self._funcion_segura()
            else:
                instr = self._instruccion_segura()
            if instr is not None:
                instrucciones.append(instr)
        return Programa(instrucciones)

    # -------------------------------------------------------------- funciones
    def _funcion_segura(self) -> Funcion | None:
        posicion_inicial = self.pos
        try:
            return self._funcion()
        except ErrorSintactico:
            self._sincronizar()
            if self.pos == posicion_inicial and not self._es("LLAVE_DER"):
                self._avanzar()
            return None

    def _funcion(self) -> Funcion:
        inicio = self._avanzar()  # 'funcion'
        if not self._es("TIPO", "VACIO"):
            raise self._error(f"Se esperaba el tipo de retorno (o 'vacio') después de 'funcion', "
                              f"pero se encontró {_describir(self.actual)}")
        tipo_retorno = self._avanzar().lexema
        nombre = self._consumir("ID", "como nombre de la función")
        self._consumir("PAR_IZQ", f"después del nombre de la función '{nombre.lexema}'")
        parametros: list[Parametro] = []
        if not self._es("PAR_DER"):
            while True:
                if not self._es("TIPO"):
                    raise self._error(f"Se esperaba el tipo de un parámetro de '{nombre.lexema}', "
                                      f"pero se encontró {_describir(self.actual)}")
                tipo = self._avanzar()
                id_param = self._consumir("ID", f"después del tipo '{tipo.lexema}' del parámetro")
                parametros.append(Parametro(tipo.lexema, id_param.lexema, tipo.linea, tipo.columna))
                if not self._es("COMA"):
                    break
                self._avanzar()
        self._consumir("PAR_DER", f"para cerrar los parámetros de '{nombre.lexema}'")
        cuerpo = self._bloque(f"funcion {nombre.lexema}")
        return Funcion(tipo_retorno, nombre.lexema, parametros, cuerpo, inicio.linea, inicio.columna)

    def _instruccion_segura(self) -> Nodo | None:
        posicion_inicial = self.pos
        try:
            return self._instruccion()
        except ErrorSintactico:
            self._sincronizar()
            if self.pos == posicion_inicial and not self._es("LLAVE_DER"):  # Garantiza progreso
                self._avanzar()
            return None

    def _instruccion(self) -> Nodo:
        if self._es("TIPO"):
            return self._declaracion()
        if self._es("ID") and self._siguiente_es("PAR_IZQ"):
            llamada = self._primaria()
            self._consumir("PUNTO_COMA", f"después de la llamada a '{llamada.nombre}'")
            return InstruccionExpresion(llamada, llamada.linea, llamada.columna)
        if self._es("ID"):
            return self._asignacion()
        if self._es("RETORNAR"):
            tok = self._avanzar()
            valor = None if self._es("PUNTO_COMA") else self._expresion()
            self._consumir("PUNTO_COMA", "después de 'retornar'")
            return Retornar(valor, tok.linea, tok.columna)
        if self._es("LIBERAR"):
            tok = self._avanzar()
            self._consumir("PAR_IZQ", "después de 'liberar'")
            id_tok = self._consumir("ID", "dentro de 'liberar(...)'")
            self._consumir("PAR_DER", "para cerrar 'liberar('")
            self._consumir("PUNTO_COMA", "al final de 'liberar(...)'")
            return Liberar(Variable(id_tok.lexema, id_tok.linea, id_tok.columna), tok.linea, tok.columna)
        if self._es("FUNCION"):
            funcion = self._funcion()
            self._reportar("Las funciones solo pueden declararse en el nivel global, no dentro de un bloque",
                           funcion.linea, funcion.columna)
            return funcion
        if self._es("SI"):
            return self._si()
        if self._es("MIENTRAS"):
            return self._mientras()
        if self._es("IMPRIMIR"):
            return self._imprimir()
        if self._es("LLAVE_IZQ"):
            return self._bloque("")
        if self._es("SINO"):
            raise self._error("'sino' sin un 'si' previo")
        raise self._error(f"Instrucción no válida: no se esperaba {_describir(self.actual)}")

    def _declaracion(self) -> Declaracion:
        tipo_tok = self._avanzar()
        nombre_tok = self._consumir("ID", f"después del tipo '{tipo_tok.lexema}'")
        valor = None
        if self._es("ASIGNACION"):
            self._avanzar()
            valor = self._expresion()
        self._consumir("PUNTO_COMA", f"al final de la declaración de '{nombre_tok.lexema}'")
        return Declaracion(tipo_tok.lexema, nombre_tok.lexema, valor, tipo_tok.linea, tipo_tok.columna)

    def _asignacion(self) -> Asignacion:
        nombre_tok = self._avanzar()
        if not self._es("ASIGNACION"):
            raise self._error(
                f"Se esperaba '=' después de '{nombre_tok.lexema}', pero se encontró {_describir(self.actual)}"
            )
        self._avanzar()
        valor = self._expresion()
        self._consumir("PUNTO_COMA", f"al final de la asignación a '{nombre_tok.lexema}'")
        return Asignacion(nombre_tok.lexema, valor, nombre_tok.linea, nombre_tok.columna)

    def _condicion(self, palabra: str) -> Expresion:
        self._consumir("PAR_IZQ", f"después de '{palabra}'")
        cond = self._expresion()
        self._consumir("PAR_DER", f"para cerrar la condición de '{palabra}'")
        return cond

    def _si(self) -> Si:
        si_tok = self._avanzar()
        condicion = self._condicion("si")
        entonces = self._bloque("si")
        sino = None
        if self._es("SINO"):
            self._avanzar()
            sino = self._si() if self._es("SI") else self._bloque("sino")
        return Si(condicion, entonces, sino, si_tok.linea, si_tok.columna)

    def _mientras(self) -> Mientras:
        tok = self._avanzar()
        condicion = self._condicion("mientras")
        cuerpo = self._bloque("mientras")
        return Mientras(condicion, cuerpo, tok.linea, tok.columna)

    def _imprimir(self) -> Imprimir:
        tok = self._avanzar()
        self._consumir("PAR_IZQ", "después de 'imprimir'")
        valor = self._expresion()
        self._consumir("PAR_DER", "para cerrar 'imprimir('")
        self._consumir("PUNTO_COMA", "al final de 'imprimir(...)'")
        return Imprimir(valor, tok.linea, tok.columna)

    def _bloque(self, duenio: str) -> Bloque:
        contexto = f"para abrir el bloque de '{duenio}'" if duenio else "para abrir el bloque"
        apertura = self._consumir("LLAVE_IZQ", contexto)
        instrucciones = []
        while not self._es("LLAVE_DER", "EOF"):
            instr = self._instruccion_segura()
            if instr is not None:
                instrucciones.append(instr)
        if self._es("EOF"):
            self._reportar(
                f"Bloque abierto en L:{apertura.linea} C:{apertura.columna} nunca se cerró (falta '}}')",
                self.actual.linea, self.actual.columna,
            )
        else:
            self._avanzar()
        return Bloque(instrucciones, apertura.linea, apertura.columna)

    # ------------------------------------------------------------ expresiones
    def _expresion(self) -> Expresion:
        return self._binaria(0)

    def _binaria(self, nivel: int) -> Expresion:
        if nivel == len(NIVELES_BINARIOS):
            return self._unaria()
        operadores = NIVELES_BINARIOS[nivel]
        nodo = self._binaria(nivel + 1)
        while self.actual.tipo in operadores:
            op_tok = self._avanzar()
            derecha = self._binaria(nivel + 1)
            nodo = Binaria(operadores[op_tok.tipo], nodo, derecha, op_tok.linea, op_tok.columna)
        return nodo

    def _unaria(self) -> Expresion:
        if self._es("MENOS", "NO"):
            op_tok = self._avanzar()
            operando = self._unaria()
            return Unaria(op_tok.lexema, operando, op_tok.linea, op_tok.columna)
        return self._primaria()

    def _primaria(self) -> Expresion:
        tok = self.actual
        literales = {"NUM_ENTERO": "entero", "NUM_REAL": "real", "CADENA": "texto", "BOOLEANO": "booleano"}
        if tok.tipo in literales:
            self._avanzar()
            return Literal(tok.valor, literales[tok.tipo], tok.linea, tok.columna)
        if tok.tipo == "ID" and self._siguiente_es("PAR_IZQ"):
            self._avanzar()
            self._avanzar()  # '('
            argumentos: list[Expresion] = []
            if not self._es("PAR_DER"):
                argumentos.append(self._expresion())
                while self._es("COMA"):
                    self._avanzar()
                    argumentos.append(self._expresion())
            self._consumir("PAR_DER", f"para cerrar los argumentos de '{tok.lexema}'")
            return Llamada(tok.lexema, argumentos, tok.linea, tok.columna)
        if tok.tipo == "ID":
            self._avanzar()
            return Variable(tok.lexema, tok.linea, tok.columna)
        if tok.tipo == "PAR_IZQ":
            self._avanzar()
            nodo = self._expresion()
            self._consumir("PAR_DER", "para cerrar el paréntesis")
            return nodo
        raise self._error(f"Se esperaba un valor o una expresión, pero se encontró {_describir(tok)}")


def parsear(tokens: list[Token], reporte: ReporteErrores | None = None) -> Programa:
    return Parser(tokens, reporte or ReporteErrores()).parsear()
