---
name: Monitor del bolsillo
description: La canasta básica medida en salarios, con formas proporcionales y datos oficiales.
colors:
  verde: "#0B5A49"
  verde-osc: "#07382E"
  verde-medio: "#37937A"
  menta: "#9BE8CC"
  menta-suave: "#D8F5EA"
  celda-vacia: "rgba(255,255,255,.1)"
  tinta: "#10211D"
  tinta-2: "#46574F"
  linea: "#D9E2DD"
  fondo: "#FFFFFF"
  fondo-2: "#F2F6F4"
typography:
  display:
    fontFamily: "Bricolage Grotesque, Libre Franklin, sans-serif"
    fontSize: "clamp(38px,5.2vw,74px)"
    fontWeight: 800
    lineHeight: 1.04
    letterSpacing: "-.02em"
  headline:
    fontFamily: "Bricolage Grotesque, Libre Franklin, sans-serif"
    fontSize: "clamp(30px,3.6vw,48px)"
    fontWeight: 800
    lineHeight: 1.04
    letterSpacing: "-.02em"
  title-lg:
    fontFamily: "Bricolage Grotesque, Libre Franklin, sans-serif"
    fontSize: "26px"
    fontWeight: 800
    lineHeight: 1.04
    letterSpacing: "-.02em"
  title:
    fontFamily: "Bricolage Grotesque, Libre Franklin, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: 1.04
    letterSpacing: "-.02em"
  numeral:
    fontFamily: "Bricolage Grotesque, sans-serif"
    fontSize: "clamp(15px,1.5vw,20px)"
    fontWeight: 700
  lead:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "clamp(17px,1.5vw,20px)"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  quote:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "clamp(18px,1.6vw,21px)"
    fontWeight: 500
    lineHeight: 1.4
    fontFeature: "tnum"
  body:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  body-sm:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  label:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.5
    fontFeature: "tnum"
  note:
    fontFamily: "Libre Franklin, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
rounded:
  xs: "2px"
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  gutter: "clamp(16px,4vw,64px)"
  section: "clamp(44px,6vw,80px)"
  cell-gap: "4px"
  stack-sm: "12px"
  stack-md: "18px"
  stack-lg: "22px"
components:
  button-primary:
    backgroundColor: "{colors.verde}"
    textColor: "{colors.fondo}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.verde-osc}"
  button-secondary:
    backgroundColor: "{colors.fondo}"
    textColor: "{colors.verde}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
    height: "46px"
  button-secondary-hover:
    backgroundColor: "{colors.menta-suave}"
  selector-tray:
    backgroundColor: "{colors.fondo-2}"
    rounded: "{rounded.lg}"
    padding: "4px"
  selector-option:
    textColor: "{colors.tinta}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
    height: "44px"
  selector-option-hover:
    backgroundColor: "{colors.linea}"
  selector-option-pressed:
    backgroundColor: "{colors.verde}"
    textColor: "{colors.fondo}"
  select-field:
    backgroundColor: "{colors.fondo}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
    height: "46px"
  quote-panel:
    backgroundColor: "{colors.menta-suave}"
    typography: "{typography.quote}"
    rounded: "{rounded.lg}"
    padding: "24px"
  tooltip:
    backgroundColor: "{colors.tinta}"
    textColor: "{colors.fondo}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  strip-cell:
    backgroundColor: "{colors.celda-vacia}"
    textColor: "{colors.verde-osc}"
    typography: "{typography.numeral}"
    rounded: "{rounded.sm}"
    height: "clamp(46px,5.8vw,78px)"
  strip-fill-total:
    backgroundColor: "{colors.menta}"
  strip-fill-alimentos:
    backgroundColor: "{colors.fondo}"
  bar-income:
    backgroundColor: "{colors.verde}"
    height: "40px"
  bar-bonus:
    backgroundColor: "{colors.verde-medio}"
    height: "40px"
---

# Design System: Monitor del bolsillo

## Overview

