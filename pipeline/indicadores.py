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
API_IPC = "https://api.indec.gob.ar/v1/ipc_nacional"
API_POBREZA = "https://api.indec.gob.ar/v1/pobreza_eph"
API_TRABAJO = "https://api.indec.gob.ar/v1/mercado_trabajo_eph"
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
# El índice de precios actual del INDEC empieza en diciembre de 2016.
INICIO_IPC = "2016-12"
USER_AGENT = "monitor-del-bolsillo"
ZONA_ARGENTINA = timezone(timedelta(hours=-3))

# Precios promedio que publica el INDEC para las seis regiones desde junio de 2017.
INICIO_PRECIOS = "2017-06"
# La API trae el precio pero no la presentación (kilo, litro, docena): sale de la planilla
# oficial "Precios al consumidor de una selección de alimentos, bebidas y otros artículos"
# (https://www.indec.gob.ar/ftp/cuadros/economia/sh_ipc_precios_promedio.xls).
# Código, nombre, grupo, presentación del precio, unidad corta y unidad con el producto.
PRODUCTOS = (
    ("01.1.1.1.05", "Pan francés", "Alimentos", "el kilo", "kilos", "kilos de pan francés"),
    ("01.1.1.3.11", "Harina de trigo común", "Alimentos", "el kilo", "kilos", "kilos de harina de trigo común"),
    ("01.1.1.3.01", "Arroz blanco simple", "Alimentos", "el kilo", "kilos", "kilos de arroz blanco"),
    ("01.1.1.4.04", "Fideos secos guiseros", "Alimentos", "el paquete de 500 g", "paquetes",
     "paquetes de fideos secos de 500 g"),
    ("01.1.2.1.08", "Carne picada común", "Alimentos", "el kilo", "kilos", "kilos de carne picada común"),
    ("01.1.2.2.01", "Pollo entero", "Alimentos", "el kilo", "kilos", "kilos de pollo entero"),
    ("01.1.5.1.02", "Aceite de girasol", "Alimentos", "la botella de 1,5 litros", "botellas",
     "botellas de aceite de girasol de 1,5 litros"),
    ("01.1.4.1.01", "Leche entera en sachet", "Alimentos", "el litro", "litros", "litros de leche entera en sachet"),
    ("01.1.4.4.01", "Huevos", "Alimentos", "la docena", "docenas", "docenas de huevos"),
    ("01.1.7.1.19", "Papa", "Alimentos", "el kilo", "kilos", "kilos de papa"),
    ("01.1.8.1.01", "Azúcar", "Alimentos", "el kilo", "kilos", "kilos de azúcar"),
    ("05.6.1.1.08", "Detergente líquido", "Limpieza e higiene", "la botella de 750 cc", "botellas",
     "botellas de detergente de 750 cc"),
    ("05.6.1.1.12", "Lavandina", "Limpieza e higiene", "el litro", "litros", "litros de lavandina"),
    ("12.1.3.2.11", "Jabón de tocador", "Limpieza e higiene", "el jabón de 125 g", "jabones",
     "jabones de tocador de 125 g"),
)
# Código de la API, nombre, provincias y la región dicha dentro de una frase.
# Las provincias salen de las ciudades del cuadro 5 de la Metodología 32 del INDEC.
REGIONES = (
    ("GBA", "Gran Buenos Aires", "Ciudad de Buenos Aires y 24 partidos del conurbano", "el Gran Buenos Aires"),
    ("Pampeana", "Pampeana", "Interior de Buenos Aires, Córdoba, Entre Ríos, La Pampa y Santa Fe",
     "la región pampeana"),
    ("Noreste", "Noreste", "Chaco, Corrientes, Formosa y Misiones", "el Noreste"),
    ("Noroeste", "Noroeste", "Catamarca, Jujuy, La Rioja, Salta, Santiago del Estero y Tucumán", "el Noroeste"),
    ("Cuyo", "Cuyo", "Mendoza, San Juan y San Luis", "Cuyo"),
    ("Patagonia", "Patagonia", "Chubut, Neuquén, Río Negro, Santa Cruz y Tierra del Fuego", "la Patagonia"),
)

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


ORDINALES = ("primer", "segundo", "tercer", "cuarto")


