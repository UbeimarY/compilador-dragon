"""
FASE 7 — VERIFICACIÓN POR EMULACIÓN
===================================

El primer reto del backend es PRESERVAR LA SEMÁNTICA: el código generado
debe producir exactamente los mismos resultados que el programa fuente.
Para demostrarlo, este módulo incluye dos máquinas virtuales:

* EmuladorTAC  — ejecuta las cuádruplas sobre una memoria virtual
                 (evolución del emulador de la Semana 7, con saltos).
* EmuladorASM  — ejecuta el ensamblador generado: registros, memoria,
                 pila para los SPILL, banderas de comparación y saltos.

El compilador ejecuta el TAC original, el TAC optimizado y el ensamblador,
y compara las tres salidas: si coinciden, la optimización y la generación
de código conservaron el significado del programa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .codegen import CodigoObjetivo
from .tac import Const, ProgramaTAC
from .utilidades import (ErrorEjecucion, Heap, Puntero, division_entera,
                         formatear_valor, modulo_entero, operar,
                         operar_con_heap, operar_unaria, valor_por_defecto)

LIMITE_PASOS = 1_000_000


@dataclass
class ResultadoEjecucion:
    salida: list[str] = field(default_factory=list)
    memoria: dict = field(default_factory=dict)
    pasos: int = 0
    error: str | None = None
    heap: Heap | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ======================================================================= TAC
class EmuladorTAC:
    """Ejecuta cuádruplas. Las variables globales viven en `memoria`; los
    parámetros, las variables locales y los temporales viven en el MARCO de la
    llamada actual (una pila de diccionarios), lo que permite la recursión."""

    LIMITE_LLAMADAS = 500

    def __init__(self, programa: ProgramaTAC):
        self.p = programa
        self.heap = Heap()
        self.globales = programa.globales
        self.memoria = {s.nombre_unico: self._inicial(s.tipo) for s in programa.variables}
        self.marcos: list[dict] = [{}]
        self.llamadas: list[tuple[int, str | None]] = []
        self.argumentos: list = []

    def _inicial(self, tipo: str):
        return self.heap.vacia if tipo == "texto" else valor_por_defecto(tipo)

    def _valor(self, x):
        if isinstance(x, Const):
            return self.heap.estatico(x.valor) if x.tipo == "texto" else x.valor
        if x in self.globales:
            return self.memoria[x]
        marco = self.marcos[-1]
        if x not in marco:
            return self._inicial(self.p.tipos.get(x, "entero"))
        return marco[x]

    def _escribir(self, nombre: str, valor) -> None:
        if nombre in self.globales:
            self.memoria[nombre] = valor
        else:
            self.marcos[-1][nombre] = valor

    def ejecutar(self) -> ResultadoEjecucion:
        r = ResultadoEjecucion()
        instr = self.p.instrucciones
        etiquetas = {q.res: i for i, q in enumerate(instr) if q.op in ("label", "func")}
        pc = 0
        try:
            while pc < len(instr):
                r.pasos += 1
                if r.pasos > LIMITE_PASOS:
                    raise ErrorEjecucion(f"Se superaron {LIMITE_PASOS} pasos: posible ciclo infinito")
                q = instr[pc]
                pc += 1
                if q.op in ("label", "func", "fin_func"):
                    continue
                if q.op == "fin":
                    break
                if q.op == "goto":
                    pc = etiquetas[q.res]
                elif q.op == "if_false":
                    if not self._valor(q.arg1):
                        pc = etiquetas[q.res]
                elif q.op == "print":
                    r.salida.append(formatear_valor(self.heap.leer(self._valor(q.arg1))
                                                    if self.p.tipo_de(q.arg1) == "texto" else self._valor(q.arg1)))
                elif q.op == "param":
                    self.argumentos.append(self._valor(q.arg1))
                elif q.op == "call":
                    if len(self.llamadas) >= self.LIMITE_LLAMADAS:
                        raise ErrorEjecucion(f"Stack Overflow: más de {self.LIMITE_LLAMADAS} llamadas anidadas "
                                             f"(¿recursión infinita en '{q.arg1}'?)")
                    info = self.p.funciones[q.arg1]
                    n = q.arg2
                    valores = self.argumentos[len(self.argumentos) - n:] if n else []
                    del self.argumentos[len(self.argumentos) - n:]
                    self.llamadas.append((pc, q.res))
                    self.marcos.append(dict(zip(info.parametros, valores)))
                    pc = etiquetas[q.arg1] + 1
                elif q.op == "return":
                    valor = self._valor(q.arg1) if q.arg1 is not None else None
                    if not self.llamadas:
                        break
                    pc, destino = self.llamadas.pop()
                    self.marcos.pop()
                    if destino is not None:
                        self._escribir(destino, valor if valor is not None
                                       else self._inicial(self.p.tipos.get(destino, "entero")))
                elif q.op == "free":
                    self.heap.liberar(self._valor(q.arg1))
                elif q.op == "=":
                    self._escribir(q.res, self._valor(q.arg1))
                elif q.op in ("neg", "not", "itof"):
                    self._escribir(q.res, operar_unaria(q.op, self._valor(q.arg1)))
                else:
                    self._escribir(q.res, operar_con_heap(self.heap, q.op, self._valor(q.arg1), self._valor(q.arg2)))
        except ErrorEjecucion as e:
            r.error = f"{e} (instrucción TAC {pc - 1:03d})"
        r.memoria = dict(self.memoria)
        r.heap = self.heap
        return r


# ======================================================================= ASM
class EmuladorASM:
    """CPU simulada que ejecuta el ensamblador generado.

    * Registros R0..Rn-1, RV (valor de retorno), SP (tope de la pila) y FP (marco).
    * Memoria con nombre para .data y las constantes; una PILA real direccionada
      por números que crece hacia abajo: PUSH/POP, CALL/RET y [FP±k] la usan.
    * Un heap para los textos (Semana 8).
    """

    TOPE_PILA = 0x20000
    LIMITE_PILA = 0x20000 - 64 * 1024   # 64 KB de pila: más allá hay Stack Overflow

    def __init__(self, codigo: CodigoObjetivo):
        self.c = codigo
        self.heap = Heap()
        self.registros = {f"R{i}": 0 for i in range(codigo.num_registros)}
        self.registros.update({"RV": 0, "SP": self.TOPE_PILA, "FP": self.TOPE_PILA})
        self.memoria: dict[str, object] = {
            k: (self.heap.estatico(v) if isinstance(v, str) else v) for k, v in codigo.valores_iniciales.items()}
        self.memoria.update({k: v for k, v in codigo.constantes.items() if not isinstance(v, str)})
        self.pila: dict[int, object] = {}
        self.comparacion: tuple = (0, 0)
        self.parametros: list = []
        self.profundidad = 0   # llamadas anidadas en curso

    def _direccion_pila(self, operando: str):
        """'[FP-8]' → dirección numérica; None si no es un acceso a la pila."""
        interior = operando[1:-1]
        if interior.startswith(("FP", "SP")) and len(interior) > 2:
            return self.registros[interior[:2]] + int(interior[2:])
        return None

    def _leer(self, operando: str):
        if operando in self.registros:
            return self.registros[operando]
        if operando.startswith("["):
            direccion = self._direccion_pila(operando)
            if direccion is not None:
                if direccion not in self.pila:
                    raise ErrorEjecucion(f"Lectura de una posición de pila sin inicializar {operando}")
                return self.pila[direccion]
            clave = operando[1:-1]
            if clave not in self.memoria:
                raise ErrorEjecucion(f"Lectura de memoria no inicializada {operando}")
            return self.memoria[clave]
        if operando in self.c.constantes:  # dirección de una cadena constante (str_0)
            return self.heap.estatico(self.c.constantes[operando])
        return int(operando)

    def _escribir(self, operando: str, valor) -> None:
        if operando in self.registros:
            self.registros[operando] = valor
            if operando == "SP" and valor < self.LIMITE_PILA:
                raise ErrorEjecucion("Stack Overflow: la pila superó los 64 KB (¿recursión infinita?)")
        elif operando.startswith("["):
            direccion = self._direccion_pila(operando)
            if direccion is not None:
                self.pila[direccion] = valor
            else:
                self.memoria[operando[1:-1]] = valor
        else:
            raise ErrorEjecucion(f"Destino no válido: {operando}")

    def _push(self, valor) -> None:
        self._escribir("SP", self.registros["SP"] - 8)
        self.pila[self.registros["SP"]] = valor

    def _pop(self):
        valor = self.pila.get(self.registros["SP"])
        self.registros["SP"] += 8
        return valor

    def ejecutar(self) -> ResultadoEjecucion:
        r = ResultadoEjecucion()
        instr = self.c.instrucciones
        etiquetas = {i.operandos[0]: n for n, i in enumerate(instr) if i.opcode == "LABEL"}
        pc = 0
        try:
            while pc < len(instr):
                r.pasos += 1
                if r.pasos > LIMITE_PASOS:
                    raise ErrorEjecucion(f"Se superaron {LIMITE_PASOS} pasos: posible ciclo infinito")
                ins = instr[pc]
                pc += 1
                op, ops = ins.opcode, ins.operandos
                if op == "HLT":
                    break
                if op == "LABEL":
                    continue
                if op == "MOV":
                    self._escribir(ops[0], self._leer(ops[1]))
                elif op == "PUSH":
                    self._push(self._leer(ops[0]))
                elif op == "POP":
                    self._escribir(ops[0], self._pop())
                elif op == "CONCAT":
                    self._escribir(ops[0], self.heap.concatenar(self._leer(ops[0]), self._leer(ops[1])))
                elif op in ("ADD", "FADD"):
                    self._escribir(ops[0], self._leer(ops[0]) + self._leer(ops[1]))
                elif op in ("SUB", "FSUB"):
                    self._escribir(ops[0], self._leer(ops[0]) - self._leer(ops[1]))
                elif op in ("IMUL", "FMUL"):
                    self._escribir(ops[0], self._leer(ops[0]) * self._leer(ops[1]))
                elif op in ("IDIV", "MOD", "FDIV"):
                    divisor = self._leer(ops[1])
                    if divisor == 0:
                        raise ErrorEjecucion("División por cero")
                    a = self._leer(ops[0])
                    valor = {"IDIV": division_entera, "MOD": modulo_entero}.get(op, lambda x, y: x / y)(a, divisor)
                    self._escribir(ops[0], valor)
                elif op in ("NEG", "FNEG"):
                    self._escribir(ops[0], -self._leer(ops[0]))
                elif op == "XOR":
                    self._escribir(ops[0], int(self._leer(ops[0])) ^ int(self._leer(ops[1])))
                elif op == "AND":
                    self._escribir(ops[0], int(bool(self._leer(ops[0])) and bool(self._leer(ops[1]))))
                elif op == "OR":
                    self._escribir(ops[0], int(bool(self._leer(ops[0])) or bool(self._leer(ops[1]))))
                elif op == "CVTSI2SD":
                    self._escribir(ops[0], float(self._leer(ops[1])))
                elif op in ("CMP", "FCMP"):
                    self.comparacion = (self._leer(ops[0]), self._leer(ops[1]))
                elif op == "SCMP":  # compara el CONTENIDO de dos cadenas
                    self.comparacion = (self.heap.leer(self._leer(ops[0])), self.heap.leer(self._leer(ops[1])))
                elif op.startswith("SET"):
                    a, b = self.comparacion
                    simbolo = {"SETL": "<", "SETG": ">", "SETLE": "<=", "SETGE": ">=", "SETE": "==", "SETNE": "!="}[op]
                    self._escribir(ops[0], int(operar(simbolo, a, b)))
                elif op == "JMP":
                    pc = etiquetas[ops[0]]
                elif op == "JE":
                    a, b = self.comparacion
                    if a == b:
                        pc = etiquetas[ops[0]]
                elif op == "PARAM":
                    self.parametros.append(self._leer(ops[0]))
                elif op == "CALL":
                    destino = ops[0]
                    if destino in etiquetas:          # función del usuario
                        if self.profundidad >= EmuladorTAC.LIMITE_LLAMADAS:
                            raise ErrorEjecucion(f"Stack Overflow: más de {EmuladorTAC.LIMITE_LLAMADAS} llamadas "
                                                 f"anidadas (¿recursión infinita en '{destino[3:]}'?)")
                        self.profundidad += 1
                        self._push(pc)                # dirección de retorno
                        pc = etiquetas[destino]
                    elif destino == "liberar":
                        self.heap.liberar(self.parametros.pop())
                    elif destino.startswith("imprimir_"):
                        valor = self.parametros.pop()
                        if destino == "imprimir_booleano":
                            valor = bool(valor)
                        elif destino == "imprimir_real":
                            valor = float(valor)
                        elif destino == "imprimir_texto":
                            valor = self.heap.leer(valor)
                        r.salida.append(formatear_valor(valor))
                    else:
                        raise ErrorEjecucion(f"Rutina desconocida {destino}")
                elif op == "RET":
                    self.profundidad -= 1
                    pc = self._pop()
                else:
                    raise ErrorEjecucion(f"Instrucción desconocida {op}")
        except ErrorEjecucion as e:
            fallida = instr[pc - 1]
            r.error = f"{e} (instrucción ASM: {fallida.opcode} {', '.join(fallida.operandos)})"
        r.memoria = {k: v for k, v in self.memoria.items() if k in self.c.valores_iniciales}
        r.heap = self.heap
        return r
