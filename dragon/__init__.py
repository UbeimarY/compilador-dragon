"""
Compilador Dragon
=================

Compilador educativo completo para el lenguaje Dragon (archivos .drg).

Fases del pipeline:
    1. Análisis léxico      -> dragon.lexer
    2. Análisis sintáctico  -> dragon.parser   (produce el AST de dragon.ast_nodos)
    3. Análisis semántico   -> dragon.semantico (tabla de símbolos + chequeo de tipos)
    4. Código intermedio    -> dragon.tac       (Código de Tres Direcciones en cuádruplas)
    5. Optimización         -> dragon.optimizador
    6. Código objetivo      -> dragon.codegen   (ensamblador con asignación de registros y spill)
    7. Verificación         -> dragon.emulador  (ejecuta TAC y ensamblador y compara resultados)
"""

__version__ = "1.0.0"
