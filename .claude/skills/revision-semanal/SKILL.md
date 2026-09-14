---
name: revision-semanal
description: Repaso semanal del repositorio (viernes) con foco en que los horarios de las bibliotecas sigan coincidiendo con su fuente oficial. Ejecuta las comprobaciones, interpreta los avisos y redacta un informe corto. No commitea ni arregla nada por su cuenta.
---

# Revisión semanal

Objetivo: comprobar en 5 minutos que la web sigue publicando horarios ciertos, y avisar
en cuanto deje de ser así. **Es una revisión de solo lectura**: no se commitea, no se
hace push y no se toca `calendario.json`. Si hay que arreglar algo, se propone en el
informe y decide el propietario.

## 1. Preparar

```bash
cd <raíz del repo>
git fetch origin main && git checkout main && git pull origin main
python -c "import PIL" 2>/dev/null || pip install pillow   # lo importa test_build.py
```

## 2. Ejecutar el chequeo

```bash
python .claude/skills/revision-semanal/comprobar.py
```

Sale `0` si todo correcto, `1` si hay avisos, `2` si hay fallos. Comprueba:

| Comprobación | Qué caza |
|---|---|
| Calendario vigente | `calendario.json` de un año vencido: en enero **bloquea el despliegue** (`build.sh`) |
| Frescura de fuentes | `source.checked_at` envejecido (aviso a los 35 días, fallo a los 120) |
| Auditoría | centros marcados `!!`: el horario guardado ya no es el que dice la fuente |
| Avisos de interpretación | líneas de horario que el auditor no sabe leer (descontando los `solo_url`, que son de diseño) |
| Build | que lo commiteado sea lo que genera `build.py` (alguien tocó `index.html` sin regenerar) |
| Meses de horarios | los 12 `horarios/AAAA-MM.json`, sin los cuales el despliegue aborta |
| Tests | `python -m unittest test_build` |
| Web publicada | `bibliotecasmadrid.es` responde y sirve el mismo calendario del mes que el repo |
| BiblioAgenda | la API de UAM/UCM, de la que 24 fichas sacan su horario en vivo |

## 3. Interpretar lo que salga

Antes de sacar conclusiones, lee la sección "Horarios y fuentes oficiales" de `AGENTS.md`.

- **Centro marcado `!!`** — mira su bloque en `python auditar_horarios.py --informe` y
  compara la línea `calendario:` con la `oficial:`. Dos causas distintas:
  1. el centro **cambió su horario** y `source.texto` está viejo: hay que volver a la
     página oficial, copiar el bloque de horario y aplicarlo con `--fuentes f.json
     --aplicar`;
  2. el auditor **interpreta mal** una frase (ya pasó con «de Jueves Santo a Domingo de
     Resurrección», que cerraba todos los jueves). Aquí el arreglo es del parser, no de
     los datos. Distínguelas leyendo el `source.texto` que imprime el informe: si el
     texto sigue diciendo lo mismo que el calendario, el fallo es del parser.
  No apliques ningún cambio de horario sin haber visto la página oficial: un horario mal
  deducido es peor que uno sin tocar.
- **`Arbol de trabajo con cambios sin commitear`** — la comprobación de build se salta
  para no pisar nada. Míralo con `git status` y repite si procede.
- **`La web sirve un calendario distinto`** — o hay un despliegue pendiente en Cloudflare
  Pages, o la caché de borde sigue sirviendo lo viejo. Comprueba el último commit de
  `main` y la hora del último despliegue.
- **Fuentes envejecidas** — madrid.es bloquea a los scripts (Akamai da 403), así que el
  texto hay que extraerlo desde un navegador de verdad. Si no puedes, deja dicho en el
  informe qué centros tocan.

Fechas que conviene mirar sin que las cace el script:

- **Cambios de temporada** (mediados de junio, mediados de septiembre, Navidad, Semana
  Santa): es cuando los centros publican horarios nuevos y cuando la web se equivoca.
- **UNED**: publica solo la temporada en curso; su `#:~:text=` deja de resaltar al pasar
  el verano y toca reauditar las tres fichas de la Sede Central.
- **Noviembre y diciembre**: hay que preparar el `calendario.json` del año siguiente
  (festivos regionales y municipales) antes del 1 de enero.

## 4. Informe

Un informe corto en castellano, sin adornos:

1. veredicto en una línea (todo en orden / N cosas que mirar);
2. los fallos y avisos, uno por línea, con el centro o archivo concreto y qué habría que
   hacer;
3. lo que has verificado a mano más allá del script, si es que has verificado algo.

Si todo sale correcto, dilo en dos líneas y termina. No hace falta adjuntar la salida
entera del script.
