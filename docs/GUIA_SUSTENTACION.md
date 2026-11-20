# Guía de sustentación — Compilador Dragon

## 1. Guion de la demostración (15 minutos)

Todos los comandos se ejecutan desde la carpeta del repositorio.

| Min | Qué mostrar | Comando | Qué decir |
|---|---|---|---|
| 0–1 | El lenguaje | abrir `ejemplos/programa_correcto.drg` | "Dragon tiene tipos estáticos, palabras clave en español, ámbitos por bloque, `si/sino`, `mientras`, funciones y textos en el heap." |
| 1–3 | Fase 1 + autómatas | `python main.py ejemplos/programa_correcto.drg --fases 1 --automatas` | "El lexer produce tokens con línea y columna. Para los números e identificadores construimos el autómata: RegEx → NFA con Thompson → DFA con subconjuntos → DFA mínimo con Hopcroft. Quedan 5 estados, la matriz de la Semana 2, y el DFA verifica cada lexema." |
| 3–4 | Fase 2 | `python main.py ejemplos/programa_correcto.drg --fases 2` | "El parser descendente recursivo construye el AST respetando la precedencia." |
| 4–6 | Fase 3 | `python main.py ejemplos/programa_correcto.drg --fases 3` | "Tabla de símbolos con pila de ámbitos: las globales tienen dirección en `.data`; los parámetros de `calcular_dano` están en FP+16 y FP+24, y sus locales en FP-8. Se insertaron coerciones entero → real." |
| 6–8 | Fases 4 y 5 | `python main.py ejemplos/programa_correcto.drg --fases 4,5` | "El TAC convierte `si` y `mientras` en saltos y las llamadas en `param`/`call`/`return`. El optimizador pasa de 78 a 63 instrucciones, y el grafo de flujo muestra los bloques básicos con el ciclo como una arista hacia atrás." |
| 8–10 | Fase 6 | `python main.py ejemplos/programa_funciones.drg --fases 6` | "Cada función tiene su marco de pila: prólogo, `PUSH` de argumentos, `CALL`, resultado en `RV`, `RET`. Los registros son caller-saved." |
| 10–11 | Spill y coloreo | `python main.py ejemplos/programa_registros.drg --registros 2 --fases 6` y luego `--registros 4 --asignador coloreo` | "Con Belady se desaloja el temporal de uso más lejano. Con Chaitin-Briggs se construye el grafo de interferencia y se colorea con K colores." |
| 11–12 | Heap | `python main.py ejemplos/programa_memoria.drg --fases 7` | "Cada concatenación reserva memoria en el heap y `liberar` la devuelve. El compilador reporta la fuga que dejamos a propósito." |
| 12–13 | Verificación | `python main.py ejemplos/programa_correcto.drg --fases 7` | "Cuatro ejecuciones iguales: el intérprete del AST, el TAC, el TAC optimizado y el ensamblador. La semántica se preservó." |
| 13–14 | Errores | `python main.py ejemplos/programa_estres.drg` y `python main.py ejemplos/errores/error_funciones.drg` | "16 errores con línea, columna y `^`, sin detenerse; y los errores de funciones: argumentos, retorno, `vacio`." |
| 14 | Errores en ejecución | `python main.py ejemplos/errores/error_memoria.drg --fases 7` | "Compila, pero usa memoria liberada: dangling pointer detectado en las cuatro ejecuciones." |
| Cierre | Pruebas | `python -m unittest` | "95 pruebas automáticas; GitHub Actions las corre en Windows, Linux y macOS, y SonarCloud revisa la seguridad." |

Si el tiempo es corto: líneas 1, 4, 6, 9 y 10.

---

## 2. Mapa del código (dónde está cada cosa)

