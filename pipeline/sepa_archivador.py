#!/usr/bin/env python3
"""Archivador diario de la base SEPA (Precios Claros).

El dataset oficial publica un ZIP por dia de la semana y cada archivo pisa al
de la semana anterior: lo que no se guarda dentro de los 7 dias se pierde. Cada
corrida revisa los 7 archivos y procesa los que todavia no estan archivados, asi
que una corrida fallida se recupera sola mientras no pase una semana.

Por cada fecha genera:
  datos/AAAA-MM/productos_AAAA-MM-DD.parquet   precios de las zonas elegidas
  datos/AAAA-MM/sucursales_AAAA-MM-DD.parquet  todas las sucursales del pais
  manifiestos/AAAA-MM-DD.json                  fuente, conteos y alertas

Los valores se guardan como texto, tal como vienen. Interpretar precios y
descartar extremos es tarea de la etapa de calculo: asi un error de criterio se
puede corregir despues sin haber perdido el dato original.
"""
from __future__ import annotations

import argparse
import csv
from codecs import BOM_UTF8
import hashlib
import json
import logging
import math
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger("sepa")

VERSION_ESQUEMA = 1
USER_AGENT = "monitor-del-bolsillo-archivador/1.0"

_BASE = "https://datos.produccion.gob.ar/dataset/6f47ec76-d1ce-4e34-a7e1-621fe9b1d0b5/resource"
URLS = {
    "lunes": f"{_BASE}/0a9069a9-06e8-4f98-874d-da5578693290/download/sepa_lunes.zip",
    "martes": f"{_BASE}/9dc06241-cc83-44f4-8e25-c9b1636b8bc8/download/sepa_martes.zip",
    "miercoles": f"{_BASE}/1e92cd42-4f94-4071-a165-62c4cb2ce23c/download/sepa_miercoles.zip",
    "jueves": f"{_BASE}/d076720f-a7f0-4af8-b1d6-1b99d5a90c14/download/sepa_jueves.zip",
    "viernes": f"{_BASE}/91bc072a-4726-44a1-85ec-4a8467aad27e/download/sepa_viernes.zip",
    "sabado": f"{_BASE}/b3c3da5d-213d-41e7-8d74-f23fda0a3c30/download/sepa_sabado.zip",
    "domingo": f"{_BASE}/f8e75128-515a-436e-bf8d-5c63a62f2005/download/sepa_domingo.zip",
}

# Zonas por distancia a un centro. Se filtra por coordenadas porque el campo de
# provincia no es confiable (hay sucursales de Cordoba cargadas como CABA).
# "gba_ampliado" es a proposito mas grande que CABA + 24 partidos: incluye La
# Plata, Pilar y Escobar. El recorte exacto se hace despues; lo que no se archiva
# hoy no se puede recuperar.
ZONAS = {
    "gba_ampliado": {"lat": -34.6037, "lon": -58.3816, "radio_km": 60.0},
    "mar_del_plata": {"lat": -38.0055, "lon": -57.5426, "radio_km": 30.0},
}

COLUMNAS_PRODUCTOS = [
    "id_comercio", "id_bandera", "id_sucursal", "id_producto", "productos_ean",
    "productos_descripcion", "productos_cantidad_presentacion",
    "productos_unidad_medida_presentacion", "productos_marca",
    "productos_precio_lista", "productos_precio_referencia",
    "productos_cantidad_referencia", "productos_unidad_medida_referencia",
    "productos_precio_unitario_promo1", "productos_leyenda_promo1",
    "productos_precio_unitario_promo2", "productos_leyenda_promo2",
]
COLUMNAS_SUCURSALES = [
    "id_comercio", "id_bandera", "id_sucursal", "sucursales_nombre", "sucursales_tipo",
    "sucursales_calle", "sucursales_numero", "sucursales_latitud", "sucursales_longitud",
    "sucursales_barrio", "sucursales_codigo_postal", "sucursales_localidad",
    "sucursales_provincia",
]
REQUERIDAS_PRODUCTOS = {"id_comercio", "id_bandera", "id_sucursal", "id_producto", "productos_precio_lista"}
REQUERIDAS_SUCURSALES = {"id_comercio", "id_bandera", "id_sucursal", "sucursales_latitud", "sucursales_longitud"}

ZONA_DESCONOCIDA = "sin_sucursal"
FILAS_POR_LOTE = 250_000
UMBRAL_RECHAZADAS = 0.001
UMBRAL_HUERFANAS = 0.01
UMBRAL_CAIDA_FILAS = 0.30
DIAS_DESACTUALIZADO = 7

