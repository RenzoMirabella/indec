"""Calcula los indicadores oficiales del Monitor del bolsillo y arma la página.

Baja la canasta de la API del INDEC y las series de salario mínimo, jubilación
mínima y RIPTE de datos.gob.ar, aplica las correcciones documentadas en `datos/`
y escribe el sitio estático en la carpeta de salida. Si un dato no pasa las
validaciones, termina con error y no escribe nada: la página publicada queda
como estaba.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_INDEC = "https://api.indec.gob.ar/v1/valorizacion_canastas_cba_cbt"
SERIES_ABIERTAS = {
    "smvm": (
        "https://infra.datos.gob.ar/catalog/sspm/dataset/57/distribution/57.1/download/"
        "indice-salario-minimo-vital-movil-valores-mensuales-pesos-corrientes-desde-1988.csv",
        "salario_minimo_vital_movil_mensual",
    ),
    "haber": (
        "https://infra.datos.gob.ar/catalog/sspm/dataset/58/distribution/58.1/download/"
        "haber-minimo-jubilatorio-pesos-corrientes-valores-mensuales-desde-1971.csv",
        "mensual_pesos_corrientes",
    ),
    "ripte": (
        "https://infra.datos.gob.ar/catalog/sspm/dataset/158/distribution/158.1/download/"
        "remuneracion-imponible-promedio-trabajadores-estables-ripte-total-pais-pesos-serie-mensual.csv",
        "ripte",
    ),
}
INICIO = "2016-04"
USER_AGENT = "monitor-del-bolsillo"
ZONA_ARGENTINA = timezone(timedelta(hours=-3))

# Unidades de adulto equivalente de la Metodología 22 del INDEC, anexo 7.1.
ADULTOS_HOGAR_TIPO = 3.09
ADULTOS_JUBILADO = 0.83
ADULTOS_JUBILADA = 0.67
ADULTOS_PAREJA_JUBILADA = ADULTOS_JUBILADO + ADULTOS_JUBILADA

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
)


class DatosInvalidos(Exception):
    """Un dato de origen no pasó las validaciones."""


def nombre_mes(periodo: str) -> str:
    anio, mes = periodo.split("-")
    return f"{MESES[int(mes) - 1]} de {anio}"


def numero(valor: float, decimales: int = 0) -> str:
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def pesos(valor: float) -> str:
    return "$" + numero(valor)


def porcentaje(valor: float) -> str:
    return numero(valor * 100) + "%"


def _pedir(url: str, encabezados: dict[str, str] | None = None) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(encabezados or {})})
    with urllib.request.urlopen(pedido, timeout=90) as respuesta:
        return respuesta.read()


def leer_token(raiz: Path) -> str:
    token = os.environ.get("INDEC_TOKEN", "").strip()
    archivo = raiz / ".env"
    if not token and archivo.exists():
        coincidencia = re.search(
            r"^\s*INDEC_TOKEN\s*=\s*(.+?)\s*$", archivo.read_text(encoding="utf-8-sig"), re.M
        )
        token = coincidencia.group(1).strip("\"'") if coincidencia else ""
    if not token:
        raise DatosInvalidos("Falta INDEC_TOKEN: definilo como variable de entorno o en .env.")
    return token


def bajar_canastas(token: str) -> list[dict]:
    """Baja las filas de valores en pesos de la canasta, página por página."""
    filas: list[dict] = []
    consulta = {
        "tipo_de_indicador": "in.(CBA,CBT,Hogar 2)",
        "select": "periodo,codigo,tipo_de_indicador,valor",
        "order": "periodo,codigo,tipo_de_indicador",
        "limit": "1000",
    }
    while True:
        consulta["offset"] = str(len(filas))
        url = f"{API_INDEC}?{urllib.parse.urlencode(consulta, safe='(),')}"
        pagina = json.loads(_pedir(url, {"Authorization": f"Bearer {token}"}))
        filas.extend(pagina)
        if len(pagina) < 1000:
            return filas


def interpretar_canastas(filas: list[dict]) -> dict[str, dict[str, float]]:
    """Ordena las filas por mes y valida que el hogar tipo sea el esperado."""
    claves = {"CBA": "cba", "CBT": "cbt", "CBA H2": "cba_hogar", "CBT H2": "cbt_hogar"}
    meses: dict[str, dict[str, float]] = {}
    for fila in filas:
        faltan = {"periodo", "codigo", "valor"} - fila.keys()
        if faltan:
            raise DatosInvalidos(f"La API del INDEC cambió de formato: faltan {sorted(faltan)}.")
        clave = claves.get(fila["codigo"])
        if clave is None or fila["valor"] is None:
            continue
        periodo = str(fila["periodo"])
        if not re.fullmatch(r"\d{6}", periodo):
            raise DatosInvalidos(f"Período inesperado en la API del INDEC: {periodo!r}.")
        periodo = f"{periodo[:4]}-{periodo[4:]}"
        meses.setdefault(periodo, {})[clave] = float(fila["valor"])

    completos: dict[str, dict[str, float]] = {}
    for periodo in sorted(meses):
        datos = meses[periodo]
        if set(datos) != set(claves.values()):
            raise DatosInvalidos(f"Canasta incompleta en {periodo}: {sorted(datos)}.")
        if min(datos.values()) <= 0:
            raise DatosInvalidos(f"Canasta con valores no positivos en {periodo}.")
        for adulto, hogar in (("cba", "cba_hogar"), ("cbt", "cbt_hogar")):
            esperado = datos[adulto] * ADULTOS_HOGAR_TIPO
            if abs(datos[hogar] / esperado - 1) > 0.002:
                raise DatosInvalidos(f"El hogar tipo de {periodo} no equivale a 3,09 adultos.")
        completos[periodo] = datos
    return completos


def interpretar_serie(texto: str, columna: str) -> dict[str, float]:
    lector = csv.DictReader(io.StringIO(texto))
    if not lector.fieldnames or "indice_tiempo" not in lector.fieldnames or columna not in lector.fieldnames:
        raise DatosInvalidos(f"La serie cambió de formato: no encuentro {columna!r}.")
    serie: dict[str, float] = {}
    for fila in lector:
        if fila[columna] not in ("", None):
            serie[fila["indice_tiempo"][:7]] = float(fila[columna])
    return serie


def aplicar_correcciones(series: dict[str, dict[str, float]], correcciones: list[dict]) -> None:
    for fila in correcciones:
        nombre = fila["serie"]
        if nombre not in series:
            raise DatosInvalidos(f"Corrección para una serie desconocida: {nombre!r}.")
        series[nombre][fila["periodo"]] = float(fila["valor"])


def descartar_caidas_ripte(ripte: dict[str, float]) -> list[str]:
    """Saca los valores que bajan respecto del mes anterior, para revisarlos a mano.

    Desde 2016 el RIPTE no bajó nunca salvo por un error de carga: si vuelve a
    pasar, es más seguro mostrar el mes anterior y avisar que publicar una caída
    que quizás no existió.
    """
    alertas = []
    anterior = None
    for periodo in sorted(ripte):
        valor = ripte[periodo]
        if periodo >= INICIO and anterior is not None and valor < anterior:
            alertas.append(f"RIPTE de {periodo} ({valor}) es menor que el del mes anterior: se omitió.")
            del ripte[periodo]
            continue
        anterior = valor
    return alertas


def _siguiente(periodo: str) -> str:
    anio, mes = (int(parte) for parte in periodo.split("-"))
    return f"{anio + mes // 12}-{mes % 12 + 1:02d}"


def combinar(
    canastas: dict[str, dict[str, float]],
    series: dict[str, dict[str, float]],
) -> list[dict]:
    """Une las fuentes y calcula, para cada mes con canasta, cuántos ingresos hacen falta."""
    if not canastas or min(canastas) != INICIO:
        raise DatosInvalidos(f"La canasta tiene que empezar en {INICIO}.")
    filas = []
    periodo = INICIO
    ultimo = max(canastas)
    while periodo <= ultimo:
        if periodo not in canastas:
            raise DatosInvalidos(f"Falta la canasta de {periodo}.")
        canasta = canastas[periodo]
        fila: dict = {"periodo": periodo, **canasta}
        fila["cba_pareja"] = canasta["cba"] * ADULTOS_PAREJA_JUBILADA
        fila["cbt_pareja"] = canasta["cbt"] * ADULTOS_PAREJA_JUBILADA
        for nombre in ("smvm", "haber", "ripte"):
            fila[nombre] = series[nombre].get(periodo)
        if fila["smvm"] is None:
            raise DatosInvalidos(f"Falta el salario mínimo de {periodo}.")
        for ingreso, hogar in (("smvm", "hogar"), ("ripte", "hogar"), ("haber", "pareja")):
            for canasta_nombre in ("cbt", "cba"):
                monto = fila[ingreso]
                fila[f"{ingreso}_{canasta_nombre}"] = (
                    round(fila[f"{canasta_nombre}_{hogar}"] / monto, 4) if monto else None
                )
        filas.append(fila)
        periodo = _siguiente(periodo)
    return filas


@dataclass
class Fila:
    nombre: str
    detalle: str
    cobertura: float
    extra: float = 0.0
    nota: str = ""


def _ultimo_con(filas: list[dict], clave: str) -> dict:
    for fila in reversed(filas):
        if fila.get(clave):
            return fila
    raise DatosInvalidos(f"No hay ningún mes con {clave}.")


def coberturas(filas: list[dict], bonos: dict[str, float]) -> tuple[list[Fila], float]:
    """Arma las barras de ingresos: qué parte de la canasta total cubre cada uno."""
    ultima = filas[-1]
    con_ripte = _ultimo_con(filas, "ripte")
    con_haber = _ultimo_con(filas, "haber")
    mes = MESES[int(ultima["periodo"][5:]) - 1]
    mes_ripte = MESES[int(con_ripte["periodo"][5:]) - 1]
    mes_haber = MESES[int(con_haber["periodo"][5:]) - 1]
    bono = bonos.get(con_haber["periodo"], 0.0)

    def jubilacion(nombre: str, detalle: str, adultos: float, cantidad: int) -> Fila:
        canasta = con_haber["cbt"] * adultos
        sin_bono = con_haber["haber"] * cantidad / canasta
        extra = bono * cantidad / canasta
        nota = f"Sin bono: {porcentaje(sin_bono)}" if bono else ""
        return Fila(nombre, f"{detalle}, {mes_haber}", sin_bono, extra, nota)

    resultado = [
        Fila("Un salario mínimo", f"Familia de 4, {mes}", ultima["smvm"] / ultima["cbt_hogar"]),
        Fila("Dos salarios mínimos", f"Familia de 4, {mes}", 2 * ultima["smvm"] / ultima["cbt_hogar"]),
        Fila("Sueldo promedio registrado", f"RIPTE, familia de 4, {mes_ripte}", con_ripte["ripte"] / con_ripte["cbt_hogar"]),
        jubilacion("Jubilación mínima, varón solo", "De 61 a 75 años", ADULTOS_JUBILADO, 1),
        jubilacion("Jubilación mínima, mujer sola", "De 61 a 75 años", ADULTOS_JUBILADA, 1),
        jubilacion("Una jubilación mínima, pareja", "De 61 a 75 años", ADULTOS_PAREJA_JUBILADA, 1),
        jubilacion("Dos jubilaciones mínimas, pareja", "De 61 a 75 años", ADULTOS_PAREJA_JUBILADA, 2),
    ]
    return resultado, bono


def tira(titulo: str, monto: str, valor: float, clase: str, unidades: int) -> str:
    celdas = []
    orden = 0
    for indice in range(unidades):
        relleno = max(0.0, min(1.0, valor - indice))
        contenido = ""
        if relleno > 0:
            contenido += f'<i style="width:{relleno * 100:.1f}%;--n:{orden}"></i>'
            orden += 1
        if relleno == 1:
            contenido += f"<em>{indice + 1}</em>"
        celdas.append(f'<div class="celda">{contenido}</div>')
    return (
        f'<div><div class="fila-t"><b>{titulo}: {numero(valor, 2)} salarios</b><span>{monto}</span></div>'
        f'<div class="tira {clase}">{"".join(celdas)}</div></div>'
    )


def barras_html(barras: list[Fila], escala: float) -> str:
    salida = []
    for barra in barras:
        total = barra.cobertura + barra.extra
        ancho = barra.cobertura / escala * 100
        segmentos = f'<span class="seg" style="width:{ancho:.2f}%"></span>'
        if barra.extra:
            segmentos += f'<span class="seg bono" style="width:{barra.extra / escala * 100:.2f}%"></span>'
        detalle = html.escape(barra.detalle)
        if barra.nota:
            detalle += f"<br>{html.escape(barra.nota)}"
        salida.append(
            '<div class="b-fila">'
            f'<div class="b-nombre"><b>{html.escape(barra.nombre)}</b><span>{detalle}</span></div>'
            f'<div class="b-pista"><div class="b-marcas">{segmentos}<b class="b-num">{porcentaje(total)}</b></div></div>'
            "</div>"
        )
    return "".join(salida)


def tabla_html(filas: list[dict]) -> str:
    salida = []
    for fila in reversed(filas):
        haber = pesos(fila["haber"]) if fila["haber"] else "sin dato"
        ripte = pesos(fila["ripte"]) if fila["ripte"] else "sin dato"
        salida.append(
            f'<tr><td>{nombre_mes(fila["periodo"])}</td><td>{pesos(fila["cbt_hogar"])}</td>'
            f'<td>{pesos(fila["cba_hogar"])}</td><td>{pesos(fila["smvm"])}</td>'
            f'<td>{numero(fila["smvm_cbt"], 2)}</td><td>{numero(fila["smvm_cba"], 2)}</td>'
            f"<td>{haber}</td><td>{ripte}</td></tr>"
        )
    return "".join(salida)


def frase_cita(fila: dict) -> str:
    return (
        f'En {nombre_mes(fila["periodo"])}, una familia de 4 en el Gran Buenos Aires necesitó '
        f'{pesos(fila["cbt_hogar"])} para no ser pobre, el equivalente a {numero(fila["smvm_cbt"], 2)} '
        "salarios mínimos brutos. Fuente: Monitor del bolsillo, con datos del INDEC y de la Secretaría de Trabajo."
    )


def escribir_csv(destino: Path, filas: list[dict]) -> None:
    columnas = [
        "periodo", "cba_adulto", "cbt_adulto", "cba_familia_4", "cbt_familia_4",
        "salario_minimo", "jubilacion_minima", "ripte",
        "salarios_minimos_para_cbt", "salarios_minimos_para_cba",
        "ripte_para_cbt", "ripte_para_cba",
        "jubilaciones_para_cbt_pareja", "jubilaciones_para_cba_pareja",
    ]
    origen = [
        "periodo", "cba", "cbt", "cba_hogar", "cbt_hogar", "smvm", "haber", "ripte",
        "smvm_cbt", "smvm_cba", "ripte_cbt", "ripte_cba", "haber_cbt", "haber_cba",
    ]
    with destino.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(columnas)
        for fila in filas:
            escritor.writerow(["" if fila[clave] is None else fila[clave] for clave in origen])


def armar_sitio(
    plantilla: str,
    filas: list[dict],
    barras: list[Fila],
    bono: float,
    correcciones: list[dict],
    actualizado: datetime,
    fuente_bono: str = "https://www.argentina.gob.ar/anses",
) -> str:
    ultima = filas[-1]
    escala = max(1.5, max(b.cobertura + b.extra for b in barras) * 1.08)
    unidades = int(ultima["smvm_cbt"]) + 1
    series = [
        {
            "p": fila["periodo"],
            "cbt": fila["cbt_hogar"],
            "smvm_cbt": fila["smvm_cbt"], "smvm_cba": fila["smvm_cba"],
            "ripte_cbt": fila["ripte_cbt"], "ripte_cba": fila["ripte_cba"],
            "haber_cbt": fila["haber_cbt"], "haber_cba": fila["haber_cba"],
            "smvm": fila["smvm"],
        }
        for fila in filas
    ]
    datos_json = json.dumps(series, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    notas_correccion = " ".join(
        f'El RIPTE de {nombre_mes(c["periodo"])} sale del <a href="{html.escape(c["fuente"], quote=True)}">informe oficial</a>, '
        "porque la base abierta repite un valor anterior."
        for c in correcciones
        if c["serie"] == "ripte"
    )
    leyenda = '<span class="ley"><i class="seg"></i>Ingreso</span>'
    if bono:
        leyenda += f'<span class="ley"><i class="seg bono"></i>Bono de {pesos(bono)}</span>'
    reemplazos = {
        "SALARIOS_REDONDO": numero(ultima["smvm_cbt"], 1),
        "SALARIOS": numero(ultima["smvm_cbt"], 2),
        "MES": nombre_mes(ultima["periodo"]),
        "SALARIO_MINIMO": pesos(ultima["smvm"]),
        "TIRAS": tira("Canasta total", pesos(ultima["cbt_hogar"]), ultima["smvm_cbt"], "total", unidades)
        + tira("Canasta de alimentos", pesos(ultima["cba_hogar"]), ultima["smvm_cba"], "alim", unidades),
        "ETIQUETA_TIRAS": (
            f'La canasta total equivale a {numero(ultima["smvm_cbt"], 2)} salarios mínimos '
            f'y la de alimentos a {numero(ultima["smvm_cba"], 2)}.'
        ),
        "BARRAS": barras_html(barras, escala),
        "LINEA_100": f"{100 / escala:.2f}",
        "LEYENDA": leyenda,
        "NOTA_CORRECCION": notas_correccion,
        "BONO_FUENTE": html.escape(fuente_bono, quote=True),
        "TABLA": tabla_html(filas),
        "CITA": frase_cita(ultima),
        "ACTUALIZADO": f"{actualizado.day} de {MESES[actualizado.month - 1]} de {actualizado.year}",
        "DATOS_JSON": datos_json,
    }
    resultado = plantilla
    for clave, valor in reemplazos.items():
        resultado = resultado.replace("{{" + clave + "}}", valor)
    pendientes = re.findall(r"\{\{[A-Z0-9_]+\}\}", resultado)
    if pendientes:
        raise DatosInvalidos(f"La plantilla tiene marcadores sin completar: {pendientes}.")
    return resultado


def leer_csv_local(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def ejecutar(raiz: Path, salida: Path) -> list[str]:
    token = leer_token(raiz)
    canastas = interpretar_canastas(bajar_canastas(token))
    series = {
        nombre: interpretar_serie(_pedir(url).decode("utf-8-sig"), columna)
        for nombre, (url, columna) in SERIES_ABIERTAS.items()
    }
    correcciones = leer_csv_local(raiz / "datos" / "correcciones.csv")
    aplicar_correcciones(series, correcciones)
    alertas = descartar_caidas_ripte(series["ripte"])
    filas_bono = leer_csv_local(raiz / "datos" / "bonos.csv")
    bonos = {f["periodo"]: float(f["monto"]) for f in filas_bono}

    filas = combinar(canastas, series)
    barras, bono = coberturas(filas, bonos)
    if not bono:
        alertas.append(f"Falta el bono de {_ultimo_con(filas, 'haber')['periodo']} en datos/bonos.csv.")

    actualizado = datetime.now(ZONA_ARGENTINA)
    plantilla = (raiz / "sitio" / "plantilla.html").read_text(encoding="utf-8")
    fuente_bono = max(filas_bono, key=lambda f: f["periodo"])["fuente"]
    pagina = armar_sitio(plantilla, filas, barras, bono, correcciones, actualizado, fuente_bono)

    # Se arma aparte y se reemplaza al final: si algo falla, la salida anterior queda intacta.
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = Path(tempfile.mkdtemp(prefix=salida.name + ".", dir=salida.parent))
    try:
        (temporal / "datos").mkdir()
        (temporal / "index.html").write_text(pagina, encoding="utf-8")
        escribir_csv(temporal / "datos" / "indicadores.csv", filas)
        (temporal / "datos" / "indicadores.json").write_text(
            json.dumps(
                {
                    "actualizado": actualizado.date().isoformat(),
                    "fuentes": {
                        "canasta": API_INDEC,
                        **{nombre: url for nombre, (url, _) in SERIES_ABIERTAS.items()},
                    },
                    "correcciones": correcciones,
                    "bonos": bonos,
                    "meses": filas,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        if salida.exists():
            shutil.rmtree(salida)
        temporal.replace(salida)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    return alertas


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--salida", type=Path, default=Path("_site"))
    argumentos = analizador.parse_args()
    raiz = Path(__file__).resolve().parent.parent
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        alertas = ejecutar(raiz, argumentos.salida)
    except (DatosInvalidos, OSError, ValueError) as error:
        print(f"::error::{error}")
        return 1
    for alerta in alertas:
        print(f"::warning::{alerta}")
    print(f"Sitio escrito en {argumentos.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
