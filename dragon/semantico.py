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
   ámbitos distintos) y una DIRECCIÓN: las variables globales viven en el
   segmento de datos (0x1000...) y las de una función en su MARCO DE PILA
   (parámetros en FP+16, FP+24...; variables locales en FP-8, FP-16...).
   Así las fases siguientes ya no necesitan conocer los ámbitos.

   FUNCIONES (Semana 6): se registran todas las firmas en una pasada previa
   (permite llamar a una función declarada más abajo y la recursión), y se
   verifica el número y el tipo de los argumentos, el tipo de retorno y que
   toda función no vacía tenga un 'retornar'.

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
                        Expresion, Funcion, Imprimir, InstruccionExpresion,
                        Liberar, Literal, Llamada, Mientras, Nodo, Programa,
                        Retornar, Si, Unaria, Variable)
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
    funcion: Optional[str] = None      # None = variable global
    desplazamiento: int = 0            # posición relativa a FP si es local
    es_parametro: bool = False

    @property
    def tamanio(self) -> int:
        return TAMANIOS[self.tipo]

    @property
    def es_local(self) -> bool:
        return self.funcion is not None

    @property
    def ubicacion(self) -> str:
        return f"FP{self.desplazamiento:+d}" if self.es_local else "0x%04X" % self.direccion


@dataclass
class InfoFuncion:
    nombre: str
    tipo_retorno: str
    tipos_parametros: list[str]
    linea: int
    columna: int
    parametros: list[str] = field(default_factory=list)   # nombres únicos, en orden
    locales: list[str] = field(default_factory=list)      # nombres únicos de variables locales
    tiene_retorno: bool = False
    usada: bool = False

    @property
    def firma(self) -> str:
        return f"{self.tipo_retorno} {self.nombre}({', '.join(self.tipos_parametros)})"


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

    def definir(self, nombre: str, tipo: str, linea: int, columna: int,
                funcion: Optional[str] = None, desplazamiento: int = 0,
                es_parametro: bool = False) -> Simbolo:
        simbolo = Simbolo(nombre, tipo, self.actual.nombre, self.actual.nivel, linea, columna,
                          funcion=funcion, desplazamiento=desplazamiento, es_parametro=es_parametro)
        simbolo.nombre_unico = self._generar_nombre_unico(nombre)
        if funcion is None:
            simbolo.direccion = self._asignar_direccion(simbolo.tamanio)
        self.actual.simbolos[nombre] = simbolo
        self.todos.append(simbolo)
        clase = "parámetro" if es_parametro else tipo
        self.eventos.append(f"{'  ' * (self.actual.nivel + 1)}[DECLARA] {clase} {nombre} "
                            f"→ {simbolo.nombre_unico} @ {simbolo.ubicacion}")
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
        columnas = ["Nombre", "Interno", "Tipo", "Ámbito", "Nivel", "Línea", "Dirección", "Bytes"]
        datos = [[s.nombre, s.nombre_unico, s.tipo, s.ambito, str(s.nivel), str(s.linea),
                  s.ubicacion, str(s.tamanio)] for s in self.todos]
        anchos = [max([len(c)] + [len(f[i]) for f in datos]) + 2 for i, c in enumerate(columnas)]
        fila = lambda valores: "".join(v.ljust(a) for v, a in zip(valores, anchos)).rstrip()
        encabezado = fila(columnas)
        return "\n".join([encabezado, "-" * len(encabezado)] + [fila(f) for f in datos])


# =============================================================== Analizador
@dataclass
class ResultadoSemantico:
    tabla: TablaSimbolos
    coerciones: list[str]
    funciones: dict[str, InfoFuncion] = field(default_factory=dict)

    def funciones_como_texto(self) -> str:
        if not self.funciones:
            return "(el programa no declara funciones)"
        filas = []
        for f in self.funciones.values():
            marco = 8 * len(f.locales)
            filas.append(f"{f.firma:<40} L:{f.linea:<5} parámetros: {len(f.parametros)} · "
                         f"locales: {len(f.locales)} ({marco} bytes en el marco)")
        return "\n".join(filas)


