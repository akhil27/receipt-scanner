import base64
import json
import logging
import os
from datetime import date
from typing import Optional
from abc import ABC, abstractmethod
from dotenv import load_dotenv
import requests

from models import Receipt, ReceiptItem

load_dotenv()

logger = logging.getLogger("receipt_scanner")
logging.basicConfig(level=logging.INFO)

PROVIDER = os.environ.get("VISION_PROVIDER", "nvidia").lower()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")
NVIDIA_MODEL_FALLBACK = os.environ.get("NVIDIA_MODEL_FALLBACK", "meta/llama-3.2-90b-vision-instruct")
NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"

MERCHANT_MAP = {
    "wal-mart": "Walmart",
    "walmart supercenter": "Walmart",
    "walmart.com": "Walmart",
    "amzn mktp us": "Amazon",
    "amazon.com": "Amazon",
    "amzn": "Amazon",
    "target stores": "Target",
    "target store": "Target",
    "target.com": "Target",
    "costco wholesale": "Costco",
    "costco wholesale corp": "Costco",
    "sam's club": "Sam's Club",
    "sams club": "Sam's Club",
    "sams club store": "Sam's Club",
    "trader joe's": "Trader Joe's",
    "trader joes": "Trader Joe's",
    "whole foods market": "Whole Foods",
    "whole foods": "Whole Foods",
    "mcdonald's": "McDonald's",
    "starbucks coffee": "Starbucks",
    "starbucks": "Starbucks",
    "home depot": "The Home Depot",
    "the home depot": "The Home Depot",
    "best buy": "Best Buy",
    "walgreens": "Walgreens",
    "cvs pharmacy": "CVS",
    "cvs": "CVS",
}


def normalize_merchant(name: str) -> str:
    cleaned = name.strip()
    return MERCHANT_MAP.get(cleaned.lower(), cleaned)


def validate_totals(receipt: Receipt) -> bool:
    if receipt.subtotal is None or receipt.tax is None:
        return True
    item_sum = sum(i.price for i in receipt.items)
    calculated = receipt.subtotal + receipt.tax
    return abs(calculated - receipt.total) <= 0.02 and abs(item_sum - receipt.subtotal) <= 0.05


def clean_json_response(raw_text: str) -> str:
    import re
    cleaned = raw_text.strip()
    cleaned = re.sub(r"<?>.*?<?>", "", cleaned, flags=re.DOTALL).strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]
    return cleaned.strip()


PROMPT = (
    "Extract merchant, date, items (name, price, category), subtotal, "
    "tax, and total from this receipt image. Categories must be one of: Food, Groceries, "
    "Restaurant, Alcohol, Household, Electronics, Health, Transportation, "
    "Entertainment, Other. Return ONLY valid JSON matching this exact shape: "
    '{"merchant": "Store Name", "date": "YYYY-MM-DD", "total": 0.00, '
    '"subtotal": 0.00, "tax": 0.00, '
    '"items": [{"name": "Item Name", "price": 0.00, "category": "Groceries"}]}. '
    "No markdown fences, no explanation, valid JSON only."
)


class VisionProvider(ABC):
    @abstractmethod
    def call_vision(self, model: str, image_b64: str, mime_type: str) -> str:
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        pass

    @property
    @abstractmethod
    def fallback_model(self) -> Optional[str]:
        pass

    @property
    @abstractmethod
    def api_key(self) -> str:
        pass


class NVIDIAProvider(VisionProvider):
    def call_vision(self, model: str, image_b64: str, mime_type: str) -> str:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
                ],
            }],
            "temperature": 0.1,
            "max_tokens": 1500,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        resp = requests.post(NIM_ENDPOINT, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    @property
    def default_model(self) -> str:
        return NVIDIA_MODEL

    @property
    def fallback_model(self) -> Optional[str]:
        return NVIDIA_MODEL_FALLBACK if NVIDIA_MODEL_FALLBACK != NVIDIA_MODEL else None

    @property
    def api_key(self) -> str:
        return NVIDIA_API_KEY


class OpenAIProvider(VisionProvider):
    def call_vision(self, model: str, image_b64: str, mime_type: str) -> str:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
                ],
            }],
            "temperature": 0.1,
            "max_tokens": 1500,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        resp = requests.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    @property
    def default_model(self) -> str:
        return OPENAI_MODEL

    @property
    def fallback_model(self) -> Optional[str]:
        return None

    @property
    def api_key(self) -> str:
        return OPENAI_API_KEY