**Creative North Star: "El salario como regla"**

El sistema mide con formas: un cuadro es un salario, el largo de una barra es una parte de la canasta, una línea marca el punto en que el ingreso alcanza justo. El número siempre está, pero la forma lo explica antes de que se lo lea. La terminación apunta a los gráficos de Our World in Data y The Economist: pocos colores, rótulos directos sobre el dato y notas al pie que dicen de dónde sale cada cifra.

El mundo es una franja de verde profundo con cuadros menta y blancos, sobre un cuerpo blanco y gris verdoso. La densidad es de lectura, no de panel: secciones anchas con un solo gráfico o argumento por banda, anchos de texto acotados y notas pequeñas pero legibles al pie de cada dato. Los titulares tienen peso y escala; todo lo demás es sobrio.

La página rechaza el tablero de tarjetas iguales con un número cada una y evita los colores asociados con espacios políticos.

**Key Characteristics:**
- Formas proporcionales como lenguaje principal; los números las rotulan.
- Una sola familia de verdes para todos los datos.
- Bandas de color a todo el ancho en lugar de tarjetas flotantes.
- Superficies planas, sin sombras que eleven nada.
- Cifras tabulares en toda la página.
- Un solo movimiento coreografiado: los cuadros que se llenan al cargar.

## Colors

Una familia de verdes que va del casi negro a la menta clara, con neutros apenas teñidos de verde y sin ningún color de acento ajeno a esa familia.

