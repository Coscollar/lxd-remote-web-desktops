---
name: tfg-estilo-academico
description: Reglas de redaccion academica para la memoria del TFG (registro, persona gramatical, figuras, codigo, citas, coherencia objetivos-conclusiones). Usar junto a tfg-formato-etsinf al escribir cualquier texto de la memoria.
---

# Estilo academico de la memoria

## Registro y persona

- Registro **formal y preciso**, sin coloquialismos ni marketing ("potente",
  "increible", "facilisimo" → fuera). Afirmaciones medibles o citadas.
- **3a persona / impersonal** ("se ha desarrollado", "el sistema permite").
  Excepcion admitida: la *motivacion personal* de la Introduccion puede ir
  en 1a persona del singular.
- Tiempos: pasado para lo realizado ("se implemento"), presente para lo que
  el sistema hace ("el orquestador lanza"), condicional/futuro solo en
  Trabajos futuros.
- Escribir para un **informatico no especialista**: definir la jerga la
  primera vez y remitir al glosario. Si un parrafo solo lo entiende quien
  ya conoce el proyecto, reescribirlo.
- La Introduccion puede usar prosa mas ligera que motive a seguir leyendo;
  el resto, rigor tecnico.

## Elementos visuales y codigo

- Toda figura/tabla: **numerada, con pie descriptivo y citada en el texto**
  ("como muestra la Figura 4.2..."). Nada de figuras huerfanas.
- Diagramas con notacion estandar cuando exista (UML de casos de uso,
  componentes, despliegue, clases; diagramas de bloques para topologia).
- Codigo fuente: **solo fragmentos** relevantes/criticos, en tipografia
  monoespaciada, comentados en el texto o en el propio codigo. Volumen
  grande de codigo → anexo o referencia al repositorio.
- Comandos y salidas de terminal: bloque monoespaciado, recortados a lo
  esencial.
- Declarar las convenciones tipograficas en Introduccion→Convenciones y
  respetarlas en toda la obra (p.ej.: codigo en `courier` cursiva,
  extranjerismos en *cursiva*, citas textuales "entrecomilladas").

## Citas y notas

- Cita en el texto para toda afirmacion no evidente que venga de una
  fuente; la fuente entra en Referencias (ISO 690-2010 o el formato fijado
  con el tutor).
- URLs de productos/fabricantes y videos → **nota al pie** la primera vez.
- Nunca inventar referencias: si no se ha localizado la fuente, no se cita.

## Coherencia estructural (lo que mas valora el tribunal)

- **Objetivos ↔ Resultados ↔ Conclusiones** deben ser trazables uno a uno.
  Cada objetivo declarado en la Introduccion se retoma en Conclusiones
  indicando si se alcanzo y donde se demuestra.
- La Metodologia declarada debe corresponderse con la estructura real de
  los capitulos.
- Cada capitulo abre con 2-4 lineas que anuncian su contenido y cierra
  enlazando con el siguiente.
- No repetir contenido entre capitulos: resumir y remitir con referencia
  cruzada ("vease el Capitulo 5").

## Honestidad tecnica

- Documentar tambien **lo que no funciono**, las limitaciones y las deudas
  tecnicas: en un TFG suma, no resta (demuestra criterio de ingeniero).
- Las cifras (paginas, GB, numero de alumnos soportados, tiempos) deben
  salir del proyecto real o de una fuente citada, nunca estimarse sin
  declararlo.
- Todo contenido debe ser original o citado: la memoria pasa Turnitin.
