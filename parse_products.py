import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import ftfy 
import json 
import re 

TARGET_URL = 'https://reflex-boutique.fr/parquet-flottant/22125-parquet-contrecolle-krefeld-chene-naturel-vitrifie-planche-165120-cm.html'

def fetch_page_content(url_to_fetch):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7,ru;q=0.6', 
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    }
    try:
        response = requests.get(url_to_fetch, headers=headers, timeout=15)
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
    if not html_string or not isinstance(html_string, str):
        return "" 
    
    temp_soup = BeautifulSoup(html_string, 'html.parser')
    for tag in temp_soup.find_all(True): 
        tag.attrs = {} 
        
    if temp_soup.body: 
        return temp_soup.body.decode_contents() 
    elif temp_soup.html: 
        return temp_soup.html.decode_contents() 
    else: 
        return "".join(str(content) for content in temp_soup.contents)

def parse_data(html_content, current_url):
    if not html_content: return None
    soup = BeautifulSoup(html_content, 'html.parser') 
    data = {
        'url': current_url, 'title': '', 'category': '', 'price': None, 
        'short_description': '', 'full_description_html': '', 
        'product_details_html': '', 'image_url': ''
    }

    # --- Title, Category, Descriptions, Image URL (логика остается прежней) ---
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

    # --- Логика Цены (возврат к более ранней, возможно, более успешной для вас) ---
    print("\n[DEBUG] Поиск Цены (восстановленная логика):")
    price_str_cleaned = None
    price_source_debug = "не определен"

    product_prices_div = soup.select_one('div.product-prices')
    if product_prices_div:
        print(f"  ℹ️ Найден блок div.product-prices.")

        # 1. Попытка найти "обычную/старую" цену
        regular_price_tag = product_prices_div.select_one('.regular-price') # Более точный селектор для примера "75,87 €"
        if regular_price_tag:
            regular_price_text_raw = regular_price_tag.get_text(strip=True)
            price_source_debug = f"ОБЫЧНАЯ цена из текста тега '{regular_price_tag.name}.{regular_price_tag.get('class', [])}'"
            print(f"  ✅ {price_source_debug}: '{regular_price_text_raw}'")
            # Очищаем: удаляем все кроме цифр, точки, запятой. Заменяем запятую на точку.
            temp_price = re.sub(r'[^\d,.]', '', regular_price_text_raw)
            price_str_cleaned = temp_price.replace(',', '.')
        else:
            print(f"  ℹ️ Тег 'обычной цены' (.regular-price) не найден.")

        # 2. Если обычная цена не найдена, ищем текущую цену из атрибута 'content'
        if not price_str_cleaned:
            current_price_span_with_content = product_prices_div.select_one('span.current-price-value[content]')
            if current_price_span_with_content:
                content_price = current_price_span_with_content.get('content')
                if content_price:
                    price_source_debug = "ТЕКУЩАЯ цена из атрибута 'content' у span.current-price-value"
                    print(f"  ✅ {price_source_debug}: '{content_price}'")
                    # Атрибут content обычно уже содержит число или число с точкой
                    price_str_cleaned = re.sub(r'[^\d.]', '', content_price) # Оставляем только цифры и точку
                else:
                    print(f"  ℹ️ Атрибут 'content' у span.current-price-value пуст.")
            else:
                print(f"  ℹ️ Тег span.current-price-value с 'content' не найден.")
        
        # 3. Если все еще не найдена, пробуем текст текущей цены (менее приоритетно)
        if not price_str_cleaned:
            current_price_text_tag = product_prices_div.select_one('span.current-price-value') # или .current-price > span:first-child
            if current_price_text_tag:
                current_price_text_raw = current_price_text_tag.get_text(separator='', strip=True)
                price_source_debug = "ТЕКУЩАЯ цена из текста span.current-price-value"
                print(f"  ✅ {price_source_debug}: '{current_price_text_raw}'")
                # Извлекаем числовой паттерн (например, 56.90 из 56€90/m²)
                match = re.search(r'(\d+([.,]\d{1,2})?)', current_price_text_raw.replace('€', '.')) # Заменяем € на . для упрощения
                if match:
                    price_str_cleaned = match.group(1).replace(',', '.')
                else: # Очень простая очистка, если regex не сработал
                    price_str_cleaned = re.sub(r'[^\d,.]', '', current_price_text_raw).replace(',', '.')

    else:
        print(f"  ⚠️ Блок div.product-prices НЕ НАЙДЕН на странице.")

    # Конвертация
    if price_str_cleaned:
        # Финальная проверка на лишние точки
        if price_str_cleaned.count('.') > 1:
            parts = price_str_cleaned.split('.', 1)
            price_str_cleaned = parts[0] + '.' + parts[1].replace('.', '')
        
        print(f"    Итоговая очищенная строка для преобразования в float: '{price_str_cleaned}' (источник: {price_source_debug})")
        try:
            data['price'] = float(price_str_cleaned)
            print(f"    ✅ Цена успешно преобразована в float: {data['price']}")
        except ValueError:
            data['price'] = price_str_cleaned 
            print(f"    ⚠️ Не удалось преобразовать '{price_str_cleaned}' в float. Сохранено как очищенная строка.")
    else:
        print(f"  ⚠️ Не удалось извлечь и очистить строку для цены.")
    # --- КОНЕЦ ЛОГИКИ ЦЕНЫ ---

    short_desc_container = soup.find('div', id=lambda x: x and x.startswith('product-description-short-'))
    if short_desc_container:
        data['short_description'] = strip_all_attributes_from_html_tags(str(short_desc_container))
    
    full_desc_tab_content = soup.find('div', id='description')
    if full_desc_tab_content:
        data['full_description_html'] = strip_all_attributes_from_html_tags(str(full_desc_tab_content))

    product_details_section = soup.select_one('#product-details section.product-features')
    if product_details_section:
        data['product_details_html'] = strip_all_attributes_from_html_tags(str(product_details_section))
    else:
        product_details_tab_fallback = soup.find('div', id='product-details')
        if product_details_tab_fallback:
            data['product_details_html'] = strip_all_attributes_from_html_tags(str(product_details_tab_fallback))

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

