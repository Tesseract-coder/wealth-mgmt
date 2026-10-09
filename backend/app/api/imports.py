import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlmodel import Session

from app.api.convert import imported_out
from app.core.db import get_session
from app.core.profiles import get_profiles
from app.importers import cas, groww, manual
from app.importers.groww import NeedsMapping, UserMapping, field_specs
from app.importers.tabular import ImportFileError
from app.models.schemas import (
    ColumnMappingIn,
    FieldSpecOut,
    ImportedOut,
    ManualMFIn,
    NeedsMappingOut,
)

router = APIRouter(prefix="/import", tags=["import"])


async def _read(file: UploadFile) -> bytes:
    limit = int(get_profiles().importing.max_upload_mb * 1024 * 1024)
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"File is larger than {get_profiles().importing.max_upload_mb} MB")
    if not content:
        raise HTTPException(400, "The uploaded file is empty")
    return content


def _user_mapping(raw: str | None) -> UserMapping | None:
    if not raw:
        return None
    try:
        m = ColumnMappingIn.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(422, f"Invalid 'mapping' field: {e}") from None
    return UserMapping(m.header_row, m.columns, m.remember)


def _needs_mapping_out(kind: Literal["stocks", "mf"], n: NeedsMapping) -> NeedsMappingOut:
    m = n.mapping
    return NeedsMappingOut(
        kind=kind,
        header_row=m.header_row,
        headers=m.headers,
        detected=m.mapping,
        missing_required=m.missing_required,
        fields=[FieldSpecOut.model_validate(f) for f in field_specs(kind)],
        preview=n.preview,
    )


async def _tabular_import(
    kind: Literal["stocks", "mf"], file: UploadFile, mapping: str | None, session: Session
) -> ImportedOut | NeedsMappingOut:
    content = await _read(file)
    importer = groww.import_stocks if kind == "stocks" else groww.import_mf
    try:
        result = importer(session, content, file.filename or "upload.csv", _user_mapping(mapping))
    except (ImportFileError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    if isinstance(result, NeedsMapping):
        return _needs_mapping_out(kind, result)
    return imported_out(session, result)


@router.post("/groww-stocks", response_model=ImportedOut | NeedsMappingOut)
async def import_groww_stocks(
    file: UploadFile = File(..., description="Groww Holdings report, .xlsx or .csv"),
    mapping: str | None = Form(
        None, description="JSON ColumnMappingIn, after a needs_mapping reply"
    ),
    session: Session = Depends(get_session),
) -> ImportedOut | NeedsMappingOut:
    return await _tabular_import("stocks", file, mapping, session)


@router.post("/groww-mf", response_model=ImportedOut | NeedsMappingOut)
async def import_groww_mf(
    file: UploadFile = File(..., description="Groww mutual fund holdings, .xlsx or .csv"),
    mapping: str | None = Form(
        None, description="JSON ColumnMappingIn, after a needs_mapping reply"
    ),
    session: Session = Depends(get_session),
) -> ImportedOut | NeedsMappingOut:
    return await _tabular_import("mf", file, mapping, session)


@router.post("/cas", response_model=ImportedOut)
async def import_cas(
    file: UploadFile = File(..., description="CAMS/KFintech or NSDL/CDSL CAS PDF"),
    password: str = Form(..., description="PDF password. Used once in memory, never stored."),
    session: Session = Depends(get_session),
) -> ImportedOut:
    content = await _read(file)
    try:
        result = cas.import_cas(session, content, password, file.filename or "cas.pdf")
    except ImportFileError as e:
        raise HTTPException(400, str(e)) from None
    finally:
        del password
    return imported_out(session, result)


@router.post("/mf-manual", response_model=ImportedOut)
def import_mf_manual(body: ManualMFIn, session: Session = Depends(get_session)) -> ImportedOut:
    result = manual.add_manual_mf(
        session,
        scheme=body.scheme,
        units=body.units,
        invested=body.invested,
        folio=body.folio,
        purchase_date=body.purchase_date,
    )
    return imported_out(session, result)


@router.get("/fields/{kind}", response_model=list[FieldSpecOut])
def import_fields(kind: Literal["stocks", "mf"]) -> list[FieldSpecOut]:
    return [FieldSpecOut.model_validate(f) for f in field_specs(kind)]