class AnalizadorSemantico:
    def __init__(self, reporte: ReporteErrores):
        self.reporte = reporte
        self.tabla = TablaSimbolos()
        self.coerciones: list[str] = []
        self.funciones: dict[str, InfoFuncion] = {}
        self._funcion_actual: Optional[InfoFuncion] = None
        self._contador_bloques = 0

    def analizar(self, programa: Programa) -> ResultadoSemantico:
        # Pasada previa: registrar todas las firmas (permite recursión y llamar
        # a funciones declaradas más abajo en el archivo).
        for instr in programa.instrucciones:
            if isinstance(instr, Funcion):
                self._registrar_firma(instr)
        for instr in programa.instrucciones:
            if isinstance(instr, Funcion):
                self._funcion(instr)
            else:
                self._instruccion(instr)
        self._advertir_no_usadas(self.tabla.actual)
        return ResultadoSemantico(self.tabla, self.coerciones, self.funciones)

    # ---------------------------------------------------------------- funciones
    def _registrar_firma(self, n: Funcion) -> None:
        if n.nombre in self.funciones:
            previa = self.funciones[n.nombre]
            self._error(f"La función '{n.nombre}' ya fue declarada (L:{previa.linea})", n)
            return
        self.funciones[n.nombre] = InfoFuncion(n.nombre, n.tipo_retorno, [p.tipo for p in n.parametros],
                                               n.linea, n.columna)

    def _funcion(self, n: Funcion) -> None:
        info = self.funciones.get(n.nombre)
        if info is None or info.linea != n.linea:  # duplicada: ya se reportó
            return
        self._funcion_actual = info
        self.tabla.entrar_ambito(f"funcion {n.nombre}")
        total = len(n.parametros)
        for i, p in enumerate(n.parametros):
            if self.tabla.buscar_local(p.nombre):
                self._error(f"El parámetro '{p.nombre}' está repetido en '{n.nombre}'", p)
                continue
            # Convención de llamada: el último argumento apilado queda más cerca de FP
            s = self.tabla.definir(p.nombre, p.tipo, p.linea, p.columna, funcion=n.nombre,
                                   desplazamiento=16 + 8 * (total - 1 - i), es_parametro=True)
            s.inicializado = s.usado = True
            p.nombre_unico = s.nombre_unico
            info.parametros.append(s.nombre_unico)
        # El cuerpo comparte el ámbito de los parámetros (como en C)
        for instr in n.cuerpo.instrucciones:
            self._instruccion(instr)
        self._advertir_no_usadas(self.tabla.actual)
        self.tabla.salir_ambito()
        if info.tipo_retorno != "vacio" and not info.tiene_retorno:
            self._error(f"La función '{n.nombre}' debe retornar un valor de tipo {info.tipo_retorno} "
                        f"(no tiene ningún 'retornar')", n)
        self._funcion_actual = None

    def _definir_variable(self, nombre: str, tipo: str, nodo: Nodo) -> Simbolo:
        f = self._funcion_actual
        if f is None:
            return self.tabla.definir(nombre, tipo, nodo.linea, nodo.columna)
        s = self.tabla.definir(nombre, tipo, nodo.linea, nodo.columna, funcion=f.nombre,
                               desplazamiento=-8 * (len(f.locales) + 1))
        f.locales.append(s.nombre_unico)
        return s

    def _retornar(self, n: Retornar) -> None:
        f = self._funcion_actual
        if f is None:
            self._error("'retornar' solo puede usarse dentro de una función", n)
            if n.valor is not None:
                self._expresion(n.valor)
            return
        f.tiene_retorno = True
        if f.tipo_retorno == "vacio":
            if n.valor is not None:
                self._expresion(n.valor)
                self._error(f"La función '{f.nombre}' es vacio: 'retornar' no puede llevar un valor", n)
            return
        if n.valor is None:
            self._error(f"La función '{f.nombre}' debe retornar un valor de tipo {f.tipo_retorno}", n)
            return
        tipo = self._expresion(n.valor)
        n.valor = self._verificar_asignable(f.tipo_retorno, n.valor, tipo, f.nombre, n,
                                            contexto=f"El valor retornado por '{f.nombre}'")

    def _llamada(self, n: Llamada) -> str:
        f = self.funciones.get(n.nombre)
        tipos = [self._expresion(a) for a in n.argumentos]
        if f is None:
            self._error(f"La función '{n.nombre}' no ha sido declarada", n)
            return ERROR
        f.usada = True
        if len(n.argumentos) != len(f.tipos_parametros):
            self._error(f"La función '{n.nombre}' espera {len(f.tipos_parametros)} argumento(s), "
                        f"pero recibió {len(n.argumentos)}", n)
            return f.tipo_retorno
        for i, (arg, tipo, esperado) in enumerate(zip(n.argumentos, tipos, f.tipos_parametros)):
            n.argumentos[i] = self._verificar_asignable(
                esperado, arg, tipo, n.nombre, arg, contexto=f"El argumento {i + 1} de '{n.nombre}'")
        return f.tipo_retorno

    def _liberar(self, n: Liberar) -> None:
        tipo = self._expresion(n.variable)
        if tipo not in (ERROR, "texto"):
            self._error(f"Solo se puede liberar un texto (memoria del heap); "
                        f"'{n.variable.nombre}' es {tipo}", n)

    def _error(self, mensaje: str, nodo: Nodo) -> None:
        self.reporte.error(SEMANTICO, mensaje, nodo.linea, nodo.columna)

    # ------------------------------------------------------------ instrucciones
    def _instruccion(self, n: Nodo) -> None:
        if isinstance(n, Retornar):
            self._retornar(n)
        elif isinstance(n, Liberar):
            self._liberar(n)
        elif isinstance(n, InstruccionExpresion):
            self._expresion(n.expresion, permitir_vacio=True)
        elif isinstance(n, Funcion):
            pass  # función dentro de un bloque: el parser ya reportó el error
        elif isinstance(n, Declaracion):
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
            if not s.usado and not s.es_parametro:
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

        simbolo = self._definir_variable(n.nombre, n.tipo_declarado, n)
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

    def _verificar_asignable(self, destino: str, expr: Expresion, origen: str, nombre: str, nodo: Nodo,
                             contexto: Optional[str] = None) -> Expresion:
        """`contexto` describe un argumento o un retorno ("El argumento 1 de 'f'")."""
        if origen == ERROR or destino == origen:
            return expr
        if destino == "real" and origen == "entero":
            quien = contexto or f"'{nombre}'"
            self.coerciones.append(f"L:{nodo.linea} — {quien}: valor entero convertido implícitamente a real")
            return Conversion(expr, expr.linea, expr.columna)
        if contexto:
            extra = " (posible pérdida de precisión)" if (destino, origen) == ("entero", "real") else ""
            self._error(f"{contexto} debe ser {destino}, pero se recibió un valor {origen}{extra}", nodo)
        elif destino == "entero" and origen == "real":
            self._error(f"No se puede asignar un valor real a '{nombre}' (entero): posible pérdida de precisión", nodo)
        else:
            self._error(f"Tipos incompatibles: no se puede asignar un valor {origen} a '{nombre}' ({destino})", nodo)
        return expr

    def _condicion(self, expr: Expresion, palabra: str) -> None:
        tipo = self._expresion(expr)
        if tipo not in (ERROR, "booleano"):
            self._error(f"La condición de '{palabra}' debe ser booleana, pero es de tipo {tipo}", expr)

    # -------------------------------------------------------------- expresiones
    def _expresion(self, n: Expresion, permitir_vacio: bool = False) -> str:
        n.tipo = self._inferir(n)
        if n.tipo == "vacio" and not permitir_vacio:
            self._error(f"La función '{n.nombre}' es vacio: no devuelve un valor que se pueda usar", n)
            n.tipo = ERROR
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
        if isinstance(n, Llamada):
            return self._llamada(n)
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
