from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class ImageBase64Schema(BaseModel):
    task_id: Optional[int] = None
    images: List[Dict[str, Any]]  # Каждое изображение содержит base64 и дополнительные метаданные

