from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic_extra_types.phone_numbers import PhoneNumber


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )


class StakeholderAddress(BaseModel):
    street: Annotated[str, Field(max_length=255)]
    city: Annotated[str, Field(max_length=100)]
    state: Annotated[str, Field(max_length=100)]
    postal_code: Annotated[str, Field(min_length=4, max_length=10)]
    country: Annotated[str, Field(default="IN", min_length=2, max_length=2)]


class StakeholderBase(BaseModel):
    name: Annotated[
        str, Field(max_length=255, description="Name must match with name on PAN card")
    ]
    email: EmailStr | None = None
    phone: PhoneNumber
    percentage_ownership: Annotated[Decimal, Field(ge=0, le=100)]
    is_director: bool = False
    address: StakeholderAddress


class RazorpayLinkedAccountCreaterequest(BaseSchema):
    legal_business_name: Annotated[str, Field(max_length=200)]
    business_type: str
    pan_number: Annotated[str, Field(min_length=10, max_length=10)]
    gst_number: Annotated[str | None, Field(default=None, max_length=15)]
    contact_email: EmailStr
    contact_phone: PhoneNumber

    bank_account_number: Annotated[str, Field(max_length=35)]
    bank_ifsc: Annotated[str, Field(min_length=11, max_length=11)]
    bank_beneficiary_name: Annotated[str, Field(max_length=255)]

    stakeholder: StakeholderBase

    tnc_accepted: bool = Field(
        ...,
        description="Organizer's explicit acceptance of Razorpay Route's terms and conditions.",
    )
