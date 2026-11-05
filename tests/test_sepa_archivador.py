"""Tests del archivador. Los casos raros salen de archivos reales de SEPA.

Se corren con: python -m unittest discover -s tests -v
"""
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import sepa_archivador as sa  # noqa: E402

ENC_COMERCIO = "id_comercio|id_bandera|comercio_cuit|comercio_razon_social|comercio_bandera_nombre|comercio_bandera_url|comercio_ultima_actualizacion|comercio_version_sepa"
ENC_SUC = "id_comercio|id_bandera|id_sucursal|sucursales_nombre|sucursales_tipo|sucursales_calle|sucursales_numero|sucursales_latitud|sucursales_longitud|sucursales_observaciones|sucursales_barrio|sucursales_codigo_postal|sucursales_localidad|sucursales_provincia"
ENC_PROD = "|".join(sa.COLUMNAS_PRODUCTOS)

OBELISCO = ("-34.6037", "-58.3816")
MAR_DEL_PLATA = ("-38.0055", "-57.5426")
CORDOBA = ("-31.4201", "-64.1888")


def sucursal(comercio, bandera, id_suc, lat, lon, provincia="AR-C", localidad="X"):
    return f"{comercio}|{bandera}|{id_suc}|Suc|Supermercado|Calle|1|{lat}|{lon}||B|1000|{localidad}|{provincia}"


def producto(comercio, bandera, id_suc, id_prod="779", descripcion="LECHE", precio="1000.00"):
    return f"{comercio}|{bandera}|{id_suc}|{id_prod}|1|{descripcion}|1|lt|MARCA|{precio}|{precio}|1|lt||||"