_RE_FECHA = re.compile(r"(\d{4}-\d{2}-\d{2})")
_RE_COMERCIO = re.compile(r"comercio-sepa-(\d+)")
_RE_TRAILER = re.compile(r"^\W*.?ltima actualizaci.{1,2}n\s*:?\s*(.*)$", re.IGNORECASE)


class ErrorDeArchivo(Exception):
    """El ZIP del dia no se puede procesar."""


# --- Lectura de CSV ----------------------------------------------------------


def partir_linea(linea: str, esperadas: int) -> list[str] | None:
    """Separa una fila o devuelve None si no tiene las columnas esperadas.

    Se procesa linea por linea, y no con un lector CSV sobre todo el archivo,
    porque una comilla suelta en una descripcion (`TV 32"`) haria que el lector
    se trague miles de filas siguientes sin avisar.
    """
    partes = linea.split("|")
    if '"' in linea:
        try:
            con_comillas = next(csv.reader([linea], delimiter="|"))
        except (csv.Error, StopIteration):
            con_comillas = []
        if len(con_comillas) == esperadas:
            return con_comillas
    return partes if len(partes) == esperadas else None


@dataclass
class ConteoCsv:
    rechazadas: int = 0
    reparadas: int = 0
    latin1: int = 0
    trailer: str | None = None
    columnas_faltantes: list[str] = field(default_factory=list)
    columnas_extra: list[str] = field(default_factory=list)
    ejemplos_rechazadas: list[str] = field(default_factory=list)


def _decodificar(crudo: bytes, conteo: ConteoCsv) -> str:
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        conteo.latin1 += 1
        return crudo.decode("latin-1")


def leer_csv(stream, columnas: list[str], requeridas: set[str], conteo: ConteoCsv) -> Iterator[dict[str, str]]:
    """Recorre un CSV de SEPA tolerando BOM, NUL, fila de cierre y filas cortadas.

    Algunas cadenas meten saltos de linea dentro de un campo. Una fila con menos
    columnas de las esperadas se une con las siguientes hasta completarse; si al
    unirla se pasa, el fragmento se rechaza y la linea nueva se evalua sola.
    """
    encabezado: list[str] | None = None
    pendiente = ""

    def rechazar(linea: str) -> None:
        conteo.rechazadas += 1
        if len(conteo.ejemplos_rechazadas) < 3:
            conteo.ejemplos_rechazadas.append(linea[:200])

    def como_fila(partes: list[str]) -> dict[str, str]:
        return dict(zip(encabezado, (p.strip() for p in partes)))

    for crudo in stream:
        crudo = crudo.rstrip(bytes([13, 10])).strip(bytes([0]))
        if encabezado is None:
            crudo = crudo.removeprefix(BOM_UTF8)
        if not crudo.strip():
            continue
        linea = _decodificar(crudo, conteo)
        if encabezado is None:
            encabezado = [c.strip().lower() for c in linea.split("|")]
            conteo.columnas_faltantes = [c for c in columnas if c not in encabezado]
            conteo.columnas_extra = [c for c in encabezado if c not in columnas]
            faltan = requeridas - set(encabezado)
            if faltan:
                raise ErrorDeArchivo(f"faltan columnas requeridas: {sorted(faltan)}")
            continue
        esperadas = len(encabezado)
        cierre = _RE_TRAILER.match(linea)
        if cierre and "|" not in linea:
            if pendiente:
                rechazar(pendiente)
                pendiente = ""
            conteo.trailer = cierre.group(1).strip() or None
            continue
        if pendiente:
            unida = pendiente + linea
            partes = partir_linea(unida, esperadas)
            if partes is not None:
                pendiente = ""
                conteo.reparadas += 1
                yield como_fila(partes)
                continue
            if unida.count("|") + 1 < esperadas:
                pendiente = unida
                continue
            rechazar(pendiente)
            pendiente = ""
        partes = partir_linea(linea, esperadas)
        if partes is not None:
            yield como_fila(partes)
        elif linea.count("|") + 1 < esperadas:
            pendiente = linea
        else:
            rechazar(linea)
    if pendiente:
        rechazar(pendiente)


# --- Zonas -------------------------------------------------------------------


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180
    h = (
        math.sin((lat2 - lat1) * rad / 2) ** 2
        + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin((lon2 - lon1) * rad / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))


