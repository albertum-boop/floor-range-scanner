# Floor Visit Scanner — Vercel

Aplicación estática, sin dependencias de servidor. Vercel puede desplegarla directamente como proyecto **Other / Static**.

## Estrategia v3: rango validado antes de ordenar por proximidad
- Caída previa ≥12% terminada antes del inicio de la base, respecto al máximo de cierre de las 20 sesiones anteriores.
- Base de al menos 15 sesiones, 3 visitas y 15 sesiones de separación entre primera y última visita.
- El soporte se fija con las dos primeras pruebas, ambas con rebote ≥5% en 5 sesiones. No se recalcula como el mínimo de toda la ventana.
- Ningún cierre por debajo del soporte; pruebas agrupadas dentro del 3,5%; banda inferior sin deterioro superior al 3,5%.
- Amplitud del rango ≤25% y deriva del precio ≤min(8%, la mitad de la amplitud). El techo es el percentil 85 de los máximos.
- Una ruptura invalida esa base. Una base posterior debe cumplir otra vez todos los requisitos.
- `VISITANDO_SUELO` requiere cerrar dentro de la zona, además de tocarla. El score se calcula sólo tras validar el rango.
- La señal `CONFIRMACION_DIARIA` requiere contacto con soporte hoy o ayer, cierre alcista sobre el máximo anterior, proximidad ≤5% y recorrido hasta el techo ≥5%. Es una señal al cierre, sin asumir ejecución a ese precio; no se ha backtesteado. Una visita sin esa vela figura como `ESPERAR_REBOTE`.
- `REBOTE_RECIENTE` exige que el cierre haya recuperado al menos 5% desde el mínimo de la última visita; el tiempo transcurrido por sí solo no basta.
- Cada ficha incluye un gráfico diario con rango, soporte y techo. Los snapshots anteriores se ocultan mientras se recalculan.
- Son reglas de cribado explícitas, no evidencia de acumulación institucional ni un backtest de rentabilidad.

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