| Si preguntan por… | Archivo | Método o clase clave |
|---|---|---|
| Expresiones regulares y orden de prioridad | `dragon/lexer.py` | `PATRON_LEXICO` |
| Conteo de líneas y columnas | `dragon/lexer.py` | `Lexer.tokenizar` (`linea`, `inicio_linea`) |
| Thompson, subconjuntos, Hopcroft | `dragon/automatas.py` | `ParserRegex`, `subconjuntos`, `hopcroft` |
| Precedencia de operadores | `dragon/parser.py` | `NIVELES_BINARIOS` y `_binaria(nivel)` |
| Recuperación de errores sintácticos | `dragon/parser.py` | `_consumir` (inserción) y `_sincronizar` (modo pánico) |
| Gramática de funciones | `dragon/parser.py` | `_funcion`, llamada en `_primaria` |
| Pila de ámbitos | `dragon/semantico.py` | `TablaSimbolos.entrar_ambito`, `salir_ambito`, `buscar` |
| Firmas, argumentos y retorno | `dragon/semantico.py` | `_registrar_firma`, `_llamada`, `_retornar` |
| Reglas de tipos y coerción | `dragon/semantico.py` | `_binaria`, `_promover`, `_verificar_asignable` |
| `si`/`mientras`/llamadas a TAC | `dragon/tac.py` | `GeneradorTAC._si`, `_mientras`, `_funcion`, rama `Llamada` |
| Optimizaciones | `dragon/optimizador.py` | `_propagar_y_plegar`, `_codigo_muerto`, … |
| Bloques básicos | `dragon/flujo.py` | `construir_grafo` |
| Selección de instrucciones | `dragon/codegen.py` | `OPCODES`, `SETCC`, `_binaria` |
| Liveness, Belady y spill | `dragon/codegen.py` | `_proximo_uso`, `_muere_en`, `_asignar` |
| Marcos de pila y convención de llamada | `dragon/codegen.py` | `_segmento`, `_llamada` |
| Coloreo de grafos | `dragon/coloreo.py` | `_preparar_segmento`, `_colorear` |
| Heap (malloc/free, fugas) | `dragon/utilidades.py` | clase `Heap` |
| Ejecución del ensamblador | `dragon/emulador.py` | `EmuladorASM.ejecutar` |
| Intérprete del AST | `dragon/interprete.py` | `Interprete._evaluar`, `_llamar` |

---

## 3. Preguntas probables y respuestas

### Front-end

**¿Por qué un parser descendente recursivo y no LR?**
Porque la gramática no tiene recursión izquierda: cada regla se vuelve una función, el código es legible y los errores se controlan con precisión. Los LR/LALR son más potentes, pero se generan con herramientas como Yacc o Bison porque sus tablas no se escriben a mano. Es la misma decisión que se tomó en clase.

**¿Cómo se maneja la precedencia?**
Con niveles en la gramática. Una regla más profunda se resuelve primero, así que `*` queda más abajo en el árbol que `+`. La asociatividad izquierda sale del ciclo `while`: `10 - 4 - 3` se analiza como `(10 - 4) - 3`.

**¿El lexer usa los autómatas que construyeron?**
El lexer usa el módulo `re`, que internamente es un motor de expresiones regulares. Los autómatas se construyen aparte para los números e identificadores, y su DFA mínimo **verifica** cada lexema que produjo el lexer: ambos deben clasificarlo igual. Con eso se demuestra el pipeline RegEx → NFA → DFA → DFA mínimo sobre los tokens reales del programa.

**¿Qué hace Hopcroft exactamente?**
Parte los estados en grupos (uno por token aceptado, más los no aceptadores) y divide un grupo cada vez que dos de sus estados van a grupos distintos con el mismo símbolo. Cuando ya no se puede dividir más, cada grupo es un estado del DFA mínimo. En Dragon, D1, D3 y D4 (todos "dentro de un identificador") se juntan: de 7 estados quedan 5.

### Análisis semántico y funciones

**¿Cómo se puede llamar a una función que está declarada más abajo?**
El analizador hace una pasada previa que registra todas las firmas. Así también funciona la recursión: cuando se analiza el cuerpo de `factorial`, su firma ya existe.

**¿Qué pasa si se llama `f(1, 2)` y `f` espera un argumento?**
Error semántico: "La función 'f' espera 1 argumento(s), pero recibió 2". También se verifica el tipo de cada argumento (con coerción entero → real), el tipo del `retornar`, que una función no `vacio` tenga `retornar` y que una `vacio` no se use como valor.

**¿Dónde viven los parámetros y las variables locales?**
En el marco de pila de cada llamada: los parámetros en `FP+16`, `FP+24`… (el último argumento apilado queda más cerca) y las locales en `FP-8`, `FP-16`… Por eso cada llamada recursiva tiene su propio `n`.

### Código intermedio y optimización

**¿Cómo se traduce una llamada a TAC?**
`x = f(a, 2)` se vuelve `param a` · `param 2` · `t1 = call f, 2` · `x = t1`. La función queda entre `func f(...)` y `fin_func f`, después de `fin`.

**¿Qué es un bloque básico y para qué sirve el grafo de flujo?**
Una secuencia sin saltos que entren ni salgan por el medio. La propagación de constantes solo es segura dentro de uno, porque a una etiqueta se llega por varios caminos. El grafo de flujo muestra esos bloques y sus aristas: un `mientras` aparece como una arista que vuelve hacia atrás.

