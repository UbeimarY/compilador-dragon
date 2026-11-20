"""
Compilador Dragon — punto de entrada desde la carpeta del repositorio.

    python main.py ejemplos/programa_correcto.drg

La lógica de la línea de comandos está en dragon/cli.py.
"""

import sys

from dragon.cli import main

if __name__ == "__main__":
    sys.exit(main())