def nombre_semestre(periodo: str) -> str:
    anio, parte = periodo.split("-S")
    return f"{ORDINALES[int(parte) - 1]} semestre de {anio}"


def nombre_trimestre(periodo: str) -> str:
    anio, parte = periodo.split("-T")
    return f"{ORDINALES[int(parte) - 1]} trimestre de {anio}"


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


def _bajar_api(url: str, consulta: dict[str, str], token: str) -> list[dict]:
    """Baja todas las filas de un servicio de la API del INDEC, página por página."""
    filas: list[dict] = []
    consulta = {**consulta, "limit": "1000"}
    while True:
        consulta["offset"] = str(len(filas))
        direccion = f"{url}?{urllib.parse.urlencode(consulta, safe='(),.')}"
        pagina = json.loads(_pedir(direccion, {"Authorization": f"Bearer {token}"}))
        filas.extend(pagina)
        if len(pagina) < 1000:
            return filas


def bajar_canastas(token: str) -> list[dict]:
    """Baja las filas de valores en pesos de la canasta."""
    consulta = {
        "tipo_de_indicador": "in.(CBA,CBT,Hogar 2)",
        "select": "periodo,codigo,tipo_de_indicador,valor",
        "order": "periodo,codigo,tipo_de_indicador",
    }
    return _bajar_api(API_INDEC, consulta, token)


def bajar_ipc(token: str) -> list[dict]:
    """Baja el nivel general del índice de precios del Gran Buenos Aires."""
    consulta = {
        "region": "eq.GBA",
        "codigo": "eq.0",
        "tipo_de_indicador": "eq.Indice",
        "select": "periodo,valor",
        "order": "periodo",
    }
    return _bajar_api(API_IPC, consulta, token)


def bajar_precios(token: str) -> list[dict]:
    """Baja los precios promedio de los productos que el INDEC publica para todas las regiones."""
    codigos = ",".join(codigo for codigo, *_ in PRODUCTOS)
    consulta = {
        "tipo_de_indicador": "eq.Precio promedio",
        "codigo": f"in.({codigos})",
        "select": "region,codigo,periodo,valor,valor_null",
        "order": "region,codigo,periodo",
    }
    return _bajar_api(API_IPC, consulta, token)


def interpretar_precios(filas: list[dict]) -> dict:
    """Ordena los precios por producto y región, y valida que estén todos los meses desde junio de 2017.

    Devuelve los meses y, para cada producto y región, una lista de precios alineada con esos meses.
    Un mes puede quedar vacío solo si el INDEC lo marca con un signo convencional (por ejemplo,
    la Patagonia en marzo de 2020), y nunca el primero ni el último.
    """
    regiones = {codigo for codigo, *_ in REGIONES}
    productos = {codigo for codigo, *_ in PRODUCTOS}
    precios: dict[tuple[str, str], dict[str, float | None]] = {}
    for fila in filas:
        if {"region", "codigo", "periodo", "valor"} - fila.keys():
            raise DatosInvalidos("Los precios promedio de la API del INDEC cambiaron de formato.")
        periodo = str(fila["periodo"])
        if not re.fullmatch(r"\d{6}", periodo):
            raise DatosInvalidos(f"Período inesperado en los precios promedio: {periodo!r}.")
        periodo = f"{periodo[:4]}-{periodo[4:]}"
        clave = (fila["codigo"], fila["region"])
        if clave[0] not in productos or clave[1] not in regiones or periodo < INICIO_PRECIOS:
            continue
        if fila["valor"] is None and fila.get("valor_null"):
            precios.setdefault(clave, {})[periodo] = None
            continue
        if fila["valor"] is None or float(fila["valor"]) <= 0:
            raise DatosInvalidos(f"Precio vacío o no positivo: {clave[0]} en {clave[1]}, {periodo}.")
        precios.setdefault(clave, {})[periodo] = float(fila["valor"])
    if not precios:
        raise DatosInvalidos("La API del INDEC no devolvió precios promedio.")
    ultimo = max(max(meses) for meses in precios.values())
    meses, periodo = [], INICIO_PRECIOS
    while periodo <= ultimo:
        meses.append(periodo)
        periodo = _siguiente(periodo)
    valores: dict[str, dict[str, list[float | None]]] = {}
    for codigo, *_ in PRODUCTOS:
        for region, *_ in REGIONES:
            serie = precios.get((codigo, region), {})
            faltan = [mes for mes in meses if mes not in serie]
            faltan += [mes for mes in (meses[0], meses[-1]) if serie.get(mes) is None]
            if faltan:
                raise DatosInvalidos(f"Falta el precio de {codigo} en {region} para {faltan[0]}.")
            valores.setdefault(codigo, {})[region] = [serie[mes] for mes in meses]
    return {"meses": meses, "valores": valores}


