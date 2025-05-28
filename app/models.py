from pydantic import BaseModel
from datetime import datetime

class Prompt(BaseModel):
    id: int
    user_prompt: str
    created_at: datetime = datetime.now()
    status: str = "pending"

class Result(BaseModel):
    id: int
    prompt_id: int
    raw_data: str
    processed_options: str  # Could be a JSON string
    summary: str
    created_at: datetime = datetime.now()
