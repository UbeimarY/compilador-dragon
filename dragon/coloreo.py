"""
ASIGNACIÓN DE REGISTROS POR COLOREO DE GRAFOS — Chaitin-Briggs (Semana 10)
=========================================================================

Alternativa GLOBAL al asignador local (Belady). Se activa con:

    python main.py programa.drg --asignador coloreo

1. INTERVALOS DE VIDA: un temporal está vivo DESPUÉS de la instrucción que
   lo define y HASTA su último uso. Si un operando muere en la instrucción
   que define el resultado, ambos pueden compartir registro.
2. GRAFO DE INTERFERENCIA: un nodo por temporal; una arista une dos
   temporales si uno se define mientras el otro está vivo (no pueden
   compartir registro). Restricción extra del código de dos direcciones:
   en `t = a op b` el resultado no puede compartir registro con `b`,
   porque `MOV R, a` lo destruiría antes de leerlo.
3. COLOREO con K colores (K = registros disponibles):
     · simplificar: se quita del grafo cualquier nodo con grado < K (siempre
       podrá colorearse) y se apila;
     · si todos tienen grado ≥ K, se apila igualmente el de menor costo como
       posible spill (optimismo de Briggs: quizás sus vecinos compartan color);
     · seleccionar: se desapila y a cada nodo se le da el primer color que no
       usen sus vecinos; si no queda ninguno, ese temporal va a la PILA (spill).
4. Un registro (el último, Rn-1) se reserva como AUXILIAR para cargar los
   valores desalojados y para los movimientos memoria → memoria.
5. Los temporales que siguen vivos después de un CALL se desalojan de
   entrada (los registros son caller-saved).

A diferencia de Belady, la ubicación de cada temporal es FIJA durante todo
el segmento: se decide antes de generar una sola instrucción.
"""

from __future__ import annotations

from .codegen import GeneradorCodigo
from .tac import Cuadrupla