def revisar_saltos_de_precios(precios: dict) -> list[str]:
    """Avisa si un precio del último mes se duplicó o cayó a la mitad.

    Puede ser un cambio real, pero también que el INDEC cambió la presentación
    (por ejemplo, de botella de 1,5 litros a 900 cc), que la API no informa.
    """
    alertas = []
    nombres = {codigo: nombre for codigo, nombre, *_ in PRODUCTOS}
    for codigo, regiones in precios["valores"].items():
        for region, serie in regiones.items():
            if len(serie) > 1 and serie[-2] and not 0.5 <= serie[-1] / serie[-2] <= 2:
                alertas.append(
                    f"Revisar el precio de {nombres[codigo]} en {region}: pasó de {pesos(serie[-2])} "
                    f"a {pesos(serie[-1])}. Si cambió la presentación, hay que corregirla en PRODUCTOS."
                )
    return alertas


def interpretar_ipc(filas: list[dict]) -> dict[str, float]:
    """Ordena el índice por mes y valida que no falte ningún mes desde diciembre de 2016."""
    ipc: dict[str, float] = {}
    for fila in filas:
        if {"periodo", "valor"} - fila.keys():
            raise DatosInvalidos("El índice de precios de la API del INDEC cambió de formato.")
        periodo = str(fila["periodo"])
        if not re.fullmatch(r"\d{6}", periodo):
            raise DatosInvalidos(f"Período inesperado en el índice de precios: {periodo!r}.")
        if fila["valor"] is None or float(fila["valor"]) <= 0:
            raise DatosInvalidos(f"Índice de precios vacío o no positivo en {periodo}.")
        ipc[f"{periodo[:4]}-{periodo[4:]}"] = float(fila["valor"])
    if not ipc or min(ipc) != INICIO_IPC:
        raise DatosInvalidos(f"El índice de precios tiene que empezar en {INICIO_IPC}.")
    periodo = INICIO_IPC
    while periodo < max(ipc):
        periodo = _siguiente(periodo)
        if periodo not in ipc:
            raise DatosInvalidos(f"Falta el índice de precios de {periodo}.")
    return ipc


def _tasa(fila: dict, columna: str) -> float | None:
    valor = fila.get(columna)
    if valor is None:
        return None
    valor = float(valor)
    if not 0 <= valor <= 100:
        raise DatosInvalidos(f"Tasa fuera de rango en {columna} ({fila.get('periodo')}): {valor}.")
    return valor


def _observacion(fila: dict) -> str:
    return " ".join(str(fila.get("observaciones") or "").split())


def interpretar_pobreza(filas: list[dict]) -> list[dict]:
    """Ordena la pobreza y la indigencia de personas por semestre."""
    columnas = {"periodo", "tasa_pobreza_personas", "tasa_indigencia_personas", "observaciones"}
    semestres = []
    for fila in filas:
        if columnas - fila.keys():
            raise DatosInvalidos("La pobreza de la API del INDEC cambió de formato.")
        periodo = str(fila["periodo"])
        coincidencia = re.fullmatch(r"(\d{4})([12])S", periodo)
        if not coincidencia:
            raise DatosInvalidos(f"Semestre inesperado en la pobreza: {periodo!r}.")
        pobreza = _tasa(fila, "tasa_pobreza_personas")
        indigencia = _tasa(fila, "tasa_indigencia_personas")
        if pobreza is None or indigencia is None or indigencia > pobreza:
            raise DatosInvalidos(f"Pobreza o indigencia inválidas en {periodo}.")
        observacion = _observacion(fila)
        semestres.append({
            "periodo": f"{coincidencia[1]}-S{coincidencia[2]}",
            "pobreza": pobreza,
            "indigencia": indigencia,
            "provisorio": "provisorio" in observacion.lower(),
            "observacion": observacion,
        })
    semestres.sort(key=lambda s: s["periodo"])
    if not semestres:
        raise DatosInvalidos("La API del INDEC no devolvió datos de pobreza.")
    if len({s["periodo"] for s in semestres}) != len(semestres):
        raise DatosInvalidos("La pobreza trae semestres repetidos.")
    return semestres