def _coordenadas(sucursal: dict[str, str]) -> tuple[float, float] | None:
    try:
        lat = float(sucursal.get("sucursales_latitud", "").replace(",", "."))
        lon = float(sucursal.get("sucursales_longitud", "").replace(",", "."))
    except ValueError:
        return None
    # Fuera de este rectangulo la coordenada esta mal cargada (por ejemplo, 0,0).
    return (lat, lon) if -56 <= lat <= -21 and -74 <= lon <= -53 else None


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.upper().strip()


def zona_de(sucursal: dict[str, str]) -> str | None:
    """Zona de una sucursal. Solo usa el texto si no hay coordenadas validas."""
    coordenadas = _coordenadas(sucursal)
    if coordenadas:
        for nombre, z in ZONAS.items():
            if distancia_km(*coordenadas, z["lat"], z["lon"]) <= z["radio_km"]:
                return nombre
        return None
    localidad = _normalizar(sucursal.get("sucursales_localidad", ""))
    if "MAR DEL PLATA" in localidad or "BATAN" == localidad:
        return "mar_del_plata"
    if "CAPITAL FEDERAL" in localidad or "CIUDAD AUTONOMA" in localidad or localidad == "CABA":
        return "gba_ampliado"
    return None


# --- Salida ------------------------------------------------------------------


class EscritorParquet:
    """Escribe por lotes a un temporal; el archivo final aparece solo al cerrar."""

    def __init__(self, destino: Path, columnas: list[str], extras: dict[str, pa.DataType]):
        self.destino = destino
        self.columnas = columnas
        self.extras = extras
        self.temporal = destino.with_name(destino.name + ".tmp")
        destino.parent.mkdir(parents=True, exist_ok=True)
        campos = [(c, pa.string()) for c in columnas] + list(extras.items())
        self.esquema = pa.schema(campos)
        self.escritor = pq.ParquetWriter(
            self.temporal, self.esquema, compression="zstd", compression_level=9, use_dictionary=True
        )
        self.lote: list[dict] = []
        self.filas = 0

    def agregar(self, fila: dict) -> None:
        self.lote.append(fila)
        self.filas += 1
        if len(self.lote) >= FILAS_POR_LOTE:
            self._volcar()

    def _volcar(self) -> None:
        if not self.lote:
            return
        arrays = {}
        for nombre in self.esquema.names:
            valores = [f.get(nombre) or None for f in self.lote]
            arrays[nombre] = pa.array(valores, type=self.esquema.field(nombre).type)
        self.escritor.write_table(pa.table(arrays, schema=self.esquema))
        self.lote = []

    def cerrar(self) -> dict:
        self._volcar()
        self.escritor.close()
        os.replace(self.temporal, self.destino)
        return {
            "archivo": self.destino.name,
            "filas": self.filas,
            "bytes": self.destino.stat().st_size,
            "sha256": sha256_de(self.destino),
        }

    def descartar(self) -> None:
        self.escritor.close()
        self.temporal.unlink(missing_ok=True)


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def escribir_json(ruta: Path, contenido: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporal, ruta)


# --- Procesamiento de un dia -------------------------------------------------


def fecha_del_zip(zip_externo: zipfile.ZipFile) -> str:
    """La fecha sale de las carpetas internas: el nombre (sepa_lunes) no la dice."""
    fechas = {m.group(1) for n in zip_externo.namelist() if (m := _RE_FECHA.match(n))}
    if len(fechas) != 1:
        raise ErrorDeArchivo(f"se esperaba una sola fecha en el ZIP y hay: {sorted(fechas)}")
    return fechas.pop()


def _abrir_csv(interno: zipfile.ZipFile, nombre: str):
    nombres = {n.split("/")[-1].lower(): n for n in interno.namelist()}
    if nombre not in nombres:
        raise ErrorDeArchivo(f"falta {nombre}")
    return interno.open(nombres[nombre])


