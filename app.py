import os
import re
import json
import random
import base64
import requests
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from PIL import Image
import io
import time

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH, override=True)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64 MB max upload

MASTER_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "MASTER_PROMPT_V1.md")

def load_master_prompt():
    if os.path.exists(MASTER_PROMPT_PATH):
        with open(MASTER_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "You are a professional video script director."

@app.route("/")
def index():
    has_key = bool(os.getenv("GEMINI_API_KEY"))
    return render_template("index.html", has_key=has_key)

@app.route("/api/status", methods=["GET"])
def get_status():
    load_dotenv(ENV_PATH, override=True)
    api_key = os.getenv("GEMINI_API_KEY", "")
    masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else ("Configured" if api_key else "Missing")
    return jsonify({
        "has_api_key": bool(api_key),
        "masked_key": masked
    })

@app.route("/api/save-key", methods=["POST"])
def save_key():
    data = request.get_json() or {}
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "API key cannot be empty"}), 400
    
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"GEMINI_API_KEY={api_key}\n")
    
    os.environ["GEMINI_API_KEY"] = api_key
    return jsonify({"success": True, "message": "API key saved successfully!"})

def optimize_image(image_bytes, max_dim=1280, quality=85):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        if w > max_dim or h > max_dim:
            if w > h:
                new_h = int(h * (max_dim / w))
                new_w = max_dim
            else:
                new_w = int(w * (max_dim / h))
                new_h = max_dim
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=quality, optimize=True)
        return out_buf.getvalue(), "image/jpeg"
    except Exception as e:
        return image_bytes, "image/jpeg"

def extract_safe_garment_crop(image_bytes, index=0):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        # If portrait aspect ratio (model photo), tightly crop to central garment:
        # Cuts off:
        # - Left & right bare arms (crops x from 22% to 78%)
        # - Top face, neck & cleavage (crops y starting from 34%)
        # - Bottom thighs, legs & groin (crops y ending at 64%)
        if h > w * 1.1:
            crop_box = (int(w * 0.22), int(h * 0.34), int(w * 0.78), int(h * 0.64))
            cropped = img.crop(crop_box)
        else:
            cropped = img
        
        save_dir = os.path.join(os.path.dirname(__file__), "static", "safe_crops")
        os.makedirs(save_dir, exist_ok=True)
        
        out_filename = f"safe_product_{int(time.time())}_{index+1}.jpg"
        out_path = os.path.join(save_dir, out_filename)
        cropped.save(out_path, format="JPEG", quality=95)
        return f"/static/safe_crops/{out_filename}"
    except Exception as e:
        print("Crop error:", e)
        return None

