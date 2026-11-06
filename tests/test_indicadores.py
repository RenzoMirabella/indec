"""Pruebas del cálculo de indicadores, con casos tomados de los datos reales."""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import indicadores as ind  # noqa: E402


def canasta(cbt=528318.67, cba=239058.22):
    return {"cba": cba, "cbt": cbt, "cba_hogar": cba * 3.09, "cbt_hogar": cbt * 3.09}


def filas_api(periodo="202609", cbt=528318.67, cba=239058.22):
    return [
        {"periodo": periodo, "codigo": "CBA", "tipo_de_indicador": "CBA", "valor": cba},
        {"periodo": periodo, "codigo": "CBT", "tipo_de_indicador": "CBT", "valor": cbt},
        {"periodo": periodo, "codigo": "CBA H2", "tipo_de_indicador": "Hogar 2", "valor": cba * 3.09},
        {"periodo": periodo, "codigo": "CBT H2", "tipo_de_indicador": "Hogar 2", "valor": cbt * 3.09},
    ]


class Formatos(unittest.TestCase):
    def test_numeros_en_formato_argentino(self):
        self.assertEqual(ind.numero(1632504.69), "1.632.505")
        self.assertEqual(ind.numero(4.2535, 2), "4,25")
        self.assertEqual(ind.pesos(383800), "$383.800")
        self.assertEqual(ind.porcentaje(0.235), "24%")

    def test_nombre_de_mes(self):
        self.assertEqual(ind.nombre_mes("2026-09"), "septiembre de 2026")


