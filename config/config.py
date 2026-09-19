from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    name: str = "deepseek-chat"


class Config(BaseModel):
    model: ModelConfig = Field(default_factort=ModelConfig)
