import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import ftfy 
import json 
import re 
import os 
import time 

# URL СТАРТОВОЙ СТРАНИЦЫ КАТЕГОРИИ ДЛЯ СКАНИРОВАНИЯ
START_CATEGORY_URL = 'https://reflex-boutique.fr/parquet-flottant/754-parquet-sol-stratifie'


def fetch_page_content(url_to_fetch):
    """Загружает HTML-содержимое страницы и исправляет кодировку, если нужно."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7,ru;q=0.6', 
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    }
    try:
        # print(f"  Загрузка: {url_to_fetch}") 
        response = requests.get(url_to_fetch, headers=headers, timeout=20)
        response.raise_for_status() 
        html_text = response.text
        if "√" in html_text and ("©" in html_text or "Г" in html_text): 
            fixed_text = ftfy.fix_text(html_text)
            return fixed_text
        else:
            return html_text
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при загрузке страницы {url_to_fetch}: {e}")
        return None
    except Exception as e:
        print(f"Неизвестная ошибка в fetch_page_content для {url_to_fetch}: {e}")
        return None

def strip_all_attributes_from_html_tags(html_string):
    """
    Удаляет ВСЕ атрибуты (class, id, style и т.д.) из ВСЕХ HTML-тегов в предоставленной строке.
    Оставляет только "голые" HTML-теги и их текстовое содержимое.
    """
    if not html_string or not isinstance(html_string, str): return "" 
    temp_soup = BeautifulSoup(html_string, 'html.parser')
    for tag in temp_soup.find_all(True): tag.attrs = {} 
    if temp_soup.body: return temp_soup.body.decode_contents() 
    elif temp_soup.html: return temp_soup.html.decode_contents() 
    else: return "".join(str(content) for content in temp_soup.contents)

def parse_data(html_content, product_url): 
    """Извлекает все необходимые данные со страницы товара."""
    if not html_content: return None
    soup = BeautifulSoup(html_content, 'html.parser') 
    data = {
        'url': product_url, 'title': '', 'category': '', 'price': None, 
        'short_description': '', 'full_description_html': '', 
        'product_details_html': '', 'image_url': ''
    }

    title_tag = soup.find('h1', class_='h1') 
    if title_tag: data['title'] = title_tag.get_text(strip=True)
    else: 
        first_h1 = soup.find('h1') 
        if first_h1: data['title'] = first_h1.get_text(strip=True)

    breadcrumb_nav = soup.select_one('nav.breadcrumb')
    if breadcrumb_nav:
        spans = breadcrumb_nav.select('ol li a span')
        if len(spans) > 1: data['category'] = spans[1].get_text(strip=True)
        elif len(spans) == 1: data['category'] = spans[0].get_text(strip=True)

    price_str_to_convert = None
    price_tag_with_content = soup.select_one('div.product-prices span.current-price-value[content]')
    if price_tag_with_content:
        content_val = price_tag_with_content.get('content')
        if content_val: price_str_to_convert = content_val
    
    if not price_str_to_convert: 
        regular_price_tag = soup.select_one('div.product-prices .regular-price, div.product-prices .old-price, div.product-prices .product-price-without-reduction')
        if regular_price_tag:
            price_text_raw = regular_price_tag.get_text(strip=True)
            match = re.search(r'(\d+([.,]\d+)?)', price_text_raw)
            if match: price_str_to_convert = match.group(1)
        
        if not price_str_to_convert: 
            current_price_tag = soup.select_one('div.product-prices span.current-price-value, div.product-prices .current-price > span:first-child, div.product-prices .price > span:first-child')
            if current_price_tag:
                price_text_raw = current_price_tag.get_text(separator=' ',strip=True)
                match = re.search(r'(\d+([.,]\d+)?)', price_text_raw)
                if match: price_str_to_convert = match.group(1)
    
    if price_str_to_convert:
        try:
            cleaned_price_str = re.sub(r'[^\d.]', '', price_str_to_convert.replace(',', '.'))
            if cleaned_price_str: 
                 data['price'] = float(cleaned_price_str)
        except (ValueError, TypeError):
            data['price'] = price_str_to_convert 

    short_desc_container = soup.find('div', id=lambda x: x and x.startswith('product-description-short-'))
    if short_desc_container: data['short_description'] = strip_all_attributes_from_html_tags(str(short_desc_container))
    
    full_desc_tab_content = soup.find('div', id='description')
    if full_desc_tab_content: data['full_description_html'] = strip_all_attributes_from_html_tags(str(full_desc_tab_content))

    product_details_section = soup.select_one('#product-details section.product-features')
    if product_details_section: data['product_details_html'] = strip_all_attributes_from_html_tags(str(product_details_section))
    else:
        pd_fallback = soup.find('div', id='product-details')
        if pd_fallback: data['product_details_html'] = strip_all_attributes_from_html_tags(str(pd_fallback))

    images_container = soup.select_one('div.product-images')
    if images_container:
        imgs = images_container.find_all('img')
        for img in imgs:
            large_src = img.get('data-image-large-src')
            if large_src: data['image_url'] = large_src; break
            if not data['image_url']:
                sources_json = img.get('data-image-large-sources')
                if sources_json:
                    try:
                        sources = json.loads(sources_json)
                        data['image_url'] = sources.get('jpg', next(iter(sources.values()), ''))
                        if data['image_url']: break
                    except: pass
        if not data['image_url'] and imgs: data['image_url'] = imgs[0].get('src', '')  
    return data

def get_product_links_and_next_page(category_page_html):
    """Извлекает ссылки на товары, ссылку на следующую страницу пагинации и название категории."""
    if not category_page_html:
        return [], None, "unknown_category"
    
    soup = BeautifulSoup(category_page_html, 'html.parser')
    product_links = []
    
    # --- ОТЛАДКА ПОИСКА ССЫЛОК НА ТОВАРЫ ---
    print("\n  [DEBUG get_product_links] Поиск блоков товаров (product-miniature):")
    # Ищем <article class="product-miniature js-product-miniature" ...>
    # или просто <article class="product-miniature">
    product_articles = soup.select('article.product-miniature') 
    
    if product_articles:
        print(f"    Найдено {len(product_articles)} элементов <article.product-miniature>.")
        for i, article in enumerate(product_articles):
            # Внутри каждой карточки ищем ссылку.
            # Селектор для основной ссылки товара в карточке:
            link_tag = article.select_one('.product-thumbnail[href], .thumbnail[href], .product-title a[href], h2.product-title a[href], .product_img_link[href]') 
            # Добавил больше вариантов для ссылки внутри карточки товара
            
            if not link_tag: # Если не нашли по специфичным классам, ищем любую ссылку с href
                 link_tag = article.find('a', href=True)

            if link_tag and link_tag.get('href'):
                href = link_tag.get('href')
                product_links.append(href)
                # print(f"      Найден URL товара [{i}]: {href}") # Раскомментировать для детальной отладки каждой ссылки
            else:
                print(f"      ⚠️ В <article.product-miniature>[{i}] ссылка на товар не найдена или отсутствует href.")
                # print(f"        HTML карточки товара [{i}] (первые 200 символов): {str(article)[:200]}") 
    else:
        print(f"    ⚠️ Элементы <article.product-miniature> НЕ НАЙДЕНЫ.")
        products_list_container = soup.select_one('#js-product-list .products, #content .products, div.products') # Более общие селекторы
        if products_list_container:
            print(f"    [ОТЛАДКА HTML] Содержимое блока списка товаров (первые 500 символов):\n{products_list_container.prettify()[:500]}")
            # Попробуем найти ссылки внутри этого общего контейнера более простым способом
            all_links_in_list = products_list_container.find_all('a', href=True)
            print(f"    Найдено {len(all_links_in_list)} ссылок внутри products_list_container.")
            # Здесь нужна будет логика фильтрации, чтобы выбрать только ссылки на товары
            # Пока просто выведем несколько для анализа
            for idx, l in enumerate(all_links_in_list[:5]): # Первые 5 ссылок
                print(f"      Пример ссылки [{idx}]: {l.get('href')}")

        else:
            print(f"    [ОТЛАДКА HTML] Блок списка товаров также не найден стандартными селекторами.")
    # --- КОНЕЦ ОТЛАДКИ ПОИСКА ССЫЛОК ---
            
    next_page_tag = soup.select_one('nav.pagination a.next.js-search-link, nav.pagination a.next') # Добавлен запасной селектор для пагинации
    next_page_url = None
    if next_page_tag and next_page_tag.get('href'):
        next_page_url = next_page_tag.get('href')
        
    category_name_tag = soup.select_one('h1.h1.page-title, h1.page-heading, h1.category-title') # Добавлены запасные селекторы
    category_name_from_h1 = category_name_tag.get_text(strip=True) if category_name_tag else "unknown_category"

    return product_links, next_page_url, category_name_from_h1


def crawl_category_products(start_category_url):
    """Собирает все URL товаров со всех страниц указанной категории."""
    all_product_urls = set() 
    current_page_url = start_category_url
    processed_pages = 0
    category_name_for_folder = start_category_url.split('/')[-1] 
    if not category_name_for_folder or '.html' in category_name_for_folder: 
        category_name_for_folder = start_category_url.split('/')[-2] if len(start_category_url.split('/')) > 1 else "default_category"
    category_name_for_folder = re.sub(r'[^\w-]', '', category_name_for_folder.lower().replace(' ', '_'))

    print(f"Начало сканирования категории: {start_category_url}")

    while current_page_url:
        processed_pages += 1
        print(f"  Обработка страницы категории ({processed_pages}): {current_page_url}")
        category_page_html = fetch_page_content(current_page_url)
        if not category_page_html:
            print(f"  Не удалось загрузить страницу категории: {current_page_url}")
            break 
        
        product_links_on_page, next_page_url_temp, cat_name_h1 = get_product_links_and_next_page(category_page_html)
        
        if processed_pages == 1 and cat_name_h1 and cat_name_h1.lower() != "unknown_category": 
            new_cat_name = re.sub(r'[^\w-]', '', cat_name_h1.lower().replace(' ', '_'))
            if new_cat_name: # Убедимся, что имя не пустое после очистки
                category_name_for_folder = new_cat_name
            print(f"  Установлено имя категории для папки: {category_name_for_folder}")

        if product_links_on_page:
            print(f"    Найдено {len(product_links_on_page)} ссылок на товары.")
            for link in product_links_on_page:
                all_product_urls.add(link)
        else:
            print(f"    Ссылок на товары на странице не найдено.")

        if next_page_url_temp:
            # Проверяем, не является ли ссылка относительной и не начинается ли она с #
            if next_page_url_temp.startswith("http"):
                current_page_url = next_page_url_temp
            elif next_page_url_temp.startswith("/"):
                # Собираем абсолютный URL из схемы и хоста стартового URL
                from urllib.parse import urlparse, urljoin
                parsed_start_url = urlparse(start_category_url)
                base_url = f"{parsed_start_url.scheme}://{parsed_start_url.netloc}"
                current_page_url = urljoin(base_url, next_page_url_temp)
            elif next_page_url_temp.startswith("#"): # Игнорируем ссылки-якоря
                print(f"    Найдена ссылка-якорь для пагинации: {next_page_url_temp}. Завершаем пагинацию.")
                current_page_url = None
                break
            else: # Если это относительная ссылка без / в начале, предполагаем, что она относится к текущей директории URL
                current_page_url = os.path.join(os.path.dirname(current_page_url), next_page_url_temp)


            print(f"    Переход на следующую страницу: {current_page_url}")
            time.sleep(1) 
        else:
            print(f"  Достигнута последняя страница категории или ссылка на следующую не найдена.")
            current_page_url = None 

    print(f"Завершено сканирование категории. Всего найдено уникальных ссылок на товары: {len(all_product_urls)}")
    return list(all_product_urls), category_name_for_folder


def save_to_csv(list_of_products_data, category_folder_name, base_filename="products"):
    """Сохраняет список данных о товарах в CSV-файл в указанную подпапку."""
    if not list_of_products_data: 
        print("Нет данных для сохранения в CSV.")
        return None
        
    if not category_folder_name: 
        category_folder_name = "default_category_output"
        print(f"Предупреждение: Имя категории для папки не определено, используется '{category_folder_name}'")

    if not os.path.exists(category_folder_name):
        try:
            os.makedirs(category_folder_name)
            print(f"Создана подпапка: ./{category_folder_name}/")
        except OSError as e:
            print(f"Ошибка при создании подпапки ./{category_folder_name}/: {e}")
            return None 
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base_part = re.sub(r'[^\w-]', '', category_folder_name) 
    csv_filename = os.path.join(category_folder_name, f"{filename_base_part}_{base_filename}_{timestamp}.csv")

    processed_data_list = []
    for product_data_dict in list_of_products_data:
        processed_item = {}
        for key, value in product_data_dict.items():
            if isinstance(value, str):
                temp_value = value.replace('"', "'")
                processed_item[key] = temp_value
            else:
                processed_item[key] = value 
        processed_data_list.append(processed_item)

    fieldnames = ['url', 'title', 'category', 'price', 
                  'short_description', 'full_description_html', 'product_details_html',
                  'image_url']
    try:
        with open(csv_filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore') 
            writer.writeheader() 
            writer.writerows(processed_data_list) 
        print(f"Данные ({len(processed_data_list)} товаров) сохранены в файл: {csv_filename}")
        return csv_filename
    except IOError as e:
        print(f"Ошибка при записи в CSV файл {csv_filename}: {e}")
        return None

def main():
    """Основная функция для запуска скрапера."""
    print(f"Парсинг URL категории: {START_CATEGORY_URL}")
    
    product_urls_to_parse, category_folder_name = crawl_category_products(START_CATEGORY_URL)
    
    if not product_urls_to_parse:
        print("Не найдено URL товаров для обработки. Завершение работы.")
        return

    all_products_data = []
    total_products = len(product_urls_to_parse)
    print(f"\nНачало парсинга {total_products} товаров из категории '{category_folder_name}'...")

    for i, product_url in enumerate(product_urls_to_parse):
        print(f"  Обработка товара {i+1}/{total_products}: {product_url}")
        product_html = fetch_page_content(product_url)
        if product_html:
            product_data = parse_data(product_html, product_url) 
            if product_data:
                all_products_data.append(product_data)
            else:
                print(f"    Не удалось извлечь данные для товара: {product_url}")
        else:
            print(f"    Не удалось загрузить страницу товара: {product_url}")
        time.sleep(0.3 + abs(0.4 * (i % 5 - 2))) # Небольшая случайная задержка 0.1-0.5 сек

    if all_products_data:
        # Вывод отладочной информации для первого товара перед сохранением
        if all_products_data:
            print("\n--- Пример данных первого товара (перед записью в CSV) ---")
            first_item = all_products_data[0]
            print(f"URL: {first_item.get('url', 'N/A')}")
            print(f"Title: {first_item.get('title', 'N/A')}")
            print(f"Category: {first_item.get('category', 'N/A')}")
            print(f"Price: {first_item.get('price', 'N/A')}")
            print(f"Image URL: {first_item.get('image_url', 'N/A')}")
            print(f"Short Description (очищенный HTML, начало):\n{str(first_item.get('short_description', 'N/A'))[:100]}...")
            print(f"Full Description (очищенный HTML, начало):\n{str(first_item.get('full_description_html', 'N/A'))[:100]}...")
            print(f"Product Details (очищенный HTML, начало):\n{str(first_item.get('product_details_html', 'N/A'))[:100]}...")

        save_to_csv(all_products_data, category_folder_name, base_filename=category_folder_name) 
    else:
        print("Не собрано данных о товарах для сохранения.")

    print("\n--- Работа скрапера завершена ---")

if __name__ == '__main__':
    main()