# Floor Visit Scanner — Vercel

Aplicación estática, sin dependencias de servidor. Vercel puede desplegarla directamente como proyecto **Other / Static**.

## Estrategia
- `F`: mínimo estructural del rango detectado.
- Zona de visita: `F` a `F × 1.035`.
- Días consecutivos en zona cuentan como una sola visita.
- Para contar una visita nueva, el precio debe separarse antes al menos un 5% del suelo.
- Se registran número de visitas, densidad temporal, rebotes >=5%, proximidad actual y un SL de referencia situado por debajo del mínimo observado.
- SES, APP y SGI se muestran como benchmarks del patrón.

## Datos
`public/data/current.json` contiene la última sesión publicada. El snapshot inicial del 25/09/2026 tenía 428 patrones obtenidos sobre 564 candidatos prefiltrados de 2.430 series. La actualización automática examina el universo completo de 2.438 símbolos (acciones y ETF), tomado de `mtr-swing-retest-scanner/config/ticker_database.json`. Por eso el número de patrones puede cambiar respecto a la selección inicial.

## Despliegue
Importar la carpeta/repo en Vercel. No necesita variables de entorno ni paquetes externos. La compilación copia y valida los archivos estáticos.

Repositorio: https://github.com/albertum-boop/floor-range-scanner

1. En Vercel, crear un proyecto e importar este repositorio de GitHub.
2. Framework Preset: **Other**. Root Directory: **./**.
3. Build Command: **npm run build**. Install Command: vacío. Output Directory: **dist**.
4. Pulsar **Deploy**. Los cambios posteriores en `main` se publicarán mediante la integración de GitHub.

## Actualizar datos

GitHub Actions ejecuta `.github/workflows/daily-refresh.yml` todos los días a las **02:00 de Europe/Madrid**, ajustando el cambio de hora. Puede empezar con retraso si GitHub tiene cola. El calendario NYSE selecciona la última sesión cerrada y espera hasta las 18:00 de Nueva York para darla por finalizada. Si esa sesión ya está publicada, no vuelve a descargarla; fines de semana y festivos no generan sesiones ficticias.

El proceso descarga 400 días naturales de OHLCV de Yahoo Finance, vuelve a calcular rangos, suelos y revisitas, y guarda JSON y CSV en un commit. La integración Git de Vercel publica ese commit automáticamente. No necesita una API key ni un token de Vercel. La descarga se ejecuta en GitHub, no al abrir la página. Una pestaña abierta comprueba nuevas publicaciones cada 15 minutos y al volver a ella.

Se validan las velas y su fecha. Las series sin la última sesión, con menos de 60 velas o con huecos en las últimas 60 sesiones se excluyen y constan en `quality` dentro del JSON. Si menos del 95% del universo supera la validación, el workflow falla y conserva la publicación anterior. Los reintentos sólo repiten símbolos fallidos. Se redescarga la ventana completa para incorporar correcciones históricas y splits; se mantiene `auto_adjust=False` como en los históricos originales.

Para revisar o lanzar una actualización: **GitHub → Actions → Daily floor scanner → Run workflow**. La opción `force` permite regenerar la última sesión para recoger correcciones del proveedor. El workflow también se ejecuta al cambiar el motor, el universo o su configuración. La fecha de cierre, hora de actualización y cobertura se muestran en la web.

```bash
python -m pip install -r scanner/requirements.txt
python -m unittest discover -s tests -v
python scripts/refresh_data.py
```

El estado «Visitando suelo» identifica un contacto con soporte, no una entrada confirmada.
La proporción de rebotes es una estadística histórica, no una probabilidad de éxito futura.

También se pueden regenerar los archivos manualmente desde un directorio de CSV OHLCV diarios o un ZIP:

```bash
python -m pip install -r scanner/requirements.txt
python scanner/scanner.py --source /ruta/a/prices.zip --config scanner/config.json --out public/data/current.json
```

El comando vuelve a examinar toda la fuente suministrada. El corte incluido en esta entrega
se obtuvo sobre 564 candidatos prefiltrados, por lo que un barrido completo puede cambiar el universo.
Después de actualizar, subir `public/data/current.json` y `public/data/current.csv` al repositorio.

## Configuración estática explícita

`vercel.json` fija `framework: null` (Other), omite la instalación y ejecuta `npm run build`, que valida y copia `public/` a `dist/`. El escáner Python de `scanner/` se ejecuta fuera del servidor web para preparar los datos; no es una función ni necesita un entrypoint HTTP.

Para revisar la web localmente: `python -m http.server 8000 --directory public`.
