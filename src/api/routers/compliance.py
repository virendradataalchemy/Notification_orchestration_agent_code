from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import logging

from src.core import get_db
from src.models.inbound import InboundMessageRaw
from src.api.dependencies import get_current_tenant

router = APIRouter(prefix="/compliance", tags=["compliance"])
logger = logging.getLogger(__name__)

@router.get("/candidate/{candidate_id}")
async def get_candidate_data(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    Retrieve all data associated with a specific candidate for GDPR compliance (Right of Access).
    """
    query = select(InboundMessageRaw).where(
        InboundMessageRaw.tenant_id == tenant_id,
        InboundMessageRaw.candidate_id == candidate_id
    )
    result = await db.execute(query)
    messages = result.scalars().all()
    
    # We might want to construct a structured response
    data = []
    for msg in messages:
        data.append({
            "id": str(msg.id),
            "channel": msg.channel.value,
            "received_at": msg.created_at,
            "raw_payload": msg.raw_payload,
        })
        
    return {
        "candidate_id": candidate_id,
        "tenant_id": tenant_id,
        "record_count": len(data),
        "data": data
    }


@router.delete("/candidate/{candidate_id}")
async def delete_candidate_data(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant)
):
    """
    Delete all data associated with a specific candidate for GDPR compliance (Right to Erasure).
    """
    # Delete InboundMessageRaw records (Cascade will handle parsed and intent records)
    stmt = delete(InboundMessageRaw).where(
        InboundMessageRaw.tenant_id == tenant_id,
        InboundMessageRaw.candidate_id == candidate_id
    )
    result = await db.execute(stmt)
    await db.commit()
    
    deleted_count = result.rowcount
    
    # Audit log this action (ideally outside of this model, perhaps in AuditLog)
    from src.models.audit_log import AuditLog
    audit_entry = AuditLog(
        event_type="gdpr_erasure",
        user_id="system", # Typically the admin user triggering this
        resource_type="candidate_data",
        resource_id=candidate_id,
        action="delete",
        details={"tenant_id": tenant_id, "records_deleted": deleted_count}
    )
    db.add(audit_entry)
    await db.commit()
    
    logger.info(f"GDPR Erasure: Deleted {deleted_count} records for candidate {candidate_id} in tenant {tenant_id}")
    
    return {"status": "success", "records_deleted": deleted_count}
