from pydantic import BaseModel
from typing import List, Optional

class ImageBase64Schema(BaseModel):
    task_id: Optional[int] = None
    images: List[str]
