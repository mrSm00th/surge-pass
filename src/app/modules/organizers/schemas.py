import re
import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

from src.app.modules.organizers.models import OrganizerBusinessType

_PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IndianPhoneNumber(PhoneNumber):
    default_region_code = "IN"
    phone_format = "E164"


class StakeholderAddress(BaseSchema):
    street: Annotated[str, Field(max_length=255)]
    city: Annotated[str, Field(max_length=100)]
    state: Annotated[str, Field(max_length=100)]
    postal_code: Annotated[str, Field(min_length=4, max_length=10)]
    country: Annotated[str, Field(default="IN", min_length=2, max_length=2)]


class StakeholderBase(BaseSchema):
    name: Annotated[
        str, Field(max_length=255, description="Name must match with name on PAN card")
    ]
    email: EmailStr | None = None
    phone: IndianPhoneNumber

    percentage_ownership: Annotated[Decimal, Field(ge=0, le=100)]
    is_director: bool = False
    address: StakeholderAddress


class OrganizerKYCSubmitRequest(BaseSchema):
    legal_business_name: Annotated[str, Field(max_length=200)]
    business_type: OrganizerBusinessType
    pan_number: Annotated[str, Field(min_length=10, max_length=10)]
    gst_number: Annotated[str | None, Field(default=None, max_length=15)]
    contact_email: EmailStr
    contact_phone: IndianPhoneNumber
    bank_account_number: Annotated[str, Field(max_length=35)]
    bank_ifsc: Annotated[str, Field(min_length=11, max_length=11)]
    bank_beneficiary_name: Annotated[str, Field(max_length=255)]
    stakeholder: StakeholderBase
    tnc_accepted: bool = Field(
        ...,
        description="Organizer's explicit acceptance of Razorpay Route's terms and conditions.",
    )

    @field_validator("pan_number")
    @classmethod
    def _normalize_and_validate_pan(cls, v: str) -> str:
        v = v.strip().upper()
        if not _PAN_PATTERN.match(v):
            raise ValueError("PAN must match the format AAAAA9999A.")
        return v

    @field_validator("bank_ifsc")
    @classmethod
    def _normalize_ifsc(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("gst_number")
    @classmethod
    def _normalize_gst(cls, v: str | None) -> str | None:

        return v.strip().upper() if v else None

    @field_validator("tnc_accepted")
    @classmethod
    def _must_accept_tnc(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Terms and conditions must be accepted to submit KYC.")
        return v


class OrganizerKYCStatusResponse(BaseSchema):
    kyc_status: str
    kyc_provider_status: str | None
    kyc_requirements: dict | None
    message: str


class OrganizerProfileResponse(BaseSchema):
    id: uuid.UUID

    razorpay_account_status: str | None
    kyc_status: str
    kyc_provider_status: str | None
    business_name: str
    total_events_hosted: int