class Canastas(unittest.TestCase):
    def test_interpreta_un_mes_real(self):
        meses = ind.interpretar_canastas(filas_api())
        self.assertAlmostEqual(meses["2026-09"]["cbt_hogar"], 1632504.69, places=0)

    def test_rechaza_formato_cambiado(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_canastas([{"periodo": "202609", "codigo": "CBT"}])

    def test_rechaza_mes_incompleto(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_canastas(filas_api()[:3])

    def test_rechaza_hogar_tipo_distinto(self):
        filas = filas_api()
        filas[3]["valor"] = 528318.67 * 3.5
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_canastas(filas)

    def test_ignora_otros_hogares(self):
        filas = filas_api() + [
            {"periodo": "202609", "codigo": "CBT H1", "tipo_de_indicador": "Hogar 1", "valor": 1.0}
        ]
        self.assertEqual(len(ind.interpretar_canastas(filas)["2026-09"]), 4)


class Series(unittest.TestCase):
    def test_lee_serie_y_saltea_vacios(self):
        texto = "indice_tiempo,ripte\n2026-07-01,1946028.12\n2026-08-01,\n"
        self.assertEqual(ind.interpretar_serie(texto, "ripte"), {"2026-07": 1946028.12})

    def test_rechaza_columna_ausente(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_serie("indice_tiempo,otra\n2026-07-01,1\n", "ripte")

    def test_correccion_del_ripte_de_agosto(self):
        series = {"ripte": {"2026-07": 1946028.12, "2026-08": 1915878.76}}
        ind.aplicar_correcciones(series, [{"serie": "ripte", "periodo": "2026-08", "valor": "1982518.19"}])
        self.assertEqual(series["ripte"]["2026-08"], 1982518.19)
        self.assertEqual(ind.descartar_caidas_ripte(series["ripte"]), [])

    def test_sin_correccion_la_caida_se_descarta_y_avisa(self):
        ripte = {"2026-07": 1946028.12, "2026-08": 1915878.76}
        alertas = ind.descartar_caidas_ripte(ripte)
        self.assertEqual(len(alertas), 1)
        self.assertNotIn("2026-08", ripte)

    def test_correccion_de_serie_desconocida(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.aplicar_correcciones({}, [{"serie": "otra", "periodo": "2026-08", "valor": "1"}])


class Calculo(unittest.TestCase):
    def setUp(self):
        self.canastas = {"2016-04": canasta(3663.66, 1514.53), "2016-05": canasta()}
        self.series = {
            "smvm": {"2016-04": 6060.0, "2016-05": 383800.0},
            "haber": {"2016-04": 4958.8965, "2016-05": 428633.20},
            "ripte": {"2016-04": 17691.29},
        }

    def test_salarios_necesarios(self):
        filas = ind.combinar(self.canastas, self.series)
        self.assertAlmostEqual(filas[1]["smvm_cbt"], 4.2535, places=3)
        self.assertAlmostEqual(filas[1]["smvm_cba"], 1.9247, places=3)

    def test_ripte_faltante_queda_vacio(self):
        filas = ind.combinar(self.canastas, self.series)
        self.assertIsNone(filas[1]["ripte"])
        self.assertIsNone(filas[1]["ripte_cbt"])

    def test_falta_un_mes_de_canasta(self):
        self.canastas["2016-07"] = canasta()
        with self.assertRaises(ind.DatosInvalidos):
            ind.combinar(self.canastas, self.series)

    def test_falta_salario_minimo(self):
        del self.series["smvm"]["2016-05"]
        with self.assertRaises(ind.DatosInvalidos):
            ind.combinar(self.canastas, self.series)

    def test_inicio_incorrecto(self):
        del self.canastas["2016-04"]
        with self.assertRaises(ind.DatosInvalidos):
            ind.combinar(self.canastas, self.series)

    def test_coberturas_de_jubilados(self):
        filas = ind.combinar(self.canastas, self.series)
        barras, bono = ind.coberturas(filas, {"2016-05": 70000.0})
        self.assertEqual(bono, 70000.0)
        varon, mujer, pareja, dos = barras[3:7]
        self.assertAlmostEqual(varon.cobertura, 0.9775, places=3)
        self.assertAlmostEqual(mujer.cobertura, 1.2109, places=3)
        self.assertAlmostEqual(pareja.cobertura, 0.5409, places=3)
        self.assertAlmostEqual(dos.cobertura + dos.extra, 1.2583, places=3)

    def test_sin_bono_no_hay_segmento(self):
        filas = ind.combinar(self.canastas, self.series)
        barras, bono = ind.coberturas(filas, {})
        self.assertEqual(bono, 0.0)
        self.assertEqual(barras[3].extra, 0.0)
        self.assertEqual(barras[3].nota, "")


class Sitio(unittest.TestCase):
    def setUp(self):
        canastas = {"2016-04": canasta(3663.66, 1514.53), "2016-05": canasta()}
        series = {
            "smvm": {"2016-04": 6060.0, "2016-05": 383800.0},
            "haber": {"2016-04": 4958.8965, "2016-05": 428633.20},
            "ripte": {"2016-04": 17691.29, "2016-05": 18000.0},
        }
        self.filas = ind.combinar(canastas, series)
        self.barras, self.bono = ind.coberturas(self.filas, {"2016-05": 70000.0})
        self.fecha = datetime(2026, 11, 6)

    def test_plantilla_real_queda_completa(self):
        raiz = Path(__file__).resolve().parent.parent
        plantilla = (raiz / "sitio" / "plantilla.html").read_text(encoding="utf-8")
        pagina = ind.armar_sitio(plantilla, self.filas, self.barras, self.bono, [], self.fecha)
        self.assertIn("4,3 salarios mínimos", pagina)
        self.assertIn("6 de noviembre de 2026", pagina)
        self.assertNotIn("{{", pagina)

    def test_marcador_desconocido_falla(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.armar_sitio("{{NO_EXISTE}}", self.filas, self.barras, self.bono, [], self.fecha)

    def test_datos_no_cierran_el_script(self):
        filas = [dict(f) for f in self.filas]
        filas[0]["periodo"] = "2016-04"
        pagina = ind.armar_sitio("{{DATOS_JSON}}", filas, self.barras, self.bono, [], self.fecha)
        self.assertNotIn("</", pagina)

    def test_csv_deja_vacios_los_faltantes(self):
        filas = [dict(f) for f in self.filas]
        filas[1]["ripte"] = None
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "x.csv"
            ind.escribir_csv(destino, filas)
            lineas = destino.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lineas), 3)
        self.assertIn(",,", lineas[2])


if __name__ == "__main__":
    unittest.main()
