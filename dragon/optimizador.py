"""
FASE 5 — OPTIMIZACIÓN DEL CÓDIGO INTERMEDIO
===========================================

Optimizaciones independientes de la máquina aplicadas sobre el TAC. Se
ejecutan en ciclo hasta que ninguna produce cambios (punto fijo):

1. Plegado de constantes ........ t1 = 15 * 2          → t1 = 30
2. Propagación de constantes .... t1 = 30; t2 = t1 + 5 → t2 = 30 + 5
   (dentro de cada BLOQUE BÁSICO: se reinicia en cada etiqueta o salto,
   porque a una etiqueta se puede llegar por varios caminos)
3. Simplificación algebraica .... x + 0 → x,  x * 1 → x,  x * 0 → 0
4. Saltos con condición constante  if_false verdadero goto L → (se elimina)
                                   if_false falso goto L     → goto L
5. Código inalcanzable .......... instrucciones después de un goto y antes
                                   de la siguiente etiqueta
6. Saltos redundantes ........... goto L1 seguido inmediatamente de L1:
7. Etiquetas sin uso ............ etiquetas a las que nadie salta
8. Fusión de temporales ......... t5 = vida - 10; vida = t5 → vida = vida - 10
9. Eliminación de código muerto . asignaciones cuyo resultado nunca se lee

Las optimizaciones conservan la semántica: el módulo emulador ejecuta el TAC
antes y después de optimizar y verifica que la salida sea idéntica.
"""

from __future__ import annotations

import re
from collections import Counter

from .tac import BINARIOS, UNARIOS, Const, Cuadrupla, ProgramaTAC
from .utilidades import ErrorEjecucion, operar, operar_unaria

ES_TEMPORAL = re.compile(r"^t\d+$")
NUMERICOS = ("entero", "real")


def _es_temporal(nombre) -> bool:
    return isinstance(nombre, str) and bool(ES_TEMPORAL.match(nombre))


