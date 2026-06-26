import os
import io
import json
import base64
import zipfile
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import google.generativeai as genai

load_dotenv()

# ============== SETUP ==============
app = FastAPI(
    title="Faaya Product Preprocessor API",
    description="Smart e-commerce garment image preprocessing with AI metadata generation",
    version="1.0.0"
)

# Add CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Create output directory
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# Initialize Gemini client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY not found in .env file!")

genai.configure(api_key=api_key)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ============== IMAGE PROCESSING FUNCTIONS ==============

def remove_background(image_bytes: bytes) -> Image.Image:
    """
    Remove background from image using rembg.
    Returns RGBA image with transparent background.
    """
    from rembg import remove

    try:
        result_bytes = remove(image_bytes)
        return Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    except Exception as e:
        raise Exception(f"Background removal failed: {str(e)}")


def standardize_image(image: Image.Image, size: int = 800) -> Image.Image:
    """
    Resize image to square canvas with transparent padding.
    Output: 800x800 RGBA PNG
    """
    image.thumbnail((size, size), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - image.width) // 2, (size - image.height) // 2)
    canvas.paste(image, offset, image)

    return canvas


def get_dominant_color(image: Image.Image) -> dict:
    """
    Extract dominant color from garment (ignores transparent areas).
    Returns: { "hex": "#FF5733", "rgb": [255, 87, 51] }
    """
    rgb_image = image.convert("RGB")
    rgb_image.thumbnail((100, 100))
    pixels = list(rgb_image.getdata())

    if not pixels:
        return {"hex": "#808080", "rgb": [128, 128, 128]}

    r = sum(p[0] for p in pixels) // len(pixels)
    g = sum(p[1] for p in pixels) // len(pixels)
    b = sum(p[2] for p in pixels) // len(pixels)

    return {
        "hex": f"#{r:02x}{g:02x}{b:02x}",
        "rgb": [r, g, b]
    }


def generate_metadata_with_gemini(image: Image.Image) -> dict:
    """
    Send image to Gemini Vision API and get garment metadata.
    Returns: { title, alt_text, category, tags, style }
    """
    try:
        prompt = """Analyze this clothing/garment product image and return ONLY a valid JSON object with these exact fields:
{
  "title": "short product title like 'Red Floral Summer Dress' (3-6 words)",
  "alt_text": "one SEO-friendly sentence describing the garment for accessibility",
  "category": "one of: dress, top, bottom, outerwear, footwear, accessory",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "style": "one of: casual, formal, streetwear, ethnic, sportswear, vintage, minimalist"
}

Requirements:
- Return ONLY valid JSON, no markdown, no explanation, no code blocks
- If no garment visible, still return valid JSON with best guess
- Tags should be descriptive (color, pattern, season, fabric type, occasion)
- Make title suitable for e-commerce listing"""

        # Convert PIL image to RGB JPEG bytes for Gemini
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=85)
        buf.seek(0)

        # Use Gemini's inline image input
        img_part = {"mime_type": "image/jpeg", "data": base64.b64encode(buf.read()).decode()}
        response = gemini_model.generate_content([prompt, {"inline_data": img_part}])

        raw_response = response.text.strip()

        # Clean markdown fences if present
        if raw_response.startswith("```"):
            raw_response = raw_response.split("```")[1]
            if raw_response.startswith("json"):
                raw_response = raw_response[4:]
            raw_response = raw_response.strip()

        metadata = json.loads(raw_response)

        required_fields = ["title", "alt_text", "category", "tags", "style"]
        for field in required_fields:
            if field not in metadata:
                raise ValueError(f"Missing required field: {field}")

        return metadata

    except json.JSONDecodeError as e:
        return {
            "title": "Garment Item",
            "alt_text": "Clothing product image",
            "category": "accessory",
            "tags": ["image", "product", "garment"],
            "style": "casual",
            "error": f"AI analysis skipped: {str(e)}"
        }
    except Exception as e:
        return {
            "title": "Garment Item",
            "alt_text": "Clothing product image",
            "category": "accessory",
            "tags": ["image", "product", "garment"],
            "style": "casual",
            "error": f"AI generation failed: {str(e)}"
        }


