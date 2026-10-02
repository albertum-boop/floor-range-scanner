# Floor Visit Scanner — Vercel

Aplicación estática, sin dependencias de servidor. Vercel puede desplegarla directamente como proyecto **Other / Static**.

## Detector v8: caída seguida de rango
- La tendencia anterior puede ser alcista, bajista o lateral: no se exige una tendencia de fondo concreta.
- Caída previa ≥12% en el primer cierre de la base respecto al máximo de cierre de las 20 sesiones anteriores. Una mecha aislada no basta.
- La mediana de los cierres posteriores debe permanecer ≥8% por debajo de ese máximo; un mínimo aislado en una zona de precios alta no basta.
- Base de al menos 15 sesiones, 3 visitas y 15 sesiones de separación entre primera y última visita.
- Frecuencia sostenida: máximo 12 sesiones desde el final de una visita hasta el inicio de la siguiente durante todo el rango; al menos 3 visitas en las últimas 40 sesiones, de las cuales 2 deben haber rebotado ≥5%. Se rechazan bases apoyadas sólo en contactos antiguos y un retorno aislado.
- El soporte se fija con las dos primeras pruebas, ambas con rebote ≥5% en 5 sesiones. No se recalcula como el mínimo de toda la ventana.
- Una nueva visita independiente exige un cierre diario ≥5% por encima del suelo entre ambas pruebas; un máximo intradía no basta. El rebote mínimo→máximo se mantiene como referencia descriptiva y se informa por separado de cuántos rebotes superaron el 5% también en un cierre.
- Se tolera una mecha aislada bajo las primeras pruebas, pero dos visitas independientes con mínimos >1% inferiores invalidan el suelo.
- Ningún cierre por debajo del soporte; pruebas agrupadas dentro del 3,5%; banda inferior sin deterioro superior al 3,5%.
- Amplitud del rango ≤25% y deriva del precio ≤min(8%, la mitad de la amplitud). El techo es el percentil 85 de los máximos.
- Una ruptura invalida esa base. Una base posterior debe cumplir otra vez todos los requisitos.
- `VISITANDO_SUELO` requiere cerrar dentro de la zona, además de tocarla. La puntuación estructural se calcula sólo tras validar el rango y no incluye la distancia al suelo. Combina duración (25 puntos), extensión temporal de visitas (25), proporción de rebotes (15 intradía y 5 al cierre), lateralidad (20) y agrupación de mínimos (10). No representa probabilidad de éxito.
- La interfaz muestra por defecto todos los patrones ordenados por estructura y distingue el total de la cantidad cercana al suelo. Se puede limitar la distancia al 5% y ordenar por cercanía o número de visitas.
- La salida se limita al patrón: suelo, techo estimado, visitas, distancias, liquidez y gráfico. No se generan entradas, stops, objetivos ni juicios de valoración.
- Cada ficha incluye un gráfico diario con rango, soporte y techo. La interfaz requiere snapshots v8 para no mezclar puntuaciones de versiones anteriores.
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

GitHub Actions ejecuta `.github/workflows/daily-refresh.yml` todos los días a las **02:00 de Europe/Madrid**, con un intento de respaldo a las **06:23** por si GitHub retrasa u omite la primera ejecución. Si la sesión ya está publicada, el respaldo termina sin descargarla otra vez. El calendario NYSE selecciona la última sesión cerrada y espera hasta las 18:00 de Nueva York para darla por finalizada; fines de semana y festivos no generan sesiones ficticias.

El proceso descarga 400 días naturales de OHLCV de Yahoo Finance, vuelve a calcular rangos, suelos y revisitas, y guarda JSON y CSV en un commit. La integración Git de Vercel publica ese commit automáticamente. No necesita una API key ni un token de Vercel. La descarga se ejecuta en GitHub, no al abrir la página. Una pestaña abierta comprueba nuevas publicaciones cada 15 minutos y al volver a ella.

Se validan las velas y su fecha. Las series sin la última sesión, con menos de 60 velas o con huecos en las últimas 60 sesiones se excluyen y constan en `quality` dentro del JSON. Si menos del 95% del universo supera la validación, el workflow falla y conserva la publicación anterior. Los reintentos sólo repiten símbolos fallidos. Se redescarga la ventana completa para incorporar correcciones históricas y splits; se mantiene `auto_adjust=False` como en los históricos originales.

Para revisar o lanzar una actualización: **GitHub → Actions → Daily floor scanner → Run workflow**. La opción `force` permite regenerar la última sesión para recoger correcciones del proveedor. El workflow también se ejecuta al cambiar el motor, el universo o su configuración. La fecha de cierre, hora de actualización y cobertura se muestran en la web.

```bash
python -m pip install -r scanner/requirements.txt
python -m unittest discover -s tests -v
python scripts/refresh_data.py
```

Los estados describen la posición respecto al suelo: visitando, cerca o dentro del rango.
La proporción de rebotes es una estadística histórica, no una probabilidad de éxito futura.

También se pueden regenerar los archivos manualmente desde un directorio de CSV OHLCV diarios o un ZIP:

```bash
python -m pip install -r scanner/requirements.txt
python scanner/scanner.py --source /ruta/a/prices.zip --config scanner/config.json --out public/data/current.json
```

El comando vuelve a examinar toda la fuente suministrada. La actualización automática utiliza el universo completo configurado.
Después de actualizar, subir `public/data/current.json` y `public/data/current.csv` al repositorio.

## Configuración estática explícita

`vercel.json` fija `framework: null` (Other), omite la instalación y ejecuta `npm run build`, que valida y copia `public/` a `dist/`. El escáner Python de `scanner/` se ejecuta fuera del servidor web para preparar los datos; no es una función ni necesita un entrypoint HTTP.

Para revisar la web localmente: `python -m http.server 8000 --directory public`.
