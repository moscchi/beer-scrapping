#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


@dataclass
class ProductDeal:
    site: str
    title: str
    promotion: str
    price: str
    list_price: str
    url: str


class BaseScraper:
    name: str

    def search(self, query: str) -> List[ProductDeal]:
        raise NotImplementedError


class VtexScraper(BaseScraper):
    def __init__(self, name: str, base_url: str) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")

    def search(self, query: str) -> List[ProductDeal]:
        url = (
            f"{self.base_url}/api/catalog_system/pub/products/search"
            f"?ft={quote(query)}&_from=0&_to=9"
        )
        headers = {
            "user-agent": USER_AGENT,
            "accept": "application/json",
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        payload = response.json()
        deals: List[ProductDeal] = []
        for product in payload:
            deal = self._parse_product(product)
            if deal:
                deals.append(deal)
        return deals

    def _parse_product(self, product: dict) -> Optional[ProductDeal]:
        items = product.get("items") or []
        if not items:
            return None
        item = items[0]
        sellers = item.get("sellers") or []
        if not sellers:
            return None
        offer = sellers[0].get("commertialOffer") or {}
        if not self._is_in_stock(offer):
            return None
        price = offer.get("Price")
        list_price = offer.get("ListPrice") or price
        title = product.get("productName") or item.get("name") or "Producto"
        promotion = self._promotion_label(offer, price, list_price)
        url = self._build_url(product)
        return ProductDeal(
            site=self.name,
            title=title,
            promotion=promotion,
            price=format_money(price),
            list_price=format_money(list_price),
            url=url,
        )

    def _build_url(self, product: dict) -> str:
        link = product.get("link")
        if link:
            return link
        link_text = product.get("linkText")
        if link_text:
            return f"{self.base_url}/{link_text}/p"
        return self.base_url

    def _promotion_label(
        self, offer: dict, price: Optional[float], list_price: Optional[float]
    ) -> str:
        highlights = offer.get("DiscountHighLight") or []
        if highlights:
            return highlights[0].get("Name") or "Promoción"
        teasers = offer.get("Teasers") or []
        for teaser in teasers:
            name = teaser.get("Name")
            if name:
                return name
        discount = self._discount_label(price, list_price)
        return discount or "Sin promoción"

    def _discount_label(self, price: Optional[float], list_price: Optional[float]) -> str:
        if not price or not list_price or price <= 0 or list_price <= 0:
            return ""
        if price >= list_price:
            return ""
        percent = round((1 - price / list_price) * 100)
        if percent <= 0 or percent > 90:
            return ""
        return f"{percent}% OFF"

    @staticmethod
    def _is_in_stock(offer: dict) -> bool:
        if offer.get("IsAvailable") is False:
            return False
        available = offer.get("AvailableQuantity")
        if isinstance(available, (int, float)) and available <= 0:
            return False
        return True


class CotoScraper(BaseScraper):
    name = "Coto Digital"

    def __init__(self) -> None:
        self.search_url = "https://www.cotodigital.com.ar/sitios/cdigi/search?Ntt="

    def search(self, query: str) -> List[ProductDeal]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(f"{self.search_url}{quote(query)}", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            content = page.content()
            browser.close()
        return self._parse_html(content)[:10]

    def _parse_html(self, html: str) -> List[ProductDeal]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.producto, div.product-card, li.product-item")
        deals: List[ProductDeal] = []
        for card in cards:
            if not self._is_in_stock(card):
                continue
            title = self._text_from_selectors(
                card, ["h2", ".nombre", ".productTitle", ".title"]
            )
            price = self._text_from_selectors(
                card, [".price", ".precio", ".atg_store_newPrice", ".price"],
            )
            list_price = self._text_from_selectors(
                card,
                [
                    ".old-price",
                    ".precio-viejo",
                    ".precioAnterior",
                    ".price-old",
                    ".list-price",
                ],
            )
            promotion = self._text_from_selectors(
                card,
                [
                    ".promo", ".promocion", ".discount", ".label", ".tag", ".badge",
                    ".atg_store_promo", ".product-offer",
                ],
            )
            promotion = promotion or "Sin promoción"
            link_tag = card.select_one("a[href]")
            url = link_tag["href"] if link_tag else "https://www.cotodigital.com.ar/"
            if url.startswith("/"):
                url = f"https://www.cotodigital.com.ar{url}"
            if not title or not price:
                continue
            deals.append(
                ProductDeal(
                    site=self.name,
                    title=title,
                    promotion=promotion,
                    price=price,
                    list_price=list_price,
                    url=url,
                )
            )
        return deals

    @staticmethod
    def _text_from_selectors(card: BeautifulSoup, selectors: Iterable[str]) -> str:
        for selector in selectors:
            element = card.select_one(selector)
            if element:
                text = " ".join(element.get_text(" ", strip=True).split())
                if text:
                    return text
        return ""

    @staticmethod
    def _is_in_stock(card: BeautifulSoup) -> bool:
        unavailable_selectors = [
            ".sin-stock", ".agotado", ".stock-out", ".no-disponible",
        ]
        for selector in unavailable_selectors:
            if card.select_one(selector):
                return False
        for element in card.select("button, a"):
            text = element.get_text(" ", strip=True).lower()
            if any(keyword in text for keyword in ["agregar", "comprar", "sumar"]):
                classes = " ".join(element.get("class", []))
                if element.has_attr("disabled") or "disabled" in classes:
                    return False
                return True
        return False


def format_money(value: Optional[float]) -> str:
    if value is None:
        return ""
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {formatted}"


def render_results(results: List[ProductDeal]) -> None:
    if not results:
        print("No se encontraron promociones para esta marca.\n")
        return
    results_by_site: dict[str, List[ProductDeal]] = {}
    for deal in results:
        results_by_site.setdefault(deal.site, []).append(deal)
    for site, deals in results_by_site.items():
        print(f"\n=== {site} ===")
        for deal in deals:
            print(f"- {deal.title}")
            if deal.promotion and deal.promotion.lower() != "sin promoción":
                print(f"  Tipo de promoción: {deal.promotion}")
            if deal.list_price:
                print(f"  Precio lista: {deal.list_price}")
            print(f"  Precio promo: {deal.price}")
            print(f"  Link: {deal.url}\n")


def run_interactive(scrapers: List[BaseScraper]) -> None:
    print("Buscador de promociones de cerveza (CTRL+C para salir).")
    while True:
        try:
            query = input("\nMarca de cerveza: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            return
        if not query:
            print("Ingresá una marca para buscar.")
            continue
        results: List[ProductDeal] = []
        for scraper in scrapers:
            try:
                print(f"Buscando en {scraper.name}...")
                results.extend(scraper.search(query))
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] {scraper.name}: {exc}")
        render_results(results)


def main() -> None:
    scrapers: List[BaseScraper] = [
        CotoScraper(),
        VtexScraper("Vea", "https://www.vea.com.ar"),
        VtexScraper("Jumbo", "https://www.jumbo.com.ar"),
        VtexScraper("Disco", "https://www.disco.com.ar"),
        VtexScraper("DIA Online", "https://diaonline.supermercadosdia.com.ar"),
        VtexScraper("Carrefour", "https://www.carrefour.com.ar"),
    ]
    run_interactive(scrapers)


if __name__ == "__main__":
    main()
