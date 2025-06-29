# KoBo Toolkit Integration Guide

This document provides instructions for setting up and using the KoBo Toolkit integration with the Tree Monitoring application.

## Overview

The integration allows users to:
1. Launch a KoBo form directly from the "Plant a Tree" section
2. Capture planting data including geolocation coordinates
3. Generate a unique tree ID and QR code
4. Store all data in the application's database

## Setup Instructions

### 1. KoBo Toolbox Configuration

1. Create a KoBo Toolbox account at [https://www.kobotoolbox.org/](https://www.kobotoolbox.org/) if you don't have one
2. Create a form with the following fields (at minimum):
   - institution (text)
   - local_name (text)
   - scientific_name (text)
   - student_name (text)
   - date_planted (date)
   - tree_stage (select: Seedling, Sapling, Mature)
   - rcd_cm (decimal)
   - dbh_cm (decimal)
   - height_m (decimal)
   - _geolocation (geopoint - this is built-in)
   - country (text)
   - county (text)
   - sub_county (text)
   - ward (text)
   - notes (text)

3. Deploy your form and note the Asset ID (found in the URL when viewing the form)
4. Generate an API token:
   - Go to your KoBo account settings
   - Navigate to the API section
   - Generate a new token and copy it

### 2. Application Configuration

1. Open `app.py` and update the KoBo configuration section:
   ```python
   # KoBo Toolbox configuration
   KOBO_API_URL = "https://kf.kobotoolbox.org/api/v2"  # Use kc.kobotoolbox.org for legacy API
   KOBO_API_TOKEN = "your_kobo_api_token"  # Replace with your actual token
   KOBO_ASSET_ID = "your_asset_id"  # Replace with your actual asset ID
   ```

2. Open `kobo_integration.py` and update the same configuration variables there

### 3. Database Setup

The application will automatically create the necessary database tables when it first runs. Make sure the data directory exists and is writable:

```bash
mkdir -p /path/to/app/data
mkdir -p /path/to/app/data/qr_codes
```

## Usage Instructions

### Planting a Tree

1. Log in to the application as an admin, institution user, or field agent
2. Navigate to the "Plant a Tree" section
3. Click the "Open Tree Planting Form" button
4. Complete the KoBo form, making sure to capture the geolocation
5. Submit the form
6. Return to the application and click "I've Completed the Form"
7. The application will check for new submissions and process them
8. Upon successful processing, you'll see the tree details and QR code

### QR Code Usage

The QR code contains the unique tree ID and can be used for:
- Quick tree identification in the field
- Monitoring and updating tree status
- Linking to adoption and payment systems

## Troubleshooting

### Form Not Launching

- Check that your KoBo API token and Asset ID are correct
- Ensure your KoBo form is deployed and active
- Verify internet connectivity

### Submissions Not Appearing

- Check that you're using the same KoBo account that owns the form
- Verify the form was successfully submitted in KoBo
- Check application logs for API connection errors

### Database Errors

- Ensure the data directory exists and is writable
- Check database permissions
- Verify that all required fields are present in the KoBo form

## Technical Details

### Data Flow

1. User clicks "Plant a Tree" in the application
2. KoBo form is launched in a new browser tab
3. User completes and submits the form
4. User returns to the application and confirms submission
5. Application queries KoBo API for recent submissions
6. New submissions are processed:
   - Data is mapped to database schema
   - Tree ID is generated
   - CO2 sequestration is calculated
   - QR code is generated and saved as PNG
   - All data is stored in the database

### Files

- `app.py`: Main application file
- `kobo_integration.py`: KoBo integration module
- `tests/`: Test suite for validation
- `data/`: Database and QR code storage
- `data/qr_codes/`: Directory for QR code PNG files

## Testing

Run the test suite to verify the integration:

```bash
python run_tests.py
```

All tests should pass, confirming that:
- KoBo form fields map correctly to the database
- Tree IDs are generated properly
- QR codes are created and stored as PNGs
- Database updates work correctly
