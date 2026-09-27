"""
Niche catalogue: what a person types ("dentists", "real estate agency",
"avocat") → the OpenStreetMap tag filters that find those businesses, plus the
Google / Yelp search term. Unknown niches fall back to a tag-value + name match.
"""

from __future__ import annotations

import re
import unicodedata

import taxonomy

# key: (label, synonyms (any language), overpass filters)
_N = {
    # ---------------- health ----------------
    "dentist": ("Dentists", "dentist dental dentiste zahnarzt dentista tandarts orthodontist dental clinic",
                ['["amenity"="dentist"]', '["healthcare"="dentist"]']),
    "doctor": ("Doctors & clinics", "doctor doctors physician gp medecin arzt medico clinic clinique klinik medical practice",
               ['["amenity"="doctors"]', '["amenity"="clinic"]', '["healthcare"~"^(doctor|clinic)$"]']),
    "pharmacy": ("Pharmacies", "pharmacy pharmacie apotheke farmacia chemist drugstore",
                 ['["amenity"="pharmacy"]', '["shop"="chemist"]']),
    "hospital": ("Hospitals", "hospital hopital krankenhaus ospedale hospital", ['["amenity"="hospital"]']),
    "veterinary": ("Veterinarians", "vet vets veterinary veterinarian veterinaire tierarzt veterinario animal clinic",
                   ['["amenity"="veterinary"]']),
    "physiotherapist": ("Physiotherapists", "physio physiotherapy physiotherapist kine kinesitherapeute physiotherapie fisioterapia chiropractor osteopath",
                        ['["healthcare"~"^(physiotherapist|chiropractor|osteopath)$"]', '["healthcare:speciality"~"physiotherapy|chiropract|osteopath"]']),
    "optician": ("Opticians", "optician optics optometrist opticien optiker ottico eyewear glasses",
                 ['["shop"="optician"]', '["healthcare"="optometrist"]']),
    "psychologist": ("Psychologists & therapists", "psychologist psychotherapist therapist psychologue psychologe counselling",
                     ['["healthcare"~"^(psychotherapist|counselling)$"]', '["office"="psychologist"]']),
    "nursing_home": ("Nursing homes", "nursing home care home elderly care retirement home ehpad pflegeheim",
                     ['["social_facility"~"nursing_home|assisted_living"]', '["amenity"="nursing_home"]']),
    "laboratory": ("Medical labs", "medical laboratory lab laboratoire labor", ['["healthcare"="laboratory"]']),
    # ---------------- beauty & wellness ----------------
    "hairdresser": ("Hair salons & barbers", "hairdresser hair salon barber barbershop coiffeur friseur parrucchiere peluqueria",
                    ['["shop"="hairdresser"]']),
    "beauty": ("Beauty salons", "beauty salon beauty institut de beaute kosmetik estetica nail salon nails spa lashes",
               ['["shop"="beauty"]', '["shop"="cosmetics"]']),
    "spa": ("Spas & massage", "spa massage wellness sauna hammam", ['["leisure"="sauna"]', '["shop"="massage"]', '["amenity"="spa"]', '["leisure"="spa"]']),
    "tattoo": ("Tattoo studios", "tattoo tattoo studio tatouage piercing", ['["shop"="tattoo"]']),
    "gym": ("Gyms & fitness", "gym gyms fitness fitness center fitnessstudio salle de sport crossfit yoga pilates",
            ['["leisure"="fitness_centre"]', '["sport"~"fitness|yoga|pilates|crossfit"]["leisure"~"sports_centre|fitness_centre"]']),
    # ---------------- food & drink ----------------
    "restaurant": ("Restaurants", "restaurant restaurants ristorante restaurante gaststatte brasserie bistro eatery",
                   ['["amenity"="restaurant"]']),
    "cafe": ("Cafés & coffee shops", "cafe cafes coffee coffee shop cafeteria kaffee", ['["amenity"="cafe"]']),
    "bar": ("Bars & pubs", "bar bars pub pubs kneipe cocktail bar lounge", ['["amenity"~"^(bar|pub|biergarten)$"]']),
    "nightclub": ("Nightclubs", "nightclub club disco discotheque", ['["amenity"="nightclub"]']),
    "fast_food": ("Fast food", "fast food burger pizza kebab takeaway snack", ['["amenity"="fast_food"]']),
    "bakery": ("Bakeries", "bakery bakeries boulangerie backerei panaderia panetteria patisserie pastry",
               ['["shop"~"^(bakery|pastry|confectionery)$"]']),
    "butcher": ("Butchers", "butcher boucherie metzgerei carniceria macelleria", ['["shop"="butcher"]']),
    "catering": ("Caterers", "catering caterer traiteur", ['["craft"="caterer"]', '["shop"="caterer"]']),
    "winery": ("Wineries & wine shops", "winery wine shop cave a vin vineyard weingut bodega wine",
               ['["craft"="winery"]', '["shop"="wine"]']),
    "brewery": ("Breweries", "brewery brasserie artisanale brauerei craft beer", ['["craft"="brewery"]']),
    "supermarket": ("Supermarkets & grocers", "supermarket grocery grocer epicerie supermarche supermarkt convenience store",
                    ['["shop"~"^(supermarket|convenience|greengrocer|deli)$"]']),
    # ---------------- lodging & travel ----------------
    "hotel": ("Hotels", "hotel hotels motel hostel guest house b&b bed and breakfast inn",
              ['["tourism"~"^(hotel|motel|hostel|guest_house|apartment)$"]']),
    "travel_agency": ("Travel agencies", "travel agency travel agent agence de voyage reiseburo tour operator",
                      ['["shop"="travel_agency"]', '["office"="travel_agent"]']),
    "car_rental": ("Car rental", "car rental rent a car location de voiture autovermietung", ['["amenity"="car_rental"]']),
    "taxi": ("Taxi & transport", "taxi limousine chauffeur transport company", ['["office"="taxi"]', '["amenity"="taxi"]']),
    # ---------------- professional services ----------------
    "lawyer": ("Lawyers & law firms", "lawyer lawyers attorney law firm solicitor avocat anwalt rechtsanwalt abogado avvocato notary notaire notar",
               ['["office"~"^(lawyer|notary)$"]']),
    "accountant": ("Accountants", "accountant accountants accounting cpa bookkeeper expert comptable steuerberater contable commercialista tax advisor",
                   ['["office"~"^(accountant|tax_advisor|financial)$"]']),
    "real_estate": ("Real estate agencies", "real estate estate agent realtor realty property agency immobilier agence immobiliere immobilien makler inmobiliaria immobiliare",
                    ['["office"="estate_agent"]', '["shop"="estate_agent"]']),
    "insurance": ("Insurance agencies", "insurance insurance agent assurance versicherung seguros assicurazioni",
                  ['["office"="insurance"]']),
    "financial": ("Financial advisors", "financial advisor wealth management financial services conseiller financier finanzberater",
                  ['["office"~"^(financial|financial_advisor)$"]']),
    "bank": ("Banks", "bank banks banque banco", ['["amenity"="bank"]']),
    "marketing": ("Marketing & ad agencies", "marketing agency advertising agency digital agency ad agency seo agency agence marketing werbeagentur agencia de marketing",
                  ['["office"~"^(advertising_agency|marketing)$"]']),
    "it": ("IT & software companies", "it company software company web agency web design web developer tech company it services informatique softwarefirma",
           ['["office"~"^(it|software|telecommunication)$"]', '["craft"="computer"]']),
    "consulting": ("Consultancies", "consulting consultant consultancy management consulting conseil beratung",
                   ['["office"="consulting"]']),
    "architect": ("Architects", "architect architects architecture firm architecte architekt arquitecto", ['["office"="architect"]']),
    "engineer": ("Engineering firms", "engineering firm engineers bureau d etudes ingenieurburo", ['["office"="engineer"]']),
    "employment": ("Recruitment agencies", "recruitment agency staffing employment agency headhunter recruiter interim personalvermittlung",
                   ['["office"="employment_agency"]']),
    "coworking": ("Coworking spaces", "coworking co-working shared office", ['["amenity"="coworking_space"]', '["office"="coworking"]']),
    "photographer": ("Photographers", "photographer photography studio photographe fotograf",
                     ['["craft"="photographer"]', '["shop"="photo"]', '["office"="photographer"]']),
    "printing": ("Print shops", "printing print shop printer copy shop imprimerie druckerei", ['["shop"="copyshop"]', '["craft"="printer"]']),
    "translator": ("Translation agencies", "translation translator translation agency traduction ubersetzung", ['["office"="translator"]']),
    "event": ("Event & wedding planners", "event planner wedding planner events agency evenementiel", ['["office"="event_management"]', '["shop"="wedding"]']),
    "security": ("Security companies", "security company guard services securite sicherheitsdienst", ['["office"="security"]']),
    "logistics": ("Logistics & freight", "logistics freight courier shipping company transport logistique spedition",
                  ['["office"~"^(logistics|courier|moving_company)$"]', '["shop"="storage_rental"]']),
    "ngo": ("NGOs & associations", "ngo association nonprofit charity foundation verein", ['["office"~"^(ngo|association|foundation|charity)$"]']),
    "company": ("Company offices", "company companies corporate office business office entreprise firma", ['["office"="company"]']),
    # ---------------- trades & home ----------------
    "plumber": ("Plumbers", "plumber plumbing plombier klempner sanitar fontanero idraulico", ['["craft"="plumber"]']),
    "electrician": ("Electricians", "electrician electrical electricien elektriker electricista elettricista", ['["craft"="electrician"]']),
    "hvac": ("HVAC & heating", "hvac heating air conditioning chauffagiste heizung climatisation", ['["craft"~"^(hvac|heating_engineer)$"]']),
    "roofer": ("Roofers", "roofer roofing couvreur dachdecker", ['["craft"="roofer"]']),
    "carpenter": ("Carpenters & joiners", "carpenter joiner menuisier schreiner tischler carpintero", ['["craft"~"^(carpenter|joiner|cabinet_maker)$"]']),
    "painter": ("Painters & decorators", "painter painting decorator peintre maler", ['["craft"~"^(painter|plasterer)$"]']),
    "builder": ("Builders & contractors", "builder construction contractor general contractor construction company btp bauunternehmen construccion",
                ['["craft"~"^(builder|construction|tiler|stonemason|bricklayer)$"]', '["office"="construction_company"]']),
    "gardener": ("Landscapers & gardeners", "landscaper landscaping gardener paysagiste gartenbau jardinero", ['["craft"="gardener"]', '["shop"="garden_centre"]']),
    "cleaning": ("Cleaning services", "cleaning cleaning company cleaners nettoyage reinigung limpieza janitorial", ['["craft"="cleaning"]', '["office"="cleaning"]', '["shop"="dry_cleaning"]', '["shop"="laundry"]']),
    "locksmith": ("Locksmiths", "locksmith serrurier schlusseldienst", ['["craft"="locksmith"]', '["shop"="locksmith"]']),
    "solar": ("Solar installers", "solar solar panels solar installer photovoltaique photovoltaik", ['["craft"="solar"]', '["office"="energy_supplier"]']),
    "furniture": ("Furniture stores", "furniture furniture store meubles mobel muebles interior design", ['["shop"~"^(furniture|interior_decoration|kitchen)$"]']),
    "hardware": ("Hardware & DIY", "hardware store diy quincaillerie baumarkt ferreteria", ['["shop"~"^(hardware|doityourself|trade)$"]']),
    # ---------------- auto ----------------
    "car_dealer": ("Car dealers", "car dealer car dealership auto dealer concessionnaire autohaus concesionario used cars",
                   ['["shop"="car"]']),
    "car_repair": ("Car repair & garages", "car repair garage mechanic auto repair garagiste autowerkstatt taller mecanico body shop",
                   ['["shop"~"^(car_repair|tyres|car_parts)$"]', '["craft"="car_repair"]']),
    "car_wash": ("Car washes", "car wash lavage auto waschanlage", ['["amenity"="car_wash"]']),
    "driving_school": ("Driving schools", "driving school auto ecole fahrschule autoescuela", ['["amenity"="driving_school"]']),
    # ---------------- retail ----------------
    "clothes": ("Clothing & fashion stores", "clothing store clothes fashion boutique apparel vetements mode bekleidung ropa",
                ['["shop"~"^(clothes|boutique|fashion|shoes|bag|fashion_accessories)$"]']),
    "jewelry": ("Jewelry stores", "jewelry jewellery jeweler bijouterie juwelier joyeria", ['["shop"="jewelry"]', '["craft"="jeweller"]']),
    "electronics": ("Electronics & phone shops", "electronics phone shop mobile phone repair computer store", ['["shop"~"^(electronics|mobile_phone|computer)$"]']),
    "florist": ("Florists", "florist flower shop fleuriste blumen floristeria", ['["shop"="florist"]']),
    "bookstore": ("Bookstores", "bookstore bookshop librairie buchhandlung libreria", ['["shop"="books"]']),
    "pet_shop": ("Pet shops & grooming", "pet shop pet store animalerie zoohandlung grooming", ['["shop"~"^(pet|pet_grooming)$"]']),
    "sports_shop": ("Sports shops", "sports shop sporting goods bike shop cycle shop velo", ['["shop"~"^(sports|bicycle|outdoor)$"]']),
    "cosmetics": ("Cosmetics & perfume", "cosmetics perfume parfumerie parfumerie", ['["shop"~"^(cosmetics|perfumery)$"]']),
    "toys": ("Toy stores", "toy store toys jouets spielwaren", ['["shop"="toys"]']),
    "gift": ("Gift & souvenir shops", "gift shop souvenir", ['["shop"~"^(gift|art|craft)$"]']),
    # ---------------- education ----------------
    "school": ("Schools", "school schools ecole schule escuela scuola private school",
               ['["amenity"="school"]']),
    "language_school": ("Language schools", "language school ecole de langues sprachschule academia de idiomas",
                        ['["amenity"="language_school"]']),
    "training": ("Training centers & tutoring", "tutoring training center coaching formation nachhilfe academy",
                 ['["amenity"~"^(training|prep_school|music_school|dancing_school)$"]', '["office"="educational_institution"]']),
    "kindergarten": ("Kindergartens & childcare", "kindergarten daycare childcare nursery creche kita guarderia", ['["amenity"~"^(kindergarten|childcare)$"]']),
    "university": ("Universities & colleges", "university college universite universitat universidad", ['["amenity"~"^(university|college)$"]']),
    # ---------------- leisure ----------------
    "golf": ("Golf clubs", "golf golf club golf course", ['["leisure"="golf_course"]']),
    "sports_club": ("Sports clubs", "sports club football club tennis club sports centre", ['["leisure"="sports_centre"]', '["club"="sport"]']),
    "cinema": ("Cinemas & theatres", "cinema theatre theater kino", ['["amenity"~"^(cinema|theatre)$"]']),
    "museum": ("Museums & galleries", "museum gallery musee galerie", ['["tourism"~"^(museum|gallery)$"]']),
    "attraction": ("Attractions & activities", "attraction escape room bowling amusement park", ['["tourism"~"^(attraction|theme_park)$"]', '["leisure"~"^(amusement_arcade|bowling_alley|escape_game)$"]']),
    "wedding_venue": ("Event venues", "event venue wedding venue banquet hall salle de reception", ['["amenity"~"^(events_venue|conference_centre)$"]']),
    # ---------------- other ----------------
    "church": ("Places of worship", "church mosque temple synagogue eglise kirche", ['["amenity"="place_of_worship"]']),
    "funeral": ("Funeral homes", "funeral home funeral directors pompes funebres bestattung", ['["shop"="funeral_directors"]']),
    "manufacturer": ("Manufacturers & factories", "manufacturer factory manufacturing industrial company usine fabrik",
                     ['["man_made"="works"]["name"]', '["industrial"]["name"]', '["craft"~"^(metal_construction|window_construction|sawmill)$"]']),
    "wholesale": ("Wholesalers", "wholesale wholesaler distributor grossiste grosshandel", ['["shop"="wholesale"]', '["wholesale"]']),
    "coworking_it": ("Startups", "startup startups", ['["office"~"^(company|it)$"]["website"]']),
    # every business in the area, whatever it does
    "all": ("All businesses", "all businesses every business all companies everything",
            ['["shop"]["name"]', '["office"]["name"]', '["craft"]["name"]', '["healthcare"]["name"]',
             '["amenity"~"^(restaurant|cafe|bar|pub|fast_food|dentist|doctors|clinic|pharmacy|bank|veterinary|'
             'car_rental|car_wash|driving_school|nightclub|language_school|kindergarten|coworking_space|'
             'events_venue|ice_cream|biergarten)$"]["name"]',
             '["tourism"~"^(hotel|motel|hostel|guest_house|apartment)$"]["name"]',
             '["leisure"~"^(fitness_centre|sports_centre|spa|sauna|dance)$"]["name"]']),
}
ALL_KEY = "all"


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]", " ", s.lower())).strip()