def interpretar_trabajo(filas: list[dict]) -> list[dict]:
    """Ordena las tasas de la EPH por trimestre y calcula qué parte del empleo es informal."""
    columnas = {
        "periodo", "tasa_de_empleo", "tasa_de_empleo_formal", "tasa_de_empleo_informal",
        "tasa_de_desocupacion", "observaciones",
    }
    trimestres = []
    for fila in filas:
        if columnas - fila.keys():
            raise DatosInvalidos("El mercado de trabajo de la API del INDEC cambió de formato.")
        periodo = str(fila["periodo"])
        coincidencia = re.fullmatch(r"(\d{4})([1-4])T", periodo)
        if not coincidencia:
            raise DatosInvalidos(f"Trimestre inesperado en el mercado de trabajo: {periodo!r}.")
        empleo = _tasa(fila, "tasa_de_empleo")
        formal = _tasa(fila, "tasa_de_empleo_formal")
        informal = _tasa(fila, "tasa_de_empleo_informal")
        informalidad = None
        if empleo and formal is not None and informal is not None:
            # Las dos tasas son sobre la población total y tienen que sumar la de empleo.
            if abs(formal + informal - empleo) > 0.5:
                raise DatosInvalidos(f"El empleo formal e informal no suman el total en {periodo}.")
            informalidad = round(informal / empleo * 100, 1)
        observacion = _observacion(fila)
        trimestres.append({
            "periodo": f"{coincidencia[1]}-T{coincidencia[2]}",
            "desocupacion": _tasa(fila, "tasa_de_desocupacion"),
            "informalidad": informalidad,
            "provisorio": "provisorio" in observacion.lower(),
            "observacion": observacion,
        })
    trimestres.sort(key=lambda t: t["periodo"])
    if not any(t["informalidad"] is not None for t in trimestres):
        raise DatosInvalidos("El mercado de trabajo no trae ningún trimestre con informalidad.")
    return trimestres


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
        fila["ipc"] = series.get("ipc", {}).get(periodo)
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
    monto: float = 0.0
    canasta: float = 0.0


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
        return Fila(
            nombre, f"{detalle}, {mes_haber}", sin_bono, extra, nota,
            monto=con_haber["haber"] * cantidad, canasta=canasta,
        )

    resultado = [
        Fila(
            "Un salario mínimo", f"Familia de 4, {mes}", ultima["smvm"] / ultima["cbt_hogar"],
            monto=ultima["smvm"], canasta=ultima["cbt_hogar"],
        ),
        Fila(
            "Dos salarios mínimos", f"Familia de 4, {mes}", 2 * ultima["smvm"] / ultima["cbt_hogar"],
            monto=2 * ultima["smvm"], canasta=ultima["cbt_hogar"],
        ),
        Fila(
            "Sueldo promedio registrado", f"RIPTE, familia de 4, {mes_ripte}",
            con_ripte["ripte"] / con_ripte["cbt_hogar"],
            monto=con_ripte["ripte"], canasta=con_ripte["cbt_hogar"],
        ),
        jubilacion("Jubilación mínima, varón solo", "De 61 a 75 años", ADULTOS_JUBILADO, 1),
        jubilacion("Jubilación mínima, mujer sola", "De 61 a 75 años", ADULTOS_JUBILADA, 1),
        jubilacion("Una jubilación mínima, pareja", "De 61 a 75 años", ADULTOS_PAREJA_JUBILADA, 1),
        jubilacion("Dos jubilaciones mínimas, pareja", "De 61 a 75 años", ADULTOS_PAREJA_JUBILADA, 2),
    ]
    return resultado, bono


PODER_INGRESOS = (
    ("smvm", "Salario mínimo", "Bruto"),
    ("haber", "Jubilación mínima", "Sin bono"),
    ("ripte", "Sueldo promedio registrado", "RIPTE, bruto"),
)


def _ultimo_real(filas: list[dict], clave: str) -> dict:
    for fila in reversed(filas):
        if fila.get(clave) and fila.get("ipc"):
            return fila
    raise DatosInvalidos(f"No hay ningún mes con {clave} y con índice de precios.")


