"""Render the dated, public clams-and-chips menu observations in the landing HTML."""
from html import escape


def menu_summary(catalogue):
    shops = {r["id"]: r for r in catalogue["restaurants"]}
    rows = []
    for item in catalogue["items"]:
        if item["dish"] != "meal":
            continue
        shop = shops[item["restaurant_id"]]
        evidence = escape(shop.get("evidence_url") or shop["menu_url"], quote=True)
        label = escape(f"{shop['name']} · {shop['area']}")
        price = f"${item['cents'] / 100:.2f}" if item["cents"] is not None else escape(item["price_note"])
        clam = {"whole": "Whole clams", "strips": "Clam strips", "unspecified": "Type unstated"}[item["type"]]
        rows.append(f'<tr><th scope="row"><a href="{evidence}">{label}</a></th>'
                    f'<td>{price}</td><td>{clam}</td><td>{escape(item["portion"])}</td>'
                    f'<td>{escape(shop["reviewed_at"])}</td></tr>')
    return """<section class="about"><h2>Halifax-area clams and chips menu prices</h2>
<p>Each row is one restaurant’s meal as described on its menu. Portion and clam type affect what you get
for the listed Canadian-dollar price. Market-priced meals retain the menu wording.</p>
<div class="menu-scroll"><table><caption>Dated restaurant menu observations</caption><thead><tr>
<th scope="col">Restaurant and menu</th><th scope="col">Listed price</th><th scope="col">Clam type</th>
<th scope="col">Listed portion</th><th scope="col">Reviewed</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table></div>
<p><a href="#results-title">Compare orders and included sides</a> · <a href="/donairafterdark/">Compare Halifax donair prices</a>
 · <a href="/clamground/">Explore Nova Scotia clam landings</a> · <a href="/inspectiontrail/">Find restaurant inspection records</a></p></section>"""
