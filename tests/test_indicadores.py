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


def datos_completos():
    """De abril de 2016 a febrero de 2017: la canasta sube igual que los precios y los ingresos quedan fijos."""
    periodos, periodo = [], "2016-04"
    while periodo <= "2017-02":
        periodos.append(periodo)
        periodo = ind._siguiente(periodo)
    ipc = {"2016-12": 100.0, "2017-01": 105.0, "2017-02": 110.0}
    canastas = {p: canasta(4000 * ipc.get(p, 100) / 100, 1600 * ipc.get(p, 100) / 100) for p in periodos}
    series = {
        "smvm": {p: 8240.0 for p in periodos},
        "haber": {p: 5000.0 for p in periodos},
        "ripte": {p: 20000.0 for p in periodos if p != "2017-02"},
        "ipc": ipc,
    }
    return ind.combinar(canastas, series)


SEMESTRES_API = [
    {"periodo": "20232S", "tasa_pobreza_personas": 41.7, "tasa_indigencia_personas": 11.9, "observaciones": None},
    {"periodo": "20192S", "tasa_pobreza_personas": 35.5, "tasa_indigencia_personas": 8,
     "observaciones": "Los resultados del segundo semestre de 2019 no incluyen el aglomerado Gran Resistencia."},
    {"periodo": "20261S", "tasa_pobreza_personas": 32.3, "tasa_indigencia_personas": 7.5, "observaciones": "Dato provisorio"},
]

TRIMESTRES_API = [
    {"periodo": "20233T", "tasa_de_empleo": 45.5, "tasa_de_empleo_formal": None, "tasa_de_empleo_informal": None,
     "tasa_de_desocupacion": 5.7, "observaciones": None},
    {"periodo": "20262T", "tasa_de_empleo": 45, "tasa_de_empleo_formal": 24.7, "tasa_de_empleo_informal": 20.2,
     "tasa_de_desocupacion": 7.9, "observaciones": "Dato provisorio"},
]


class Formatos(unittest.TestCase):
    def test_numeros_en_formato_argentino(self):
        self.assertEqual(ind.numero(1632504.69), "1.632.505")
        self.assertEqual(ind.numero(4.2535, 2), "4,25")
        self.assertEqual(ind.pesos(383800), "$383.800")
        self.assertEqual(ind.porcentaje(0.235), "24%")

    def test_nombre_de_mes(self):
        self.assertEqual(ind.nombre_mes("2026-09"), "septiembre de 2026")

    def test_nombres_de_semestre_y_trimestre(self):
        self.assertEqual(ind.nombre_semestre("2026-S1"), "primer semestre de 2026")
        self.assertEqual(ind.nombre_trimestre("2026-T2"), "segundo trimestre de 2026")

    def test_variacion_en_palabras(self):
        self.assertEqual(ind.variacion(128.0), "se multiplicó por 128")
        self.assertEqual(ind.variacion(2.4, plural=True), "se multiplicaron por 2,4")
        self.assertEqual(ind.variacion(1.23, plural=True), "subieron 23%")
        self.assertEqual(ind.variacion(0.9), "bajó 10%")