def _real(fila: dict, clave: str) -> float:
    return fila[clave] / fila["ipc"]


def bases_posibles(filas: list[dict]) -> list[str]:
    """Meses contra los que se puede comparar: tienen que tener los tres ingresos y el índice."""
    hasta = min(_ultimo_real(filas, clave)["periodo"] for clave, _, _ in PODER_INGRESOS)
    return [
        f["periodo"] for f in filas
        if INICIO_IPC <= f["periodo"] <= hasta and f.get("ipc") and all(f.get(c) for c, _, _ in PODER_INGRESOS)
    ]


def poder_de_compra(filas: list[dict], base: str) -> list[Fila]:
    """Qué parte de lo que compraba cada ingreso en el mes base compra en su último mes."""
    origen = next((f for f in filas if f["periodo"] == base), None)
    if origen is None or base not in bases_posibles(filas):
        raise DatosInvalidos(f"No se puede comparar el poder de compra contra {base}.")
    barras = []
    for clave, nombre, detalle in PODER_INGRESOS:
        ultimo = _ultimo_real(filas, clave)
        valor = _real(ultimo, clave) / _real(origen, clave)
        # Lo que valía el ingreso en el mes base, llevado a precios de su último mes.
        antes = origen[clave] * ultimo["ipc"] / origen["ipc"]
        mes_base = nombre_mes(base)
        nota = f"{mes_base[0].upper()}{mes_base[1:]}, en pesos de hoy: {pesos(antes)}"
        barras.append(Fila(nombre, f"{detalle}, {nombre_mes(ultimo['periodo'])}", valor, nota=nota, monto=ultimo[clave]))
    return barras


def variacion(factor: float, plural: bool = False) -> str:
    n = "n" if plural else ""
    if factor >= 2:
        verbo = "se multiplicaron" if plural else "se multiplicó"
        return f"{verbo} por {numero(factor, 0 if factor >= 10 else 1)}"
    if factor >= 1:
        return f"subiero{n} {porcentaje(factor - 1)}" if plural else f"subió {porcentaje(factor - 1)}"
    return f"bajaro{n} {porcentaje(1 - factor)}" if plural else f"bajó {porcentaje(1 - factor)}"


def frase_poder(filas: list[dict], base: str) -> str:
    """Explica el cambio en salarios mínimos necesarios: precios de la canasta frente al poder de compra.

    Los salarios necesarios son canasta / salario, que es lo mismo que
    (canasta / precios) / (salario / precios). Si la canasta sube como el resto
    de los precios, todo el cambio viene de lo que compra el salario.
    """
    origen = next(f for f in filas if f["periodo"] == base)
    ultimo = _ultimo_real(filas, "smvm")
    canasta = ultimo["cbt"] / origen["cbt"]
    precios = ultimo["ipc"] / origen["ipc"]
    salario = _real(ultimo, "smvm") / _real(origen, "smvm")
    texto = (
        f"Entre {nombre_mes(base)} y {nombre_mes(ultimo['periodo'])}, los salarios mínimos necesarios "
        f"para que una familia de 4 no sea pobre pasaron de {numero(origen['smvm_cbt'], 2)} a "
        f"{numero(ultimo['smvm_cbt'], 2)}. La canasta total {variacion(canasta)}"
    )
    relacion = canasta / precios
    if abs(relacion - 1) < 0.05:
        return (
            texto + f", casi lo mismo que los precios en general, que {variacion(precios, plural=True)}. "
            "Por eso el cambio viene de lo que compra el salario mínimo, "
            f"que hoy es el {porcentaje(salario)} de lo que compraba entonces."
        )
    return (
        texto + f" y los precios en general {variacion(precios, plural=True)}: "
        f"la canasta subió {'más' if relacion > 1 else 'menos'} que el resto. "
        f"Y el salario mínimo compra hoy el {porcentaje(salario)} de lo que compraba entonces."
    )


