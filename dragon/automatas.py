"""
AUTÓMATAS DEL ANALIZADOR LÉXICO (Semana 2)
==========================================

Construye, paso a paso, la máquina que reconoce los tokens numéricos y los
identificadores del lenguaje, siguiendo el pipeline clásico:

    RegEx ──Thompson──► NFA ──subconjuntos──► DFA ──Hopcroft──► DFA mínimo

* Las expresiones regulares se escriben sobre CLASES de caracteres, como la
  matriz de transición de la Semana 2:  L = letra o '_',  D = dígito,
  '.' = el punto.  Operadores:  |  *  +  ?  y paréntesis.

      ID      L(L|D)*
      ENTERO  D+
      REAL    D+.D+

* Thompson: cada operador de la RegEx es un pequeño NFA con transiciones ε.
* Subconjuntos: cada estado del DFA es un CONJUNTO de estados del NFA
  (su ε-cerradura); así desaparece el no determinismo.
* Hopcroft: agrupa los estados equivalentes hasta obtener el DFA mínimo.

El DFA mínimo se usa luego para VERIFICAR los lexemas que produjo el lexer
(que usa el módulo `re`): ambos deben clasificar igual cada número e
identificador.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ALFABETO = ("letra", "digito", "punto")
SIMBOLOS = {"L": "letra", "D": "digito", ".": "punto"}
EPSILON = "ε"

EXPRESIONES = [            # (token, regex) — el orden es la prioridad
    ("ID", "L(L|D)*"),
    ("ENTERO", "D+"),
    ("REAL", "D+.D+"),
]


def clase_de(caracter: str) -> str | None:
    if caracter == "_" or caracter.isalpha():
        return "letra"
    if caracter.isdigit():
        return "digito"
    if caracter == ".":
        return "punto"
    return None


# ================================================================== NFA (Thompson)
@dataclass
class Fragmento:
    inicio: int
    fin: int


@dataclass
class NFA:
    transiciones: dict[int, dict[str, set[int]]] = field(default_factory=dict)
    total: int = 0
    inicio: int = 0
    aceptacion: dict[int, str] = field(default_factory=dict)   # estado → token

    def nuevo(self) -> int:
        self.total += 1
        self.transiciones[self.total - 1] = {}
        return self.total - 1

    def arista(self, desde: int, simbolo: str, hasta: int) -> None:
        self.transiciones[desde].setdefault(simbolo, set()).add(hasta)

    def num_aristas(self) -> int:
        return sum(len(d) for t in self.transiciones.values() for d in t.values())


class ParserRegex:
    """Descenso recursivo sobre la RegEx que, al mismo tiempo, aplica Thompson.

        union     → concat ( '|' concat )*
        concat    → postfijo+
        postfijo  → atomo ( '*' | '+' | '?' )*
        atomo     → L | D | '.' | '(' union ')'
    """

    def __init__(self, regex: str, nfa: NFA):
        self.regex, self.nfa, self.pos = regex, nfa, 0

    def _actual(self) -> str | None:
        return self.regex[self.pos] if self.pos < len(self.regex) else None

    def construir(self) -> Fragmento:
        fragmento = self._union()
        if self._actual() is not None:
            raise ValueError(f"RegEx inválida cerca de '{self._actual()}' en {self.regex}")
        return fragmento

    def _union(self) -> Fragmento:
        f = self._concat()
        while self._actual() == "|":
            self.pos += 1
            g = self._concat()
            i, fin = self.nfa.nuevo(), self.nfa.nuevo()
            for desde, hasta in ((i, f.inicio), (i, g.inicio), (f.fin, fin), (g.fin, fin)):
                self.nfa.arista(desde, EPSILON, hasta)
            f = Fragmento(i, fin)
        return f

    def _concat(self) -> Fragmento:
        f = self._postfijo()
        while self._actual() not in (None, "|", ")"):
            g = self._postfijo()
            self.nfa.arista(f.fin, EPSILON, g.inicio)
            f = Fragmento(f.inicio, g.fin)
        return f

    def _postfijo(self) -> Fragmento:
        f = self._atomo()
        while self._actual() in ("*", "+", "?"):
            op = self._actual()
            self.pos += 1
            i, fin = self.nfa.nuevo(), self.nfa.nuevo()
            self.nfa.arista(i, EPSILON, f.inicio)
            self.nfa.arista(f.fin, EPSILON, fin)
            if op in ("*", "?"):
                self.nfa.arista(i, EPSILON, fin)          # cero repeticiones
            if op in ("*", "+"):
                self.nfa.arista(f.fin, EPSILON, f.inicio)  # repetir
            f = Fragmento(i, fin)
        return f

    def _atomo(self) -> Fragmento:
        c = self._actual()
        if c == "(":
            self.pos += 1
            f = self._union()
            if self._actual() != ")":
                raise ValueError(f"Falta ')' en {self.regex}")
            self.pos += 1
            return f
        if c in SIMBOLOS:
            self.pos += 1
            i, fin = self.nfa.nuevo(), self.nfa.nuevo()
            self.nfa.arista(i, SIMBOLOS[c], fin)
            return Fragmento(i, fin)
        raise ValueError(f"Símbolo inesperado '{c}' en {self.regex}")


def construir_nfa(expresiones=EXPRESIONES) -> tuple[NFA, list[tuple[str, str, int, int]]]:
    """NFA combinado: un estado inicial con ε hacia el NFA de cada token."""
    nfa = NFA()
    nfa.inicio = nfa.nuevo()
    detalle = []
    for token, regex in expresiones:
        antes = nfa.total
        f = ParserRegex(regex, nfa).construir()
        nfa.arista(nfa.inicio, EPSILON, f.inicio)
        nfa.aceptacion[f.fin] = token
        detalle.append((token, regex, nfa.total - antes, f.fin))
    return nfa, detalle


# ============================================================ DFA (subconjuntos)
@dataclass
class DFA:
    estados: list[str]
    inicio: str
    transiciones: dict[str, dict[str, str]]
    aceptacion: dict[str, str]                  # estado → token
    composicion: dict[str, frozenset] = field(default_factory=dict)

    def reconocer(self, lexema: str) -> str | None:
        estado = self.inicio
        for c in lexema:
            clase = clase_de(c)
            estado = self.transiciones.get(estado, {}).get(clase)
            if estado is None:
                return None
        return self.aceptacion.get(estado)

    def matriz(self) -> str:
        filas = [f"{'Estado':<10}" + "".join(f"{a:<10}" for a in ALFABETO) + "Acepta", "-" * 48]
        for e in self.estados:
            marca = ("→" if e == self.inicio else " ") + ("*" if e in self.aceptacion else " ")
            celdas = "".join(f"{self.transiciones.get(e, {}).get(a, '—'):<10}" for a in ALFABETO)
            filas.append(f"{marca}{e:<8}{celdas}{self.aceptacion.get(e, '')}")
        return "\n".join(filas)

    def dot(self, titulo: str) -> str:
        lineas = [f'digraph "{titulo}" {{', "  rankdir=LR;", '  inicio [shape=point];']
        for e in self.estados:
            forma = "doublecircle" if e in self.aceptacion else "circle"
            etiqueta = f"{e}\\n{self.aceptacion[e]}" if e in self.aceptacion else e
            lineas.append(f'  "{e}" [shape={forma}, label="{etiqueta}"];')
        lineas.append(f'  inicio -> "{self.inicio}";')
        for e, t in self.transiciones.items():
            for a, d in t.items():
                lineas.append(f'  "{e}" -> "{d}" [label="{a}"];')
        lineas.append("}")
        return "\n".join(lineas)


def _cerradura(nfa: NFA, estados) -> frozenset:
    pila, resultado = list(estados), set(estados)
    while pila:
        e = pila.pop()
        for siguiente in nfa.transiciones[e].get(EPSILON, ()):
            if siguiente not in resultado:
                resultado.add(siguiente)
                pila.append(siguiente)
    return frozenset(resultado)


def _token_de(nfa: NFA, conjunto, prioridad: dict[str, int]) -> str | None:
    tokens = [nfa.aceptacion[e] for e in conjunto if e in nfa.aceptacion]
    return min(tokens, key=prioridad.get) if tokens else None


def subconjuntos(nfa: NFA) -> DFA:
    prioridad = {t: i for i, (t, _) in enumerate(EXPRESIONES)}
    inicial = _cerradura(nfa, {nfa.inicio})
    nombres = {inicial: "D0"}
    pendientes = [inicial]
    transiciones: dict[str, dict[str, str]] = {}
    while pendientes:
        actual = pendientes.pop(0)
        nombre = nombres[actual]
        transiciones[nombre] = {}
        for simbolo in ALFABETO:
            alcanzados = {d for e in actual for d in nfa.transiciones[e].get(simbolo, ())}
            if not alcanzados:
                continue
            destino = _cerradura(nfa, alcanzados)
            if destino not in nombres:
                nombres[destino] = f"D{len(nombres)}"
                pendientes.append(destino)
            transiciones[nombre][simbolo] = nombres[destino]
    aceptacion = {n: t for c, n in nombres.items() if (t := _token_de(nfa, c, prioridad))}
    return DFA(list(nombres.values()), "D0", transiciones, aceptacion,
               {n: c for c, n in nombres.items()})


# ============================================================ Hopcroft (mínimo)
def hopcroft(dfa: DFA) -> tuple[DFA, list[str]]:
    """Minimiza el DFA. Devuelve el DFA mínimo y la traza de particiones."""
    muerto = "∅"
    estados = dfa.estados + [muerto]
    delta = {e: {a: dfa.transiciones.get(e, {}).get(a, muerto) for a in ALFABETO} for e in estados}

    # Partición inicial: un grupo por token aceptado + los no aceptadores
    grupos: dict[str | None, set[str]] = {}
    for e in estados:
        grupos.setdefault(dfa.aceptacion.get(e), set()).add(e)
    particion = [frozenset(g) for g in grupos.values()]
    pendientes = list(particion)
    traza = [f"inicial: {_mostrar_particion(particion)}"]

    while pendientes:
        a = pendientes.pop()
        for simbolo in ALFABETO:
            x = {e for e in estados if delta[e][simbolo] in a}
            nueva = []
            for y in particion:
                dentro, fuera = y & x, y - x
                if dentro and fuera:
                    nueva += [frozenset(dentro), frozenset(fuera)]
                    if y in pendientes:
                        pendientes.remove(y)
                        pendientes += [frozenset(dentro), frozenset(fuera)]
                    else:
                        pendientes.append(frozenset(min(dentro, fuera, key=len)))
                    traza.append(f"'{simbolo}' divide {_conjunto(y)} en {_conjunto(dentro)} y {_conjunto(fuera)}")
                else:
                    nueva.append(y)
            particion = nueva

    # Construir el DFA mínimo (sin el estado muerto)
    particion = [g for g in particion if g != frozenset({muerto})]
    particion.sort(key=lambda g: (dfa.inicio not in g, min(int(e[1:]) for e in g if e != muerto)))
    nombre_de = {e: f"M{i}" for i, g in enumerate(particion) for e in g}
    transiciones: dict[str, dict[str, str]] = {}
    aceptacion: dict[str, str] = {}
    for g in particion:
        rep = next(iter(g))
        n = nombre_de[rep]
        transiciones[n] = {a: nombre_de[d] for a in ALFABETO if (d := delta[rep][a]) != muerto}
        if rep in dfa.aceptacion:
            aceptacion[n] = dfa.aceptacion[rep]
    traza.append(f"final: {_mostrar_particion(particion)}")
    minimo = DFA([f"M{i}" for i in range(len(particion))], nombre_de[dfa.inicio], transiciones, aceptacion,
                 {f"M{i}": g for i, g in enumerate(particion)})
    return minimo, traza


def _conjunto(estados) -> str:
    return "{" + ", ".join(sorted(estados, key=lambda e: (e == "∅", e))) + "}"


def _mostrar_particion(particion) -> str:
    return "  ".join(_conjunto(g) for g in particion)


# ==================================================================== reporte
@dataclass
class ReporteAutomatas:
    nfa: NFA
    detalle: list
    dfa: DFA
    minimo: DFA
    traza: list[str]


def construir_automatas() -> ReporteAutomatas:
    nfa, detalle = construir_nfa()
    dfa = subconjuntos(nfa)
    minimo, traza = hopcroft(dfa)
    return ReporteAutomatas(nfa, detalle, dfa, minimo, traza)


TOKEN_ESPERADO = {"NUM_ENTERO": "ENTERO", "NUM_REAL": "REAL"}


def verificar_tokens(minimo: DFA, tokens) -> tuple[int, list[str]]:
    """Pasa por el DFA mínimo cada número e identificador que reconoció el lexer."""
    revisados, diferencias = 0, []
    for t in tokens:
        if t.tipo in TOKEN_ESPERADO:
            esperado = TOKEN_ESPERADO[t.tipo]
        elif t.lexema and clase_de(t.lexema[0]) == "letra" and t.tipo not in ("CADENA",):
            esperado = "ID"  # identificadores y palabras reservadas (se separan con la tabla)
        else:
            continue
        revisados += 1
        obtenido = minimo.reconocer(t.lexema)
        if obtenido != esperado:
            diferencias.append(f"L:{t.linea} '{t.lexema}': lexer={t.tipo}, DFA={obtenido}")
    return revisados, diferencias