### Primary
- **Verde Profundo** (#0B5A49): la franja inicial, la línea y los puntos del gráfico histórico, las barras de ingreso, el botón principal y la opción elegida del selector. El blanco sobre este verde da 8,16:1.
- **Verde Noche** (#07382E): el pie de página, el hover del botón principal, los números dentro de los cuadros y el texto seleccionado.
- **Verde Medio** (#37937A): solo para el tramo del bono, en las barras y en su leyenda. No tiene variable propia en el código; se usa como valor directo en esas dos piezas.

### Secondary
- **Menta** (#9BE8CC): el relleno de los cuadros de la canasta total y el fondo de la selección de texto.
- **Menta Suave** (#D8F5EA): el texto secundario sobre la franja verde y sobre el pie, el área bajo la línea del gráfico, el panel de la cita y el hover del botón secundario.
- **Cuadro Vacío** (rgba(255,255,255,.1)): la base de cada cuadro, visible donde todavía no hay relleno. Muestra el largo total de la tira y no transmite un dato por sí sola.

### Neutral
- **Tinta** (#10211D): el texto principal, los titulares, el eje base, la línea del 100%, la guía del gráfico, el contorno de foco y el fondo de la etiqueta flotante.
- **Tinta Suave** (#46574F): las introducciones, las notas, las etiquetas de los ejes y los detalles bajo el nombre de cada barra. Da 7,67:1 sobre blanco y 7,04:1 sobre el gris verdoso.
- **Línea** (#D9E2DD): los filetes de tablas y listas, el borde de la caja de la tabla y el hover de las opciones del selector.
- **Blanco** (#FFFFFF): el fondo de las bandas de lectura, el texto sobre verde y el relleno de los cuadros de la canasta de alimentos.
- **Gris Verdoso** (#F2F6F4): el fondo de las bandas alternas, la bandeja del selector y el encabezado de la tabla.

### Named Rules

**The Una Sola Familia Rule.** Todo dato se dibuja en verde. Tinta queda para ejes y líneas de referencia; el blanco distingue la canasta de alimentos solo dentro de la franja verde. Cualquier serie nueva se resuelve dentro de esta familia, no con un tono nuevo.

**The Sin Bandera Rule.** Se evitan los colores asociados con espacios políticos, en datos, fondos y detalles. La paleta tiene que poder mostrar a cualquier gobierno o período con el mismo tratamiento.

## Typography

**Display Font:** Bricolage Grotesque (con Libre Franklin y sans-serif de respaldo)
**Body Font:** Libre Franklin (con system-ui y sans-serif de respaldo)

**Character:** Bricolage pone la voz, ancha y con carácter, a escala de titular de diario. Libre Franklin es la voz de la lectura y de los datos: clara a tamaños chicos y con la seriedad de una tipografía de prensa.

### Hierarchy
- **Display** (800, clamp(38px,5.2vw,74px), 1.04): el titular con el dato del mes. Ancho máximo de 21ch.
- **Headline** (800, clamp(30px,3.6vw,48px), 1.04): el título de cada sección. Ancho máximo de 24ch.
- **Title Grande** (800, 26px, 1.04): el título de una columna lateral, como los límites antes de citar.
- **Title** (800, 22px, 1.04): subtítulos dentro de una sección. El nombre del sitio usa este tamaño con un tracking de -.01em.
- **Numeral** (700, clamp(15px,1.5vw,20px)): los números dentro de los cuadros.
- **Lead** (400, clamp(17px,1.5vw,20px), 1.5): la bajada de la franja verde. Máximo de 62ch.
- **Quote** (500, clamp(18px,1.6vw,21px), 1.4): la frase lista para citar.
- **Body** (400, 17px, 1.5): la lectura general y las introducciones de sección. Máximo de 66ch.
- **Body Chico** (400, 16px, 1.5): metodología y listas de límites. Máximo de 64ch.
- **Label** (600, 15px): navegación, opciones del selector, etiquetas de campo y encabezados de tabla. Las celdas de tabla y la leyenda usan este tamaño a peso 400.
- **Note** (400, 14px, 1.5): notas de fuente, detalles de cada barra, rótulos del gráfico y leyenda de la tabla. Máximo de 80ch.

Los títulos llevan `text-wrap: balance` y tracking de -.02em. Las mayúsculas sostenidas no se usan.

### Named Rules

**The Cifras Parejas Rule.** Toda la página usa cifras tabulares (`font-variant-numeric: tabular-nums`) para que las columnas y los valores que cambian no bailen.

**The Dos Voces Rule.** Bricolage es para títulos, el nombre del sitio y los números dentro de los cuadros. Todo lo que se lee de corrido, se compara o se opera va en Libre Franklin.

## Layout

Una columna central de hasta 1280px con un margen lateral fluido, dentro de bandas de color que ocupan todo el ancho. El bloque vertical de cada sección también es fluido. No hay barra fija: la navegación vive en la franja inicial y las anclas llevan a cada banda.

La secuencia de fondos es franja verde, blanco y gris verdoso alternados, y cierre en verde noche. El contenido se apila con separaciones de 12, 18 y 22px, más algunos valores cercanos; el ritmo es óptico, no una escala estricta. Los filetes de 1px y los fondos de banda ordenan más que las cajas.

Las composiciones de dos columnas son pocas y concretas: nombre y barra (hasta 300px y el resto, con 28px entre ambos), cita y límites (3fr y 2fr), metodología (columnas automáticas de al menos 300px). El gráfico histórico ocupa todo el ancho, con una altura de entre 290 y 430px proporcional al ancho.

Debajo de 760px todo pasa a una columna. Las opciones del selector se reparten en partes iguales a lo ancho, y la línea del 100%, que en escritorio es una sola para todas las barras, pasa a repetirse en cada barra con su propio rótulo. Con el gráfico por debajo de 600px, las etiquetas de los años se muestran cada tres y se achican los márgenes.

### Named Rules

**The Bandas Rule.** Una sección nueva se separa de la anterior cambiando el fondo de toda la banda, no encerrándola en una tarjeta.

## Elevation & Depth

El sistema es plano. La profundidad se comunica con el cambio de fondo entre bandas y con filetes de 1px; ninguna superficie proyecta sombra, ni en reposo ni al pasar el puntero. La etiqueta flotante del gráfico se separa por su fondo oscuro. Existen dos usos de `box-shadow`, y ninguno eleva: dibujan un contorno.

### Shadow Vocabulary
- **Contorno del botón secundario** (`box-shadow: inset 0 0 0 2px var(--verde)`): da el borde de 2px sin alterar la medida del botón.
- **Halo de la línea del 100%** (`box-shadow: 0 0 0 1px var(--fondo-2)`): separa la línea de tinta de las barras verdes que cruza, donde sola se perdería.

### Named Rules

**The Plano Rule.** Nada flota. Una sombra solo se admite si dibuja un contorno de ancho exacto y sin difuminar.

## Shapes

Esquinas apenas curvas, siempre chicas, en cuatro pasos: 2px para la muestra de la leyenda, 4px para cuadros y final de barra, 6px para botones, campos, opciones, etiqueta flotante y caja de tabla, 8px para los contenedores blandos, como la bandeja del selector y el panel de la cita. El contenedor lleva el radio mayor y lo que tiene adentro, el menor. No hay formas de píldora ni círculos, salvo los puntos del gráfico. Los bordes visibles son de 2px en verde en los controles y de 1px en Línea en la información.

### Named Rules

**The Base Recta Rule.** Una barra arranca a escuadra desde su base y redondea solo el final, a 4px. El tramo del bono se separa del ingreso con un espacio de 2px, que es lo que distingue a dos verdes cercanos.

## Components

### Buttons
Compactos y seguros, con una sola acción fuerte por bloque.
- **Shape:** esquinas suaves (6px), altura mínima de 46px, texto 600 a 16px.
- **Primary:** fondo Verde Profundo con texto blanco; padding de 10px y 18px.
- **Hover / Focus:** pasa a Verde Noche, sin transición. El foco es el global, un contorno de 3px en Tinta con 2px de separación; dentro de la franja verde el contorno es blanco.
- **Secondary:** fondo blanco, texto verde y contorno interior de 2px; al pasar el puntero, fondo Menta Suave.
- **Estado tras la acción:** copiar cambia el texto del botón por 2,5 segundos para confirmar el resultado o explicar el error.

### Selector de serie
Controla qué se dibuja en el gráfico. Es de una sola elección y expone el estado con `aria-pressed`.
- **Style:** bandeja Gris Verdoso (8px) con 4px de relleno; opciones sin fondo (6px), texto 600 a 15px, altura mínima de 44px.
- **State:** la opción elegida va en Verde Profundo con texto blanco; las demás toman fondo Línea al pasar el puntero.
- **Móvil:** opciones en partes iguales, ocupando todo el ancho, con texto de 14px y padding de 8px y 6px; la altura mínima se mantiene.

### Cards / Containers
El único panel de color es la cita.
- **Corner Style:** 8px.
- **Background:** Menta Suave.
- **Shadow Strategy:** ninguna.
- **Border:** ninguno.
- **Internal Padding:** 24px.

### Inputs / Fields
- **Style:** selector nativo con fondo blanco, contorno de 2px en Verde Profundo, 6px de radio, texto 500 a 16px y altura mínima de 46px. La etiqueta va arriba, en 600 a 15px.
- **Focus:** el contorno global de 3px en Tinta.

### Navigation
- **Style:** el nombre del sitio a la izquierda y los enlaces a la derecha, en la franja verde, texto blanco 600 a 15px y subrayado con separación de 3px. Se envuelve en dos líneas si no entra. No tiene hover propio ni estado activo.
- **Enlaces de texto:** heredan el color del texto y conservan el subrayado, con separación de 3px.

### Tira de cuadros
La pieza propia del sistema: una fila de cuadros iguales con 4px entre sí, donde cada cuadro vale una unidad del ingreso.
- **Forma:** altura fluida, 4px de radio; base Cuadro Vacío y relleno desde la izquierda.
- **Relleno:** Menta para la canasta total y blanco para la de alimentos, siempre proporcional a la fracción de unidad.
- **Rótulos:** encima, nombre con el valor a la izquierda y monto a la derecha. Cada cuadro completo lleva su número de orden en Verde Noche; el parcial no lleva ninguno.
- **Accesibilidad:** la tira entera es una imagen con una etiqueta que da los dos valores en palabras.

**The Cuadro Rule.** Un cuadro es siempre una unidad entera del ingreso que se mide, y su relleno es proporcional al dato. Si los cuadros no miden nada, son tarjetas y no pertenecen a este sistema.

**The Movimiento Único Rule.** La única animación coreografiada es el llenado de los cuadros: 0,7 segundos con `cubic-bezier(.16,1,.3,1)`, desde la izquierda, con 90ms entre un cuadro y el siguiente. Con movimiento reducido no hay ninguna animación ni transición. Los únicos otros movimientos son funcionales: el fundido de .12s de la etiqueta flotante y el desplazamiento suave hacia las anclas.

### Barras de cobertura
Comparan ingresos contra la misma línea.
- **Fila:** nombre en 700 con el detalle debajo en 14px, y a la derecha una barra de 40px de alto.
- **Barra:** ingreso en Verde Profundo y, cuando corresponde, bono en Verde Medio. El porcentaje va al final, en 700 a 16px, sobre el fondo de la banda.
- **Línea del 100%:** 2px en Tinta con su halo y un rótulo en 600 a 14px. Cruza las barras por encima y es la referencia de lectura de toda la pieza.

### Gráfico histórico
Una serie por vez, dibujada en SVG, con rótulos directos.
- **Trazo:** línea de 2,5px en Verde Profundo sobre un área Menta Suave; eje base en Tinta y guías horizontales muy pálidas, sin guías verticales.
- **Rótulos:** el último valor en 700 a 20px al lado de su punto; máximo y mínimo en 600 a 14px con un contorno blanco que los despega del fondo, salvo si están a menos de 7 meses del último dato.
- **Exploración:** con puntero, dedo o flechas del teclado, una guía vertical y un punto en Tinta marcan el mes, y la etiqueta flotante muestra su nombre y el valor. Los cambios se anuncian a lectores de pantalla.
- **Alternativa:** cada gráfico lleva debajo una nota de período y fuentes, y una tabla desplegable con todos los meses.

### Tabla de datos
- **Style:** caja con desplazamiento propio de hasta 440px de alto, borde de 1px en Línea y 6px de radio. Texto a 15px y números alineados a la derecha.
- **Encabezado:** fijo al desplazar, sobre Gris Verdoso, en peso 600.

## Do's and Don'ts

### Do:
- **Do** explicar cada dato principal con una forma proporcional y rotularla con su número.
- **Do** usar Verde Profundo (#0B5A49) para la serie o el ingreso principal y Verde Medio (#37937A) solo para un tramo que se suma a él.
- **Do** poner un período y una fuente debajo de cada gráfico, en Note (14px) y Tinta Suave.
- **Do** acompañar cada gráfico con una alternativa en texto o tabla.
- **Do** mantener alturas mínimas de 44 a 46px en los controles, también en el celular.
- **Do** usar el contorno de foco de 3px en Tinta, y en blanco dentro de la franja verde.
- **Do** separar las secciones con bandas a todo el ancho, alternando blanco (#FFFFFF) y Gris Verdoso (#F2F6F4).

### Don't:
- **Don't** armar tableros de tarjetas iguales con un número cada una. Los cuadros iguales de la tira quedan fuera de esta prohibición porque son unidades de una misma medida.
- **Don't** usar colores asociados con espacios políticos.
- **Don't** agregar un segundo tono de datos fuera de la familia de verdes.
- **Don't** usar sombras difusas ni elevar superficies al pasar el puntero. Quedan permitidos el contorno interior de 2px del botón secundario y el halo de 1px de la línea del 100%.
- **Don't** sumar animaciones de entrada o de desplazamiento. El llenado de los cuadros es la única.
- **Don't** usar Verde Medio (#37937A) para texto ni para elementos de la interfaz.