@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        duration = request.form.get("duration", "30 seconds")
        language = request.form.get("language", "Hinglish")
        presentation_mode = request.form.get("presentation_mode", "Magic Transition")
        category_hint = request.form.get("category_hint", "Auto-detect")
        notes = request.form.get("notes", "").strip()
        custom_key = request.form.get("api_key", "").strip()
        load_dotenv(ENV_PATH, override=True)
        api_key = custom_key or os.getenv("GEMINI_API_KEY", "")

        if not api_key:
            return jsonify({"error": "Gemini API key is required. Please configure your key in .env or provide it in the request."}), 400

        # Files handling
        creator_file = request.files.get("creator_image")
        product_files = request.files.getlist("product_images")

        if not creator_file:
            return jsonify({"error": "Creator reference photo is required."}), 400
        if not product_files or len(product_files) == 0 or product_files[0].filename == '':
            return jsonify({"error": "At least one Meesho product photo is required."}), 400

        # Auto-extract safe "Only Clothes" crops for ALL uploaded product photos
        safe_crop_urls = []
        for idx, p_file in enumerate(product_files):
            raw_p_bytes = p_file.read()
            p_file.seek(0)
            crop_url = extract_safe_garment_crop(raw_p_bytes, idx)
            if crop_url:
                safe_crop_urls.append(crop_url)

        # Read & optimize images into base64 parts
        contents_parts = []

        # 1. Creator Image
        raw_creator_bytes = creator_file.read()
        creator_bytes, creator_mime = optimize_image(raw_creator_bytes)
        contents_parts.append({
            "text": "CREATOR REFERENCE IMAGE (Treat this image as CREATOR_REFERENCE for 100% identity lock: exact face, hair, body shape silhouette, height, and natural body proportions):"
        })
        contents_parts.append({
            "inlineData": {
                "mimeType": creator_mime,
                "data": base64.b64encode(creator_bytes).decode("utf-8")
            }
        })

        # 2. Product Images
        for idx, p_file in enumerate(product_files):
            raw_p_bytes = p_file.read()
            p_bytes, p_mime = optimize_image(raw_p_bytes)
            contents_parts.append({
                "text": f"PRODUCT REFERENCE IMAGE {idx+1} (Treat this image as PRODUCT_REFERENCE_{idx+1:02d}):"
            })
            contents_parts.append({
                "inlineData": {
                    "mimeType": p_mime,
                    "data": base64.b64encode(p_bytes).decode("utf-8")
                }
            })

        # 3. User instructions
        prompt_instruction = f"""
Please generate the complete professional short-form video script according to the MASTER PROMPT instructions.

USER PREFERENCES:
- Target Duration: {duration} (Strictly between Minimum 10 Seconds and Maximum 60 Seconds / 01:00)
- Spoken Language: {language}
- DURATION, SCENE PACING & WORD COUNT STRICT RULES (MINIMUM 10s, MAXIMUM 60s):
  * Absolute Enforced Boundaries: MINIMUM 10 SECONDS, MAXIMUM 60 SECONDS (01:00). Every scene timestamp MUST start at 00:00 and end within the target duration (never exceeding 01:00).
  * 10s (Minimum 10s): 2 to 3 fast-paced scenes (00:00 - 00:10), strictly 25-30 total spoken words. Instant hook ➔ price drop ➔ CTA.
  * 15-20s: 3 to 4 fast scenes (00:00 - 00:20), strictly 45-55 total spoken words.
  * 30s (Standard Reel): 4 balanced scenes (00:00 - 00:30), strictly 75-90 total spoken words.
  * 45s: 4 to 5 detailed scenes (00:00 - 00:45), strictly 110-125 total spoken words.
  * 60s (Maximum 60s): 5 to 6 comprehensive scenes (00:00 - 01:00 max), strictly 140-160 total spoken words.
  * Custom X seconds (10s to 60s): Scene timestamps must end exactly at 00:X (or 01:00) and spoken words scaled to ~X * 2.5 words. Timestamps must NEVER exceed 01:00 or fall below 00:10!
- Creator Wardrobe & Presentation Format: {presentation_mode}
  * CRITICAL RULE (Section 8B & 8D):
    - If 'Magic Transition': In Scene 1, the creator MUST wear their own everyday casual clothes (from CREATOR_REFERENCE) while holding the unopened Meesho package or folded garment. They must NOT be wearing the reviewed product in Scene 1! At the end of Scene 1 or start of Scene 2, perform a quick finger snap / spin transition, after which the creator is wearing the reviewed product in Scene 2 onwards.
    - If 'Problem-Solution Hack' (Section 8D): Follow the 3-second relatable wardrobe struggle hook (e.g. bra strap showing in deep blouse, petticoat bulge, VPL panty lines, white kurti innerwear) ➔ creator demonstrates the Meesho secret hack product live on camera ➔ shows the flawless clean payoff!
    - If 'Hold & Review Only': Creator remains in their everyday casual clothes throughout the entire video. They NEVER wear the reviewed product. They hold it on a hanger, tabletop, or against their body. (Mandatory for intimate wear/bikini).
    - If 'Direct Try-On': Creator is already wearing the reviewed product from 00:00.
- User Category Hint: {category_hint}
- Additional Seller/Product Notes: {notes if notes else 'None provided'}

CONSISTENCY LOCK RULES (MANDATORY IN EVERY SCENE PROMPT):
- 'Identity & Anatomy Lock: REFERENCE IMAGE 1 (CREATOR) - Lock exact facial identity, hair styling, body shape, silhouette, height, and natural body proportions across all cuts without morphing or warping.'
- 'Garment Lock: REFERENCE IMAGE 2 (PRODUCT FRONT) - Lock exact garment cut, fabric, color, prints, and stitching.'
- 'Environment Lock: Lock room architecture and background elements across all cuts.'
- In every scene prompt, the 'Avoid:' block MUST include: 'no face swapping, no morphing facial identity, no changing body shape, no warping body proportions, no shifting waist or bust size, no inconsistent height, no fluctuating skin tone, no altering dress colors, no changing fabric patterns, no inconsistent neckline, no background shifts'.

REQUIREMENTS:
1. Perform automatic image role detection & product truth analysis.
2. AUTHENTIC APPAREL TERMINOLOGY & GOOGLE FLOW ZERO-REJECTION ENGINE:
   - When the reviewed product is a bra, panty, undergarment, shapewear, or lingerie set:
     * YOU MUST EXPLICITLY USE AUTHENTIC COMMERCIAL TERMS ("bra", "panty", "undergarments", "bra-panty set", "wire-free bra", "seamless panty", "innerwear", "shapewear") across Script, Spoken Voice-Over, and Google Flow Video Prompts!
     * NEVER use awkward false euphemisms like "dress" or "mini tunic" to disguise undergarments in speech or prompt.
     * E-Commerce Styling Standard: Use Zivame/Clovia formula (top/bra worn with high-waist palazzo/trousers + matching panty held in hands demonstrating waist elastic stretch) or Parachute pants + bralette hack with panty side-strings visible at waistband.
     * What to avoid: ONLY sexually explicit/pornographic content (nudity, exposed breasts, erotic, cleavage zoom) is prohibited. Commercial fashion terms ("bra", "panty", "undergarments") are 100% permitted.
   - MANDATORY PROMPT FORMAT (Section 8C): Format all Google Flow prompts with the winning commercial ad structure: 'Voice-over:', 'Visual:', 'Environment Lock:', 'Style:', 'Camera:', 'Audio:', 'Transition:', and the critical 'Avoid:' negative safety block ('No nudity, no underwear exposure without outer layer, no suggestive camera angles, no sexualized presentation, no warped limbs, no unnatural body physics, no background shifts, no changing room decor, no inconsistent wall colors...'). This guarantees 100% Zero-Policy Block in Google Flow!
3. Deliver the final output strictly in the exact Markdown layout specified in Section 33 of the Master Prompt, including:
   - Product & Strategy Analysis
   - Selected Hook (with score benchmark target 99/100)
   - Scene-by-Scene breakdown (with timing, Voice-Over, Visual, and complete Google Flow Video Prompts for each scene)
   - Final Quality & Safety Report table.
   - Complete Instagram Launch Kit: Viral Hook Caption, ManyChat/DM Auto-Reply Keyword, Pinned Comment, and 15-20 Targeted High-Ranking Hashtags!
"""
        contents_parts.append({"text": prompt_instruction})

        master_system_instruction = load_master_prompt()

        candidate_models = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.7-flash"]
        generated_text = ""
        last_error = ""

        payload = {
            "system_instruction": {
                "parts": [{"text": master_system_instruction}]
            },
            "contents": [
                {
                    "parts": contents_parts
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "maxOutputTokens": 8192
            }
        }

        for model_name in candidate_models:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                response = requests.post(api_url, json=payload, timeout=120)
                if response.status_code == 200:
                    result_json = response.json()
                    candidates = result_json.get("candidates", [])
                    if candidates:
                        generated_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if generated_text:
                            break
                else:
                    err_json = response.json() if response.content else {}
                    last_error = err_json.get("error", {}).get("message", f"HTTP {response.status_code}")
                    print(f"Model {model_name} returned {response.status_code}. Switching to next backup model...")
            except Exception as req_err:
                last_error = str(req_err)
                print(f"Model {model_name} exception: {req_err}. Switching to next backup model...")

        if not generated_text:
            return jsonify({"error": f"All models busy. Last message: {last_error}"}), 500

        return jsonify({
            "mode": "live",
            "markdown": generated_text,
            "safe_crop_url": safe_crop_urls[0] if safe_crop_urls else None,
            "safe_crop_urls": safe_crop_urls
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/meesho-extract", methods=["POST"])
def meesho_extract():
    try:
        data = request.get_json() or {}
        input_text = data.get("text", "") or data.get("url", "")
        load_dotenv(ENV_PATH, override=True)
        api_key = os.getenv("GEMINI_API_KEY", "")
        
        # Fast URL slug extraction
        raw_url = ""
        url_match = re.search(r'https?://[^\s]+', input_text)
        if url_match: raw_url = url_match.group(0)
        
        code_match = re.search(r'\b(s-[a-zA-Z0-9]+)\b', input_text, re.IGNORECASE)
        code = code_match.group(0) if code_match else "s-18392841"
        
        price_match = re.search(r'(?:₹|Rs\.?|INR)\s*([0-9,]+)', input_text, re.IGNORECASE)
        price = f"₹{price_match.group(1)}" if price_match else "₹499"
        
        slug_title = ""
        if raw_url:
            parts = raw_url.split("?")[0].strip("/").split("/")
            if "p" in parts:
                p_idx = parts.index("p")
                if p_idx > 0 and parts[p_idx-1] != "s":
                    slug_title = " ".join(w.capitalize() for w in parts[p_idx-1].split("-") if w)
                    
        title = slug_title or input_text.split("\n")[0][:80] or "Trending Meesho Fashion Fit"
        return jsonify({
            "success": True,
            "product": {
                "title": title,
                "price": price,
                "meesho_code": code,
                "url": raw_url,
                "category": "Ethnic Wear"
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate-hd-photo", methods=["POST"])
def generate_hd_photo_endpoint():
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt", "")
        width = int(data.get("width", 1024))
        height = int(data.get("height", 1024))
        seed = data.get("seed", random.randint(1000, 9999999))
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        encoded = requests.utils.quote(prompt.strip().replace("\n", " "))
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=flux&nologo=true&seed={seed}"
        r = requests.get(url, timeout=35)
        if r.status_code == 200:
            b64_data = base64.b64encode(r.content).decode("utf-8")
            return jsonify({"success": True, "image_base64": b64_data, "mime_type": "image/jpeg", "seed": seed})
        return jsonify({"error": f"Image service HTTP {r.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Meesho AI Video Script & Flow Director running at: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