def nota_bono_poder(filas: list[dict], bonos: dict[str, float]) -> str:
    ultimo = _ultimo_real(filas, "haber")
    bono = bonos.get(ultimo["periodo"], 0.0)
    if not bono:
        return "La jubilación se compara sin bono, porque todavía no está cargado el de cada mes."
    return (
        f"La jubilación se compara sin bono, porque todavía no está cargado el de cada mes. "
        f"En {nombre_mes(ultimo['periodo'])}, el bono de {pesos(bono)} sumaba un "
        f"{porcentaje(bono / ultimo['haber'])} a la mínima."
    )


def tabla_poder_html(filas: list[dict]) -> str:
    """Cada ingreso en pesos del último mes con índice de precios."""
    ultimo = _ultimo_real(filas, "smvm")
    salida = []
    for fila in reversed(filas):
        if fila["periodo"] < INICIO_IPC or not fila.get("ipc"):
            continue
        celdas = [
            pesos(fila[clave] * ultimo["ipc"] / fila["ipc"]) if fila.get(clave) else "sin dato"
            for clave, _, _ in PODER_INGRESOS
        ]
        salida.append(
            f'<tr><td>{nombre_mes(fila["periodo"])}</td><td>{numero(fila["ipc"], 1)}</td>'
            + "".join(f"<td>{c}</td>" for c in celdas)
            + "</tr>"
        )
    return "".join(salida)


def frase_pobreza(semestres: list[dict]) -> str:
    ultimo = semestres[-1]
    provisorio = ", un dato provisorio" if ultimo["provisorio"] else ""
    return (
        f"En el {nombre_semestre(ultimo['periodo'])}{provisorio}, el {numero(ultimo['pobreza'], 1)}% de las personas "
        f"vivía en hogares pobres y el {numero(ultimo['indigencia'], 1)}%, en hogares indigentes."
    )


def tabla_pobreza_html(semestres: list[dict]) -> str:
    salida = []
    for semestre in reversed(semestres):
        nota = html.escape(semestre["observacion"]) if semestre["observacion"] else ""
        salida.append(
            f'<tr><td>{nombre_semestre(semestre["periodo"])}</td><td>{numero(semestre["pobreza"], 1)}%</td>'
            f'<td>{numero(semestre["indigencia"], 1)}%</td><td>{nota}</td></tr>'
        )
    return "".join(salida)


def notas_pobreza(semestres: list[dict]) -> str:
    """Las aclaraciones del INDEC que no son la marca de provisorio, que ya va en la frase."""
    return " ".join(
        html.escape(s["observacion"].rstrip(".") + ".")
        for s in semestres
        if s["observacion"] and not s["provisorio"]
    )


def ultimo_trabajo(trimestres: list[dict]) -> dict:
    return next(t for t in reversed(trimestres) if t["informalidad"] is not None)


