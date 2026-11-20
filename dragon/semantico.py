"""
FASE 3 — ANÁLISIS SEMÁNTICO
===========================

Recorre el AST validando el *significado* del programa:

1. TABLA DE SÍMBOLOS CON ÁMBITOS (Semana 5)
   Pila de ámbitos encadenados: cada bloque { } crea un ámbito hijo. La
   búsqueda (lookup) empieza en el ámbito actual y sube hasta el GLOBAL.
   Detecta: variables no declaradas, redeclaraciones en el mismo ámbito y
   uso de variables fuera de su ámbito. Advierte sobre variables que ocultan
   a otra externa, variables sin inicializar y variables nunca usadas.

   Cada símbolo recibe un NOMBRE ÚNICO (ej. `x` y `x_1` si hay dos `x` en
   ámbitos distintos) y una DIRECCIÓN de memoria en el segmento de datos.
   Así las fases siguientes ya no necesitan conocer los ámbitos.

2. CHEQUEO DE TIPOS (Semana 6)
   Infiere el tipo de cada expresión y verifica la compatibilidad de los
   operadores. Inserta COERCIONES IMPLÍCITAS entero → real cuando son
   seguras (nodos Conversion en el AST) y rechaza las inseguras
   (real → entero, texto con números, condiciones no booleanas, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .ast_nodos import (Asignacion, Binaria, Bloque, Conversion, Declaracion,
                        Expresion, Imprimir, Literal, Mientras, Nodo, Programa,
                        Si, Unaria, Variable)
from .errores import SEMANTICO, ReporteErrores

ERROR = "error"  # Tipo comodín para no reportar errores en cascada
NUMERICOS = ("entero", "real")
TAMANIOS = {"entero": 4, "real": 8, "booleano": 1, "texto": 8}  # texto = puntero
DIRECCION_BASE_DATOS = 0x1000
NOMBRES_RESERVADOS_IR = re.compile(r"^[tL]\d+$")  # chocarían con temporales/etiquetas del TAC


# =============================================================== Tabla de símbolos
@dataclass
class Simbolo:
    nombre: str
    tipo: str
    ambito: str
    nivel: int
    linea: int
    columna: int
    nombre_unico: str = ""
    direccion: int = 0
    inicializado: bool = False
    usado: bool = False

    @property
    def tamanio(self) -> int:
        return TAMANIOS[self.tipo]


@dataclass
class Ambito:
    nombre: str
    nivel: int
    padre: Optional["Ambito"] = None
    simbolos: dict[str, Simbolo] = field(default_factory=dict)


class TablaSimbolos:
    def __init__(self):
        self.actual = Ambito("GLOBAL", 0)
        self.todos: list[Simbolo] = []          # Historial completo (para el reporte)
        self.eventos: list[str] = []            # Traza de entrada/salida de ámbitos
        self._nombres_usados: set[str] = set()
        self._siguiente_direccion = DIRECCION_BASE_DATOS

    def entrar_ambito(self, nombre: str) -> None:
        self.actual = Ambito(nombre, self.actual.nivel + 1, self.actual)
        self.eventos.append(f"{'  ' * self.actual.nivel}---> entra a '{nombre}' (nivel {self.actual.nivel})")

    def salir_ambito(self) -> Ambito:
        saliente = self.actual
        self.eventos.append(f"{'  ' * saliente.nivel}<--- sale de '{saliente.nombre}' "
                            f"(se destruyen: {', '.join(saliente.simbolos) or 'ninguna'})")
        if saliente.padre is not None:  # Nunca se sale del ámbito GLOBAL
            self.actual = saliente.padre
        return saliente

    def buscar_local(self, nombre: str) -> Optional[Simbolo]:
        return self.actual.simbolos.get(nombre)

    def buscar(self, nombre: str) -> Optional[Simbolo]:
        ambito = self.actual
        while ambito is not None:
            if nombre in ambito.simbolos:
                return ambito.simbolos[nombre]
            ambito = ambito.padre
        return None

    def definir(self, nombre: str, tipo: str, linea: int, columna: int) -> Simbolo:
        simbolo = Simbolo(nombre, tipo, self.actual.nombre, self.actual.nivel, linea, columna)
        simbolo.nombre_unico = self._generar_nombre_unico(nombre)
        simbolo.direccion = self._asignar_direccion(simbolo.tamanio)
        self.actual.simbolos[nombre] = simbolo
        self.todos.append(simbolo)
        self.eventos.append(f"{'  ' * (self.actual.nivel + 1)}[DECLARA] {tipo} {nombre} "
                            f"→ {simbolo.nombre_unico} @ 0x{simbolo.direccion:04X}")
        return simbolo

    def _generar_nombre_unico(self, nombre: str) -> str:
        base = nombre + "_v" if NOMBRES_RESERVADOS_IR.match(nombre) else nombre
        candidato, k = base, 1
        while candidato in self._nombres_usados:
            candidato = f"{base}_{k}"
            k += 1
        self._nombres_usados.add(candidato)
        return candidato

    def _asignar_direccion(self, tamanio: int) -> int:
        alineada = (self._siguiente_direccion + tamanio - 1) // tamanio * tamanio
        self._siguiente_direccion = alineada + tamanio
        return alineada

    def como_texto(self) -> str:
        encabezado = f"{'Nombre':<12}{'Interno':<12}{'Tipo':<10}{'Ámbito':<26}{'Nivel':<7}{'Línea':<7}{'Dirección':<11}{'Bytes':<6}"
        filas = [encabezado, "-" * len(encabezado)]
        for s in self.todos:
            filas.append(f"{s.nombre:<12}{s.nombre_unico:<12}{s.tipo:<10}{s.ambito:<26}{s.nivel:<7}"
                         f"{s.linea:<7}{'0x%04X' % s.direccion:<11}{s.tamanio:<6}")
        return "\n".join(filas)


# =============================================================== Analizador
@dataclass
class ResultadoSemantico:
    tabla: TablaSimbolos
    coerciones: list[str]


class AnalizadorSemantico:
    def __init__(self, reporte: ReporteErrores):
        self.reporte = reporte
        self.tabla = TablaSimbolos()
        self.coerciones: list[str] = []
        self._contador_bloques = 0

    def analizar(self, programa: Programa) -> ResultadoSemantico:
        for instr in programa.instrucciones:
            self._instruccion(instr)
        self._advertir_no_usadas(self.tabla.actual)
        return ResultadoSemantico(self.tabla, self.coerciones)

    def _error(self, mensaje: str, nodo: Nodo) -> None:
        self.reporte.error(SEMANTICO, mensaje, nodo.linea, nodo.columna)

    # ------------------------------------------------------------ instrucciones
    def _instruccion(self, n: Nodo) -> None:
        if isinstance(n, Declaracion):
            self._declaracion(n)
        elif isinstance(n, Asignacion):
            self._asignacion(n)
        elif isinstance(n, Si):
            self._condicion(n.condicion, "si")
            self._bloque(n.entonces, "si")
            if isinstance(n.sino, Bloque):
                self._bloque(n.sino, "sino")
            elif n.sino is not None:
                self._instruccion(n.sino)
        elif isinstance(n, Mientras):
            self._condicion(n.condicion, "mientras")
            self._bloque(n.cuerpo, "mientras")
        elif isinstance(n, Imprimir):
            self._expresion(n.valor)
        elif isinstance(n, Bloque):
            self._bloque(n, "bloque")

    def _bloque(self, bloque: Bloque, duenio: str) -> None:
        self._contador_bloques += 1
        self.tabla.entrar_ambito(f"{duenio}#{self._contador_bloques} (L:{bloque.linea})")
        for instr in bloque.instrucciones:
            self._instruccion(instr)
        self._advertir_no_usadas(self.tabla.actual)
        self.tabla.salir_ambito()

    def _advertir_no_usadas(self, ambito: Ambito) -> None:
        for s in ambito.simbolos.values():
            if not s.usado:
                self.reporte.advertencia(f"La variable '{s.nombre}' se declaró pero nunca se usa", s.linea, s.columna)

    def _declaracion(self, n: Declaracion) -> None:
        if n.valor is not None:
            tipo_valor = self._expresion(n.valor)
            n.valor = self._verificar_asignable(n.tipo_declarado, n.valor, tipo_valor, n.nombre, n)

        previa = self.tabla.buscar_local(n.nombre)
        if previa is not None:
            self._error(f"La variable '{n.nombre}' ya fue declarada en este ámbito (L:{previa.linea})", n)
            n.nombre_unico = previa.nombre_unico
            return

        externa = self.tabla.buscar(n.nombre)
        if externa is not None:
            self.reporte.advertencia(
                f"La variable '{n.nombre}' oculta a la declarada en el ámbito '{externa.ambito}' (L:{externa.linea})",
                n.linea, n.columna)

        simbolo = self.tabla.definir(n.nombre, n.tipo_declarado, n.linea, n.columna)
        simbolo.inicializado = n.valor is not None
        n.nombre_unico = simbolo.nombre_unico

    def _asignacion(self, n: Asignacion) -> None:
        tipo_valor = self._expresion(n.valor)
        simbolo = self.tabla.buscar(n.nombre)
        if simbolo is None:
            self._error(f"La variable '{n.nombre}' no ha sido declarada (o no es visible en este ámbito)", n)
            return
        n.valor = self._verificar_asignable(simbolo.tipo, n.valor, tipo_valor, n.nombre, n)
        simbolo.inicializado = True
        n.nombre_unico = simbolo.nombre_unico

    def _verificar_asignable(self, destino: str, expr: Expresion, origen: str, nombre: str, nodo: Nodo) -> Expresion:
        if origen == ERROR or destino == origen:
            return expr
        if destino == "real" and origen == "entero":
            self.coerciones.append(f"L:{nodo.linea} — '{nombre}': valor entero convertido implícitamente a real")
            return Conversion(expr, expr.linea, expr.columna)
        if destino == "entero" and origen == "real":
            self._error(f"No se puede asignar un valor real a '{nombre}' (entero): posible pérdida de precisión", nodo)
        else:
            self._error(f"Tipos incompatibles: no se puede asignar un valor {origen} a '{nombre}' ({destino})", nodo)
        return expr

    def _condicion(self, expr: Expresion, palabra: str) -> None:
        tipo = self._expresion(expr)
        if tipo not in (ERROR, "booleano"):
            self._error(f"La condición de '{palabra}' debe ser booleana, pero es de tipo {tipo}", expr)

    # -------------------------------------------------------------- expresiones
    def _expresion(self, n: Expresion) -> str:
        n.tipo = self._inferir(n)
        return n.tipo

    def _inferir(self, n: Expresion) -> str:
        if isinstance(n, Literal):
            return n.tipo
        if isinstance(n, Variable):
            simbolo = self.tabla.buscar(n.nombre)
            if simbolo is None:
                self._error(f"La variable '{n.nombre}' no ha sido declarada (o no es visible en este ámbito)", n)
                return ERROR
            if not simbolo.inicializado:
                self.reporte.advertencia(f"La variable '{n.nombre}' se usa sin haber sido inicializada", n.linea, n.columna)
            simbolo.usado = True
            n.nombre_unico = simbolo.nombre_unico
            return simbolo.tipo
        if isinstance(n, Unaria):
            tipo = self._expresion(n.operando)
            if tipo == ERROR:
                return ERROR
            if n.operador == "-" and tipo in NUMERICOS:
                return tipo
            if n.operador == "!" and tipo == "booleano":
                return "booleano"
            esperado = "numérico" if n.operador == "-" else "booleano"
            self._error(f"El operador '{n.operador}' requiere un operando {esperado}, pero recibió {tipo}", n)
            return ERROR
        if isinstance(n, Binaria):
            return self._binaria(n)
        if isinstance(n, Conversion):
            return "real"
        return ERROR

    def _promover(self, n: Binaria, ti: str, td: str) -> None:
        """Inserta Conversion entero→real en el operando que lo necesite."""
        if ti == "entero" and td == "real":
            n.izquierda = Conversion(n.izquierda, n.izquierda.linea, n.izquierda.columna)
            self.coerciones.append(f"L:{n.linea} — operando izquierdo de '{n.operador}' convertido a real")
        elif ti == "real" and td == "entero":
            n.derecha = Conversion(n.derecha, n.derecha.linea, n.derecha.columna)
            self.coerciones.append(f"L:{n.linea} — operando derecho de '{n.operador}' convertido a real")

    def _binaria(self, n: Binaria) -> str:
        ti = self._expresion(n.izquierda)
        td = self._expresion(n.derecha)
        if ERROR in (ti, td):
            return ERROR
        op = n.operador
        incompatibles = f"No se puede aplicar '{op}' entre {ti} y {td}"

        if op in ("+", "-", "*", "/", "%"):
            if op == "+" and ti == td == "texto":
                return "texto"
            if ti in NUMERICOS and td in NUMERICOS:
                if op in ("/", "%") and isinstance(n.derecha, Literal) and n.derecha.valor == 0:
                    self._error("División por cero detectada en tiempo de compilación", n)
                    return ERROR
                if op == "%":
                    if ti == td == "entero":
                        return "entero"
                    self._error("El operador '%' solo se aplica entre enteros", n)
                    return ERROR
                if ti == td:
                    return ti
                self._promover(n, ti, td)
                return "real"
            self._error(incompatibles, n)
            return ERROR

        if op in ("<", ">", "<=", ">="):
            if ti in NUMERICOS and td in NUMERICOS:
                self._promover(n, ti, td)
                return "booleano"
            self._error(f"{incompatibles}: la comparación '{op}' requiere números", n)
            return ERROR

        if op in ("==", "!="):
            if ti in NUMERICOS and td in NUMERICOS:
                self._promover(n, ti, td)
                return "booleano"
            if ti == td:
                return "booleano"
            self._error(incompatibles, n)
            return ERROR

        if op in ("&&", "||"):
            if ti == td == "booleano":
                return "booleano"
            self._error(f"{incompatibles}: '{op}' requiere operandos booleanos", n)
            return ERROR

        self._error(f"Operador desconocido '{op}'", n)
        return ERROR


def analizar(programa: Programa, reporte: ReporteErrores | None = None) -> ResultadoSemantico:
    return AnalizadorSemantico(reporte or ReporteErrores()).analizar(programa)