def procesar_comercio(interno, fecha, escritor_productos, escritor_sucursales) -> dict:
    """Archiva un comercio y devuelve sus conteos."""
    resultado: dict = {}

    conteo = ConteoCsv()
    with _abrir_csv(interno, "comercio.csv") as f:
        banderas = list(leer_csv(f, ["id_comercio", "id_bandera"], {"id_comercio"}, conteo))
    resultado["banderas"] = sorted({b.get("comercio_bandera_nombre", "") for b in banderas})
    actualizaciones = [b.get("comercio_ultima_actualizacion", "") for b in banderas]
    resultado["ultima_actualizacion"] = max(actualizaciones, default=None) or None

    conteo = ConteoCsv()
    zonas: dict[tuple[str, str, str], str | None] = {}
    with _abrir_csv(interno, "sucursales.csv") as f:
        for s in leer_csv(f, COLUMNAS_SUCURSALES, REQUERIDAS_SUCURSALES, conteo):
            clave = (s["id_comercio"], s["id_bandera"], s["id_sucursal"])
            zona = zona_de(s)
            zonas[clave] = zona
            escritor_sucursales.agregar({**s, "zona": zona, "fecha": date.fromisoformat(fecha)})
    resultado["sucursales"] = len(zonas)
    resultado["sucursales_en_zona"] = sum(1 for z in zonas.values() if z)
    resultado["sucursales_rechazadas"] = conteo.rechazadas
    resultado["sucursales_reparadas"] = conteo.reparadas

    conteo = ConteoCsv()
    leidas = archivadas = huerfanas = 0
    fecha_d = date.fromisoformat(fecha)
    with _abrir_csv(interno, "productos.csv") as f:
        for p in leer_csv(f, COLUMNAS_PRODUCTOS, REQUERIDAS_PRODUCTOS, conteo):
            leidas += 1
            clave = (p["id_comercio"], p["id_bandera"], p["id_sucursal"])
            # Sin sucursal conocida no se sabe donde esta: se conserva y se marca,
            # porque descartarla hoy seria perderla para siempre.
            zona = zonas.get(clave, ZONA_DESCONOCIDA)
            if zona == ZONA_DESCONOCIDA:
                huerfanas += 1
            if zona:
                archivadas += 1
                escritor_productos.agregar({**p, "zona": zona, "fecha": fecha_d})
    resultado.update(
        filas_leidas=leidas,
        filas_archivadas=archivadas,
        filas_huerfanas=huerfanas,
        filas_rechazadas=conteo.rechazadas,
        filas_reparadas=conteo.reparadas,
        filas_latin1=conteo.latin1,
        cierre_del_archivo=conteo.trailer,
        columnas_faltantes=conteo.columnas_faltantes,
        columnas_extra=conteo.columnas_extra,
        ejemplos_rechazadas=conteo.ejemplos_rechazadas,
    )
    return resultado


def _ultimo_manifiesto_previo(dir_manifiestos: Path, fecha: str) -> dict | None:
    previos = sorted(p for p in dir_manifiestos.glob("*.json") if p.stem < fecha)
    return json.loads(previos[-1].read_text(encoding="utf-8")) if previos else None


def calcular_alertas(fecha: str, comercios: list[dict], previo: dict | None) -> list[str]:
    alertas = []
    fecha_d = date.fromisoformat(fecha)
    for c in comercios:
        nombre = f"comercio {c['id_comercio']}"
        if c["estado"] != "ok":
            alertas.append(f"{nombre}: {c['estado']} ({c.get('detalle', '')})")
            continue
        leidas = c["filas_leidas"]
        total = leidas + c["filas_rechazadas"]
        if total and c["filas_rechazadas"] / total > UMBRAL_RECHAZADAS:
            alertas.append(f"{nombre}: {c['filas_rechazadas']} filas rechazadas de {total}")
        if leidas and c["filas_huerfanas"] / leidas > UMBRAL_HUERFANAS:
            alertas.append(f"{nombre}: {c['filas_huerfanas']} filas de sucursales desconocidas de {leidas}")
        if c["sucursales_rechazadas"]:
            alertas.append(f"{nombre}: {c['sucursales_rechazadas']} sucursales rechazadas")
        if c["columnas_faltantes"]:
            alertas.append(f"{nombre}: faltan columnas {c['columnas_faltantes']}")
        # La fila de cierre refleja el archivo de hoy; el campo del comercio a veces
        # queda congelado durante anos aunque los precios sigan cambiando.
        actualizada = (c.get("cierre_del_archivo") or c.get("ultima_actualizacion") or "")[:10]
        if _RE_FECHA.fullmatch(actualizada):
            atraso = (fecha_d - date.fromisoformat(actualizada)).days
            if atraso > DIAS_DESACTUALIZADO:
                alertas.append(f"{nombre}: declara ultima actualizacion {actualizada} ({atraso} dias)")
    if previo:
        hoy = {c["id_comercio"]: c for c in comercios}
        for c in previo.get("comercios", []):
            actual = hoy.get(c["id_comercio"])
            if actual is None:
                alertas.append(f"comercio {c['id_comercio']}: estaba el {previo['fecha']} y hoy no vino")
            elif actual["estado"] == "ok" and c["estado"] == "ok":
                antes, ahora = c["filas_archivadas"], actual["filas_archivadas"]
                if antes and (antes - ahora) / antes > UMBRAL_CAIDA_FILAS:
                    alertas.append(f"comercio {c['id_comercio']}: filas archivadas bajaron de {antes} a {ahora}")
    return alertas