class GeneradorCodigoColoreo(GeneradorCodigo):
    def __init__(self, programa, num_registros: int = 3):
        super().__init__(programa, num_registros)
        self.auxiliar = self.registros[-1]
        self.colores = self.registros[:-1]
        self.grafos: list[tuple[str, dict[str, set[str]], dict[str, str]]] = []

    # --------------------------------------------------- análisis y coloreo
    def _preparar_segmento(self, indices: range) -> None:
        instrucciones = self.p.instrucciones
        definicion, ultimo_uso = {}, {}
        llamadas = [i for i in indices if instrucciones[i].op == "call"]
        for i in indices:
            q = instrucciones[i]
            for u in q.usos():
                if self._es_temporal(u):
                    ultimo_uso[u] = i
            d = q.define()
            if self._es_temporal(d):
                definicion.setdefault(d, i)
        intervalos = {t: (d, ultimo_uso.get(t, d)) for t, d in definicion.items()}

        grafo: dict[str, set[str]] = {t: set() for t in intervalos}
        nombres = sorted(intervalos, key=lambda t: int(t[1:]))
        for a_pos, a in enumerate(nombres):
            for b in nombres[a_pos + 1:]:
                (da, ua), (db, ub) = intervalos[a], intervalos[b]
                if db <= da < ub or da <= db < ua:   # uno se define mientras el otro vive
                    grafo[a].add(b)
                    grafo[b].add(a)
        for i in indices:  # código de dos direcciones: resultado ≠ segundo operando
            q = instrucciones[i]
            if (self._es_temporal(q.res) and self._es_temporal(q.arg2) and q.arg2 != q.arg1
                    and q.res in grafo and q.arg2 in grafo):
                grafo[q.res].add(q.arg2)
                grafo[q.arg2].add(q.res)

        forzados = {t for t, (d, u) in intervalos.items() if any(d < c < u for c in llamadas)}
        coloreo, pila_simplificacion, desalojados = self._colorear(grafo, forzados)

        # Ubicación FIJA de cada temporal: un registro de color o una ranura de pila
        for t in nombres:
            if t in coloreo:
                self.ubicacion[t] = coloreo[t]
            else:
                ranura = self._nueva_ranura()
                self.ubicacion[t] = ranura
                self.spills += 1
        self.grafos.append((self._funcion_actual or "main", grafo, dict(self.ubicacion)))

        # Traza para la consola
        k = len(self.colores)
        self.eventos.append(f"Colores disponibles K = {k}: {', '.join(self.colores)} "
                            f"(registro auxiliar reservado: {self.auxiliar})")
        if not nombres:
            self.eventos.append("Sin temporales en este segmento.")
            return
        self.eventos.append("Intervalos de vida:  " + "  ".join(
            f"{t}[{intervalos[t][0]:03d}–{intervalos[t][1]:03d}]" for t in nombres))
        self.eventos.append("Grafo de interferencia:")
        for t in nombres:
            vecinos = ", ".join(sorted(grafo[t], key=lambda v: int(v[1:]))) or "—"
            self.eventos.append(f"   {t:<5} grado {len(grafo[t])}: {vecinos}")
        if forzados:
            self.eventos.append(f"Vivos a través de un CALL (van a la pila): {', '.join(sorted(forzados))}")
        self.eventos.append("Pila de simplificación (del primero al último en apilarse): "
                            + " ".join(pila_simplificacion))
        self.eventos.append("Resultado:  " + "  ".join(
            f"{t}→{self.ubicacion[t]}" for t in nombres))
        if desalojados:
            self.eventos.append(f"SPILL real (sin color disponible): {', '.join(desalojados)}")

    def _colorear(self, grafo: dict[str, set[str]], forzados: set[str]):
        k = len(self.colores)
        restantes = {t: set(v) for t, v in grafo.items() if t not in forzados}
        for t in restantes:
            restantes[t] -= forzados
        usos = {t: len(self._usos.get(t, [])) or 1 for t in grafo}
        pila: list[str] = []
        while restantes:
            faciles = [t for t in restantes if len(restantes[t]) < k]
            if faciles:
                elegido = min(faciles, key=lambda t: (len(restantes[t]), int(t[1:])))
                pila.append(elegido)
            else:  # Briggs: candidato a spill optimista, el de menor costo uso/grado
                elegido = min(restantes, key=lambda t: (usos[t] / max(1, len(restantes[t])), int(t[1:])))
                pila.append(f"{elegido}?")  # "?" = posible spill
            for vecino in restantes[elegido]:
                restantes[vecino].discard(elegido)
            del restantes[elegido]

        coloreo: dict[str, str] = {}
        desalojados: list[str] = []
        for entrada in reversed(pila):
            t = entrada.rstrip("?")
            ocupados = {coloreo[v] for v in grafo[t] if v in coloreo}
            libre = next((c for c in self.colores if c not in ocupados), None)
            if libre is None:
                desalojados.append(t)
            else:
                coloreo[t] = libre
        return coloreo, pila, desalojados

    # ------------------------------------------- generación con ubicación fija
    def _liberar_muertos(self, *args) -> None:
        pass  # la ubicación de cada temporal no cambia durante el segmento

    def _asignar(self, duenio: str, fijos: set[str]) -> str:
        if self._es_temporal(duenio) and duenio in self.ubicacion:
            return self.ubicacion[duenio]   # su registro de color, o su ranura (MOV [FP-k], RV es válido)
        return self.auxiliar

    def _registro_destino(self, q: Cuadrupla) -> tuple[str, bool]:
        lugar = self.ubicacion.get(q.res) if self._es_temporal(q.res) else None
        if lugar is not None and lugar.startswith("R"):
            # Si el primer operando ya está en ese registro, no hace falta MOV
            return lugar, self._es_temporal(q.arg1) and self.ubicacion.get(q.arg1) == lugar
        return self.auxiliar, False     # spill o variable: se calcula en el auxiliar y luego se guarda

    def _guardar_resultado(self, q: Cuadrupla, reg: str) -> None:
        if self._es_temporal(q.res):
            lugar = self.ubicacion[q.res]
            if not lugar.startswith("R"):
                self._emitir("MOV", lugar, reg, comentario=f"{q.res} vive en la pila (spill)")
            return
        super()._guardar_resultado(q, reg)

    def _copia(self, q: Cuadrupla, comentario: str) -> None:
        if self._es_temporal(q.res) and not self.ubicacion[q.res].startswith("R"):
            self._emitir("MOV", self.auxiliar, self._operando(q.arg1), comentario=comentario)
            self._emitir("MOV", self.ubicacion[q.res], self.auxiliar)
            return
        super()._copia(q, comentario)
