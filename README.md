
# Navigator UK Market Intelligence — MVP

Django MVP com **scraping configurável por retalhista** (via CSS selectors), histórico de preços/promoções e dashboard simples.

## 🚀 Funcionalidades
- Modelos: SKU, Retailer, SKUListing, RetailerSelector, PricePoint
- Scraping por gestão de seletores CSS por retalhista
- Histórico de preços (com promoções) por SKU e retalhista
- Dashboard com último preço e página de detalhes com gráfico (Chart.js)
- Botão **Scrape Now** para executar scraping síncrono (MVP)
- Management command: `python manage.py scrape_prices`

## 🔧 Setup rápido

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser  # criar utilizador admin
python manage.py loaddata demo_books.json  # dados demo (Books to Scrape)
python manage.py runserver
```

Abrir: http://127.0.0.1:8000

Admin: http://127.0.0.1:8000/admin

## 🧪 Demo que "funciona já"
Incluímos um retalhista de demonstração **Books to Scrape** (site público de teste).  
- Em Admin, encontrará:
  - **Retailer**: "Books to Scrape"
  - **RetailerSelector**: com seletores válidos para a página de um livro
  - **SKU** e **SKUListing**: apontando para a página de um livro real no demo

Execute o scraping:
```bash
python manage.py scrape_prices
```
ou clique em **Scrape Now** no menu.

Deverá ver PricePoints a serem criados, e os valores aparecem no Dashboard e no detalhe do SKU.

## 🧩 Como configurar um novo retalhista
1. Criar `Retailer` (ex.: "Amazon UK").
2. Criar `RetailerSelector` com os seletores CSS das páginas de produto (ex.: preço atual, preço promocional, badge de promo).
3. Criar `SKU` e um `SKUListing` por URL de produto (do retalhista).
4. Correr `scrape_prices`.

> **Nota**: para páginas dinâmicas (JS), pode ser necessário Playwright/Selenium. Este MVP usa `requests + BeautifulSoup`. Podemos evoluir para `playwright` numa próxima fase.

## ⚠️ Boas práticas & conformidade
- Respeitar `robots.txt` e termos de uso dos retalhistas.
- Preferir **APIs oficiais** quando disponíveis.
- Implementar **delay aleatório** e _retry_ para ser "polite".
- Este MVP recolhe apenas páginas de produto configuradas manualmente (sem crawling massivo).

## 🗺️ Roadmap (próxima fase)
- Headless browser para páginas dinâmicas
- Scheduler (Celery beat) com retries e alertas
- Deduplicação e validação (outliers)
- API REST (Django REST Framework)
- RBAC e auditoria
- Forecasting e deteção de padrões (IA)
