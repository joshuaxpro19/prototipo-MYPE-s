import os
import shutil
import sys
import time

if os.name == "nt":
    os.system("")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m", "gray": "\033[90m",
}
ANCHO = min(shutil.get_terminal_size((110, 30)).columns, 110)
LENTO = os.environ.get("DEMO_RAPIDO") != "1"


def p(texto="", *estilos, fin="\n"):
    print("".join(C[e] for e in estilos) + str(texto) + C["reset"], end=fin, flush=True)


def dormir(seg=0.35):
    if LENTO:
        time.sleep(seg)


def linea(char="─"):
    p(char * ANCHO, "gray")


def titulo(texto, subtitulo=""):
    print()
    p("╔" + "═" * (ANCHO - 2) + "╗", "cyan")
    p("║ " + texto.upper().ljust(ANCHO - 4) + " ║", "cyan", "bold")
    if subtitulo:
        p("║ " + subtitulo.ljust(ANCHO - 4) + " ║", "cyan", "dim")
    p("╚" + "═" * (ANCHO - 2) + "╝", "cyan")
    print()


def paso(n, total, texto, detalle=""):
    p()
    p(" PASO %d/%d  %s" % (n, total, texto), "yellow", "bold")
    if detalle:
        p(" " + detalle, "gray")
    linea()


def ok(texto):
    p("  [OK] " + texto, "green")


def info(texto):
    p("  [..] " + texto, "gray")


def alerta(texto):
    p("  [!] " + texto, "yellow")


def error(texto):
    p("  [X] " + texto, "red", "bold")


def barra(valor, maximo, ancho=28, color="green"):
    if maximo <= 0:
        maximo = 1
    n = int(round(max(0.0, valor) / maximo * ancho))
    return c("█" * n, color) + c("·" * (ancho - n), "gray")


def c(texto, color):
    return C[color] + str(texto) + C["reset"]


def tabla(cabeceras, filas, alinear=None, ancho_max=ANCHO):
    alinear = alinear or ["<"] * len(cabeceras)
    anchos = [len(h) for h in cabeceras]
    for fila in filas:
        for i, celda in enumerate(fila):
            anchos[i] = max(anchos[i], len(str(celda)))
    total = sum(anchos) + 3 * (len(anchos) - 1)
    if total > ancho_max:
        anchos[-1] = max(8, anchos[-1] - (total - ancho_max))
    p(" " + "   ".join(c(str(h).ljust(anchos[i]), "bold") for i, h in enumerate(cabeceras)), "gray")
    p(" " + "   ".join("─" * a for a in anchos), "gray")
    for fila in filas:
        celdas = []
        for i, celda in enumerate(fila):
            texto = str(celda)
            if len(texto) > anchos[i]:
                texto = texto[: anchos[i] - 1] + "…"
            celdas.append(texto.ljust(anchos[i]) if alinear[i] == "<" else texto.rjust(anchos[i]))
        p(" " + "   ".join(celdas))
        dormir(0.04)


def arbol(claves, valor, prefijo="", es_ultimo=True):
    conector = "└─ " if es_ultimo else "├─ "
    p(prefijo + conector + claves + ": " + c(str(valor), "cyan"))
    dormir(0.05)


def pausa(mensaje="  Enter para continuar…"):
    if os.environ.get("DEMO_SIN_PAUSA") == "1" or not sys.stdin.isatty():
        return
    try:
        input(c(mensaje, "gray"))
    except (EOFError, KeyboardInterrupt):
        print()