def frase_trabajo(trimestres: list[dict]) -> str:
    ultimo = ultimo_trabajo(trimestres)
    provisorio = ", un dato provisorio" if ultimo["provisorio"] else ""
    texto = (
        f"En el {nombre_trimestre(ultimo['periodo'])}{provisorio}, {numero(ultimo['informalidad'])} de cada 100 "
        "personas ocupadas tenían un empleo informal."
    )
    if ultimo["desocupacion"] is not None:
        texto += f" La desocupación era del {numero(ultimo['desocupacion'], 1)}%."
    return texto


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
        # El monto va dentro de la barra; si no entra, el script de la página lo pasa al lado del porcentaje.
        adentro = f"<i>{pesos(barra.monto)}</i>" if barra.monto else ""
        afuera = f'<span class="b-afuera"> · {pesos(barra.monto)}</span>' if barra.monto else ""
        segmentos = f'<span class="seg" style="width:{ancho:.2f}%">{adentro}</span>'
        if barra.extra:
            segmentos += f'<span class="seg bono" style="width:{barra.extra / escala * 100:.2f}%"></span>'
        detalle = html.escape(barra.detalle)
        extras = [f"Canasta: {pesos(barra.canasta)}"] if barra.canasta else []
        if barra.nota:
            extras.append(barra.nota)
        if extras:
            detalle += "".join(f"<br>{html.escape(texto)}" for texto in extras)
        salida.append(
            '<div class="b-fila">'
            f'<div class="b-nombre"><b>{html.escape(barra.nombre)}</b><span>{detalle}</span></div>'
            f'<div class="b-pista"><div class="b-marcas">{segmentos}<b class="b-num">{porcentaje(total)}{afuera}</b></div></div>'
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


def _presentacion(texto: str) -> str:
    """Saca el artículo: "el kilo" queda "kilo"."""
    return texto.split(" ", 1)[1]


def tabla_precios_html(precios: dict) -> str:
    """Precios del último mes: un producto por fila y una región por columna."""
    salida = []
    for codigo, nombre, _, presentacion, *_ in PRODUCTOS:
        celdas = "".join(f"<td>{pesos(precios['valores'][codigo][region][-1])}</td>" for region, *_ in REGIONES)
        salida.append(
            f"<tr><td>{html.escape(nombre)}</td><td>{html.escape(_presentacion(presentacion))}</td>{celdas}</tr>"
        )
    return "".join(salida)


def precios_json(precios: dict) -> str:
    """Datos de la sección de precios para el script de la página."""
    datos = {
        "meses": precios["meses"],
        "regiones": [
            {"id": codigo, "nombre": nombre, "provincias": provincias, "en": en}
            for codigo, nombre, provincias, en in REGIONES
        ],
        "productos": [
            {"id": codigo, "nombre": nombre, "grupo": grupo, "precio": presentacion, "corta": corta, "larga": larga}
            for codigo, nombre, grupo, presentacion, corta, larga in PRODUCTOS
        ],
        "valores": {
            codigo: {
                region: [None if valor is None else round(valor, 2) for valor in serie]
                for region, serie in regiones.items()
            }
            for codigo, regiones in precios["valores"].items()
        },
    }
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


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
        "ipc_gba",
    ]
    origen = [
        "periodo", "cba", "cbt", "cba_hogar", "cbt_hogar", "smvm", "haber", "ripte",
        "smvm_cbt", "smvm_cba", "ripte_cbt", "ripte_cba", "haber_cbt", "haber_cba",
        "ipc",
    ]
    _escribir_tabla(destino, columnas, ([fila.get(clave) for clave in origen] for fila in filas))


def _escribir_tabla(destino: Path, columnas: list[str], filas) -> None:
    with destino.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(columnas)
        for fila in filas:
            escritor.writerow(["" if valor is None else valor for valor in fila])


def escribir_csv_precios(destino: Path, precios: dict) -> None:
    filas = (
        [mes, region, codigo, nombre, _presentacion(presentacion), precios["valores"][codigo][region][indice]]
        for codigo, nombre, _, presentacion, *_ in PRODUCTOS
        for region, *_ in REGIONES
        for indice, mes in enumerate(precios["meses"])
    )
    _escribir_tabla(destino, ["periodo", "region", "codigo", "producto", "presentacion", "precio_promedio"], filas)


def escribir_csv_sociales(carpeta: Path, semestres: list[dict], trimestres: list[dict]) -> None:
    _escribir_tabla(
        carpeta / "pobreza.csv",
        ["semestre", "pobreza_personas", "indigencia_personas", "observaciones"],
        ([s["periodo"], s["pobreza"], s["indigencia"], s["observacion"]] for s in semestres),
    )
    _escribir_tabla(
        carpeta / "trabajo.csv",
        ["trimestre", "desocupacion", "ocupados_informales_cada_100", "observaciones"],
        ([t["periodo"], t["desocupacion"], t["informalidad"], t["observacion"]] for t in trimestres),
    )