def _singular(w: str) -> str:
    for suf, rep in (("ies", "y"), ("shes", "sh"), ("ches", "ch"), ("sses", "ss"), ("s", "")):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[: -len(suf)] + rep
    return w


_INDEX: list[tuple[str, str]] = []
for _k, (_label, _syn, _f) in _N.items():
    # synonyms are one space-separated string, so index every 1-, 2- and 3-word run of it
    words = _fold(_syn).split()
    phrases = set(words)
    for i in range(len(words) - 1):
        phrases.add(words[i] + " " + words[i + 1])
    for i in range(len(words) - 2):
        phrases.add(" ".join(words[i:i + 3]))
    phrases.add(_fold(_label))
    phrases.add(_k.replace("_", " "))
    for ph in phrases:
        _INDEX.append((ph, _k))

_GENERIC_WORDS = {"store", "shop", "company", "agency", "services", "service", "office", "center", "centre",
                  "clinic", "studio", "home", "school", "club", "and", "de", "a", "la", "le", "the", "in", "for"}


def match(text: str) -> dict:
    """Resolve a typed niche to {key, label, filters, term, exact}."""
    t = _fold(text)
    words = [_singular(w) for w in t.split()]
    t_sing = " ".join(words)
    best, best_len = None, 0
    for ph, key in _INDEX:
        phs = " ".join(_singular(w) for w in ph.split())
        if ph in _GENERIC_WORDS or phs in _GENERIC_WORDS:
            continue
        if t in (ph, phs) or t_sing in (ph, phs):
            return _pack(key, text, True)
        if re.search(rf"\b{re.escape(phs)}\b", t_sing) and len(phs) > best_len:
            best, best_len = key, len(phs)
    if best:
        return _pack(best, text, True)
    return _generic(text)


