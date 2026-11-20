# 🐉 Compilador Dragon

Proyecto final de **Compiladores**, Ingeniería de Software, Universidad Cooperativa de Colombia.
Docente: Mg. Gabriel Guerrero Arellano.

**Integrantes:** _(completar)_

[![Pruebas](https://github.com/UbeimarY/compilador-dragon/actions/workflows/pruebas.yml/badge.svg)](https://github.com/UbeimarY/compilador-dragon/actions/workflows/pruebas.yml)
[![Playground](https://github.com/UbeimarY/compilador-dragon/actions/workflows/playground.yml/badge.svg)](https://ubeimary.github.io/compilador-dragon/)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)

### 🌐 [Pruébelo en el navegador → ubeimary.github.io/compilador-dragon](https://ubeimary.github.io/compilador-dragon/)

El **Dragon Playground** ejecuta el compilador completo dentro del navegador (con [Pyodide](https://pyodide.org)), sin instalar nada: se escribe código Dragon, se compila con `Ctrl + Enter` y cada fase aparece en su propia pestaña. Las líneas con errores se marcan en el editor.

**Dragon** es un lenguaje imperativo pequeño, con palabras clave en español y tipos estáticos. Este repositorio contiene su **compilador completo**, que lleva un archivo fuente `.drg` por todas las fases del curso:

```
Código fuente → Tokens → AST → Análisis semántico → TAC → TAC optimizado → Ensamblador → Verificación
```

* Escrito en **Python 3.10+**, **sin ninguna librería externa**: no hay que instalar nada con `pip`.
* **55 pruebas automáticas** (`unittest`).
* Detecta y reporta errores **léxicos, sintácticos y semánticos con línea y columna exactas**, todos en una sola compilación y sin detener el programa abruptamente.
* Genera ensamblador con **asignación de registros y desbordamiento (spill) a la pila**.
* **Verifica la preservación de la semántica**: ejecuta el TAC original, el TAC optimizado y el ensamblador en máquinas virtuales y comprueba que los tres producen la misma salida.

---

## Tabla de contenido

1. [Inicio rápido](#1-inicio-rápido)
2. [El lenguaje Dragon](#2-el-lenguaje-dragon)
3. [Arquitectura del compilador](#3-arquitectura-del-compilador)
4. [Ejemplo de compilación paso a paso](#4-ejemplo-de-compilación-paso-a-paso)
5. [Manejo de errores](#5-manejo-de-errores)
6. [Casos de prueba](#6-casos-de-prueba)
7. [Cumplimiento de los criterios del proyecto final](#7-cumplimiento-de-los-criterios-del-proyecto-final)
8. [Estructura del repositorio](#8-estructura-del-repositorio)
9. [Decisiones de diseño y limitaciones](#9-decisiones-de-diseño-y-limitaciones)

---

## 1. Inicio rápido

```bash
# 1. Verificar Python (3.10 o superior)
python --version

# 2. Clonar el repositorio
git clone https://github.com/UbeimarY/compilador-dragon.git
cd compilador-dragon

# 3. Compilar el programa de ejemplo (muestra las 7 fases)
python main.py ejemplos/programa_correcto.drg

# 4. Escenario de estrés: 16 errores léxicos, sintácticos y semánticos
python main.py ejemplos/programa_estres.drg

# 5. Presión de registros: forzar spill con solo 2 registros
python main.py ejemplos/programa_registros.drg --registros 2

# 6. Ejecutar las pruebas automáticas
python -m unittest -v
```

> En macOS/Linux puede ser necesario usar `python3` en lugar de `python`.

### Otras formas de ejecutarlo

```bash
# Como módulo de Python
python -m dragon ejemplos/programa_correcto.drg

# Instalado con pip: queda disponible el comando `dragon` en cualquier carpeta
pip install git+https://github.com/UbeimarY/compilador-dragon.git
dragon mi_programa.drg
```

### Integración continua

Con cada commit, **GitHub Actions** ejecuta las 55 pruebas y compila todos los ejemplos (como script y como módulo `python -m dragon`) en **Windows, Linux y macOS con Python 3.10, 3.11, 3.12 y 3.13**: 12 combinaciones. Otro flujo publica el playground en GitHub Pages. Además, **SonarCloud** analiza la calidad y la seguridad del código en cada commit.

### Opciones de la línea de comandos

| Opción | Descripción |
|---|---|
| `--registros N` | Registros físicos de la CPU simulada (por defecto 3: R0, R1, R2; mínimo 2) |
| `--sin-optimizar` | Genera el ensamblador desde el TAC sin optimizar (para comparar) |
| `--fases 1,4,6` | Muestra solo las fases indicadas (1 a 7) |
| `--sin-color` | Desactiva los colores de la consola |
| `--salida DIR` | Carpeta de los archivos generados (por defecto `salida/`) |

> **Seguridad:** el archivo fuente debe tener extensión `.drg`, y tanto el archivo como la carpeta de salida deben estar **dentro de la carpeta actual**. Las rutas se resuelven con `os.path.realpath` y se rechaza cualquiera que intente salir de ella (protección contra *Path Traversal*, por ejemplo `../../`). Por eso los comandos se ejecutan desde la raíz del repositorio.

Cada compilación exitosa genera tres archivos en `salida/`: `programa.tac`, `programa.opt.tac` y `programa.asm`.

---

## 2. El lenguaje Dragon

```c
// Comentario de línea
/* Comentario
   de bloque */
texto heroe = "Aria";
entero vida = 120;
real multiplicador = 1.5;
booleano vivo = verdadero;

mientras (vivo && vida > 0) {
    entero dano = 25;                 // variable local del bloque
    si (vida < 50) {
        real critico = dano * multiplicador;   // entero → real implícito
        imprimir(critico);
    } sino si (vida < 100) {
        dano = dano - 5;
    } sino {
        dano = dano + 1;
    }
    vida = vida - dano;
}
imprimir(heroe + " ganó");
```

### Tipos de datos

| Tipo | Ejemplo | Tamaño en memoria | Directiva ASM |
|---|---|---|---|
| `entero` | `42`, `-7` | 4 bytes | `DD` |
| `real` | `3.14` | 8 bytes | `DQ` |
| `texto` | `"Hola\n"` | 8 bytes (puntero) | `DQ` |
| `booleano` | `verdadero`, `falso` | 1 byte | `DB` |

### Operadores (de menor a mayor precedencia)

| Nivel | Operadores | Operandos válidos | Resultado |
|---|---|---|---|
| 1 | `\|\|` | booleano | booleano |
| 2 | `&&` | booleano | booleano |
| 3 | `==` `!=` | dos números, o dos valores del mismo tipo | booleano |
| 4 | `<` `>` `<=` `>=` | números | booleano |
| 5 | `+` `-` | números (`+` también concatena texto) | entero / real / texto |
| 6 | `*` `/` `%` | números (`%` solo enteros) | entero / real |
| 7 | `-` unario, `!` | número / booleano | igual al operando |

* `entero / entero` es **división entera truncada hacia cero**, como en C y Java: `-7 / 2 = -3`.
* Si se mezclan `entero` y `real`, el entero se convierte **implícitamente** a real. La conversión inversa (`real → entero`) es un **error** porque se pierde precisión.

### Gramática (EBNF)

```ebnf
programa       = { instruccion } EOF ;
instruccion    = declaracion | asignacion | si | mientras | imprimir | bloque ;
declaracion    = TIPO ID [ "=" expresion ] ";" ;
asignacion     = ID "=" expresion ";" ;
si             = "si" "(" expresion ")" bloque [ "sino" ( si | bloque ) ] ;
mientras       = "mientras" "(" expresion ")" bloque ;
imprimir       = "imprimir" "(" expresion ")" ";" ;
bloque         = "{" { instruccion } "}" ;

expresion      = o_logico ;
o_logico       = y_logico { "||" y_logico } ;
y_logico       = igualdad { "&&" igualdad } ;
igualdad       = relacional { ( "==" | "!=" ) relacional } ;
relacional     = aditiva { ( "<" | ">" | "<=" | ">=" ) aditiva } ;
aditiva        = multiplicativa { ( "+" | "-" ) multiplicativa } ;
multiplicativa = unaria { ( "*" | "/" | "%" ) unaria } ;
unaria         = ( "-" | "!" ) unaria | primaria ;
primaria       = NUM_ENTERO | NUM_REAL | CADENA | BOOLEANO | ID | "(" expresion ")" ;
```

La gramática **no tiene recursión izquierda**, así que se implementa directamente con descenso recursivo. Además, la precedencia queda codificada en los niveles: cuanto más abajo está una regla, más fuerte "amarra" su operador.

---

## 3. Arquitectura del compilador

```
                ┌──────────────────────── FRONT-END (análisis) ────────────────────────┐
 programa.drg → │ lexer.py ──tokens──► parser.py ──AST──► semantico.py ──AST anotado─► │
                └──────────────────────────────────────────────────────────────────────┘
                                                                     │  + tabla de símbolos
                ┌──────────── MIDDLE-END ─────────────┐               ▼
                │ tac.py ──TAC──► optimizador.py ───► │ ──TAC optimizado──┐
                └─────────────────────────────────────┘                   ▼
                ┌──────────── BACK-END (síntesis) ────────────────────────────────────┐
                │ codegen.py: selección de instrucciones + registros + spill ──► .asm │
                └─────────────────────────────────────────────────────────────────────┘
                                                                     │
                emulador.py: ejecuta TAC, TAC optimizado y ASM ──► ✓ misma salida
```

| Fase | Módulo | Qué hace | Semana del curso |
|---|---|---|---|
| 1. Léxico | `dragon/lexer.py` | RegEx con grupos con nombre → tokens con tipo, valor, línea y columna | Semana 2 |
| 2. Sintáctico | `dragon/parser.py`, `dragon/ast_nodos.py` | Parser descendente recursivo (Top-Down) → AST, con recuperación en modo pánico | Semanas 3 y 4 |
| 3. Semántico | `dragon/semantico.py` | Tabla de símbolos con pila de ámbitos + chequeo de tipos con coerción | Semanas 5 y 6 |
| 4. Código intermedio | `dragon/tac.py` | AST → código de tres direcciones en cuádruplas, con etiquetas y saltos | Semana 7 |
| 5. Optimización | `dragon/optimizador.py` | 9 optimizaciones independientes de la máquina, hasta punto fijo | Semana 9 |
| 6. Código objetivo | `dragon/codegen.py` | Ensamblador estilo x86, registros con análisis de vida y spill a la pila | Semanas 8 y 10 |
| 7. Verificación | `dragon/emulador.py` | Máquinas virtuales de TAC y de ensamblador | Semanas 7 y 10 |

### Detalle de cada fase

**1. Análisis léxico.** Un único patrón con grupos con nombre `(?P<NOMBRE>...)`, ordenado de lo más específico a lo más general: comentarios antes que el operador `/`, reales antes que enteros y operadores de dos caracteres antes que los de uno. Las palabras reservadas se distinguen de los identificadores con una tabla de búsqueda, así `enteros` es un identificador y no la palabra `entero` seguida de una `s`. Los comentarios de bloque actualizan el contador de líneas.

**2. Análisis sintáctico.** Cada regla de la gramática es un método del `Parser`. Para recuperarse de errores combina dos técnicas:
* **A nivel de frase**: si falta un `;` o un `)`, se "inserta" virtualmente y se sigue analizando, sin perder la línea siguiente.
* **Modo pánico**: ante una instrucción irreconocible se descartan tokens hasta un punto seguro (`;`, `}` o el inicio de otra instrucción).

**3. Análisis semántico.**
* *Tabla de símbolos*: cada bloque `{ }` apila un ámbito nuevo. `buscar()` sube desde el ámbito actual hasta el GLOBAL. Cada símbolo recibe un **nombre único** (`x`, `x_1`, …) para resolver el ocultamiento de variables, y una **dirección de memoria** alineada a su tamaño.
* *Chequeo de tipos*: infiere el tipo de cada expresión. Cuando la mezcla de tipos es segura inserta nodos `Conversion` (entero → real) y, si no lo es, reporta el error. Usa un tipo comodín `error` para no generar errores en cascada.

**4. Código intermedio (TAC).** El árbol se "desenrolla" en instrucciones de máximo tres direcciones, con temporales `t1, t2, …`. Las estructuras de control se traducen así:

```
si (c) {A} sino {B}           mientras (c) {A}
    if_false c goto L1        L1: if_false c goto L2
    A                             A
    goto L2                       goto L1
L1: B                         L2:
L2:
```

**5. Optimización.** Repite estas transformaciones hasta que ninguna cambie nada (punto fijo):

| Optimización | Antes | Después |
|---|---|---|
| Plegado de constantes | `t1 = 15 * 2` | `t1 = 30` |
| Propagación de constantes (por bloque básico) | `t1 = 30` · `t2 = t1 + 5` | `t2 = 30 + 5` |
| Simplificación algebraica | `t3 = x * 1` | `t3 = x` |
| Saltos con condición constante | `if_false falso goto L1` | `goto L1` |
| Código inalcanzable | instrucciones tras un `goto` | (eliminadas) |
| Saltos redundantes | `goto L1` seguido de `L1:` | (eliminado) |
| Etiquetas sin uso | `L3:` sin saltos hacia ella | (eliminada) |
| Fusión de temporales | `t5 = v - 10` · `v = t5` | `v = v - 10` |
| Código muerto | asignación a algo que nunca se lee | (eliminada) |

**6. Generación de código objetivo.**
* *Selección de instrucciones según el tipo*: `ADD/SUB/IMUL/IDIV/MOD` para enteros, `FADD/FSUB/FMUL/FDIV` para reales, `CMP/FCMP/SCMP` + `SETcc` para comparaciones y `CVTSI2SD` para la conversión entero → real. Las constantes reales y de texto van a `section .data`, igual que en x86 real. Nunca se emiten dos operandos de memoria en la misma instrucción.
* *Asignación de registros*: las variables viven en `.data` y los temporales en registros `R0..Rn-1`. Un **análisis de vida** (liveness) calcula el último uso de cada temporal para liberar su registro en ese momento. Si el temporal muere en la instrucción, su registro se reutiliza como destino.
* *Spill*: si no hay registros libres, se desaloja a la pila (`MOV [FP-8], R1`) el temporal cuyo **próximo uso está más lejos**, según el criterio óptimo de Belady. Después se recarga desde la pila cuando se necesita. El prólogo reserva el marco con `SUB SP, n`.

**7. Verificación.** Hay dos máquinas virtuales: una ejecuta cuádruplas y la otra ejecuta el ensamblador generado (registros, memoria, pila, banderas de comparación y saltos). Se ejecutan el TAC original, el TAC optimizado y el ensamblador. Si las tres salidas coinciden, queda demostrado que la optimización y la generación de código **preservaron la semántica** del programa, que es el primer reto del backend.

---

## 4. Ejemplo de compilación paso a paso

Programa fuente:

```c
entero vida = 100;
entero dano = 15 * 2 + 5;
mientras (vida > 0) {
    vida = vida - dano;
    imprimir(vida);
}
```

**TAC generado (fase 4)**, 12 instrucciones:

```
000     vida = 100
001     t1 = 15 * 2
002     t2 = t1 + 5
003     dano = t2
004 L1:
005     t3 = vida > 0
006     if_false t3 goto L2
007     t4 = vida - dano
008     vida = t4
009     imprimir vida
010     goto L1
011 L2:
```

**TAC optimizado (fase 5)**, 9 instrucciones, un 25 % menos:

```
000     vida = 100
001     dano = 35                    ← 15 * 2 + 5 plegado en compilación
002 L1:
003     t3 = vida > 0
004     if_false t3 goto L2
005     vida = vida - dano           ← t4 fusionado
006     imprimir vida
007     goto L1
008 L2:
```

**Ensamblador (fase 6):**

```nasm
section .data
    vida          DD 0               ; entero 'vida' @0x1000
    dano          DD 0               ; entero 'dano' @0x1004

section .text
main:
    PUSH     FP                     ; prólogo: guarda el marco anterior
    MOV      FP, SP
    MOV      [vida], 100            ; vida = 100
    MOV      [dano], 35             ; dano = 35
L1:
    MOV      R0, [vida]             ; t3 = vida > 0
    CMP      R0, 0
    SETG     R0
    CMP      R0, 0                  ; if_false t3 goto L2
    JE       L2                     ; salta si la condición es falsa
    MOV      R0, [vida]             ; vida = vida - dano
    SUB      R0, [dano]
    MOV      [vida], R0             ; vida = resultado
    PARAM    [vida]                 ; imprimir vida
    CALL     imprimir_entero
    JMP      L1                     ; goto L1
L2:
    MOV      SP, FP                 ; epílogo: libera el marco
    POP      FP
    HLT                             ; fin del programa
```

**Verificación (fase 7):**

```
  > 65
  > 30
  > -5
  TAC original      3 líneas impresas ·     29 pasos
  TAC optimizado    3 líneas impresas ·     24 pasos
  Ensamblador       3 líneas impresas ·     50 pasos
  ✓ Las tres ejecuciones producen la misma salida: la semántica se preservó.
```

---

## 5. Manejo de errores

Ninguna fase lanza excepciones hacia el usuario. Cada error se guarda en un `ReporteErrores` con su **fase, línea y columna**, y la compilación continúa para encontrar todos los errores de una vez. Al final se muestran ordenados, con la línea de código y una marca `^` en la columna exacta:

```
[SEMÁNTICO] L:22 C:13 — No se puede aplicar '-' entre entero y texto
      22 | vida = vida - "Fuego";             // entero - texto
         |             ^
[SEMÁNTICO] L:33 C:10 — La variable 'secreto' no ha sido declarada (o no es visible en este ámbito)
      33 | imprimir(secreto);                 // fuera de su ámbito
         |          ^

Compilación detenida: 16 error(es) — léxicos: 2, sintácticos: 2, semánticos: 12.
No se genera código intermedio ni ensamblador para un programa con errores.
```

| Fase | Errores detectados |
|---|---|
| Léxico | carácter fuera del alfabeto (`@`, `#`), identificador que empieza con dígito (`2vida`), cadena sin cerrar, comentario `/*` sin cerrar |
| Sintáctico | `;` o `)` faltante, expresión incompleta, `=` faltante, `sino` sin `si`, `}` sin `{`, bloque sin cerrar |
| Semántico | variable no declarada o fuera de su ámbito, redeclaración, tipos incompatibles, real → entero, condición no booleana, `%` con reales, operadores lógicos con no booleanos, división por cero literal |
| Advertencias | variable que oculta a otra externa, variable usada sin inicializar, variable declarada y nunca usada |

Para no generar **errores en cascada**, un error sintáctico no se reporta si en esa línea ya hubo un error léxico, porque es su consecuencia. Además, una expresión con un error semántico adopta el tipo `error`, que no vuelve a reportarse.

---

## 6. Casos de prueba

| Archivo | Propósito | Resultado esperado |
|---|---|---|
| `ejemplos/programa_correcto.drg` | **Flujo correcto completo**: simulador de combate con todos los tipos, ámbitos anidados, `si`/`sino si`/`sino`, `mientras`, coerciones y código muerto | 7 fases, 70 → 56 instrucciones TAC, salida verificada |
| `ejemplos/programa_estres.drg` | **Prueba de estrés del analizador semántico**: 16 errores de los tres tipos en un solo archivo | 2 léxicos, 2 sintácticos, 12 semánticos, sin detenerse |
| `ejemplos/programa_registros.drg` | Presión sobre los registros: expresiones con muchos temporales vivos | 5 spills con 2 registros, 2 con 3 y 0 con 6; misma salida |
| `ejemplos/errores/error_lexico.drg` | Solo errores léxicos | 4 errores léxicos |
| `ejemplos/errores/error_sintactico.drg` | Solo errores sintácticos | 6 errores sintácticos |
| `ejemplos/errores/error_semantico.drg` | Solo errores semánticos | 5 errores semánticos |

### Pruebas automáticas

```bash
python -m unittest -v
```

Son 55 pruebas en `tests/`: lexer (7), parser (8), semántico (15), optimizador (9), código objetivo (6) e integración (10). Entre otras cosas verifican que nunca se emiten dos operandos de memoria en una instrucción, que solo se usan los registros disponibles y que la salida es correcta con 2, 3, 4 y 6 registros.

---

## 7. Cumplimiento de los criterios del proyecto final

| Criterio | Cómo se cumple |
|---|---|
| **1. Demostración de pipeline continuo** | `python main.py archivo.drg` muestra en consola Tokens → AST → Tabla de símbolos → TAC → TAC optimizado → Ensamblador → Ejecución, y guarda los `.tac` y `.asm` |
| **2. Manejo riguroso de errores** | Errores léxicos, sintácticos y de tipos con **línea y columna exactas**, marca `^` en el código, todos en una sola pasada y sin tracebacks: el programa nunca se detiene abruptamente |
| **3. Gestión de recursos de hardware** | Tabla de símbolos con ámbitos, nombres únicos y **direcciones de memoria**; asignación de **registros** con análisis de vida; **spill** a la pila con criterio de Belady; prólogo y epílogo del marco de pila |
| **4. Defensa de los casos de prueba** | `programa_correcto.drg` (flujo completo) y `programa_estres.drg` (estrés del analizador semántico), más casos adicionales y 55 pruebas automáticas |

---

## 8. Estructura del repositorio

```
compilador-dragon/
├── main.py                    # Punto de entrada: python main.py archivo.drg
├── pyproject.toml             # Empaquetado: pip install → comando `dragon`
├── web/index.html             # Dragon Playground (se publica en GitHub Pages)
├── .github/workflows/         # CI: pruebas en 3 sistemas × 4 versiones y despliegue del playground
├── dragon/
│   ├── cli.py                 # Interfaz de línea de comandos (muestra todas las fases)
│   ├── lexer.py               # Fase 1: análisis léxico
│   ├── ast_nodos.py           # Nodos del AST y dibujo del árbol
│   ├── parser.py              # Fase 2: análisis sintáctico (descenso recursivo)
│   ├── semantico.py           # Fase 3: tabla de símbolos y chequeo de tipos
│   ├── tac.py                 # Fase 4: código de tres direcciones (cuádruplas)
│   ├── optimizador.py         # Fase 5: optimización del TAC
│   ├── codegen.py             # Fase 6: ensamblador, registros y spill
│   ├── emulador.py            # Fase 7: máquinas virtuales de TAC y ASM
│   ├── errores.py             # Reporte centralizado de errores
│   └── utilidades.py          # Semántica de operadores, formato y colores
├── ejemplos/                  # Programas .drg de prueba
│   └── errores/               # Un ejemplo por cada tipo de error
├── tests/                     # 55 pruebas automáticas (unittest)
└── docs/
    └── GUIA_SUSTENTACION.md   # Guion de la sustentación y preguntas frecuentes
```

---

## 9. Decisiones de diseño y limitaciones

* **Asignación estática de variables.** Dragon no tiene funciones, así que no hay recursión y cada variable, incluso las de bloques internos, puede tener una dirección fija en `.data`, como las variables `static` de C. La pila se usa para los spills de temporales. Con funciones, las variables locales pasarían a vivir en el marco de cada llamada.
* **Ensamblador didáctico.** Es una ISA de dos operandos con sintaxis Intel y nombres de instrucciones de x86, simplificada a propósito: registros genéricos `R0..Rn` y `IDIV`/`MOD` de dos operandos. Se eligió así para que pueda ejecutarse en el emulador y verificarse automáticamente.
* **`&&` y `||` evalúan ambos lados.** Como las expresiones de Dragon no tienen efectos secundarios (no hay funciones), el resultado es idéntico al de la evaluación en cortocircuito.
* **La propagación de constantes es local** a cada bloque básico. Es la opción segura sin un análisis de flujo de datos global, porque a una etiqueta se puede llegar por varios caminos.
* **Trabajo futuro:** funciones con parámetros y marcos de activación, arreglos en el heap, análisis de flujo de datos global y asignación de registros por coloreo de grafos (Chaitin-Briggs).