def save_to_csv(data_to_save, filename=None):
    if not data_to_save: 
        print("Нет данных для сохранения в CSV.")
        return None
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'reflex_product_price_restored_logic_{timestamp}.csv' 

    processed_data_for_csv = {}
    for key, value in data_to_save.items():
        if isinstance(value, str):
            temp_value = value.replace('"', "'")
            processed_data_for_csv[key] = temp_value
        else:
            processed_data_for_csv[key] = value 

    fieldnames = ['url', 'title', 'category', 'price', 
                  'short_description', 'full_description_html', 'product_details_html',
                  'image_url']
    try:
        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader() 
            writer.writerow(processed_data_for_csv) 
        return filename
    except IOError as e:
        print(f"Ошибка при записи в CSV файл {filename}: {e}")
        return None

def main():
    print(f"Парсинг URL: {TARGET_URL}")
    html = fetch_page_content(TARGET_URL) 
    status_summary = {
        "url": TARGET_URL, "title_found": False, "category_found": False, 
        "price_found": False, "short_desc_found": False, "full_desc_found": False,
        "product_details_found": False, "image_found": False, "csv_saved_as": "Нет"
    }
    if html:
        data = parse_data(html, TARGET_URL) 
        if data:
            status_summary["title_found"] = bool(data.get('title'))
            status_summary["category_found"] = bool(data.get('category'))
            status_summary["price_found"] = data.get('price') is not None 
            status_summary["short_desc_found"] = bool(data.get('short_description'))
            status_summary["full_desc_found"] = bool(data.get('full_description_html'))
            status_summary["product_details_found"] = bool(data.get('product_details_html'))
            status_summary["image_found"] = bool(data.get('image_url'))
            
            print("\n--- Данные, подготовленные для обработки и записи в CSV ---")
            print(f"URL: {data.get('url', 'N/A')}")
            print(f"Title: {data.get('title', 'N/A')}")
            print(f"Category: {data.get('category', 'N/A')}")
            print(f"Price (извлеченное значение): {data.get('price', 'N/A')}") 
            print(f"Image URL: {data.get('image_url', 'N/A')}")
            # ... (остальной вывод для отладки можно сократить)

            saved_filename = save_to_csv(data) 
            if saved_filename:
                status_summary["csv_saved_as"] = saved_filename
                print(f"\nCSV файл '{saved_filename}' успешно создан.")
            # ... (остальная часть main)
        else: 
            print("❌ Ошибка: Не удалось извлечь (распарсить) данные из HTML страницы.")
    else: 
        print("❌ Ошибка: Не удалось загрузить HTML содержимое страницы.")

    print(f"\n--- Итоговый отчет по парсингу ---")
    # ... (вывод отчета без изменений)
    print(f"Обработан URL: {status_summary['url']}")
    print(f"  Заголовок: {'Найден' if status_summary['title_found'] else 'НЕ НАЙДЕН'}")
    print(f"  Категория: {'Найдена' if status_summary['category_found'] else 'НЕ НАЙДЕНА'}")
    print(f"  Цена: {'Найдена' if status_summary['price_found'] else 'НЕ НАЙДЕНА'}")
    print(f"  Короткое описание: {'Найдено' if status_summary['short_desc_found'] else 'НЕ НАЙДЕНО'}")
    print(f"  Полное описание: {'Найдено' if status_summary['full_desc_found'] else 'НЕ НАЙДЕНО'}")
    print(f"  Детали продукта: {'Найдены' if status_summary['product_details_found'] else 'НЕ НАЙДЕНЫ'}")
    print(f"  URL изображения: {'Найден' if status_summary['image_found'] else 'НЕ НАЙДЕНО'}")
    print(f"Данные сохранены в файл: {status_summary['csv_saved_as']}")
    if status_summary["csv_saved_as"] != "Нет":
        print("ВАЖНОЕ ПРИМЕЧАНИЕ:")
        print("  1. В HTML-описаниях УДАЛЕНЫ ВСЕ АТРИБУТЫ ТЕГОВ.")
        print("  2. Во ВСЕХ строковых данных, записываемых в CSV, символы '\"' были ЗАМЕНЕНЫ на ''' .")

if __name__ == '__main__':
    main()