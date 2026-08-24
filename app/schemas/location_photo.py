from pydantic import BaseModel


class LocationPhotoOut(BaseModel):
    key: str
    url: str
