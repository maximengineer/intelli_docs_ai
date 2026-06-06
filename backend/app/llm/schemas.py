from pydantic import BaseModel


class PromptTemplate(BaseModel):
    name: str
    version: str
    purpose: str
    template: str
    expected_output_schema: str | None = None
