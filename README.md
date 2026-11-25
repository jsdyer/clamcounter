# Clam Counter

[Use Clam Counter](https://coolcode.ca/clamcounter/) to compare a real clams-and-chips order around Halifax, Dartmouth and nearby Nova Scotia. It runs directly in a browser; no account, API key or installation is needed.

<!-- coolcode:guide -->
Compare dated restaurant-menu observations by area, explicitly stated clam type, dish and listed price. Keep portion descriptions and included sides visible; an unweighed dish is never converted into a cost per gram. Market prices stay unknown. Enter the number of dishes, optionally estimate Nova Scotia HST, and compare up to eight alternatives, including a current phone or counter quote of your own. Favourites and deliberately saved comparisons stay on your device; JSON import/export preserves the prices and review dates originally saved. The weekly source-change watch checks pages, not current stock or prices. Open each restaurant source before travelling or ordering, especially when it is seasonal, old or flagged as changed.
<!-- /coolcode:guide -->

The first manual review covers **9 restaurants and 11 dishes**, observed **2026-11-25 UTC**. Coverage is a starting point, not a list of every restaurant. Unknown type, weight, publication date, stock and tax inclusion remain unknown. “Fresh” or “Digby” alone never becomes a whole-clam claim. Menu age is not replaced by a build or download timestamp.

| Restaurant | Menu observation | Source |
| --- | ---: | --- |
| Acadian Fish & Chips and Enzo Pizzeria | $27.99 | [Restaurant menu](https://www.acadianenzo.com/menu) |
| Bluenose II | $24.50; menu being updated | [Restaurant menu](https://bluenoseii.ca/menu/) |
| Fredie's | $28.99 | [Restaurant menu](https://frediesfantasticfish.ca/menu/) |
| Mic Mac | Market price; when available | [Restaurant menu](https://micmacbarandgrill.com/menus/food/) |
| Palladium | Market price | [Restaurant main menu image](https://palladiumfamily.ca/our-menu/) |
| Pleasant St. Diner | $33.00; seasonal | [Restaurant menu and image](https://pleasantstdiner.com/wp/menu/) |
| Sydelle's | $28.95 | [Restaurant menu](https://sydelles.ca/MENU/) |
| Tasty Pizza | $14.95; two cups of clams | [Restaurant ordering menu](https://tastypizza.ca/menu/seafood) |
| Uncle Buck's | $18.99; half-pound clam meal | [Restaurant seafood menu](https://www.unclebuckspizza.com/seafood/) |

Palladium’s restaurant main menu states market-based pricing. Its separate Popmenu takeout page previously displayed $33, but that is a different channel and is not used in the comparison. The restaurant-owned menu images and hours page provide the monitored evidence.

These are published observations, not quotes for today's service. Bluenose explicitly says its printed restaurant prices prevail. The site does not promise stock or that a restaurant is currently open. Listed hours use `America/Halifax`, support closing after midnight, and exclude the exact closing time. Restaurant hours may differ from kitchen, takeout and holiday hours; the recorded channel is shown beside the source.

The optional **14% NS HST** estimate follows the [CRA rate calculator](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate/calculator.html), reviewed with this collection. It is **off by default** and assumes the listed price excludes tax. Mic Mac explicitly excludes tax; the other menus do not establish tax inclusion. Cents are integers, and estimated tax rounds once on each compared order. Delivery charges, tips and unlisted extras are excluded. Totals compare the same count of each named dish; a dinner for two still counts as one dish.

## Run and verify

```sh
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000`. Browser checks use Playwright only as a test dependency:

```sh
python3 -m pip install -r tests/browser-requirements.txt
python3 -m playwright install chromium
python3 tests/browser_smoke.py
```

Use `CHROMIUM_PATH=/path/to/chrome` to test an existing browser. CI tests the published project subpath, filters, exact totals, unknown prices, local saving and historical imports, personal quotes, escaping, error status and mobile overflow. The builder validates editorial data and stages output before replacing an existing `dist/`. The built app requires no network besides its own static files and aggregate CoolCode page metrics; restaurant sites are visited only when a visitor selects a link.

## Expand or customize

For an immediate personal comparison, use **Add your own comparison**. Enter any restaurant label, CAD price and truthful portion description. Save deliberately on this browser, or export JSON/CSV. A personal quote is not added to the public menu collection. Imports retain historical prices rather than silently looking up new prices.

To add or review a public restaurant:

1. Read its current restaurant-owned menu or a menu explicitly linked by that restaurant. Verify address, branch/channel, price, portion, included sides and availability wording. Do not use a search snippet or aggregator alone. Use `null` cents for market/unknown prices and `unspecified` for an unstated clam type. Record the manual review date, never an inferred publication date from a copyright footer or image path.
2. Edit `web/data/catalogue.json`. Add a unique restaurant `id`, `source_id`, name, area, address, phone, HTTPS `menu_url`, channel and `reviewed_at`. Add any evidence image or source-parent link. Each item references its restaurant and has a unique `id`, integer `cents` or `null`, `type` (`whole`, `strips`, `unspecified`), `dish` (`meal`, `clams-only`, `platter`), portion, included sides, availability and price note. Keep prices tax-exclusive or unknown; tax-inclusive entries require explicit model/UI support before publication.
3. Hours are a seven-day array starting Sunday. Use `null` for unrecorded hours, `[]` for explicitly closed, or `[openingMinute, closingMinute]`. After-midnight closing uses minutes above 1440: `[660, 1560]` means 11 a.m. through 2 a.m. next day. A whole `week: null` means hours are unrecorded. Attach the actual hours source and distinguish restaurant hours from takeout hours. The current schema supports one interval per day; extend the model and tests before recording split service.
4. Add its source resources to `config/sources.json`. Keep menu images as binary resources as well as their parent menu page; replacing image bytes at the same URL must be detectable. Only after manually checking the changed evidence and updating the relevant catalogue entries, accept a new fingerprint baseline using the command documented below. Arbitrary personal quotes do not need source configuration.
5. Run all checks above, build, inspect the tool, then commit the catalogue, source config/baseline, check status, documentation and tests. Push to `main` to run the Pages workflow. Do not commit `dist/`. A normal build never fetches restaurant data.
6. For a tool-level change, follow the [CoolCode lifecycle](https://github.com/jsdyer/jsdyer.github.io/blob/main/docs/tool-lifecycle.md): sync `tool.json` and the marked README guide into the hub, regenerate homepage/README/sitemap/Worker as needed, validate audit coverage, update the independent watchdog's collector and freshness probe, and record deployment evidence. Adding a restaurant inside this app does not add a new Worker route.

Areas, dish counts, filters and comparison data derive from the collection. Tests add a restaurant beyond the initial coverage. There is no hardcoded list of supported restaurant names.

## Source-change monitoring

The scheduled Pages workflow has a weekly source check and manual dispatch. A separate allowlisted schedule guard mitigates GitHub's scheduled-workflow inactivity disablement. The independent Linux watchdog should monitor this repository's Pages collector and `https://coolcode.ca/clamcounter/data/status.json`, using **`checked_at`** with a 15-day allowance for the weekly check. `reviewed_at` belongs to the manual menu review and must never be used to imply automatic price updates. No secret or API registration is required.

```sh
python3 scripts/watch_sources.py
# After actually reviewing all changed prices/hours and updating the catalogue:
python3 scripts/watch_sources.py --accept-reviewed --reviewed-at YYYY-MM-DD
```

`config/source-fingerprints.json` stores accepted source fingerprints. `web/data/status.json` records attempted and successful checks and whether a source needs review. Changed text/image evidence flags review without changing any price. Failed HTTP responses, empty pages or source mismatches preserve successful check times and publish an error status beside the unchanged editorial menu collection. After that validated status is deployed, a reporting job fails the workflow visibly. Fatal/configuration errors or malformed status stop publication. The failed check report is also saved as an artifact, and the visible age warning exposes a stale last-complete check. A check cannot verify stock, checkout totals, holidays or a price embedded in unmonitored media; editorial review is still required.

The monitor uses ordinary public HTTP requests, source-specific user agents where needed, bounded downloads and timeouts. Some sites intermittently reject automated clients. Such responses remain failures, not proof of a changed menu. The config includes the evidence resources for the current collection; maintain it when adding or changing a source.

## Privacy and limits

Searches, imported files, favourites and personal quotes stay in the browser. The app stores favourites only when selected and comparisons only when Save is selected. Its storage keys are `coolcode:clamcounter:favorites` and `coolcode:clamcounter:comparison`. Forget saved data clears those keys; export files remain under your control. Imports are size-limited and schema-validated, text is rendered without HTML interpretation, and CSV exports protect formula-like labels. No visitor input is sent to restaurant sites or embedded in analytics. CoolCode's shared script records aggregate visits.

The collection intentionally excludes prices that could only be found in stale search snippets, inaccessible dynamic menus or third-party directories. It does not rank food quality, estimate current queues, compare incompatible weights, or claim exhaustive regional coverage.
