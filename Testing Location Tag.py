import exifread

import requests

def get_city_country(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10&addressdetails=1"
        headers = {"User-Agent": "geo-exif-script/1.0"}
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        address = data.get("address", {})
        city = address.get("city") or address.get("town") or address.get("village") or address.get("hamlet") or address.get("municipality") or address.get("county")
        country = address.get("country")
        return city, country
    except Exception as e:
        print(f"Error fetching city/country: {e}")
        return None, None

def get_address_city_country(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        headers = {"User-Agent": "geo-exif-script/1.0"}
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        address = data.get("address", {})
        display_address = data.get("display_name")
        city = address.get("city") or address.get("town") or address.get("village") or address.get("hamlet") or address.get("municipality") or address.get("county")
        country = address.get("country")
        return display_address, city, country
    except Exception as e:
        print(f"Error fetching address/city/country: {e}")
        return None, None, None


def get_exif_data(image_path):
    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f, details=False)
    return tags

def convert_to_degrees(value):
    d, m, s = value.values
    d = float(d.num) / float(d.den)
    m = float(m.num) / float(m.den)
    s = float(s.num) / float(s.den)
    return d + (m / 60.0) + (s / 3600.0)

def get_lat_lon(tags):
    try:
        gps_latitude = tags.get('GPS GPSLatitude')
        gps_latitude_ref = tags.get('GPS GPSLatitudeRef')
        gps_longitude = tags.get('GPS GPSLongitude')
        gps_longitude_ref = tags.get('GPS GPSLongitudeRef')
        if not gps_latitude or not gps_latitude_ref or not gps_longitude or not gps_longitude_ref:
            return None, None
        lat = convert_to_degrees(gps_latitude)
        if gps_latitude_ref.values[0] != 'N':
            lat = -lat
        lon = convert_to_degrees(gps_longitude)
        if gps_longitude_ref.values[0] != 'E':
            lon = -lon
        return lat, lon
    except Exception as e:
        print(f"Error extracting GPS data: {e}")
        return None, None

def get_datetime_taken(tags):
    # Try to get the original date/time the photo was taken
    date_time = tags.get('EXIF DateTimeOriginal')
    if date_time:
        return str(date_time)
    # Fallback to digitized or modified date/time
    date_time = tags.get('EXIF DateTimeDigitized') or tags.get('Image DateTime')
    if date_time:
        return str(date_time)
    return None

image_path = 'rear.png'
tags = get_exif_data(image_path)
lat, lon = get_lat_lon(tags)
date_time = get_datetime_taken(tags)
if lat is not None and lon is not None:
    address, city, country = get_address_city_country(lat, lon)
    if address:
        print(f"Address: {address}")
    else:
        print("Could not determine city and country from coordinates.")
else:
    print("No GPS location data found in the image.")
if date_time:
    print(f"Date/Time Taken: {date_time}")
else:
    print("No date/time information found in the image.")