def procesar_zip(ruta_zip: Path, salida: Path, fuente: dict) -> dict:
    """Procesa un ZIP diario completo y deja sus archivos y su manifiesto."""
    dir_manifiestos = salida / "manifiestos"
    try:
        externo = zipfile.ZipFile(ruta_zip)
    except zipfile.BadZipFile as e:
        raise ErrorDeArchivo(f"ZIP externo invalido: {e}") from e

    with externo:
        fecha = fecha_del_zip(externo)
        ruta_manifiesto = dir_manifiestos / f"{fecha}.json"
        if ruta_manifiesto.exists():
            existente = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))
            mismo_archivo = existente["fuente"].get("sha256") == fuente.get("sha256")
            if existente["estado"] == "completo" or mismo_archivo:
                log.info("%s ya esta archivado (%s); se omite", fecha, existente["estado"])
                return existente
            log.info("%s estaba parcial y hay un archivo distinto; se reprocesa", fecha)

        dir_datos = salida / "datos" / fecha[:7]
        columnas_extra = {"zona": pa.string(), "fecha": pa.date32()}
        escritor_productos = EscritorParquet(
            dir_datos / f"productos_{fecha}.parquet", COLUMNAS_PRODUCTOS, columnas_extra
        )
        escritor_sucursales = EscritorParquet(
            dir_datos / f"sucursales_{fecha}.parquet", COLUMNAS_SUCURSALES, columnas_extra
        )

        comercios = []
        internos = sorted(
            (i for i in externo.infolist() if i.filename.lower().endswith(".zip")),
            key=lambda i: i.filename,
        )
        try:
            for info in internos:
                nombre = info.filename.split("/")[-1]
                coincide = _RE_COMERCIO.search(nombre)
                registro = {
                    "id_comercio": coincide.group(1) if coincide else nombre,
                    "archivo": nombre,
                    "bytes_zip": info.file_size,
                    "estado": "ok",
                }
                filas_antes = escritor_productos.filas
                try:
                    if info.file_size == 0:
                        raise ErrorDeArchivo("ZIP de 0 bytes")
                    with externo.open(info) as stream, zipfile.ZipFile(stream) as interno:
                        registro.update(
                            procesar_comercio(interno, fecha, escritor_productos, escritor_sucursales)
                        )
                except (ErrorDeArchivo, zipfile.BadZipFile, EOFError, OSError) as e:
                    registro.update(estado="error", detalle=str(e), filas_archivadas=0)
                    registro["filas_parciales"] = escritor_productos.filas - filas_antes
                    log.warning("comercio %s: %s", registro["id_comercio"], e)
                comercios.append(registro)
                log.info(
                    "%s comercio %-3s %-6s archivadas=%s",
                    fecha, registro["id_comercio"], registro["estado"], registro.get("filas_archivadas"),
                )

            if not any(c["estado"] == "ok" and c["filas_archivadas"] for c in comercios):
                raise ErrorDeArchivo(f"{fecha}: ningun comercio aporto filas")

            salida_productos = escritor_productos.cerrar()
            salida_sucursales = escritor_sucursales.cerrar()
        except BaseException:
            escritor_productos.descartar()
            escritor_sucursales.descartar()
            raise

    previo = _ultimo_manifiesto_previo(dir_manifiestos, fecha)
    manifiesto = {
        "version_esquema": VERSION_ESQUEMA,
        "fecha": fecha,
        "estado": "completo" if all(c["estado"] == "ok" for c in comercios) else "parcial",
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": fuente,
        "zonas": ZONAS,
        "salidas": {"productos": salida_productos, "sucursales": salida_sucursales},
        "alertas": calcular_alertas(fecha, comercios, previo),
        "comercios": comercios,
    }
    # El manifiesto va ultimo: si existe, los datos de esa fecha estan completos.
    escribir_json(ruta_manifiesto, manifiesto)
    return manifiesto


# --- Descarga ----------------------------------------------------------------


