# Monitor del bolsillo

Página pública que muestra cuánto cuesta la canasta básica y cuánto tiempo de trabajo o de jubilación hace falta para pagarla. La primera versión usa indicadores oficiales; el archivo de precios se está juntando para sumar más adelante una canasta estimada en vivo.

## Página e indicadores

[`pipeline/indicadores.py`](pipeline/indicadores.py) baja los datos, los valida y arma el sitio a partir de [`sitio/plantilla.html`](sitio/plantilla.html). Una tarea de GitHub Actions lo corre todos los días y publica el resultado en GitHub Pages. Si un dato no pasa las validaciones, la tarea falla y la página anterior sigue publicada.

```bash
python pipeline/indicadores.py --salida _site
```

Necesita el token de la API del INDEC como variable `INDEC_TOKEN` o en un archivo `.env`.

| Dato | Fuente |
| --- | --- |
| Canasta básica | API del INDEC, `valorizacion_canastas_cba_cbt` |
| Salario mínimo | datos.gob.ar, Secretaría de Trabajo |
| Jubilación mínima | datos.gob.ar, ANSES |
| RIPTE | datos.gob.ar, Secretaría de Trabajo |
| Bono de jubilados | Carga manual en [`datos/bonos.csv`](datos/bonos.csv) |

**Tareas a mano:**

- **Bono:** agregar el monto de cada mes en `datos/bonos.csv`. Si falta, la página muestra la jubilación sin bono y la tarea avisa.
- **Correcciones:** si una fuente trae un error, se documenta en [`datos/correcciones.csv`](datos/correcciones.csv) con la fuente que lo respalda. Si el RIPTE baja respecto del mes anterior, la tarea descarta ese valor y avisa, para revisarlo.
- **Token:** el del INDEC vence a los 12 meses y se guarda como secreto `INDEC_TOKEN` en GitHub.

## Archivador de SEPA

La base SEPA publica un ZIP por día de la semana y cada uno reemplaza al de la semana anterior: lo que no se guarda en 7 días se pierde. [`pipeline/sepa_archivador.py`](pipeline/sepa_archivador.py) guarda los días nuevos y una tarea de GitHub Actions lo corre dos veces por día.

```bash
pip install -r requirements.txt
```

```bash
python pipeline/sepa_archivador.py --salida archivo
```

```bash
python -m unittest discover -s tests
```

### Qué guarda

| Archivo | Contenido | Dónde queda |
| --- | --- | --- |
| `productos_AAAA-MM-DD.parquet` | Precios de GBA ampliado y Mar del Plata, como texto y sin interpretar | Release mensual `sepa-AAAA-MM` |
| `sucursales_AAAA-MM-DD.parquet` | Todas las sucursales del país, con su zona | Release mensual `sepa-AAAA-MM` |
| `AAAA-MM-DD.json` | Origen del archivo, conteos por cadena y alertas | `archivo/manifiestos/`, en el repositorio |

Si existe el manifiesto de una fecha, sus datos se terminaron de escribir.

### Criterios

- **Zonas:** se definen por distancia, porque el campo de provincia tiene errores. GBA ampliado es un radio de 60 km desde el Obelisco y Mar del Plata, de 30 km desde el centro. El recorte a CABA y 24 partidos queda para la etapa de cálculo.
- **`zona = sin_sucursal`:** precios de una sucursal que no figura en el archivo de sucursales de esa cadena. Se conservan porque podrían ser de una de las zonas.
- **Sucursales `Web`:** se archivan, pero hay que decidir si se excluyen de los cálculos.
- **Precios:** se guardan como vienen, incluidos los absurdos. Filtrarlos es tarea de la etapa de cálculo.
- **Estado `parcial`:** alguna cadena vino vacía o no se pudo leer. El resto del día se guarda igual y, si la fuente publica un archivo corregido, se reprocesa. El comercio 36 vino vacío en los siete días de la primera carga, así que por ahora todos los días figuran como parciales.
- **Cadenas que van y vienen:** Farmacity, por ejemplo, está unos días sí y otros no, y esas ausencias mueven los promedios generales. Los cálculos tienen que comparar un conjunto fijo de cadenas y productos, y excluir las que no venden alimentos.

### Puesta en marcha en GitHub

Los Parquet de la primera carga están solo en esta computadora, porque el repositorio guarda los manifiestos pero no los datos. Hay que subirlos a mano una vez; si no, los manifiestos van a indicar que esas fechas ya están archivadas y no se van a volver a procesar. Después de crear el repositorio y subir el código:

```bash
gh auth login
```

```bash
for carpeta in archivo/datos/*/; do mes=$(basename "$carpeta"); gh release create "sepa-$mes" --title "Base SEPA $mes" --notes "Precios de SEPA filtrados por zona. Fuente: Precios Claros, CC-BY 4.0."; gh release upload "sepa-$mes" "$carpeta"*.parquet --clobber; done
```

Conviene correr la tarea una vez a mano desde la pestaña Actions, para confirmar que los sitios oficiales responden desde los servidores de GitHub.

Fuente de los datos: [Precios Claros — Base SEPA](https://datos.produccion.gob.ar/dataset/sepa-precios), licencia CC-BY 4.0.
