def get_ecological_zone(lat, lon):
    """Determine ecological zone based on latitude"""
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
        
    if lat < -23.5:
        return "Subtropical Southern Hemisphere"
    elif lat > 23.5:
        return "Subtropical Northern Hemisphere"
    elif -10 <= lat <= 10:
        return "Tropical Rainforest"
    elif -23.5 <= lat < -10:
        return "Tropical Dry Forest"
    elif 10 < lat <= 23.5:
        return "Tropical Moist Forest"
    else:
        return "Temperate Forest"

def calculate_co2_sequestered(dbh_cm, height_m, species=None, latitude=None, longitude=None):
    """
    Calculate CO₂ sequestered by a tree based on its dimensions and location.
    
    Args:
        dbh_cm (float): Diameter at breast height in centimeters
        height_m (float): Tree height in meters
        species (str, optional): Tree species scientific name
        latitude (float, optional): Geographic latitude
        longitude (float, optional): Geographic longitude
        
    Returns:
        float: CO₂ sequestered in kg/year
        
    Notes:
        Uses FAO coefficients for different ecological zones when location is provided.
        Falls back to generic coefficients when location is unknown.
    """
    # Validate inputs
    if not isinstance(dbh_cm, (int, float)) or not isinstance(height_m, (int, float)):
        raise ValueError("DBH and height must be numeric values")
    if dbh_cm <= 0 or height_m <= 0:
        return 0.0

    def get_zone_coefficients(zone, species=None):
        """Get biomass coefficients for the ecological zone"""
        # Future enhancement: could add species-specific coefficients here
        table = {
            "Tropical Rainforest": {"a": 0.0509, "b": 2.4, "c": 1},
            "Tropical Moist Forest": {"a": 0.060, "b": 2.3, "c": 1},
            "Tropical Dry Forest": {"a": 0.045, "b": 2.5, "c": 1},
            "Temperate Forest": {"a": 0.034, "b": 2.6, "c": 1},
            "Subtropical Northern Hemisphere": {"a": 0.030, "b": 2.4, "c": 1},
            "Subtropical Southern Hemisphere": {"a": 0.035, "b": 2.3, "c": 1},
        }
        return table.get(zone)

    # Determine ecological zone if coordinates available
    zone = None
    if latitude is not None and longitude is not None:
        try:
            zone = get_ecological_zone(float(latitude), float(longitude))
        except (TypeError, ValueError):
            pass

    # Get appropriate coefficients
    coeffs = get_zone_coefficients(zone, species) if zone else None
    if coeffs:
        a, b, c = coeffs["a"], coeffs["b"], coeffs["c"]
    else:
        # Default coefficients when zone is unknown
        a, b, c = 0.25, 2.0, 1.0

    # Calculate above-ground biomass (AGB)
    agb_kg = a * (dbh_cm ** b) * (height_m ** c)
    
    # Convert to total biomass (assuming root:shoot ratio of 0.2)
    total_biomass = agb_kg * 1.2
    
    # Convert to dry weight (assuming 72.5% dry matter)
    dry_weight = total_biomass * 0.725
    
    # Convert to carbon (assuming 50% carbon content)
    carbon_kg = dry_weight * 0.5
    
    # Convert to CO₂ equivalent (molecular weight ratio)
    co2_kg = carbon_kg * 3.67
    
    return co2_kg