def process_single_image(file_bytes: bytes, filename: str) -> dict:
    """
    Complete image processing pipeline:
    1. Remove background
    2. Standardize size
    3. Extract dominant color
    4. Generate metadata with Gemini
    5. Save output PNG
    """
    try:
        # Step 1: Remove background
        no_bg_image = remove_background(file_bytes)

        # Step 2: Standardize to 800x800
        standardized = standardize_image(no_bg_image, size=800)

        # Step 3: Get dominant color
        color_info = get_dominant_color(standardized)

        # Step 4: Generate metadata with Gemini Vision API
        metadata = generate_metadata_with_gemini(standardized)
        metadata["dominant_color"] = color_info

        # Step 5: Save output PNG
        base_name = filename.rsplit(".", 1)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"processed_{base_name}_{timestamp}.png"
        output_path = OUTPUT_DIR / output_filename
        standardized.save(output_path, format="PNG")

        # Convert to base64 for response
        buf = io.BytesIO()
        standardized.save(buf, format="PNG")
        img_b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

        return {
            "success": True,
            "filename": output_filename,
            "image_base64": img_b64,
            "metadata": metadata,
            "saved_path": str(output_path),
            "image_size": (standardized.width, standardized.height)
        }

    except Exception as e:
        return {
            "success": False,
            "filename": filename,
            "error": str(e)
        }


# ============== API ENDPOINTS ==============

@app.get("/")
def home():
    """Serve the web UI"""
    return FileResponse("static/index.html")


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Faaya Product Preprocessor",
        "version": "1.0.0"
    }


@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    """
    Upload a single garment image and process it.

    Returns:
    - Processed PNG image (800x800, transparent background)
    - AI-generated metadata (title, tags, alt-text, category, style, color)
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        allowed_extensions = {"jpg", "jpeg", "png", "webp", "gif"}
        ext = file.filename.rsplit(".", 1)[-1].lower()

        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type .{ext} not supported. Use: {', '.join(allowed_extensions)}"
            )

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        result = process_single_image(file_bytes, file.filename)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@app.post("/process-batch")
async def process_batch(file: UploadFile = File(...)):
    """
    Upload a ZIP file with multiple garment images.
    Returns processed images + metadata for all.
    """
    try:
        if not file.filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail="Please upload a ZIP file")

        file_bytes = await file.read()
        results = []

        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zip_ref:
            for file_info in zip_ref.filelist:
                if file_info.is_dir():
                    continue

                filename = file_info.filename
                ext = filename.rsplit(".", 1)[-1].lower()

                if ext in {"jpg", "jpeg", "png", "webp", "gif"}:
                    image_bytes = zip_ref.read(filename)
                    result = process_single_image(image_bytes, filename)
                    results.append(result)

        if not results:
            raise HTTPException(status_code=400, detail="No valid images found in ZIP")

        return JSONResponse({
            "success": True,
            "total_processed": len(results),
            "results": results
        })

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500
        )


@app.get("/download/{filename}")
def download_image(filename: str):
    """Download a processed image by filename"""
    try:
        file_path = OUTPUT_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="image/png"
        )
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


@app.get("/stats")
def get_stats():
    """Get processing statistics"""
    try:
        processed_files = list(OUTPUT_DIR.glob("*.png"))
        return {
            "total_processed": len(processed_files),
            "storage_used_mb": sum(f.stat().st_size for f in processed_files) / (1024 * 1024),
            "latest_files": [f.name for f in sorted(processed_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]]
        }
    except Exception as e:
        return {"error": str(e)}


# ============== ERROR HANDLERS ==============

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
