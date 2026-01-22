# Beer Scrapping CLI

Buscador interactivo de promociones de cerveza en supermercados de Argentina.

## Requisitos

- Python 3.10+
- Dependencias:

```bash
python3 -m pip install -r requirements.txt
playwright install chromium
```

## Uso

```bash
python3 beer_scraper.py
```

Ingresá la marca cuando se te solicite y el script mostrará promociones (con descuento o etiqueta promocional) para cada sitio.

## Sitios soportados

- Coto Digital (cotodigital.com.ar)
- Vea
- Jumbo
- Disco
- DIA Online
- Carrefour (carrefour.com.ar)

## Notas

- La integración con Coto usa Playwright para cargar el HTML dinámico.
- Los sitios basados en VTEX (Vea, Jumbo, Disco y DIA) se consultan usando su API pública.
- Si un sitio cambia su estructura, puede ser necesario ajustar los selectores en `beer_scraper.py`.