class Optimizador:
    def __init__(self, programa: ProgramaTAC):
        self.p = programa.copia()
        self.registro: list[tuple[str, str]] = []

    @property
    def instr(self) -> list[Cuadrupla]:
        return self.p.instrucciones

    def _anotar(self, categoria: str, detalle: str) -> None:
        self.registro.append((categoria, detalle))

    def optimizar(self) -> ProgramaTAC:
        pasos = (
            self._propagar_y_plegar,
            self._saltos_constantes,
            self._codigo_inalcanzable,
            self._saltos_redundantes,
            self._etiquetas_sin_uso,
            self._fusionar_temporales,
            self._codigo_muerto,
        )
        for _ in range(100):  # Punto fijo (con tope de seguridad)
            hubo_cambios = False
            for paso in pasos:
                if paso():
                    hubo_cambios = True
            if not hubo_cambios:
                break
        return self.p

    def resumen(self) -> Counter:
        return Counter(c for c, _ in self.registro)

    # ------------------------------------------------- 1, 2, 3: propagación
    def _const_de_tipo(self, valor, tipo: str) -> Const:
        if tipo == "real":
            valor = float(valor)
        elif tipo == "entero" and not isinstance(valor, bool):
            valor = int(valor)
        return Const(valor, tipo)

    def _propagar_y_plegar(self) -> bool:
        cambio = False
        conocidos: dict[str, object] = {}  # nombre → Const (o nombre, para copias entre temporales)

        for i, q in enumerate(self.instr):
            if q.op == "label":
                conocidos.clear()
                continue

            # ---- Propagación: reemplazar operandos con valores conocidos
            for campo in ("arg1", "arg2"):
                arg = getattr(q, campo)
                if isinstance(arg, str) and arg in conocidos:
                    nuevo = conocidos[arg]
                    antes = str(q).strip()
                    setattr(q, campo, nuevo)
                    tipo = "Propagación de constantes" if isinstance(nuevo, Const) else "Propagación de copias"
                    self._anotar(tipo, f"{antes}  →  {str(q).strip()}")
                    cambio = True

            # ---- Plegado de constantes y simplificación algebraica
            nueva = self._plegar(q) or self._simplificar(q)
            if nueva is not None:
                self.instr[i] = q = nueva
                cambio = True

            # ---- Actualizar los valores conocidos
            definido = q.define()
            if definido:
                conocidos.pop(definido, None)
                for k in [k for k, v in conocidos.items() if v == definido]:
                    del conocidos[k]
                if q.op == "=":
                    if isinstance(q.arg1, Const):
                        conocidos[definido] = q.arg1
                    elif _es_temporal(definido) and isinstance(q.arg1, str) and q.arg1 != definido:
                        conocidos[definido] = q.arg1
            if q.op in ("goto", "if_false"):
                conocidos.clear()
        return cambio

    def _plegar(self, q: Cuadrupla) -> Cuadrupla | None:
        tipo = self.p.tipos.get(q.res, "entero")
        try:
            if q.op in BINARIOS and isinstance(q.arg1, Const) and isinstance(q.arg2, Const):
                valor = operar(q.op, q.arg1.valor, q.arg2.valor)
            elif q.op in UNARIOS and isinstance(q.arg1, Const):
                valor = operar_unaria(q.op, q.arg1.valor)
            else:
                return None
        except ErrorEjecucion:
            return None  # p. ej. división por cero: se deja para tiempo de ejecución
        nueva = Cuadrupla("=", self._const_de_tipo(valor, tipo), None, q.res)
        self._anotar("Plegado de constantes", f"{str(q).strip()}  →  {str(nueva).strip()}")
        return nueva

    def _simplificar(self, q: Cuadrupla) -> Cuadrupla | None:
        if q.op not in ("+", "-", "*", "/"):
            return None
        tipo = self.p.tipos.get(q.res, "entero")
        if tipo not in NUMERICOS:
            return None
        a, b = q.arg1, q.arg2
        es = lambda x, v: isinstance(x, Const) and x.tipo in NUMERICOS and x.valor == v
        resultado = None
        if q.op == "+" and es(b, 0):
            resultado = a
        elif q.op == "+" and es(a, 0):
            resultado = b
        elif q.op == "-" and es(b, 0):
            resultado = a
        elif q.op == "*" and es(b, 1):
            resultado = a
        elif q.op == "*" and es(a, 1):
            resultado = b
        elif q.op == "*" and (es(a, 0) or es(b, 0)):
            resultado = self._const_de_tipo(0, tipo)
        elif q.op == "/" and es(b, 1):
            resultado = a
        if resultado is None:
            return None
        nueva = Cuadrupla("=", resultado, None, q.res)
        self._anotar("Simplificación algebraica", f"{str(q).strip()}  →  {str(nueva).strip()}")
        return nueva

    # ------------------------------------------------------- 4 a 7: control
    def _saltos_constantes(self) -> bool:
        cambio, resultado = False, []
        for q in self.instr:
            if q.op == "if_false" and isinstance(q.arg1, Const):
                cambio = True
                if q.arg1.valor:
                    self._anotar("Saltos constantes", f"{str(q).strip()}  →  (eliminado: nunca salta)")
                    continue
                nueva = Cuadrupla("goto", res=q.res)
                self._anotar("Saltos constantes", f"{str(q).strip()}  →  {str(nueva).strip()}")
                q = nueva
            resultado.append(q)
        self.p.instrucciones = resultado
        return cambio

    def _codigo_inalcanzable(self) -> bool:
        cambio, resultado, inalcanzable = False, [], False
        for q in self.instr:
            if q.op == "label":
                inalcanzable = False
            elif inalcanzable:
                self._anotar("Código inalcanzable", f"{str(q).strip()}  →  (eliminado)")
                cambio = True
                continue
            resultado.append(q)
            if q.op == "goto":
                inalcanzable = True
        self.p.instrucciones = resultado
        return cambio

    def _saltos_redundantes(self) -> bool:
        cambio, resultado = False, []
        for i, q in enumerate(self.instr):
            if q.op in ("goto", "if_false"):
                j = i + 1
                siguientes = set()
                while j < len(self.instr) and self.instr[j].op == "label":
                    siguientes.add(self.instr[j].res)
                    j += 1
                if q.res in siguientes:
                    self._anotar("Saltos redundantes", f"{str(q).strip()}  →  (eliminado: salta a la línea siguiente)")
                    cambio = True
                    continue
            resultado.append(q)
        self.p.instrucciones = resultado
        return cambio

    def _etiquetas_sin_uso(self) -> bool:
        destinos = {q.res for q in self.instr if q.op in ("goto", "if_false")}
        antes = len(self.instr)
        for q in self.instr:
            if q.op == "label" and q.res not in destinos:
                self._anotar("Etiquetas sin uso", f"{q.res}:  →  (eliminada)")
        self.p.instrucciones = [q for q in self.instr if not (q.op == "label" and q.res not in destinos)]
        return len(self.instr) != antes

    # -------------------------------------------------- 8 y 9: temporales
    def _contar_usos(self) -> Counter:
        usos = Counter()
        for q in self.instr:
            usos.update(q.usos())
        return usos

    def _fusionar_temporales(self) -> bool:
        usos = self._contar_usos()
        cambio, resultado, i = False, [], 0
        while i < len(self.instr):
            q = self.instr[i]
            siguiente = self.instr[i + 1] if i + 1 < len(self.instr) else None
            t = q.define()
            if (t and _es_temporal(t) and siguiente is not None and siguiente.op == "="
                    and siguiente.arg1 == t and usos[t] == 1):
                fusionada = Cuadrupla(q.op, q.arg1, q.arg2, siguiente.res)
                self._anotar("Fusión de temporales", f"{str(q).strip()}; {str(siguiente).strip()}  →  {str(fusionada).strip()}")
                resultado.append(fusionada)
                cambio = True
                i += 2
                continue
            resultado.append(q)
            i += 1
        self.p.instrucciones = resultado
        return cambio

    def _codigo_muerto(self) -> bool:
        usos = self._contar_usos()
        cambio, resultado = False, []
        for q in self.instr:
            d = q.define()
            puede_fallar = q.op in ("/", "%") and not isinstance(q.arg2, Const)
            if d and usos[d] == 0 and not puede_fallar:
                self._anotar("Código muerto", f"{str(q).strip()}  →  (eliminado: '{d}' nunca se lee)")
                cambio = True
                continue
            resultado.append(q)
        self.p.instrucciones = resultado
        return cambio


def optimizar(programa: ProgramaTAC) -> tuple[ProgramaTAC, Optimizador]:
    opt = Optimizador(programa)
    return opt.optimizar(), opt