def _pedido(url: str, metodo: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(url, method=metodo, headers={"User-Agent": USER_AGENT})


def consultar_encabezados(url: str) -> dict:
    with urllib.request.urlopen(_pedido(url, "HEAD"), timeout=60) as r:
        return {"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")}


def descargar(url: str, destino: Path, intentos: int = 4) -> dict:
    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            h = hashlib.sha256()
            total = 0
            with urllib.request.urlopen(_pedido(url), timeout=120) as r, open(destino, "wb") as f:
                esperado = r.headers.get("Content-Length")
                encabezados = {"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")}
                for bloque in iter(lambda: r.read(1 << 20), b""):
                    f.write(bloque)
                    h.update(bloque)
                    total += len(bloque)
            if esperado and int(esperado) != total:
                raise OSError(f"descarga incompleta: {total} de {esperado} bytes")
            return {"url": url, "bytes": total, "sha256": h.hexdigest(), **encabezados}
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            ultimo_error = e
            log.warning("descarga fallida (intento %d/%d): %s", intento, intentos, e)
            if intento < intentos:
                time.sleep(15 * intento)
    raise ErrorDeArchivo(f"no se pudo descargar {url}: {ultimo_error}")


def _etags_archivados(dir_manifiestos: Path) -> set[str]:
    etags = set()
    for ruta in dir_manifiestos.glob("*.json"):
        manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
        # Incluye los dias parciales: si el archivo no cambio, bajarlo de nuevo no
        # arregla nada. Si la fuente lo corrige, cambia el ETag y se reprocesa.
        if manifiesto["fuente"].get("etag"):
            etags.add(manifiesto["fuente"]["etag"])
    return etags


def _clave_orden(encabezados: dict) -> float:
    try:
        return parsedate_to_datetime(encabezados["last_modified"]).timestamp()
    except (TypeError, ValueError, KeyError):
        return 0.0


def ejecutar_remoto(salida: Path, urls: dict[str, str], dir_temporal: Path | None = None) -> int:
    """Revisa los 7 archivos y archiva los nuevos, del mas viejo al mas nuevo."""
    errores = 0
    conocidos = _etags_archivados(salida / "manifiestos")
    pendientes = []
    for dia, url in urls.items():
        try:
            encabezados = consultar_encabezados(url)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            log.warning("%s: no responde al consultar encabezados (%s); se intenta bajar igual", dia, e)
            encabezados = {}
        if encabezados.get("etag") and encabezados["etag"] in conocidos:
            log.info("%s: sin cambios", dia)
            continue
        pendientes.append((_clave_orden(encabezados), dia, url))

    # Cada ZIP se borra al terminar: no hace falta espacio para los siete juntos.
    for _, dia, url in sorted(pendientes):
        carpeta = Path(tempfile.mkdtemp(prefix=f"sepa_{dia}_", dir=dir_temporal))
        try:
            ruta = carpeta / f"sepa_{dia}.zip"
            log.info("%s: descargando", dia)
            fuente = {"dia_semana": dia, **descargar(url, ruta)}
            manifiesto = procesar_zip(ruta, salida, fuente)
            _informar(manifiesto)
        except (ErrorDeArchivo, OSError) as e:
            errores += 1
            log.error("%s: %s", dia, e)
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)
    return 1 if errores else 0


def _informar(manifiesto: dict) -> None:
    salidas = manifiesto["salidas"]["productos"]
    log.info(
        "%s: %s, %d filas, %.1f MB, %d alertas",
        manifiesto["fecha"], manifiesto["estado"], salidas["filas"],
        salidas["bytes"] / 1e6, len(manifiesto["alertas"]),
    )
    for alerta in manifiesto["alertas"]:
        log.warning("%s: %s", manifiesto["fecha"], alerta)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archiva la base SEPA filtrada por zona.")
    parser.add_argument("--salida", type=Path, default=Path("archivo"), help="carpeta del archivo")
    parser.add_argument("--zip", type=Path, action="append", help="procesar un ZIP local en vez de descargar")
    parser.add_argument("--temporal", type=Path, help="carpeta para las descargas temporales")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

    if not args.zip:
        return ejecutar_remoto(args.salida, URLS, args.temporal)
    errores = 0
    for ruta in args.zip:
        try:
            _informar(procesar_zip(ruta, args.salida, {"archivo_local": ruta.name, "sha256": sha256_de(ruta)}))
        except ErrorDeArchivo as e:
            errores += 1
            log.error("%s: %s", ruta, e)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
