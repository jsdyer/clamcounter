"""Validate editorial data before it can replace the published collection."""
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit


def fail(message):
    raise ValueError('Catalogue: ' + message)


def text(value, name, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > 2000:
        fail(name + ' must be text')


def day(value):
    if not isinstance(value, str):
        fail('invalid review date')
    try:
        if date.fromisoformat(value).isoformat() != value:
            fail('invalid review date')
    except ValueError:
        fail('invalid review date')


def url(value):
    text(value, 'URL')
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or any(x.isspace() for x in value):
        fail('source URL must be HTTPS without credentials')


def validate(data):
    if not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('currency') != 'CAD':
        fail('unsupported schema or currency')
    day(data.get('reviewed_at'))
    tax = data.get('tax', {})
    if tax.get('rate_percent') != 14 or tax.get('default_enabled') is not False:
        fail('HST model is 14%, opt-in; review model and UI before changing the rate')
    url(tax.get('source')); day(tax.get('reviewed_at'))
    shops, items = data.get('restaurants'), data.get('items')
    if not isinstance(shops, list) or not shops or not isinstance(items, list) or not items:
        fail('restaurants and menu items are required')
    shop_ids, item_ids, used = set(), set(), set()
    for shop in shops:
        for key in ['id', 'name', 'area', 'address', 'source_id', 'channel']:
            text(shop.get(key), key)
        if shop['id'] in shop_ids:
            fail('duplicate restaurant ID')
        shop_ids.add(shop['id'])
        day(shop.get('reviewed_at')); url(shop.get('menu_url'))
        if shop.get('source_published_at') is not None:
            day(shop['source_published_at'])
        for key in ['source_parent_url', 'evidence_url', 'hours_source']:
            if shop.get(key):
                url(shop[key])
        week = shop.get('week')
        if week is not None:
            if not isinstance(week, list) or len(week) != 7:
                fail('hours need seven days (Sunday first); null means unrecorded, [] means closed')
            if not shop.get('hours_source'):
                fail('recorded hours need a source')
            for interval in week:
                if interval is None or interval == []:
                    continue
                if (not isinstance(interval, list) or len(interval) != 2
                        or not all(type(m) is int for m in interval)
                        or not 0 <= interval[0] < 1440
                        or not interval[0] < interval[1] <= interval[0] + 1440):
                    fail('invalid hours; overnight closing must use minutes after midnight above 1440')
    for item in items:
        for key in ['id', 'restaurant_id', 'name', 'portion', 'availability', 'price_note']:
            text(item.get(key), key)
        if item['id'] in item_ids:
            fail('duplicate item ID')
        item_ids.add(item['id'])
        if item['restaurant_id'] not in shop_ids:
            fail('orphan item')
        used.add(item['restaurant_id'])
        if item.get('type') not in ('whole', 'strips', 'unspecified') or item.get('dish') not in ('meal', 'clams-only', 'platter'):
            fail('invalid clam type or dish')
        cents = item.get('cents', 'missing')
        if cents is not None and (type(cents) is not int or not 0 <= cents <= 1000000):
            fail('price must be integer cents or null for unknown')
        if item.get('tax_included') not in (None, False):
            fail('tax-inclusive source needs model support before inclusion')
        if not isinstance(item.get('includes'), list):
            fail('included sides must be a list')
        for side in item['includes']:
            text(side, 'side')
    if used != shop_ids:
        fail('restaurant without a reviewed dish')
    return data


def load(root):
    return validate(json.loads((Path(root) / 'web/data/catalogue.json').read_text(encoding='utf-8')))
