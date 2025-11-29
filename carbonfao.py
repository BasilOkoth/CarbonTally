import os
import pandas as pd
from shapely.geometry import Point

# === Load FAO Ecological Zones ===
GEZ_SHAPEFILE_PATH = os.path.join("data", "gez2010", "gez_2010_wgs84.shp")
FAO_ECOZONES_GDF = gpd.read_file(GEZ_SHAPEFILE_PATH)

# === Load Species-Specific Allometric Coefficients ===
SPECIES_CSV_PATH = os.path.join("data", "species_allometrics.csv")
SPECIES_ALLOMETRIC_DF = pd.read_csv(SPECIES_CSV_PATH)

# Create lookup dictionary: lowercase species name -> {'a': ..., 'b': ..., 'c': ...}
SPECIES_ALLOMETRIC = {
    row["species"].strip().lower(): {"a": row["a"], "b": row["b"], "c": row["c"]}
    for _, row in SPECIES_ALLOMETRIC_DF.iterrows()
}

def get_ecological_zone(lat, lon, gdf=FAO_ECOZONES_GDF):
    """
    Determine FAO ecological zone using geopandas shapefile lookup.
    Returns zone name from 'gez_name' column.
    """
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    point = Point(lon, lat)
    match = gdf[gdf.geometry.contains(point)]
    if not match.empty:
        return match.iloc[0]["gez_name"]
    return None

def get_zone_coefficients(zone=None, species=None):
    """
    Get biomass coefficients from species CSV or fallback to ecological zone.
    """
    # Safely clean species name
    if isinstance(species, str):
        species_key = species.strip().lower()
    else:
        species_key = ""

    # Lookup species-specific coefficients
    if species_key in SPECIES_ALLOMETRIC:
        return SPECIES_ALLOMETRIC[species_key]

    # If not found, fallback to ecological zone
    zone_table = {
        "Tropical Rainforest": {"a": 0.0509, "b": 2.4, "c": 1},
        "Tropical Moist Forest": {"a": 0.060, "b": 2.3, "c": 1},
        "Tropical Dry Forest": {"a": 0.045, "b": 2.5, "c": 1},
        "Temperate Forest": {"a": 0.034, "b": 2.6, "c": 1},
        "Subtropical Northern Hemisphere": {"a": 0.030, "b": 2.4, "c": 1},
        "Subtropical Southern Hemisphere": {"a": 0.035, "b": 2.3, "c": 1},
    }

    if zone in zone_table:
        return zone_table[zone]

    # Default fallback if both zone and species are missing or unknown
    return {"a": 0.25, "b": 2.0, "c": 1.0}

def calculate_co2_sequestered(dbh_cm=None, height_m=None, rcd_cm=None, species=None, latitude=None, longitude=None):
    """
    Calculate CO₂ sequestered by a tree based on its dimensions and location.

    Args:
        dbh_cm (float): Diameter at breast height in centimeters
        height_m (float): Tree height in meters
        rcd_cm (float): Root collar diameter in centimeters (used if DBH is not provided)
        species (str, optional): Tree species scientific name
        latitude (float, optional): Geographic latitude
        longitude (float, optional): Geographic longitude

    Returns:
        float: CO₂ sequestered in kg/year
    """
    # Estimate DBH from RCD if DBH not provided
    if dbh_cm is None and rcd_cm is not None:
        dbh_cm = rcd_cm * 0.8  # approximate conversion

    if not isinstance(dbh_cm, (int, float)) or not isinstance(height_m, (int, float)):
        raise ValueError("DBH (or RCD) and height must be numeric values")
    if dbh_cm <= 0 or height_m <= 0:
        return 0.0

    zone = None
    if latitude is not None and longitude is not None:
        try:
            zone = get_ecological_zone(float(latitude), float(longitude))
        except (TypeError, ValueError):
            pass

    coeffs = get_zone_coefficients(zone, species)
    a, b, c = coeffs["a"], coeffs["b"], coeffs["c"]

    agb_kg = a * (dbh_cm ** b) * (height_m ** c)
    total_biomass = agb_kg * 1.2
    dry_weight = total_biomass * 0.725
    carbon_kg = dry_weight * 0.5
    co2_kg = carbon_kg * 3.67

    return co2_kg