def _pack(key, text, exact):
    label, syn, filters = _N[key]
    return {"key": key, "label": label, "filters": list(filters), "term": text.strip(), "exact": exact,
            "overture": taxonomy.OVERTURE.get(key, []), "keywords": [], "words": syn.split()[:4]}


def _generic(text: str) -> dict:
    t = _fold(text)
    words = [_singular(w) for w in t.split() if w not in _GENERIC_WORDS] or [_singular(w) for w in t.split()]
    val = "_".join(words)
    rx = "|".join(re.escape(w) for w in words if len(w) > 2) or re.escape(t)
    filters = [f'["{k}"="{val}"]' for k in ("shop", "office", "craft", "amenity", "healthcare", "leisure", "tourism")]
    filters.append(f'["name"~"{rx}",i][~"^(shop|office|craft|amenity|healthcare|tourism|leisure)$"~"."]')
    kw = [w for w in words if len(w) > 2] or [t]
    return {"key": "custom:" + val, "label": text.strip().title(), "filters": filters,
            "term": text.strip(), "exact": False, "overture": [], "keywords": kw, "words": kw}


def catalogue() -> list[dict]:
    order = [ALL_KEY] + [k for k in _N if k not in (ALL_KEY, "coworking_it")]
    return [{"key": k, "label": _N[k][0], "hint": _N[k][1].split()[0]} for k in order]


def split_niches(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\n|]+", s or "") if x.strip()]
