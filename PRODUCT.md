# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: página estática publicada en GitHub Pages y actualizada por una tarea programada de GitHub Actions, sin servidores propios ni costo. Renzo dejó la elección abierta.

## Users

Periodistas que cubren economía y sociedad en Argentina y necesitan un dato confiable, con su fuente y su fecha, para citarlo o ubicarlo en contexto. Llegan buscando cómo cambió la relación entre ingresos y canasta. Organizaciones sociales, consultoras, campañas y público general pueden usar la página, pero no definen la primera versión.

## Product Purpose

Monitor del bolsillo (nombre de trabajo) muestra cuántos ingresos hacen falta para pagar la canasta básica oficial y cómo cambió esa relación desde abril de 2016. La primera versión funciona bien si una persona periodista puede recorrer esa historia, encontrar el mes o el período que necesita y salir con un dato bien entendido.

## Positioning

Expresa la canasta en ingresos, no solo en pesos: el titular es cuántos salarios mínimos hacen falta para pagarla. Se actualiza sola desde la API del INDEC y muestra los límites de cada número en el mismo lugar que el número.

## Operating Context

Se consulta durante el trabajo periodístico, a menudo con poco tiempo, en computadora y en celular. La canasta oficial se publica una vez por mes y corresponde solo al Gran Buenos Aires. El salario mínimo y la jubilación mínima no están en la API del INDEC y se bajan de datos.gob.ar. El bono se carga a mano y por ahora se apoya en notas de prensa. El RIPTE se publica con más demora, así que los períodos pueden no coincidir.

## Capabilities and Constraints

- Primera versión: canasta oficial, salario mínimo, jubilación mínima con y sin bono, RIPTE y evolución desde abril de 2016.
- Fuera de la primera versión: canasta estimada en vivo con SEPA y comparación con Mar del Plata.
- Titular confirmado: cantidad de salarios mínimos. Las horas de trabajo quedan, como mucho, como dato secundario.
- Los montos de salario, jubilación y RIPTE son brutos o tienen supuestos, y hay que decirlo donde se muestran.
- La cobertura de la jubilación depende de la tabla de adultos equivalentes y no contempla gastos propios de las personas mayores.
- Sin decidir: nombre definitivo y dominio.

## Brand Commitments

Estrictamente no partidista: muestra datos y sus límites, no opiniones.

## Evidence on Hand

- API del INDEC con la canasta de GBA desde abril de 2016, ya probada con token.
- Metodología 22 del INDEC, con la tabla de adultos equivalentes verificada contra los tres hogares que publica el organismo.
- Series oficiales en datos.gob.ar: salario mínimo, jubilación mínima y RIPTE. El RIPTE de agosto de 2026 se corrige con el informe oficial, porque la base abierta repite un valor anterior.
- Bono de jubilados: solo notas de prensa, pendiente de confirmar en el Boletín Oficial.
- No hay logos, testimonios, prensa ni casos de uso; no se inventan.

## Product Principles

- Cada número se muestra con su período, su fuente y sus límites.
- Lo que se dice tiene que poder citarse sin reinterpretarlo.
- Primero se entiende y después se explora.
- El mismo tratamiento para cualquier gobierno o período.
- Si un dato no está confirmado, no se publica como si lo estuviera.

## Accessibility & Inclusion

Tiene que leerse bien en celulares comunes y con conexiones lentas, y los gráficos necesitan una alternativa en texto o tabla.