def armar_sitio(
    plantilla: str,
    filas: list[dict],
    barras: list[Fila],
    bono: float,
    correcciones: list[dict],
    actualizado: datetime,
    semestres: list[dict],
    trimestres: list[dict],
    bonos: dict[str, float] | None = None,
    fuente_bono: str = "https://www.argentina.gob.ar/anses",
    precios: dict | None = None,
) -> str:
    ultima = filas[-1]
    escala = max(1.5, max(b.cobertura + b.extra for b in barras) * 1.08)
    poder = poder_de_compra(filas, INICIO_IPC)
    escala_poder = max(1.5, max(b.cobertura for b in poder) * 1.08)
    trabajo = ultimo_trabajo(trimestres)
    sociales = {
        "bases": bases_posibles(filas),
        "pobreza": [
            {"p": s["periodo"], "pobreza": s["pobreza"], "indigencia": s["indigencia"], "provisorio": s["provisorio"]}
            for s in semestres
        ],
    }
    sociales_json = json.dumps(sociales, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    unidades = int(ultima["smvm_cbt"]) + 1
    series = [
        {
            "p": fila["periodo"],
            "cbt": fila["cbt_hogar"],
            "smvm_cbt": fila["smvm_cbt"], "smvm_cba": fila["smvm_cba"],
            "ripte_cbt": fila["ripte_cbt"], "ripte_cba": fila["ripte_cba"],
            "haber_cbt": fila["haber_cbt"], "haber_cba": fila["haber_cba"],
            "smvm": fila["smvm"], "haber": fila["haber"], "ripte": fila["ripte"],
            "cbt_ad": fila["cbt"], "ipc": fila["ipc"],
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
        "PODER_BARRAS": barras_html(poder, escala_poder),
        "PODER_LINEA_100": f"{100 / escala_poder:.2f}",
        "PODER_FRASE": html.escape(frase_poder(filas, INICIO_IPC)),
        "PODER_NOTA": html.escape(nota_bono_poder(filas, bonos or {})),
        "PODER_TABLA": tabla_poder_html(filas),
        "PODER_MES_PESOS": nombre_mes(_ultimo_real(filas, "smvm")["periodo"]),
        "POBREZA_FRASE": html.escape(frase_pobreza(semestres)),
        "POBREZA_TABLA": tabla_pobreza_html(semestres),
        "POBREZA_NOTAS": notas_pobreza(semestres),
        "TRABAJO_FRASE": html.escape(frase_trabajo(trimestres)),
        "TRABAJO_ANCHO": f"{trabajo['informalidad']:.1f}",
        "DATOS_SOCIALES": sociales_json,
        "DATOS_PRECIOS": precios_json(precios) if precios else "null",
        "PRECIOS_TABLA": tabla_precios_html(precios) if precios else "",
        "PRECIOS_MES": nombre_mes(precios["meses"][-1]) if precios else "",
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
    series["ipc"] = interpretar_ipc(bajar_ipc(token))
    precios = interpretar_precios(bajar_precios(token))
    alertas += revisar_saltos_de_precios(precios)
    semestres = interpretar_pobreza(_bajar_api(API_POBREZA, {"order": "periodo"}, token))
    trimestres = interpretar_trabajo(_bajar_api(API_TRABAJO, {"order": "periodo"}, token))
    filas_bono = leer_csv_local(raiz / "datos" / "bonos.csv")
    bonos = {f["periodo"]: float(f["monto"]) for f in filas_bono}

    filas = combinar(canastas, series)
    barras, bono = coberturas(filas, bonos)
    if not bono:
        alertas.append(f"Falta el bono de {_ultimo_con(filas, 'haber')['periodo']} en datos/bonos.csv.")

    actualizado = datetime.now(ZONA_ARGENTINA)
    plantilla = (raiz / "sitio" / "plantilla.html").read_text(encoding="utf-8")
    fuente_bono = max(filas_bono, key=lambda f: f["periodo"])["fuente"]
    pagina = armar_sitio(
        plantilla, filas, barras, bono, correcciones, actualizado, semestres, trimestres, bonos, fuente_bono,
        precios,
    )

    # Se arma aparte y se reemplaza al final: si algo falla, la salida anterior queda intacta.
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = Path(tempfile.mkdtemp(prefix=salida.name + ".", dir=salida.parent))
    try:
        (temporal / "datos").mkdir()
        (temporal / "index.html").write_text(pagina, encoding="utf-8")
        escribir_csv(temporal / "datos" / "indicadores.csv", filas)
        escribir_csv_sociales(temporal / "datos", semestres, trimestres)
        escribir_csv_precios(temporal / "datos" / "precios.csv", precios)
        (temporal / "datos" / "indicadores.json").write_text(
            json.dumps(
                {
                    "actualizado": actualizado.date().isoformat(),
                    "fuentes": {
                        "canasta": API_INDEC,
                        **{nombre: url for nombre, (url, _) in SERIES_ABIERTAS.items()},
                        "ipc": API_IPC,
                        "pobreza": API_POBREZA,
                        "trabajo": API_TRABAJO,
                        "precios": API_IPC,
                    },
                    "correcciones": correcciones,
                    "bonos": bonos,
                    "meses": filas,
                    "pobreza": semestres,
                    "trabajo": trimestres,
                    "precios": precios,
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
