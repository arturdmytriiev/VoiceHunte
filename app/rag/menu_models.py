from pydantic import BaseModel


class MenuItem(BaseModel):
    name: str
    description: str
    price: float
    category: str
    allergens: list[str] | None = None
    tags: list[str] | None = None
