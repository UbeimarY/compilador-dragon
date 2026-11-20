# Guía de sustentación — Compilador Dragon

## 1. Guion de la demostración (10–12 minutos)

| Min | Qué mostrar | Comando | Qué decir |
|---|---|---|---|
| 0–1 | El lenguaje | abrir `ejemplos/programa_correcto.drg` | "Dragon es un lenguaje con tipos estáticos, palabras clave en español, ámbitos por bloque, `si/sino` y `mientras`." |
| 1–3 | Fases 1 y 2 | `python main.py ejemplos/programa_correcto.drg --fases 1,2` | "El lexer produce tokens con línea y columna. El parser descendente recursivo construye el AST respetando la precedencia." |
| 3–5 | Fase 3 | `python main.py ejemplos/programa_correcto.drg --fases 3` | "La tabla de símbolos usa una pila de ámbitos: `critico` vive en el nivel 2 y se destruye al salir del `si`. Se insertaron 3 coerciones entero → real." |
| 5–7 | Fases 4 y 5 | `python main.py ejemplos/programa_correcto.drg --fases 4,5` | "El TAC convierte `si` y `mientras` en saltos con etiquetas. El optimizador plegó `10*2+5` a `25`, eliminó el bloque de depuración inalcanzable y fusionó temporales: de 70 a 56 instrucciones." |
| 7–9 | Fase 6 con spill | `python main.py ejemplos/programa_registros.drg --registros 2 --fases 6` | "Con 2 registros no alcanzan: el generador desaloja a la pila el temporal cuyo próximo uso está más lejos (Belady) y luego lo recarga." |
| 9–10 | Fase 7 | `python main.py ejemplos/programa_correcto.drg --fases 7` | "Ejecutamos TAC, TAC optimizado y ensamblador en máquinas virtuales: las tres salidas coinciden, así que la semántica se preservó." |
| 10–12 | Estrés | `python main.py ejemplos/programa_estres.drg` | "16 errores de los tres tipos, cada uno con su línea, su columna y una marca `^`, sin detener el programa ni mostrar tracebacks." |
| Cierre | Pruebas | `python -m unittest -v` | "52 pruebas automáticas cubren todas las fases." |

---

## 2. Mapa del código (dónde está cada cosa)

| Si preguntan por… | Archivo | Método o clase clave |
|---|---|---|
| Expresiones regulares y orden de prioridad | `dragon/lexer.py` | `PATRON_LEXICO` |
| Conteo de líneas y columnas | `dragon/lexer.py` | `Lexer.tokenizar` (variables `linea` e `inicio_linea`) |
| Precedencia de operadores | `dragon/parser.py` | `NIVELES_BINARIOS` y `_binaria(nivel)` |
| Recuperación de errores sintácticos | `dragon/parser.py` | `_consumir` (inserción de `;` y `)`) y `_sincronizar` (modo pánico) |
| Pila de ámbitos | `dragon/semantico.py` | `TablaSimbolos.entrar_ambito`, `salir_ambito`, `buscar` |
| Reglas de tipos | `dragon/semantico.py` | `AnalizadorSemantico._binaria` |
| Coerción implícita | `dragon/semantico.py` | `_promover` y `_verificar_asignable` → nodo `Conversion` |
| Traducción de `si`/`mientras` a saltos | `dragon/tac.py` | `GeneradorTAC._si`, `_mientras` |
| Cuádruplas | `dragon/tac.py` | clase `Cuadrupla` |
| Optimizaciones | `dragon/optimizador.py` | `_propagar_y_plegar`, `_codigo_muerto`, … |
| Selección de instrucciones | `dragon/codegen.py` | `OPCODES`, `SETCC`, `_binaria` |
| Liveness y spill | `dragon/codegen.py` | `_proximo_uso`, `_muere_en`, `_asignar` |
| Ejecución del ensamblador | `dragon/emulador.py` | `EmuladorASM.ejecutar` |

---

## 3. Preguntas probables y respuestas

**¿Por qué un parser descendente recursivo y no LR?**
Porque la gramática se escribió sin recursión izquierda: cada regla se vuelve una función, el código es legible y los errores se controlan con precisión. Los LR/LALR son más potentes, pero necesitan tablas que normalmente se generan con herramientas como Yacc o Bison.

**¿Cómo se maneja la precedencia?**
Con niveles en la gramática: `o_logico → y_logico → igualdad → relacional → aditiva → multiplicativa → unaria`. Una regla más profunda se resuelve primero, así que `*` queda más abajo en el árbol que `+`. La asociatividad izquierda sale del ciclo `while`: `10 - 4 - 3` se analiza como `(10 - 4) - 3`.

