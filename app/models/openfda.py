"""Pydantic v2 schemas for openFDA drug label responses."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class OpenFDAMeta(BaseModel):
    """Metadata extracted from the nested 'openfda' block."""

    brand_name: list[str] = Field(default_factory=list)
    generic_name: list[str] = Field(default_factory=list)
    substance_name: list[str] = Field(default_factory=list)
    manufacturer_name: list[str] = Field(default_factory=list)
    spl_set_id: list[str] = Field(default_factory=list)
    spl_id: list[str] = Field(default_factory=list)
    application_number: list[str] = Field(default_factory=list)
    product_ndc: list[str] = Field(default_factory=list)

    @property
    def primary_brand_name(self) -> str | None:
        return self.brand_name[0] if self.brand_name else None

    @property
    def primary_generic_name(self) -> str | None:
        return self.generic_name[0] if self.generic_name else None


# Known non-section keys in openFDA drug label records
METADATA_KEYS = {
    "id",
    "set_id",
    "version",
    "effective_time",
    "openfda",
    "@epoch",
    "spl_product_data_elements",
    "spl_unclassified_section",
}


class OpenFDALabelRecord(BaseModel):
    """Represents a single drug label record retrieved from openFDA."""

    id: str
    set_id: str | None = None
    version: str | None = "1"
    effective_time: str | None = None  # Expected format: YYYYMMDD
    openfda: OpenFDAMeta = Field(default_factory=OpenFDAMeta)

    # Core high-signal SPL sections explicitly defined
    boxed_warning: list[str] | None = None
    indications_and_usage: list[str] | None = None
    dosage_and_administration: list[str] | None = None
    contraindications: list[str] | None = None
    warnings_and_precautions: list[str] | None = None
    warnings: list[str] | None = None
    adverse_reactions: list[str] | None = None
    drug_interactions: list[str] | None = None
    use_in_specific_populations: list[str] | None = None
    clinical_pharmacology: list[str] | None = None
    overdosage: list[str] | None = None

    # Full raw dictionary to extract any additional SPL section dynamically
    raw_sections: dict[str, str] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def populate_sections_from_raw(cls, data: Any) -> Any:
        """Extracts all text sections from openFDA format into clean unified text."""
        if not isinstance(data, dict):
            return data

        raw_sections: dict[str, str] = {}
        for key, value in data.items():
            if key in METADATA_KEYS:
                continue
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                # Join multi-line paragraphs into unified section text
                combined = "\n\n".join(item.strip() for item in value if item.strip())
                if combined:
                    raw_sections[key] = combined

        data_copy = dict(data)
        data_copy["raw_sections"] = raw_sections
        return data_copy

    @property
    def effective_date_iso(self) -> str | None:
        """Converts openFDA YYYYMMDD to ISO YYYY-MM-DD."""
        if self.effective_time and len(self.effective_time) == 8:
            return f"{self.effective_time[:4]}-{self.effective_time[4:6]}-{self.effective_time[6:]}"
        return self.effective_time

    def get_all_sections(self) -> dict[str, str]:
        """Returns map of section_name -> section_text for all present sections."""
        return self.raw_sections


class OpenFDALabelResponse(BaseModel):
    """Container for openFDA API response."""

    meta: dict[str, Any] | None = None
    results: list[OpenFDALabelRecord] = Field(default_factory=list)
