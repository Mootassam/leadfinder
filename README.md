# Lead Finder

A local B2B lead-generation app for Windows. Pick a business type and a place (a city, a region or a whole country) and Lead Finder collects the matching businesses. It then goes deeper: it finds missing websites, reads each site for emails, phones and social profiles, and lists the decision makers.

Everything runs on your own PC, and your leads never leave it.

## Data sources

| Source | Coverage | Key |
|---|---|---|
| **Overture Maps Places** | Worldwide, tens of millions of businesses | none |
| **Official business registers** | France (SIRENE), Norway (Brønnøysund), Finland (PRH) | none |
| Companies House | United Kingdom, with directors | free API key |
| OpenStreetMap (Overpass) | Worldwide | none |
| Foursquare OS Places | Worldwide, 100M+ places | free Hugging Face token |
| Google Places / Yelp | Worldwide | your own API key |

Duplicates across sources are merged automatically.

## Deepening

- **Website finder:** guesses a domain for businesses that have no website on file, and accepts it only when the page shows the business name plus its postcode, city or phone. An optional Brave Search key finds more.
- **Website visits:** reads the home, contact, imprint and team pages for emails (including obfuscated ones), phones, social profiles and people.
- **Decision makers:** owners and directors from the registers and from team pages. It works out the company's email pattern, and can ask the mail server whether a guessed mailbox exists (nothing is sent).
- **Export:** CSV, Excel, or directly into a MailBlaster group.

## Run from source

```bash
pip install -r requirements.txt
python server.py
```

Then open the printed URL (default http://127.0.0.1:5070).

## Build the Windows installer

Requires Python 3.12 and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

This produces `installer_output\LeadFinder-Setup.exe`. The installer ships the official, signed Python embeddable runtime together with the app, so Windows Smart App Control accepts it.

## Project layout

| File | Purpose |
|---|---|
| `server.py` | Flask app: API, exports, MailBlaster bridge |
| `engine.py` | Background search jobs (discover → websites → decision makers → site visits) |
| `sources.py` | Geocoding, OpenStreetMap, Google, Yelp |
| `overture.py` | Overture Maps and Foursquare, queried with DuckDB |
| `registries.py` | Official business registers |
| `enrich.py` · `people.py` · `webfind.py` · `verify.py` | Website reading, decision makers, website finder, mailbox check |
| `store.py` | SQLite storage and deduplication |
| `categories.py` · `taxonomy.py` | Business types mapped to each source's categories and activity codes |
| `static/` | Single-page interface |

Use it responsibly: follow the email laws that apply to you and to your recipients (GDPR, CAN-SPAM, CASL…), always offer an opt-out, and honour it.