def csv_bytes(encabezado, filas, cierre=True, bom=False, salto="\r\n"):
    texto = salto.join([encabezado, *filas]) + salto
    if cierre:
        texto += f"{salto}Última actualización: 2026-11-02T01:00:00-03:00{salto}"
    return (b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8")


def comercio_zip(comercio, sucursales, productos, **opciones):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        fila = f"{comercio}|1|30|SA|Cadena {comercio}|url|2026-11-02T01:00:00-03:00|1.0"
        z.writestr("comercio.csv", csv_bytes(ENC_COMERCIO, [fila], **opciones))
        z.writestr("sucursales.csv", csv_bytes(ENC_SUC, sucursales, **opciones))
        z.writestr("productos.csv", csv_bytes(ENC_PROD, productos, **opciones))
    return buffer.getvalue()


def zip_del_dia(ruta, fecha, internos):
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        z.writestr(f"{fecha}/", b"")
        for nombre, contenido in internos.items():
            z.writestr(f"{fecha}/{nombre}", contenido)
    return ruta


def nombre_interno(comercio, fecha="2026-11-02"):
    return f"sepa_1_comercio-sepa-{comercio}_{fecha}_09-05-10.zip"


class LecturaCsv(unittest.TestCase):
    def leer(self, lineas, columnas=("a", "b", "c")):
        conteo = sa.ConteoCsv()
        datos = io.BytesIO("\r\n".join(lineas).encode("utf-8"))
        filas = list(sa.leer_csv(datos, list(columnas), set(), conteo))
        return filas, conteo

    def test_comilla_suelta_no_se_traga_las_filas_siguientes(self):
        filas, conteo = self.leer(['a|b|c', '1|TV 32"|x', '2|"cerrada|y', '3|ok|z'])
        self.assertEqual([f["a"] for f in filas], ["1", "2", "3"])
        self.assertEqual(conteo.rechazadas, 0)

    def test_pipe_entre_comillas_es_parte_del_valor(self):
        filas, _ = self.leer(['a|b|c', '1|"x|y"|z'])
        self.assertEqual(filas[0]["b"], "x|y")

    def test_salto_de_linea_dentro_de_un_campo_se_repara(self):
        # Caso real: el comercio 6 parte sus sucursales en varias lineas.
        filas, conteo = self.leer(['a|b|c', '1|-24.18', '|-65.30', '2|x|y'])
        self.assertEqual(filas[0], {"a": "1", "b": "-24.18", "c": "-65.30"})
        self.assertEqual(filas[1]["a"], "2")
        self.assertEqual((conteo.reparadas, conteo.rechazadas), (1, 0))

    def test_fila_truncada_no_arrastra_a_la_siguiente(self):
        filas, conteo = self.leer(['a|b|c', '1|cortada', '2|x|y', '3|x|y'])
        self.assertEqual([f["a"] for f in filas], ["2", "3"])
        self.assertEqual(conteo.rechazadas, 1)

    def test_fila_con_columnas_de_mas_se_rechaza(self):
        filas, conteo = self.leer(['a|b|c', '1|x|y|z', '2|x|y'])
        self.assertEqual([f["a"] for f in filas], ["2"])
        self.assertEqual(conteo.rechazadas, 1)

    def test_nul_final_no_cuenta_como_rechazo(self):
        # Caso real: el comercio 47 termina con un caracter NUL.
        filas, conteo = self.leer(['a|b|c', '1|x|y', '\x00'])
        self.assertEqual(len(filas), 1)
        self.assertEqual(conteo.rechazadas, 0)

    def test_fila_de_cierre_se_captura_y_no_es_dato(self):
        filas, conteo = self.leer(['a|b|c', '1|x|y', '', 'Última actualización: 2026-11-02T01:00:00-03:00'])
        self.assertEqual(len(filas), 1)
        self.assertEqual(conteo.trailer, "2026-11-02T01:00:00-03:00")
        self.assertEqual(conteo.rechazadas, 0)

    def test_latin1_se_decodifica_y_se_cuenta(self):
        conteo = sa.ConteoCsv()
        datos = io.BytesIO(b"a|b|c\r\n1|Jam\xf3n|y\r\n")
        filas = list(sa.leer_csv(datos, ["a", "b", "c"], set(), conteo))
        self.assertEqual(filas[0]["b"], "Jamón")
        self.assertEqual(conteo.latin1, 1)

    def test_bom_no_rompe_el_encabezado(self):
        conteo = sa.ConteoCsv()
        datos = io.BytesIO(b"\xef\xbb\xbfa|b\r\n1|2\r\n")
        filas = list(sa.leer_csv(datos, ["a", "b"], {"a"}, conteo))
        self.assertEqual(filas, [{"a": "1", "b": "2"}])

    def test_falta_columna_requerida(self):
        conteo = sa.ConteoCsv()
        with self.assertRaises(sa.ErrorDeArchivo):
            list(sa.leer_csv(io.BytesIO(b"a|b\r\n1|2\r\n"), ["a", "z"], {"z"}, conteo))


class Zonas(unittest.TestCase):
    def suc(self, lat, lon, localidad="", provincia="AR-C"):
        return {
            "sucursales_latitud": lat, "sucursales_longitud": lon,
            "sucursales_localidad": localidad, "sucursales_provincia": provincia,
        }

    def test_coordenadas_mandan_sobre_la_provincia(self):
        # Caso real: Carrefour tiene sucursales de Cordoba cargadas como AR-C.
        self.assertIsNone(sa.zona_de(self.suc(*CORDOBA, provincia="AR-C")))

    def test_centros(self):
        self.assertEqual(sa.zona_de(self.suc(*OBELISCO)), "gba_ampliado")
        self.assertEqual(sa.zona_de(self.suc(*MAR_DEL_PLATA)), "mar_del_plata")

    def test_provincia_vacia_con_coordenadas_validas(self):
        self.assertEqual(sa.zona_de(self.suc(*MAR_DEL_PLATA, provincia="")), "mar_del_plata")

    def test_sin_coordenadas_usa_el_texto(self):
        self.assertEqual(sa.zona_de(self.suc("", "", "Mar del Plata")), "mar_del_plata")
        self.assertEqual(sa.zona_de(self.suc("0", "0", "Ciudad Autónoma de Buenos Aires")), "gba_ampliado")
        self.assertIsNone(sa.zona_de(self.suc("", "", "Rosario")))

    def test_coma_decimal(self):
        self.assertEqual(sa.zona_de(self.suc("-34,6037", "-58,3816")), "gba_ampliado")


class ProcesarDia(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.salida = self.tmp / "archivo"

    def tearDown(self):
        self._tmp.cleanup()

    def dia(self, fecha="2026-11-02", internos=None, nombre="dia.zip"):
        return zip_del_dia(self.tmp / nombre, fecha, internos)

    def internos_base(self):
        return {
            nombre_interno(12, ): comercio_zip(
                12,
                [
                    sucursal(12, 1, "004", *OBELISCO),
                    sucursal(12, 1, "5", *MAR_DEL_PLATA, provincia="AR-B"),
                    sucursal(12, 1, "6", *CORDOBA, provincia="AR-C"),
                ],
                [
                    producto(12, 1, "004"),
                    producto(12, 1, "5", id_prod="780"),
                    producto(12, 1, "6", id_prod="781"),
                    producto(12, 9, "999", id_prod="782"),
                ],
            ),
            nombre_interno(36): b"",
        }

    def productos(self, fecha="2026-11-02"):
        ruta = self.salida / "datos" / fecha[:7] / f"productos_{fecha}.parquet"
        return pq.read_table(ruta).to_pylist()

    def test_filtra_marca_y_conserva_ceros_a_la_izquierda(self):
        sa.procesar_zip(self.dia(internos=self.internos_base()), self.salida, {"sha256": "a"})
        filas = {f["id_producto"]: f for f in self.productos()}
        self.assertEqual(filas["779"]["zona"], "gba_ampliado")
        self.assertEqual(filas["779"]["id_sucursal"], "004")
        self.assertEqual(filas["780"]["zona"], "mar_del_plata")
        self.assertNotIn("781", filas)
        self.assertEqual(filas["782"]["zona"], sa.ZONA_DESCONOCIDA)
        self.assertEqual(str(filas["779"]["fecha"]), "2026-11-02")

    def test_sucursales_quedan_todas_incluso_fuera_de_zona(self):
        sa.procesar_zip(self.dia(internos=self.internos_base()), self.salida, {"sha256": "a"})
        ruta = self.salida / "datos" / "2026-11" / "sucursales_2026-11-02.parquet"
        self.assertEqual(pq.read_table(ruta).num_rows, 3)

    def test_zip_vacio_de_una_cadena_no_frena_al_resto(self):
        m = sa.procesar_zip(self.dia(internos=self.internos_base()), self.salida, {"sha256": "a"})
        self.assertEqual(m["estado"], "parcial")
        self.assertTrue(any("comercio 36" in a for a in m["alertas"]))
        self.assertEqual(m["salidas"]["productos"]["filas"], 3)

    def test_interno_corrupto_no_frena_al_resto(self):
        internos = self.internos_base()
        internos[nombre_interno(36)] = b"esto no es un zip"
        m = sa.procesar_zip(self.dia(internos=internos), self.salida, {"sha256": "a"})
        self.assertEqual(m["estado"], "parcial")
        self.assertEqual(m["salidas"]["productos"]["filas"], 3)

    def test_formato_alternativo_con_bom_y_lf(self):
        interno = comercio_zip(
            9, [sucursal(9, 1, "1", *OBELISCO)], [producto(9, 1, "1")], bom=True, salto="\n", cierre=False
        )
        m = sa.procesar_zip(self.dia(internos={nombre_interno(9): interno}), self.salida, {"sha256": "a"})
        self.assertEqual(m["estado"], "completo")
        self.assertEqual(m["salidas"]["productos"]["filas"], 1)

    def test_segunda_corrida_no_reescribe(self):
        ruta = self.dia(internos=self.internos_base())
        primero = sa.procesar_zip(ruta, self.salida, {"sha256": "a"})
        segundo = sa.procesar_zip(ruta, self.salida, {"sha256": "a"})
        self.assertEqual(primero["generado_utc"], segundo["generado_utc"])

    def test_dia_parcial_se_reprocesa_si_llega_otro_archivo(self):
        sa.procesar_zip(self.dia(internos=self.internos_base()), self.salida, {"sha256": "a"})
        internos = self.internos_base()
        internos[nombre_interno(36)] = comercio_zip(36, [sucursal(36, 1, "1", *OBELISCO)], [producto(36, 1, "1")])
        m = sa.procesar_zip(self.dia(internos=internos), self.salida, {"sha256": "b"})
        self.assertEqual(m["estado"], "completo")
        self.assertEqual(m["salidas"]["productos"]["filas"], 4)

    def test_dia_completo_no_se_reprocesa(self):
        internos = {nombre_interno(9): comercio_zip(9, [sucursal(9, 1, "1", *OBELISCO)], [producto(9, 1, "1")])}
        sa.procesar_zip(self.dia(internos=internos), self.salida, {"sha256": "a"})
        internos[nombre_interno(9)] = comercio_zip(9, [sucursal(9, 1, "1", *OBELISCO)], [])
        m = sa.procesar_zip(self.dia(internos=internos), self.salida, {"sha256": "b"})
        self.assertEqual(m["salidas"]["productos"]["filas"], 1)

    def test_sin_filas_falla_y_no_deja_manifiesto_ni_temporales(self):
        internos = {nombre_interno(9): comercio_zip(9, [sucursal(9, 1, "1", *CORDOBA)], [producto(9, 1, "1")])}
        with self.assertRaises(sa.ErrorDeArchivo):
            sa.procesar_zip(self.dia(internos=internos), self.salida, {"sha256": "a"})
        self.assertFalse((self.salida / "manifiestos" / "2026-11-02.json").exists())
        self.assertEqual([p for p in self.salida.rglob("*") if p.is_file()], [])

    def test_mas_de_una_fecha_en_el_zip_falla(self):
        ruta = self.tmp / "dos.zip"
        with zipfile.ZipFile(ruta, "w") as z:
            z.writestr("2026-11-02/a.zip", b"x")
            z.writestr("2026-11-03/b.zip", b"x")
        with self.assertRaises(sa.ErrorDeArchivo):
            sa.procesar_zip(ruta, self.salida, {"sha256": "a"})

    def test_zip_externo_invalido_falla(self):
        ruta = self.tmp / "roto.zip"
        ruta.write_bytes(b"nada")
        with self.assertRaises(sa.ErrorDeArchivo):
            sa.procesar_zip(ruta, self.salida, {"sha256": "a"})

    def test_alerta_si_una_cadena_desaparece_o_cae(self):
        sucursales = [sucursal(9, 1, "1", *OBELISCO)]
        prods = [producto(9, 1, "1", id_prod=str(i)) for i in range(10)]
        otros = [sucursal(10, 1, "1", *OBELISCO)]
        internos = {
            nombre_interno(9): comercio_zip(9, sucursales, prods),
            nombre_interno(10): comercio_zip(10, otros, [producto(10, 1, "1")]),
        }
        sa.procesar_zip(self.dia(internos=internos), self.salida, {"sha256": "a"})
        internos = {
            nombre_interno(9, "2026-11-03"): comercio_zip(9, sucursales, prods[:2]),
        }
        m = sa.procesar_zip(self.dia("2026-11-03", internos), self.salida, {"sha256": "b"})
        texto = " ".join(m["alertas"])
        self.assertIn("comercio 10", texto)
        self.assertIn("bajaron de 10 a 2", texto)

    def test_dia_parcial_con_el_mismo_etag_no_se_vuelve_a_bajar(self):
        fuente = {"sha256": "a", "etag": "v1"}
        m = sa.procesar_zip(self.dia(internos=self.internos_base()), self.salida, fuente)
        self.assertEqual(m["estado"], "parcial")
        self.assertIn("v1", sa._etags_archivados(self.salida / "manifiestos"))

    def test_manifiesto_es_json_valido_y_describe_las_salidas(self):
        sa.procesar_zip(self.dia(internos=self.internos_base()), self.salida, {"sha256": "a"})
        m = json.loads((self.salida / "manifiestos" / "2026-11-02.json").read_text(encoding="utf-8"))
        ruta = self.salida / "datos" / "2026-11" / m["salidas"]["productos"]["archivo"]
        self.assertEqual(m["salidas"]["productos"]["sha256"], sa.sha256_de(ruta))


if __name__ == "__main__":
    unittest.main()
