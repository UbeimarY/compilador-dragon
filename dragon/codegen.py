"""
FASE 6 — GENERACIÓN DE CÓDIGO OBJETIVO
======================================

Traduce el TAC optimizado a un ensamblador de dos operandos con sintaxis
estilo x86 (Intel). Resuelve los tres retos del backend (Semana 10):

1. SELECCIÓN DE INSTRUCCIONES
   Cada operación del TAC se traduce según el TIPO de sus operandos:
       entero:   ADD  SUB  IMUL  IDIV  MOD
       real:     FADD FSUB FMUL  FDIV        (constantes reales en .data)
       texto:    CONCAT (rutina de la biblioteca de ejecución)
       comparar: CMP / FCMP / SCMP seguido de SETL, SETG, SETE, ...
   Respeta las restricciones reales de x86: nunca usa dos operandos de
   memoria en la misma instrucción (no existe MOV [a], [b]).

2. ASIGNACIÓN DE REGISTROS (con análisis de vida / liveness)
   Las variables del usuario viven en el segmento de datos (.data). Los
   temporales del TAC viven en registros físicos R0..Rn-1. Para cada
   temporal se calcula en qué instrucción se usa por última vez: en ese
   momento su registro se libera y se reutiliza.

3. DESBORDAMIENTO (SPILL)
   Si se necesita un registro y todos están ocupados por temporales que
   siguen vivos, se elige como VÍCTIMA el temporal cuyo próximo uso está
   más lejos (criterio de Belady) y se guarda en la pila:
       MOV [FP-8], R1        ; SPILL
   Cuando la víctima vuelve a necesitarse se lee desde la pila.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .tac import BINARIOS, Const, Cuadrupla, Operando, ProgramaTAC
from .utilidades import formatear_valor, valor_por_defecto

ES_TEMPORAL = re.compile(r"^t\d+$")
INFINITO = float("inf")

OPCODES = {
    ("+", "entero"): "ADD", ("-", "entero"): "SUB", ("*", "entero"): "IMUL",
    ("/", "entero"): "IDIV", ("%", "entero"): "MOD",
    ("+", "real"): "FADD", ("-", "real"): "FSUB", ("*", "real"): "FMUL", ("/", "real"): "FDIV",
    ("+", "texto"): "CONCAT",
    ("&&", "booleano"): "AND", ("||", "booleano"): "OR",
}
SETCC = {"<": "SETL", ">": "SETG", "<=": "SETLE", ">=": "SETGE", "==": "SETE", "!=": "SETNE"}
CMP_POR_TIPO = {"entero": "CMP", "booleano": "CMP", "real": "FCMP", "texto": "SCMP"}
DIRECTIVA = {"entero": "DD", "real": "DQ", "texto": "DQ", "booleano": "DB"}


@dataclass
class InstruccionASM:
    opcode: str
    operandos: list[str] = field(default_factory=list)
    comentario: str = ""

    def __str__(self) -> str:
        if self.opcode == "LABEL":
            return f"{self.operandos[0]}:"
        texto = f"    {self.opcode:<9}{', '.join(self.operandos)}"
        if self.comentario:
            texto = f"{texto:<36}; {self.comentario}"
        return texto


@dataclass
class CodigoObjetivo:
    datos: list[str]
    instrucciones: list[InstruccionASM]
    constantes: dict[str, object]
    valores_iniciales: dict[str, object]
    eventos: list[str]
    num_registros: int
    spills: int = 0
    tamanio_marco: int = 0

    def como_texto(self) -> str:
        partes = ["section .data"] + [f"    {d}" for d in self.datos]
        partes += ["", "section .text", "main:"]
        partes += [str(i) for i in self.instrucciones]
        return "\n".join(partes)


class GeneradorCodigo:
    def __init__(self, programa: ProgramaTAC, num_registros: int = 3):
        if num_registros < 2:
            raise ValueError("Se necesitan al menos 2 registros físicos")
        self.p = programa
        self.registros = [f"R{i}" for i in range(num_registros)]
        self.contenido: dict[str, Optional[str]] = {r: None for r in self.registros}
        self.ubicacion: dict[str, str] = {}        # temporal → registro o ranura de pila
        self.salida: list[InstruccionASM] = []
        self.eventos: list[str] = []
        self.constantes: dict[str, object] = {}
        self._etiqueta_const: dict[tuple, str] = {}
        self._ranuras = 0
        self.spills = 0
        self._usos: dict[str, list[int]] = {}
        self._i = 0

    # ------------------------------------------------------------ utilidades
    def _emitir(self, opcode: str, *operandos: str, comentario: str = "") -> None:
        self.salida.append(InstruccionASM(opcode, list(operandos), comentario))

    def _es_temporal(self, x: Operando) -> bool:
        return isinstance(x, str) and bool(ES_TEMPORAL.match(x))

    def _proximo_uso(self, temporal: str, despues_de: int) -> float:
        for pos in self._usos.get(temporal, []):
            if pos > despues_de:
                return pos
        return INFINITO

    def _muere_en(self, temporal: str, i: int) -> bool:
        return self._proximo_uso(temporal, i) == INFINITO

    def _constante(self, c: Const) -> str:
        clave = (c.tipo, c.valor)
        if clave not in self._etiqueta_const:
            prefijo = "str" if c.tipo == "texto" else "real"
            etiqueta = f"{prefijo}_{sum(1 for k in self._etiqueta_const if k[0] == c.tipo)}"
            self._etiqueta_const[clave] = etiqueta
            self.constantes[etiqueta] = c.valor
        return self._etiqueta_const[clave]

    def _operando(self, x: Operando) -> str:
        """Ubicación de un valor para usarlo como operando FUENTE."""
        if isinstance(x, Const):
            if x.tipo == "booleano":
                return "1" if x.valor else "0"
            if x.tipo == "entero":
                return str(x.valor)
            if x.tipo == "real":
                return f"[{self._constante(x)}]"
            return self._constante(x)  # texto: dirección de la cadena
        if self._es_temporal(x):
            return self.ubicacion[x]
        return f"[{x}]"

    def _en_memoria(self, operando: str) -> bool:
        return operando.startswith("[")

    def _registros_de(self, *args: Operando) -> set[str]:
        return {self.ubicacion[a] for a in args if self._es_temporal(a) and self.ubicacion.get(a, "").startswith("R")}

    # ------------------------------------------------ asignación de registros
    def _asignar(self, duenio: str, fijos: set[str]) -> str:
        for r in self.registros:
            if self.contenido[r] is None and r not in fijos:
                self._ocupar(r, duenio)
                return r
        # No hay registros libres: SPILL de la víctima con el próximo uso más lejano
        candidatos = [r for r in self.registros if r not in fijos]
        victima_reg = max(candidatos, key=lambda r: self._proximo_uso(self.contenido[r], self._i))
        victima = self.contenido[victima_reg]
        self._ranuras += 1
        ranura = f"[FP-{8 * self._ranuras}]"
        proximo = self._proximo_uso(victima, self._i)
        self._emitir("MOV", ranura, victima_reg,
                     comentario=f"SPILL: {victima} se desaloja a la pila (se usa de nuevo en TAC {int(proximo):03d})")
        self.ubicacion[victima] = ranura
        self.spills += 1
        self.eventos.append(f"TAC {self._i:03d}: SPILL  {victima} {victima_reg} → {ranura} "
                            f"(su próximo uso es el más lejano: TAC {int(proximo):03d})")
        self._ocupar(victima_reg, duenio)
        return victima_reg

    def _ocupar(self, registro: str, duenio: str) -> None:
        self.contenido[registro] = duenio
        if self._es_temporal(duenio):
            self.ubicacion[duenio] = registro
            self.eventos.append(f"TAC {self._i:03d}: ASIGNA {duenio} → {registro}")

    def _liberar_registro(self, registro: str) -> None:
        self.contenido[registro] = None

    def _liberar_muertos(self, *args: Operando) -> None:
        for a in set(args):
            if self._es_temporal(a) and self._muere_en(a, self._i) and a in self.ubicacion:
                lugar = self.ubicacion.pop(a)
                if lugar.startswith("R") and self.contenido.get(lugar) == a:
                    self._liberar_registro(lugar)
                    self.eventos.append(f"TAC {self._i:03d}: LIBERA {lugar} ({a} ya no se usa más)")

    def _registro_destino(self, q: Cuadrupla) -> tuple[str, bool]:
        """Elige el registro donde se calculará q. Devuelve (registro, ya_contiene_arg1)."""
        a = q.arg1
        duenio = q.res if self._es_temporal(q.res) else "·tmp"
        if (self._es_temporal(a) and a != q.arg2 and self.ubicacion.get(a, "").startswith("R")
                and self._muere_en(a, self._i)):
            reg = self.ubicacion.pop(a)
            self.eventos.append(f"TAC {self._i:03d}: REUSA  {reg} de {a} (muere aquí)")
            self._ocupar(reg, duenio)
            return reg, True
        return self._asignar(duenio, self._registros_de(q.arg1, q.arg2)), False

    def _guardar_resultado(self, q: Cuadrupla, reg: str) -> None:
        if not self._es_temporal(q.res):  # variable de usuario: vuelve a memoria
            self._emitir("MOV", f"[{q.res}]", reg, comentario=f"{q.res} = resultado")
            self._liberar_registro(reg)

    # ------------------------------------------------------------- traducción
    def generar(self) -> CodigoObjetivo:
        instrucciones = self.p.instrucciones
        for i, q in enumerate(instrucciones):
            for u in q.usos():
                if self._es_temporal(u):
                    self._usos.setdefault(u, []).append(i)

        for i, q in enumerate(instrucciones):
            self._i = i
            self._traducir(q)

        cuerpo = self.salida
        self.salida = []
        self._emitir("PUSH", "FP", comentario="prólogo: guarda el marco anterior")
        self._emitir("MOV", "FP", "SP")
        if self._ranuras:
            self._emitir("SUB", "SP", str(8 * self._ranuras),
                         comentario=f"reserva {self._ranuras} ranura(s) de 8 bytes para SPILL")
        prologo = self.salida
        self.salida = []
        self._emitir("MOV", "SP", "FP", comentario="epílogo: libera el marco")
        self._emitir("POP", "FP")
        self._emitir("HLT", comentario="fin del programa")

        return CodigoObjetivo(
            datos=self._seccion_datos(),
            instrucciones=prologo + cuerpo + self.salida,
            constantes=self.constantes,
            valores_iniciales={s.nombre_unico: valor_por_defecto(s.tipo) for s in self.p.variables},
            eventos=self.eventos,
            num_registros=len(self.registros),
            spills=self.spills,
            tamanio_marco=8 * self._ranuras,
        )

    def _seccion_datos(self) -> list[str]:
        lineas = []
        for s in self.p.variables:
            inicial = "0.0" if s.tipo == "real" else "0"
            nota = f"{s.tipo} '{s.nombre}' @0x{s.direccion:04X}" + (" (puntero)" if s.tipo == "texto" else "")
            lineas.append(f"{s.nombre_unico:<14}{DIRECTIVA[s.tipo]} {inicial:<16}; {nota}")
        for etiqueta, valor in self.constantes.items():
            if isinstance(valor, str):
                literal = Const(valor, "texto")
                lineas.append(f"{etiqueta:<14}DB {str(literal) + ', 0':<16}; constante de texto")
            else:
                lineas.append(f"{etiqueta:<14}DQ {formatear_valor(valor):<16}; constante real")
        return lineas

    def _traducir(self, q: Cuadrupla) -> None:
        comentario = str(q).strip()
        recargas = [a for a in dict.fromkeys(q.usos())
                    if self._es_temporal(a) and self.ubicacion.get(a, "").startswith("[FP")]
        for a in recargas:
            self.eventos.append(f"TAC {self._i:03d}: RECARGA {a} se lee desde {self.ubicacion[a]}")
        if recargas:
            comentario += f"   (RECARGA {', '.join(recargas)} desde la pila)"
        if q.op == "label":
            self._emitir("LABEL", q.res)
            return
        if q.op == "goto":
            self._emitir("JMP", q.res, comentario=comentario)
            return
        if q.op == "if_false":
            self._salto_condicional(q, comentario)
            return
        if q.op == "print":
            tipo = self.p.tipo_de(q.arg1)
            self._emitir("PARAM", self._operando(q.arg1), comentario=comentario)
            self._emitir("CALL", f"imprimir_{tipo}")
            self._liberar_muertos(q.arg1)
            return
        if q.op == "=":
            self._copia(q, comentario)
            return
        if q.op in ("neg", "not", "itof"):
            self._unaria(q, comentario)
            return
        if q.op in BINARIOS:
            self._binaria(q, comentario)
            return
        raise ValueError(f"Operación TAC no soportada: {q}")

    def _salto_condicional(self, q: Cuadrupla, comentario: str) -> None:
        cond = self._operando(q.arg1)
        if isinstance(q.arg1, Const):  # solo ocurre si no se optimizó
            reg = self._asignar("·tmp", set())
            self._emitir("MOV", reg, cond)
            cond = reg
            self._liberar_registro(reg)
        self._emitir("CMP", cond, "0", comentario=comentario)
        self._emitir("JE", q.res, comentario="salta si la condición es falsa")
        self._liberar_muertos(q.arg1)

    def _copia(self, q: Cuadrupla, comentario: str) -> None:
        origen = self._operando(q.arg1)
        if self._es_temporal(q.res):
            reg, contiene = self._registro_destino(q)
            if not contiene:
                self._emitir("MOV", reg, origen, comentario=comentario)
            self._liberar_muertos(q.arg1)
            return
        destino = f"[{q.res}]"
        if self._en_memoria(origen):  # x86 no permite MOV memoria, memoria
            reg = self._asignar("·tmp", self._registros_de(q.arg1))
            self._emitir("MOV", reg, origen, comentario=comentario)
            self._emitir("MOV", destino, reg)
            self._liberar_registro(reg)
        else:
            self._emitir("MOV", destino, origen, comentario=comentario)
        self._liberar_muertos(q.arg1)

    def _unaria(self, q: Cuadrupla, comentario: str) -> None:
        tipo = self.p.tipo_de(q.res)
        if q.op == "itof":
            fuente = self._operando(q.arg1)
            reg, _ = self._registro_destino(q)
            self._emitir("CVTSI2SD", reg, fuente, comentario=comentario)
        else:
            fuente = self._operando(q.arg1)
            reg, contiene = self._registro_destino(q)
            if not contiene:
                self._emitir("MOV", reg, fuente, comentario=comentario)
            if q.op == "neg":
                self._emitir("FNEG" if tipo == "real" else "NEG", reg, comentario="" if not contiene else comentario)
            else:
                self._emitir("XOR", reg, "1", comentario="negación lógica" if not contiene else comentario)
        self._liberar_muertos(q.arg1)
        self._guardar_resultado(q, reg)

    def _binaria(self, q: Cuadrupla, comentario: str) -> None:
        tipo_operandos = self.p.tipo_de(q.arg1)
        reg, contiene = self._registro_destino(q)
        if not contiene:
            self._emitir("MOV", reg, self._operando(q.arg1), comentario=comentario)
        segundo = self._operando(q.arg2)
        nota = "" if not contiene else comentario
        if q.op in SETCC:
            self._emitir(CMP_POR_TIPO[tipo_operandos], reg, segundo, comentario=nota)
            self._emitir(SETCC[q.op], reg)
        else:
            self._emitir(OPCODES[(q.op, tipo_operandos)], reg, segundo, comentario=nota)
        self._liberar_muertos(q.arg1, q.arg2)
        self._guardar_resultado(q, reg)


def generar_codigo(programa: ProgramaTAC, num_registros: int = 3) -> CodigoObjetivo:
    return GeneradorCodigo(programa, num_registros).generar()