**¿Por qué el optimizador no pliega `"a" + "b"`?**
Porque concatenar reserva memoria en el heap. Si se plegara en compilación, el resultado sería una constante y `liberar` daría error en el programa optimizado pero no en el original: cambiaría el comportamiento.

**¿Por qué una llamada nunca se elimina como código muerto?**
Porque puede tener efectos: imprimir o modificar variables globales. Por la misma razón, después de un `call` el optimizador "olvida" los valores conocidos.

### Back-end

**¿Cómo funciona la convención de llamada?**
El llamador apila los argumentos (`PUSH`), hace `CALL` (que apila la dirección de retorno) y luego limpia con `ADD SP, 8·n`. La función hace `PUSH FP` / `MOV FP, SP` / `SUB SP, tamaño`, deja el resultado en `RV` y termina con `MOV SP, FP` / `POP FP` / `RET`.

**¿Qué significa caller-saved?**
Que la función llamada puede usar cualquier registro. Por eso, antes del `CALL`, el llamador guarda en su marco los temporales que todavía necesita después.

**¿Cómo se elige qué registro desalojar? (Belady)**
Se desaloja el temporal cuyo próximo uso está más lejos. Es la elección óptima cuando se conocen los usos futuros, y en un compilador sí se conocen.

**¿Cómo funciona el coloreo de Chaitin-Briggs?**
Se calcula el intervalo de vida de cada temporal. Dos temporales interfieren si uno se define mientras el otro sigue vivo, y entonces se unen con una arista. Se quitan del grafo los nodos con grado < K (siempre se podrán colorear) y se apilan. Si ninguno tiene grado < K, se apila de forma optimista el de menor costo (Briggs). Al desapilar, cada nodo toma el primer color que no usen sus vecinos; si no queda ninguno, va a la pila (spill).

**¿Por qué el coloreo hace más spill que Belady con pocos registros?**
Porque reserva un registro auxiliar para cargar los valores desalojados: con 3 registros colorea con K = 2. En `programa_registros.drg`, Belady llega a 0 spills con 5 registros y el coloreo con 6. Con funciones, el coloreo además manda a la pila desde el principio los temporales que siguen vivos después de un `CALL`; Belady también los guarda, pero lo reporta como `GUARDA`, no como spill.

**¿Por qué no aparece `MOV [a], [b]`?**
Porque x86 no permite dos operandos de memoria en la misma instrucción. Se pasa por un registro. Una prueba automática lo verifica en todo el código generado.

### Memoria y ejecución

**¿Cómo se usa el heap?**
Las cadenas literales son constantes (como `.rodata`). Cada concatenación reserva un bloque (malloc) y `liberar(s)` lo devuelve (free). Al terminar, los bloques sin liberar se reportan como fugas.

**¿Qué errores de memoria se detectan?**
Usar un texto ya liberado (*dangling pointer*), liberarlo dos veces (*double free*), liberar una constante y la recursión sin fin (*Stack Overflow*, más de 500 llamadas anidadas). Son errores de **ejecución**: el programa compila, y se detectan al correrlo.

**¿Cómo saben que el ensamblador es correcto?**
Hay cuatro ejecuciones: el intérprete del AST, el TAC original, el TAC optimizado y el ensamblador en una CPU simulada con pila real. Si las cuatro imprimen lo mismo, la traducción preservó la semántica. Las pruebas lo verifican con 2 a 8 registros y con los dos asignadores.

**¿Cuál es la diferencia entre el intérprete y el compilador?**
El intérprete (`--interpretar`) recorre el árbol cada vez que se ejecuta y no produce código. El compilador traduce una sola vez a ensamblador, que la máquina ejecuta con instrucciones simples. Es la comparación de la Semana 1.

**¿`&&` hace cortocircuito?**
No: evalúa ambos lados, como `&` en Java. Si un lado llama a una función, esa función se ejecuta siempre. Es una decisión documentada, y las cuatro ejecuciones la respetan.

---

## 4. Cambios en vivo (por si el profesor pide modificar algo)

**Agregar una palabra clave**, por ejemplo `mostrar` como sinónimo de `imprimir`. En `dragon/lexer.py`, agregar al diccionario `PALABRAS_RESERVADAS`:
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

**Escribir una función nueva en vivo:**
```c
funcion entero cuadrado(entero x) { retornar x * x; }
imprimir(cuadrado(7));
```

**Cambiar el número de registros o el asignador:** `--registros N` y `--asignador coloreo`.

**Ver el código sin optimizar:** `python main.py archivo.drg --sin-optimizar --fases 6`
