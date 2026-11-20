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
from .utilidades import (ErrorEjecucion, division_entera, formatear_valor,
                         modulo_entero, operar, operar_unaria,
                         valor_por_defecto)

LIMITE_PASOS = 1_000_000


@dataclass
class ResultadoEjecucion:
    salida: list[str] = field(default_factory=list)
    memoria: dict = field(default_factory=dict)
    pasos: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ======================================================================= TAC
class EmuladorTAC:
    def __init__(self, programa: ProgramaTAC):
        self.p = programa
        self.memoria = {s.nombre_unico: valor_por_defecto(s.tipo) for s in programa.variables}

    def _valor(self, x):
        if isinstance(x, Const):
            return x.valor
        if x not in self.memoria:
            return valor_por_defecto(self.p.tipos.get(x, "entero"))
        return self.memoria[x]

    def ejecutar(self) -> ResultadoEjecucion:
        r = ResultadoEjecucion()
        instr = self.p.instrucciones
        etiquetas = {q.res: i for i, q in enumerate(instr) if q.op == "label"}
        pc = 0
        try:
            while pc < len(instr):
                r.pasos += 1
                if r.pasos > LIMITE_PASOS:
                    raise ErrorEjecucion(f"Se superaron {LIMITE_PASOS} pasos: posible ciclo infinito")
                q = instr[pc]
                pc += 1
                if q.op == "label":
                    continue
                if q.op == "goto":
                    pc = etiquetas[q.res]
                elif q.op == "if_false":
                    if not self._valor(q.arg1):
                        pc = etiquetas[q.res]
                elif q.op == "print":
                    r.salida.append(formatear_valor(self._valor(q.arg1)))
                elif q.op == "=":
                    self.memoria[q.res] = self._valor(q.arg1)
                elif q.op in ("neg", "not", "itof"):
                    self.memoria[q.res] = operar_unaria(q.op, self._valor(q.arg1))
                else:
                    self.memoria[q.res] = operar(q.op, self._valor(q.arg1), self._valor(q.arg2))
        except ErrorEjecucion as e:
            r.error = f"{e} (instrucción TAC {pc - 1:03d})"
        r.memoria = {k: v for k, v in self.memoria.items() if not k.startswith("t") or not k[1:].isdigit()}
        return r


# ======================================================================= ASM
class EmuladorASM:
    def __init__(self, codigo: CodigoObjetivo):
        self.c = codigo
        self.registros = {f"R{i}": 0 for i in range(codigo.num_registros)}
        self.memoria: dict[str, object] = dict(codigo.valores_iniciales)
        self.memoria.update(codigo.constantes)
        self.comparacion: tuple = (0, 0)
        self.parametros: list = []

    def _leer(self, operando: str):
        if operando in self.registros:
            return self.registros[operando]
        if operando.startswith("["):
            clave = operando[1:-1]
            if clave not in self.memoria:
                raise ErrorEjecucion(f"Lectura de memoria no inicializada {operando}")
            return self.memoria[clave]
        if operando in self.c.constantes:  # dirección de una cadena (str_0)
            return self.c.constantes[operando]
        return int(operando)

    def _escribir(self, operando: str, valor) -> None:
        if operando in self.registros:
            self.registros[operando] = valor
        elif operando.startswith("["):
            self.memoria[operando[1:-1]] = valor
        else:
            raise ErrorEjecucion(f"Destino no válido: {operando}")

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
                if op in ("LABEL", "PUSH", "POP") or (ops and ops[0] in ("FP", "SP")):
                    continue  # el marco de pila se modela con las ranuras [FP-k]
                if op == "MOV":
                    self._escribir(ops[0], self._leer(ops[1]))
                elif op in ("ADD", "FADD", "CONCAT"):
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
                elif op in ("CMP", "FCMP", "SCMP"):
                    self.comparacion = (self._leer(ops[0]), self._leer(ops[1]))
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
                    valor = self.parametros.pop()
                    if ops[0] == "imprimir_booleano":
                        valor = bool(valor)
                    elif ops[0] == "imprimir_real":
                        valor = float(valor)
                    r.salida.append(formatear_valor(valor))
                else:
                    raise ErrorEjecucion(f"Instrucción desconocida {op}")
        except ErrorEjecucion as e:
            r.error = f"{e} (instrucción ASM: {str(instr[pc - 1]).strip()})"
        r.memoria = {k: v for k, v in self.memoria.items() if k in self.c.valores_iniciales}
        return r
