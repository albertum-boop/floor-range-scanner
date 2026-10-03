# Floor Visit Scanner - modelo auditado

Aplicación estática para Vercel. El clasificador v9 procede del barrido de 2.430
series hasta el 25/09/2026 y reemplaza el detector v8 basado en las dos
primeras pruebas. El núcleo `scanner/audited_model.py` es una copia exacta del
modelo congelado tras la auditoría (SHA256
`4ea487270d818fe6ea851464cbe0e80bf6a24395570f18748d095d93bd686003`).
`scanner/scanner.py` adapta su salida a la web y publica únicamente rangos con
una observación calculada **en la sesión de corte**. No reactiva rangos antiguos
por su estado interno `recent`.

## Qué clasifica

- Busca una caída de al menos 12% desde el pico previo y una base reciente.
- Identifica una banda modal de mínimos visitada tres o más veces, con dos
  rebotes observados de al menos 3,5% en cierre. Distingue el mínimo de la
  base de la zona habitual: MUSA tiene 501,12-506,01 frente al mínimo 490,29
  en la comprobación del 25/09.
- Fecha mechas recuperadas, cierres bajo soporte recuperados y contactos
  inferiores repetidos. Los eventos anteriores a la primera visita de la
  base se excluyen como dips del rango. Un contacto inferior repetido no se
  presenta como dip aislado.
- Invalida un suelo tras un cierre más de 3% bajo el borde inferior o dos de
  los últimos tres cierres más de 1% bajo ese borde. Un cierre bajo el borde
  sin ruptura queda como `PENETRACION_PENDIENTE`.
- Excluye ventanas con saltos de ajuste, huecos largos o barras extremas.
  La detección es estructural y exploratoria: no es un backtest de retornos
  con entradas, stops y salidas.

La pantalla muestra zona habitual, mínimo desde la primera visita, tipo de
incursión inferior, fecha de detección, cierre, distancia, visitas y gráfico.
La puntuación de evidencia es heurística; no es una probabilidad calibrada.

## Datos y actualización

`.github/workflows/daily-refresh.yml` ejecuta `scripts/refresh_data.py` cada
día a las 02:00 de Europe/Madrid y repite a las 06:23 si hace falta. Selecciona
la última sesión NYSE cerrada, descarga 400 días naturales de OHLCV (incluido
Adj Close para el filtro de ajustes), valida el 95% del universo y genera
`public/data/current.json` y `current.csv`. El escáner se ejecuta en GitHub,
no en Vercel; los commits de datos publican la página estática. Cambios en
`scanner/**` vuelven a ejecutar el flujo. Puede forzarse manualmente desde
GitHub Actions.

Para repetir la auditoría local con el ZIP de precios:

```bash
python -m pip install -r scanner/requirements.txt
python -m unittest discover -s tests -v
python scanner/scanner.py --source /ruta/a/prices.zip --as-of 2026-09-25 --out /tmp/current.json
```

Para la web, `npm run build` copia `public/` a `dist/`. En Vercel: framework
**Other**, raíz `./`, comando `npm run build` y directorio de salida **dist**.
El fichero `vercel.json` explicita estas opciones. Si los ajustes del proyecto
Vercel sobrescriben el directorio de salida, deben concordar con `dist`.

Repositorio: https://github.com/albertum-boop/floor-range-scanner