class IndicePrecios(unittest.TestCase):
    def filas(self, *periodos):
        return [{"periodo": p, "valor": 100.0 + k} for k, p in enumerate(periodos)]

    def test_interpreta_meses_seguidos(self):
        ipc = ind.interpretar_ipc(self.filas("201612", "201701", "201702"))
        self.assertEqual(ipc, {"2016-12": 100.0, "2017-01": 101.0, "2017-02": 102.0})

    def test_rechaza_un_mes_faltante(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_ipc(self.filas("201612", "201702"))

    def test_rechaza_otro_inicio(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_ipc(self.filas("201701", "201702"))

    def test_rechaza_valor_vacio(self):
        filas = self.filas("201612", "201701")
        filas[1]["valor"] = None
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_ipc(filas)


class PoderDeCompra(unittest.TestCase):
    def setUp(self):
        self.filas = datos_completos()

    def test_bases_hasta_el_ultimo_mes_con_los_tres_ingresos(self):
        self.assertEqual(ind.bases_posibles(self.filas), ["2016-12", "2017-01"])

    def test_cada_ingreso_contra_su_ultimo_mes(self):
        salario, jubilacion, ripte = ind.poder_de_compra(self.filas, "2016-12")
        self.assertAlmostEqual(salario.cobertura, 100 / 110)
        self.assertAlmostEqual(jubilacion.cobertura, 100 / 110)
        self.assertAlmostEqual(ripte.cobertura, 100 / 105)
        self.assertEqual(ripte.detalle, "RIPTE, bruto, enero de 2017")

    def test_base_sin_indice_de_precios(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.poder_de_compra(self.filas, "2016-11")

    def test_frase_cuando_la_canasta_sigue_a_los_precios(self):
        frase = ind.frase_poder(self.filas, "2016-12")
        self.assertIn("pasaron de 1,50 a 1,65", frase)
        self.assertIn("subió 10%, casi lo mismo que los precios en general, que subieron 10%", frase)
        self.assertIn("lo que compra el salario mínimo, que hoy es el 91%", frase)

    def test_frase_cuando_la_canasta_sube_mas(self):
        for fila in self.filas:
            if fila["periodo"] == "2017-02":
                fila["cbt"] *= 1.2
        frase = ind.frase_poder(self.filas, "2016-12")
        self.assertIn("la canasta subió más que el resto", frase)
        self.assertNotIn("Por eso", frase)

    def test_nota_del_bono(self):
        nota = ind.nota_bono_poder(self.filas, {"2017-02": 1000.0})
        self.assertIn("el bono de $1.000 sumaba un 20% a la mínima", nota)
        self.assertNotIn("bono de", ind.nota_bono_poder(self.filas, {}))

    def test_tabla_en_pesos_del_ultimo_mes(self):
        tabla = ind.tabla_poder_html(self.filas)
        self.assertTrue(tabla.startswith("<tr><td>febrero de 2017</td><td>110,0</td><td>$8.240</td>"))
        self.assertIn("<td>diciembre de 2016</td><td>100,0</td><td>$9.064</td>", tabla)
        self.assertNotIn("noviembre de 2016", tabla)


class PobrezaYTrabajo(unittest.TestCase):
    def test_ordena_semestres_y_marca_provisorios(self):
        semestres = ind.interpretar_pobreza(SEMESTRES_API)
        self.assertEqual([s["periodo"] for s in semestres], ["2019-S2", "2023-S2", "2026-S1"])
        self.assertTrue(semestres[-1]["provisorio"])
        self.assertEqual(
            ind.frase_pobreza(semestres),
            "En el primer semestre de 2026, un dato provisorio, el 32,3% de las personas vivía en hogares "
            "pobres y el 7,5%, en hogares indigentes.",
        )

    def test_las_notas_no_repiten_el_provisorio(self):
        notas = ind.notas_pobreza(ind.interpretar_pobreza(SEMESTRES_API))
        self.assertIn("Gran Resistencia.", notas)
        self.assertNotIn("provisorio", notas)

    def test_rechaza_indigencia_mayor_que_pobreza(self):
        filas = [dict(SEMESTRES_API[0], tasa_indigencia_personas=50)]
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_pobreza(filas)

    def test_rechaza_semestre_raro(self):
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_pobreza([dict(SEMESTRES_API[0], periodo="2023-2")])

    def test_informalidad_cada_100_ocupados(self):
        trimestres = ind.interpretar_trabajo(TRIMESTRES_API)
        self.assertIsNone(trimestres[0]["informalidad"])
        self.assertEqual(trimestres[1]["informalidad"], 44.9)
        self.assertEqual(
            ind.frase_trabajo(trimestres),
            "En el segundo trimestre de 2026, un dato provisorio, 45 de cada 100 personas ocupadas tenían "
            "un empleo informal. La desocupación era del 7,9%.",
        )

    def test_rechaza_tasas_que_no_suman(self):
        filas = [dict(TRIMESTRES_API[1], tasa_de_empleo_informal=25)]
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_trabajo(filas)

    def test_rechaza_tasa_fuera_de_rango(self):
        filas = [dict(TRIMESTRES_API[0], tasa_de_desocupacion=130)]
        with self.assertRaises(ind.DatosInvalidos):
            ind.interpretar_trabajo(filas)


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
        self.filas = datos_completos()
        self.bonos = {"2017-02": 1000.0}
        self.barras, self.bono = ind.coberturas(self.filas, self.bonos)
        self.fecha = datetime(2026, 11, 6)
        self.semestres = ind.interpretar_pobreza(SEMESTRES_API)
        self.trimestres = ind.interpretar_trabajo(TRIMESTRES_API)

    def armar(self, plantilla, filas=None):
        return ind.armar_sitio(
            plantilla, filas or self.filas, self.barras, self.bono, [], self.fecha,
            self.semestres, self.trimestres, self.bonos,
        )

    def test_plantilla_real_queda_completa(self):
        raiz = Path(__file__).resolve().parent.parent
        plantilla = (raiz / "sitio" / "plantilla.html").read_text(encoding="utf-8")
        pagina = self.armar(plantilla)
        self.assertIn("necesitó 1,65 salarios mínimos", pagina)
        self.assertIn("6 de noviembre de 2026", pagina)
        self.assertIn("que hoy es el 91% de lo que compraba entonces", pagina)
        self.assertIn("45 de cada 100 personas ocupadas", pagina)
        self.assertIn('"bases":["2016-12","2017-01"]', pagina)
        self.assertNotIn("{{", pagina)

    def test_marcador_desconocido_falla(self):
        with self.assertRaises(ind.DatosInvalidos):
            self.armar("{{NO_EXISTE}}")

    def test_datos_no_cierran_el_script(self):
        semestres = [dict(s) for s in self.semestres]
        self.semestres = semestres
        pagina = self.armar("{{DATOS_JSON}}{{DATOS_SOCIALES}}")
        self.assertNotIn("</", pagina)

    def test_csv_de_pobreza_y_trabajo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ind.escribir_csv_sociales(Path(carpeta), self.semestres, self.trimestres)
            pobreza = (Path(carpeta) / "pobreza.csv").read_text(encoding="utf-8").splitlines()
            trabajo = (Path(carpeta) / "trabajo.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(pobreza[-1], "2026-S1,32.3,7.5,Dato provisorio")
        self.assertEqual(trabajo[1], "2023-T3,5.7,,")

    def test_csv_deja_vacios_los_faltantes(self):
        filas = [dict(f) for f in self.filas]
        filas[1]["ripte"] = None
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "x.csv"
            ind.escribir_csv(destino, filas)
            lineas = destino.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lineas), len(self.filas) + 1)
        self.assertIn(",,", lineas[2])
        self.assertTrue(lineas[0].endswith(",ipc_gba"))
        self.assertTrue(lineas[-1].endswith(",110.0"))


if __name__ == "__main__":
    unittest.main()
