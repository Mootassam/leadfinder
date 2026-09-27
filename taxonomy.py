"""
How each niche is named by the other data sources:

* OVERTURE        — Overture Maps place categories. A place matches when any listed
                    category appears in its category hierarchy (parents included).
* NACE / NAF / SIC_UK — official activity codes used by business registries.
"""

from __future__ import annotations

_OV = {
    "dentist": "dental_clinic general_dentistry orthodontics cosmetic_dentistry pediatric_dentistry endodontics periodontics prosthodontics oral_and_maxillofacial_surgery teeth_whitening",
    "doctor": "doctors_office primary_care_or_general_clinic family_practice internal_medicine walk_in_clinic urgent_care_clinic pediatric_clinic dermatology cardiology neurology ophthalmology obstetrics_and_gynecology ear_nose_and_throat urology gastroenterology orthopedics surgery community_health_center public_health_clinic specialized_medical_facility medical_service",
    "pharmacy": "pharmacy pharmacy_and_drug_store drugstore",
    "hospital": "hospital specialty_hospital childrens_hospital emergency_department psychiatric_hospital",
    "veterinary": "veterinarian veterinary_care animal_hospital",
    "physiotherapist": "physical_therapy physical_medicine_and_rehabilitation chiropractic osteopathic_medicine sports_medicine occupational_therapy musculoskeletal_medicine",
    "optician": "eyewear_store optometry vision_or_eye_care_clinic",
    "psychologist": "psychology psychotherapy psychiatry_or_psychology_service counseling behavioral_or_mental_health_clinic psychoanalysis marriage_or_relationship_counseling family_counseling",
    "nursing_home": "retirement_home senior_living_facility assisted_living_facility home_health_care hospice",
    "laboratory": "laboratory laboratory_testing diagnostics_imaging_or_lab_service diagnostic_imaging radiology",
    "hairdresser": "hair_salon barber hair_stylist kids_hair_salon blow_dry_blow_out_service",
    "beauty": "beauty_salon nail_salon skin_care_and_makeup eyelash_service waxing hair_removal laser_hair_removal makeup_artist medical_spa tanning_salon esthetician threading_service permanent_makeup",
    "spa": "spa day_spa health_spa massage_therapy sauna public_bath_house float_spa",
    "tattoo": "tattoo tattoo_and_piercing piercing body_modification",
    "gym": "gym fitness_studio yoga_studio pilates_studio boxing_gym fitness_trainer cycle_studio rock_climbing_gym boot_camp barre_class",
    "restaurant": "restaurant casual_eatery bistro brasserie diner steakhouse",
    "cafe": "cafe coffee_shop tea_room bubble_tea_shop",
    "bar": "bar pub cocktail_bar wine_bar beer_bar gastropub sports_bar lounge hookah_bar beer_garden tapas_bar speakeasy alcoholic_beverage_venue",
    "nightclub": "dance_club nightlife_venue karaoke_venue",
    "fast_food": "fast_food_restaurant burger_restaurant pizza_restaurant doner_kebab_restaurant sandwich_shop fish_and_chips_restaurant chicken_restaurant food_truck_stand hot_dog_restaurant falafel_restaurant",
    "bakery": "bakery patisserie_cake_shop cupcake_shop custom_cakes_shop chocolatier donut_shop bagel_shop",
    "butcher": "butcher_shop meat_wholesaler",
    "catering": "caterer box_lunch_supplier personal_chef",
    "winery": "winery wine_tasting_room beer_wine_spirits_store liquor_store wine_wholesaler",
    "brewery": "brewery distillery",
    "supermarket": "grocery_store convenience_store organic_grocery_store produce_store delicatessen international_grocery_store asian_grocery_store superstore warehouse_club_store health_food_store specialty_foods_store",
    "hotel": "hotel hostel motel bed_and_breakfast guest_house inn resort lodge service_apartment holiday_rental_home",
    "travel_agency": "travel_agent tour_operator sightseeing_tour_agency travel_company vacation_rental_agent",
    "car_rental": "car_rental_service vehicle_rental_service truck_rental_service",
    "taxi": "taxi_service taxi_or_ride_share_service limo_service airport_shuttle coach_bus bus_rental",
    "lawyer": "attorney_or_law_firm legal_service notary_public paralegal_service mediator",
    "accountant": "accountant bookkeeper tax_service payroll_service",
    "real_estate": "real_estate_agent real_estate_service property_management commercial_real_estate apartment_agent home_developer real_estate_investment",
    "insurance": "insurance_agency life_insurance health_insurance_office auto_insurance",
    "financial": "financial_advising investing investment_management_company mortgage_broker broker stock_and_bond_broker trusts private_equity_firm",
    "bank": "bank bank_or_credit_union credit_union currency_exchange money_transfer_service",
    "marketing": "advertising_agency marketing_agency b2b_advertising_and_marketing_service b2b_marketing_consultant internet_marketing_service social_media_agency public_relations media_agency b2b_publicity_service",
    "it": "information_technology_company software_development it_service_and_computer_repair it_consultant web_designer web_hosting_service internet_service_provider telecommunications_company computer_hardware_company e_commerce_service",
    "consulting": "business_consulting b2b_business_management_service manufacturing_and_industrial_consultant food_and_beverage_consultant automotive_consultant",
    "architect": "architect architectural_designer landscape_architect interior_design",
    "engineer": "engineering_service civil_engineer structural_engineer mechanical_engineer land_surveying",
    "employment": "employment_agency temp_agency b2b_executive_search_consultants b2b_human_resource_service talent_agency",
    "coworking": "coworking_space shared_office_space",
    "photographer": "photography_service event_photography_service session_photography_service videographer video_film_production",
    "printing": "printing_service commercial_printer screen_printing_service t_shirt_printing_service sign_making 3d_printing_service",
    "translator": "translation_service translating_and_interpreting_service transcription_service",
    "event": "party_and_event_planning wedding_planning event_technology_service dj_service party_equipment_rental corporate_entertainment_service",
    "security": "security_service security_systems home_security private_investigation",
    "logistics": "freight_and_cargo_service courier_and_delivery_service shipping_center mover motor_freight_trucking freight_forwarding_agency b2b_transportation_and_storage_service self_storage_facility warehouse",
    "ngo": "non_governmental_association charity_organization civic_organization environmental_conservation_organization private_association volunteer_association youth_organization",
    "company": "corporate_or_business_office holding_company industrial_company b2b_service",
    "plumber": "plumbing water_heater_installation_repair septic_service bathroom_remodeling",
    "electrician": "electrician home_automation elevator_service",
    "hvac": "hvac_service hvac_supplier chimney_service fireplace_service",
    "roofer": "roofing ceiling_and_roofing_repair_and_service gutter_service",
    "carpenter": "carpenter cabinet_sales_service furniture_repair countertop_installation",
    "painter": "painting plasterer drywall_service stucco_service",
    "builder": "contractor building_contractor builder building_or_construction_service masonry_contractor masonry_concrete road_contractor demolition_service excavation_service construction_management tiling flooring_contractor kitchen_remodeling altering_and_remodeling_contractor handyman",
    "gardener": "landscaping gardener tree_service nursery_and_gardening_store lawn_service",
    "cleaning": "cleaning_service home_cleaning janitorial_service office_cleaning carpet_cleaning window_washing dry_cleaning laundry_service laundromat industrial_cleaning_service",
    "locksmith": "key_and_locksmith",
    "solar": "solar_installation energy_company energy_management_service",
    "furniture": "furniture_store home_decor_store kitchen_and_bath_store mattress_store home_goods_store lighting_store carpet_store",
    "hardware": "hardware_store home_improvement_store building_supply_store do_it_yourself_store paint_store tile_store",
    "car_dealer": "auto_dealer used_auto_dealer vehicle_dealer motorcycle_dealer truck_dealer",
    "car_repair": "automotive_repair auto_body_shop tire_shop tire_dealer_and_repair auto_parts_store auto_glass_service motorcycle_repair engine_repair_service brake_service_and_repair transmission_repair towing_service car_inspection",
    "car_wash": "car_wash auto_detailing",
    "driving_school": "driving_school traffic_school",
    "clothes": "clothing_store fashion_boutique fashion_and_apparel_store shoe_store womens_clothing_store mens_clothing_store childrens_clothing_store designer_clothing bridal_shop lingerie_store fashion_accessories_store",
    "jewelry": "jewelry_store jewelry_and_watches_manufacturer goldsmith watch_store",
    "electronics": "electronics_store mobile_phone_store computer_store mobile_phone_repair electronics_repair_shop camera_and_photography_store appliance_store",
    "florist": "florist floral_designer wholesale_florist",
    "bookstore": "bookstore used_bookstore academic_bookstore comic_books_store",
    "pet_shop": "pet_store animal_and_pet_store pet_groomer pet_care_service pet_boarding dog_trainer",
    "sports_shop": "sporting_goods_store bike_store outdoor_store sportswear_store golf_equipment_store",
    "cosmetics": "cosmetics_and_fragrance_store beauty_supply_store personal_care_and_beauty_store",
    "toys": "toy_store toys_and_games_store hobby_shop",
    "gift": "gift_shop souvenir_store arts_crafts_and_hobby_store craft_store framing_store",
    "school": "school private_school elementary_school middle_school high_school public_school montessori_school",
    "language_school": "language_school",
    "training": "tutoring_service test_preparation vocational_and_technical_school adult_education_center music_school art_school dance_studio cooking_school computer_coaching private_tutor",
    "kindergarten": "preschool child_care_and_day_care day_care_preschool",
    "university": "college_university business_school medical_school law_school",
    "golf": "golf_course golf_club driving_range country_club",
    "sports_club": "sport_or_recreation_club sports_complex football_club soccer_club fencing_club sailing_club amateur_sport_team martial_arts_club",
    "cinema": "movie_theater theatre_venue performing_arts_venue opera_and_ballet comedy_club",
    "museum": "museum art_gallery",
    "attraction": "amusement_park escape_room bowling_alley amusement_attraction arcade laser_tag go_kart_track zoo aquarium water_park miniature_golf_course indoor_playcenter",
    "wedding_venue": "event_venue exhibition_and_trade_fair_venue wedding_chapel",
    "church": "place_of_worship religious_organization",
    "funeral": "funeral_service cremation_service",
    "manufacturer": "manufacturer industrial_equipment_manufacturer machinery_and_tool_manufacturer metal_fabricator textile_manufacturer furniture_manufacturer chemical_plant plastics_company",
    "wholesale": "wholesaler supplier_or_distributor food_beverage_distributor distribution_service importer exporter import_export_service",
    "coworking_it": "information_technology_company software_development",
}
OVERTURE: dict[str, list[str]] = {k: v.split() for k, v in _OV.items()}