class AnthropicProvider(VisionProvider):
    def call_vision(self, model: str, image_b64: str, mime_type: str) -> str:
        payload = {
            "model": model,
            "max_tokens": 1500,
            "temperature": 0.1,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_b64}}
                ],
            }],
        }
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    @property
    def default_model(self) -> str:
        return ANTHROPIC_MODEL

    @property
    def fallback_model(self) -> Optional[str]:
        return None

    @property
    def api_key(self) -> str:
        return ANTHROPIC_API_KEY


def get_provider() -> VisionProvider:
    providers = {
        "nvidia": NVIDIAProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }
    provider_class = providers.get(PROVIDER)
    if not provider_class:
        raise ValueError(f"Unknown provider: {PROVIDER}. Choose from: {list(providers.keys())}")
    return provider_class()


def _render_pdf_first_page(pdf_path: str) -> str:
    import pymupdf
    png_path = os.path.splitext(pdf_path)[0] + "_page.png"
    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        pix.save(png_path)
    return png_path


def _prepare_image(image_path: str):
    ext = os.path.splitext(image_path)[1].lower()
    if ext == ".pdf":
        png_path = _render_pdf_first_page(image_path)
        return png_path, "image/png"
    mime_type = "image/png" if ext == ".png" else "image/jpeg"
    return image_path, mime_type


def extract_receipt(image_path: str, model: Optional[str] = None) -> Receipt:
    provider = get_provider()
    key = provider.api_key
    primary_model = model or provider.default_model
    fallback_model = provider.fallback_model

    if not key or key in ("your-key-here", "your-nvidia-api-key-here", "your-openai-api-key-here", "your-anthropic-api-key-here"):
        logger.warning(f"{PROVIDER.upper()}_API_KEY is not configured. Marking receipt for manual review.")
        return Receipt(
            merchant="Unknown Merchant",
            date=date.today().isoformat(),
            total=0.0,
            subtotal=0.0,
            tax=0.0,
            items=[],
            needs_review=True,
            image_path=image_path,
        )

    try:
        send_path, mime_type = _prepare_image(image_path)

        with open(send_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        if send_path != image_path:
            try:
                os.remove(send_path)
            except OSError:
                pass

        models_to_try = [primary_model]
        if fallback_model:
            models_to_try.append(fallback_model)

        last_error = None
        for attempt_model in models_to_try:
            try:
                logger.info(f"Attempting extraction with {PROVIDER} model: {attempt_model}")
                raw_text = provider.call_vision(attempt_model, image_b64, mime_type)
                cleaned = clean_json_response(raw_text)
                parsed = json.loads(cleaned)

                if "merchant" in parsed and parsed["merchant"]:
                    parsed["merchant"] = normalize_merchant(str(parsed["merchant"]))

                parsed["image_path"] = image_path
                receipt = Receipt(**parsed)

                if not validate_totals(receipt):
                    logger.info("Receipt arithmetic mismatch detected. Flagged as needs_review.")
                    receipt.needs_review = True

                return receipt

            except Exception as e:
                last_error = e
                logger.warning(f"Model {attempt_model} failed: {e}")
                continue

        raise last_error

    except Exception as e:
        logger.error(f"Failed to extract receipt from {image_path}: {e}", exc_info=True)
        return Receipt(
            merchant="Unknown Merchant",
            date=date.today().isoformat(),
            total=0.0,
            subtotal=0.0,
            tax=0.0,
            items=[],
            needs_review=True,
            image_path=image_path,
        )