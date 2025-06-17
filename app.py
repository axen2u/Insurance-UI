import chainlit as cl
import requests
import base64
import json
import uuid
import os
import logging
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

import exifread

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

WEBHOOK_URL = "https://togn8n.cloudnavision.com/webhook/08888ef8-fa11-44fc-887b-5adb1e3353c0"
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg","image/jpg" "application/pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


# ===== EXIF-BASED LOCATION UTILITIES =====

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
        return display_address or f"{city}, {country}"
    except Exception as e:
        print(f"Error fetching address: {e}")
        return None

def extract_location_from_image(image_bytes):
    try:
        with BytesIO(image_bytes) as img_file:
            tags = exifread.process_file(img_file, details=False)
        lat, lon = get_lat_lon(tags)
        if lat is not None and lon is not None:
            return get_address_city_country(lat, lon)
    except Exception as e:
        print(f"Location extraction failed: {e}")
    return None


# ===== CHAINLIT HANDLERS =====

@cl.on_chat_start
async def start():
    cl.user_session.set("session_id", None)
    cl.user_session.set("user_name", None)
    cl.user_session.set("user_data", None)
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)

    await cl.Message(
        content=(
            "## 👋 Welcome to EverTrustLanka Insurance Claims!\n"
            "> 📁 Upload your claim documents here or use the attachment button.\n"
            "> 🤖 I'm your AI-powered claims assistant, available 24/7 to support you.\n\n"
            "How can I assist you today?\n"
            "You can start a new claim submission by typing a message.\n"
        )
    ).send()


@cl.on_message
async def main(message: cl.Message):
    user_text = message.content or ""
    files_data = []
    uploaded_names = []
    location = None

    has_files = message.elements and len(message.elements) > 0
    has_text = user_text.strip() != ""

    if has_files and not has_text:
        user_text = "File uploaded for processing"
    if not has_files and not has_text:
        await cl.Message("Please upload a file or send a message.").send()
        return

    if message.elements:
        for element in message.elements:
            if isinstance(element, (cl.File, cl.Image)):
                uploaded_names.append(element.name)
                file_content = element.content

                if file_content is None and hasattr(element, "path") and element.path:
                    if not os.path.exists(element.path) or not os.access(element.path, os.R_OK):
                        await cl.Message(f"❌ Cannot access file: {element.path}").send()
                        continue
                    try:
                        with open(element.path, "rb") as file:
                            file_content = file.read()
                    except Exception as e:
                        await cl.Message(f"❌ Failed to read '{element.name}': {str(e)}").send()
                        continue

                if element.mime not in ALLOWED_MIME_TYPES:
                    await cl.Message(f"❌ File '{element.name}' type '{element.mime}' is not allowed.").send()
                    continue

                # Extract location BEFORE any conversion
                if location is None and element.mime in ["image/jpeg", "image/png"]:
                    loc_result = extract_location_from_image(file_content)
                    if loc_result:
                        location = loc_result
                        print(f"📍 Extracted location: {location}")

                # Handle PDFs
                if element.mime == "application/pdf":
                    try:
                        from pdf2image import convert_from_bytes
                        images = convert_from_bytes(file_content, first_page=1, last_page=1)
                        if not images:
                            raise Exception("No images generated from PDF.")
                        png_buffer = BytesIO()
                        images[0].save(png_buffer, format="PNG")
                        file_content = png_buffer.getvalue()
                        element.mime = "image/png"
                        element.name = element.name.rsplit('.', 1)[0] + '.png'
                    except Exception as e:
                        await cl.Message(f"❌ Failed to convert PDF '{element.name}': {str(e)}").send()
                        continue

                # Convert JPEG to PNG AFTER extracting EXIF
                if element.mime == "image/jpeg":
                    if Image is None:
                        await cl.Message("❌ Pillow not installed for JPEG conversion.").send()
                        continue
                    try:
                        img = Image.open(BytesIO(file_content))
                        png_buffer = BytesIO()
                        img.save(png_buffer, format="PNG")
                        file_content = png_buffer.getvalue()
                        element.mime = "image/png"
                        element.name = element.name.rsplit('.', 1)[0] + '.png'
                    except Exception as e:
                        await cl.Message(f"❌ JPEG conversion failed for '{element.name}': {str(e)}").send()
                        continue

                if file_content is None:
                    await cl.Message(f"❌ No content in '{element.name}' after processing.").send()
                    continue
                elif isinstance(file_content, str):
                    file_content = file_content.encode("utf-8")

                if len(file_content) > MAX_FILE_SIZE:
                    await cl.Message(f"❌ File '{element.name}' exceeds 10MB limit.").send()
                    continue

                try:
                    base64_content = base64.b64encode(file_content).decode("utf-8")
                    files_data.append({
                        "name": element.name,
                        "type": element.mime,
                        "content_base64": base64_content
                    })
                except Exception as e:
                    await cl.Message(f"❌ Error processing file '{element.name}': {str(e)}").send()
                    continue

    session_id = cl.user_session.get("session_id")

    payload = {
        "session_id": session_id,
        "text": user_text,
        "files": files_data,
        "location": location
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        response.raise_for_status()
        try:
            resp = response.json()
            if isinstance(resp, dict):
                if "output" in resp:
                    resp_pretty = resp["output"]
                elif "message" in resp:
                    resp_pretty = resp["message"]
                else:
                    resp_pretty = json.dumps(resp, indent=2)
            else:
                resp_pretty = json.dumps(resp, indent=2)
        except ValueError:
            resp_pretty = response.text

        msg = ""
        if uploaded_names:
            msg += "**Uploaded files:** " + ", ".join(uploaded_names) + "\n"
        msg += resp_pretty

        await cl.Message(msg).send()

    except Exception as e:
        error_msg = f"❌ Failed to send data to n8n: {str(e)}"
        await cl.Message(error_msg).send()
