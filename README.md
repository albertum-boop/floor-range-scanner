# Floor Visit Scanner — Vercel

Aplicación estática, sin dependencias ni build step. Vercel puede desplegarla directamente como proyecto **Other / Static**.

## Estrategia
- `F`: mínimo estructural del rango detectado.
- Zona de visita: `F` a `F × 1.035`.
- Días consecutivos en zona cuentan como una sola visita.
- Para contar una visita nueva, el precio debe separarse antes al menos un 5% del suelo.
- Se registran número de visitas, densidad temporal, rebotes >=5%, proximidad actual y un SL de referencia situado por debajo del mínimo observado.
- SES, APP y SGI se muestran como benchmarks del patrón.

## Datos
`data/current.json` contiene el snapshot con cierre 25/09/2026. El universo original tiene 2.430 tickers; el detector de revisitas se aplicó sobre el prefiltrado estructural del proyecto anterior y produjo 428 patrones.

## Despliegue
Importar la carpeta/repo en Vercel. No necesita variables de entorno, paquetes npm ni comando de build.

Repositorio: https://github.com/albertum-boop/floor-range-scanner

1. En Vercel, crear un proyecto e importar este repositorio de GitHub.
2. Framework Preset: **Other**. Root Directory: **./**.
3. Dejar Build Command e Install Command vacíos; servir la raíz del proyecto.
4. Pulsar **Deploy**. Los cambios posteriores en `main` se publicarán mediante la integración de GitHub.

## Actualizar datos

La web muestra un corte guardado; no descarga precios ni genera señales nuevas automáticamente.
El estado «Visitando suelo» identifica un contacto con soporte, no una entrada confirmada.
La proporción de rebotes es una estadística histórica, no una probabilidad de éxito futura.

Para regenerar los archivos desde un directorio de CSV OHLCV diarios o un ZIP:

```bash
python -m pip install -r scanner/requirements.txt
python scanner/scanner.py --source /ruta/a/prices.zip --config scanner/config.json --out data/current.json
```

El comando vuelve a examinar toda la fuente suministrada. El corte incluido en esta entrega
se obtuvo sobre 564 candidatos prefiltrados, por lo que un barrido completo puede cambiar el universo.
Después de actualizar, subir `data/current.json` y `data/current.csv` al repositorio.