**¿Por qué una sola expresión regular con grupos con nombre?**
Porque el motor prueba las alternativas en orden y `lastgroup` dice cuál coincidió. El orden resuelve los conflictos: `<=` va antes que `<` y los reales antes que los enteros. Las palabras reservadas se resuelven con un diccionario después de reconocer un identificador.

**¿Qué pasa si hay dos variables `x` en ámbitos distintos?**
Cada declaración recibe un nombre único (`x`, `x_1`). Desde la fase de TAC en adelante ya no hace falta saber de ámbitos, porque cada nombre identifica una sola variable.

**¿Por qué real → entero es error y entero → real no?**
Pasar de entero a real no pierde información, así que es una coerción segura y se inserta automáticamente. Pasar de real a entero truncaría los decimales, por eso el compilador exige que el programador lo haga explícito (Dragon no tiene casts, así que se rechaza).

**¿Qué es un bloque básico y por qué importa?**
Es una secuencia de instrucciones sin saltos que entren ni salgan por el medio. La propagación de constantes solo es segura dentro de un bloque básico, porque a una etiqueta se puede llegar por varios caminos con valores distintos.

**¿Cómo se elige qué registro desalojar?**
Con el criterio de Belady: se desaloja el temporal cuyo próximo uso está más lejos en el código. Es la decisión óptima cuando se conocen los usos futuros, y en un compilador sí se conocen porque el código ya está escrito.

**¿Cuál es la diferencia con el coloreo de grafos de Chaitin-Briggs?**
El coloreo es global: construye un grafo de interferencia, con una arista entre cada par de temporales vivos al mismo tiempo, y lo colorea con K colores, uno por registro. Nuestro algoritmo es local y lineal, más simple, y para temporales de expresiones da resultados muy buenos. El coloreo queda como trabajo futuro.

**¿Por qué no aparece `MOV [a], [b]`?**
Porque x86 no permite dos operandos de memoria en una instrucción. Cuando hace falta, se pasa por un registro: `MOV R0, [b]` y luego `MOV [a], R0`. Hay una prueba automática que lo verifica.

**¿Cómo saben que el ensamblador es correcto?**
El emulador ejecuta el ensamblador generado instrucción por instrucción, con registros, memoria, pila y banderas, y compara su salida con la del TAC original. Si coinciden, la traducción preservó la semántica. Además, las pruebas lo verifican con 2, 3, 4 y 6 registros.

**¿Dónde quedan el Stack y el Heap (semana 8)?**
El Stack se usa en el marco de `main`: `PUSH FP` / `MOV FP, SP` / `SUB SP, n` reserva las ranuras de spill `[FP-8]`, `[FP-16]`… y el epílogo las libera. Los textos se guardan como un puntero de 8 bytes a la cadena. Las variables tienen dirección estática en `.data` porque no hay funciones ni recursión.

**¿Por qué `&&` no hace cortocircuito?**
Las expresiones de Dragon no tienen efectos secundarios (no hay llamadas a funciones), así que evaluar ambos lados da el mismo resultado y simplifica la generación de código.

---

## 4. Cambios en vivo (por si el profesor pide modificar algo)

**Agregar una palabra clave**, por ejemplo `mostrar` como sinónimo de `imprimir`. En `dragon/lexer.py` se añade al diccionario:
```python
"mostrar": "IMPRIMIR",
```

**Agregar un operador nuevo**, por ejemplo potencia `^`:
1. En `lexer.py`, agregar `^` dentro de los corchetes del grupo `OPERADOR` (`[<>=!+\-*/%(){};,^]`) y `"^": "POTENCIA"` al diccionario `OPERADORES`.
2. En `parser.py`, añadir `{"POTENCIA": "^"},` al final de `NIVELES_BINARIOS` (máxima precedencia).
3. En `semantico.py`, en `_binaria`, cambiar `if op in ("+", "-", "*", "/", "%"):` por `if op in ("+", "-", "*", "/", "%", "^"):`.
4. En `tac.py`, agregar `"^"` al conjunto `BINARIOS`.
5. En `utilidades.py`, agregar a `operar`: `if op == "^": return a ** b`.
6. En `codegen.py`, agregar `("^", "entero"): "POW"` a `OPCODES`.
7. En `emulador.py`, dentro de `EmuladorASM.ejecutar`, agregar:
   ```python
   elif op == "POW":
       self._escribir(ops[0], self._leer(ops[0]) ** self._leer(ops[1]))
   ```

Prueba rápida: `entero b = 2; mientras (b < 4) { imprimir(b ^ 3); b = b + 1; }` imprime `8` y `27`.

**Cambiar el número de registros:** basta con la opción `--registros N`.

**Ver el código sin optimizar:** `python main.py archivo.drg --sin-optimizar --fases 6`