# places that are not businesses — dropped in "All businesses" mode
NOT_BUSINESS = (
    "parking parking_garage parking_lot park bridge river lake mountain beach public_plaza public_fountain "
    "public_restroom playground monument sculpture_statue memorial_site historic_site geographic_entities "
    "land_feature built_feature bus_station train_station metro_station light_rail_and_subway_station taxi_stand "
    "ev_charging_station atm bike_parking bike_sharing_location package_locker forest island waterfall canal pier "
    "quay cave nature_reserve national_park garden hiking_trail recreational_trail_or_path dog_park skate_park "
    "sport_court sport_field tennis_court basketball_court soccer_field water_feature cemetery street_art "
    "police_station fire_station town_hall courthouse jail_or_prison embassy military_site military_base "
    "rail_facility_or_service public_transit_facility_or_service apartment condominium campus_building "
    "building rest_stop").split()

# Official activity codes — NACE rev.2 (4 digits) serves every EU/EEA registry
NACE = {
    "dentist": ["86.23"], "doctor": ["86.21", "86.22"], "pharmacy": ["47.73"], "hospital": ["86.10"],
    "veterinary": ["75.00"], "physiotherapist": ["86.90"], "optician": ["47.78"], "psychologist": ["86.90"],
    "nursing_home": ["87.10", "87.30"], "laboratory": ["86.90"], "hairdresser": ["96.02"], "beauty": ["96.02"],
    "spa": ["96.04"], "tattoo": ["96.09"], "gym": ["93.13"], "restaurant": ["56.10"], "cafe": ["56.30"],
    "bar": ["56.30"], "nightclub": ["56.30"], "fast_food": ["56.10"], "bakery": ["10.71", "47.24"],
    "butcher": ["47.22"], "catering": ["56.21"], "winery": ["11.02", "47.25"], "brewery": ["11.05"],
    "supermarket": ["47.11"], "hotel": ["55.10", "55.20"], "travel_agency": ["79.11", "79.12"],
    "car_rental": ["77.11"], "taxi": ["49.32"], "lawyer": ["69.10"], "accountant": ["69.20"],
    "real_estate": ["68.31"], "insurance": ["66.22"], "financial": ["66.19", "66.30"], "bank": ["64.19"],
    "marketing": ["73.11", "73.12", "70.21"], "it": ["62.01", "62.02", "62.09", "63.11"],
    "consulting": ["70.22"], "architect": ["71.11"], "engineer": ["71.12"],
    "employment": ["78.10", "78.20", "78.30"], "photographer": ["74.20"], "printing": ["18.12"],
    "translator": ["74.30"], "event": ["82.30"], "security": ["80.10", "80.20"],
    "logistics": ["49.41", "52.29", "53.20"], "ngo": ["94.99"], "plumber": ["43.22"], "electrician": ["43.21"],
    "hvac": ["43.22"], "roofer": ["43.91"], "carpenter": ["43.32"], "painter": ["43.34"],
    "builder": ["41.20", "43.39", "43.99"], "gardener": ["81.30"], "cleaning": ["81.21", "81.22", "96.01"],
    "furniture": ["47.59"], "hardware": ["47.52"], "car_dealer": ["45.11"], "car_repair": ["45.20"],
    "driving_school": ["85.53"], "clothes": ["47.71"], "jewelry": ["47.77"], "electronics": ["47.42", "47.43"],
    "florist": ["47.76"], "bookstore": ["47.61"], "pet_shop": ["47.76"], "sports_shop": ["47.64"],
    "cosmetics": ["47.75"], "toys": ["47.65"], "school": ["85.20", "85.31"], "language_school": ["85.59"],
    "training": ["85.59"], "kindergarten": ["88.91", "85.10"], "university": ["85.42"], "golf": ["93.11"],
    "sports_club": ["93.12"], "cinema": ["59.14", "90.04"], "museum": ["91.02"], "funeral": ["96.03"],
    "manufacturer": ["25.62", "28.29", "25.11"], "wholesale": ["46.90"], "coworking_it": ["62.01"],
}
# France (NAF rév.2): code + letter; the subdivisions are more precise than NACE
NAF = {
    "restaurant": ["56.10A", "56.10B"], "fast_food": ["56.10C"], "hairdresser": ["96.02A"], "beauty": ["96.02B"],
    "physiotherapist": ["86.90E"], "laboratory": ["86.90B"], "psychologist": ["86.90F"], "optician": ["47.78A"],
    "bakery": ["10.71C", "10.71D", "47.24Z"], "doctor": ["86.21Z", "86.22A", "86.22B", "86.22C"],
    "hotel": ["55.10Z", "55.20Z"], "builder": ["41.20A", "41.20B", "43.39Z", "43.99C"],
    "cleaning": ["81.21Z", "81.22Z", "96.01B"], "logistics": ["49.41A", "49.41B", "52.29A", "52.29B", "53.20Z"],
    "language_school": ["85.59B"], "training": ["85.59A", "85.59B"], "kindergarten": ["88.91A", "85.10Z"],
    "car_repair": ["45.20A", "45.20B"], "winery": ["11.02A", "11.02B", "47.25Z"],
    "it": ["62.01Z", "62.02A", "62.09Z", "63.11Z"], "manufacturer": ["25.62B", "28.29B", "25.11Z"],
}
# United Kingdom (SIC 2007, 5 digits)
SIC_UK = {
    "restaurant": ["56101"], "fast_food": ["56102", "56103"], "bar": ["56302"], "cafe": ["56102"],
    "nightclub": ["56301"], "lawyer": ["69101", "69102", "69109"], "accountant": ["69201", "69202", "69203"],
    "hotel": ["55100", "55201", "55202", "55209"], "doctor": ["86210", "86220"],
    "it": ["62011", "62012", "62020", "62090", "63110"], "builder": ["41201", "41202", "43390", "43999"],
    "logistics": ["49410", "52290", "53202"], "training": ["85590", "85600"], "kindergarten": ["88910", "85100"],
    "cleaning": ["81210", "81221", "81222", "96010"], "winery": ["11020", "47250"], "bakery": ["10710", "47240"],
}


def activity_codes(key: str, scheme: str) -> list[str]:
    """Registry codes for a niche. scheme: nace | naf | sic_uk | tol (Finland, 5 digits)."""
    base = NACE.get(key, [])
    if scheme == "naf":
        return NAF.get(key) or [c + "Z" for c in base]
    if scheme == "sic_uk":
        return SIC_UK.get(key) or [c.replace(".", "") + "0" for c in base]
    if scheme == "tol":
        return [c.replace(".", "") + "0" for c in base]
    return base
