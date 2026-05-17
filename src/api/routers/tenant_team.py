from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict, EmailStr, Field
import uuid
from datetime import datetime, timedelta
import secrets

from src.core import get_db
from src.api.dependencies import get_authenticated_tenant
from src.config import settings
from src.models import Tenant, TenantUser, TenantInvitation
from src.core.security import hash_password
from src.services.notification_service import NotificationService
from src.api.schemas import SendNotificationRequest, RecipientInfo, NotificationData, Channel, Priority

router = APIRouter(prefix="/tenant/team", tags=["tenant-team"])

class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="marketing", pattern="^(admin|marketing)$")
    permissions: Optional[Dict] = None

class InviteResponse(BaseModel):
    invite_id: uuid.UUID
    email: str
    token: str
    expires_at: datetime

class AcceptInviteRequest(BaseModel):
    token: str
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = None

def require_admin(tenant: Tenant = Depends(get_authenticated_tenant)):
    if tenant.current_user_role not in ["root", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can manage the team."
        )
    return tenant

@router.get("/members", response_model=List[TeamMemberResponse])
async def list_team_members(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """List all team members for the tenant."""
    query = select(TenantUser).where(TenantUser.tenant_id == tenant.id).order_by(TenantUser.created_at)
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/invites")
async def list_pending_invites(
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all pending invitations for the tenant."""
    query = select(TenantInvitation).where(
        TenantInvitation.tenant_id == tenant.id,
        TenantInvitation.accepted_at.is_(None)
    ).order_by(TenantInvitation.created_at.desc())
    result = await db.execute(query)
    invites = result.scalars().all()
    
    response = []
    for inv in invites:
        # Get the email of the user who invited them if available
        invited_by = "Admin"
        if inv.invited_by_user_id:
            user_query = select(TenantUser).where(TenantUser.id == inv.invited_by_user_id)
            user_res = await db.execute(user_query)
            user = user_res.scalar_one_or_none()
            if user:
                invited_by = user.email
                
        # Inject the invited_by field into the response
        inv_dict = {
            "invite_id": inv.id,
            "email": inv.email,
            "token": inv.token,
            "expires_at": inv.expires_at,
            "role": inv.role,
        }
        # Since InviteResponse doesn't have invited_by and role fields natively yet in schemas, 
        # we'll just return a dict and FastAPI will serialize it
        # Actually, let's just return a list of dicts directly to bypass schema limits for now
        response.append({
            "id": inv.id,
            "email": inv.email,
            "role": inv.role,
            "token": inv.token,
            "expires_at": inv.expires_at,
            "invited_by": invited_by
        })
    
    return response

@router.delete("/invites/{invite_id}")
async def cancel_invite(
    invite_id: uuid.UUID,
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a pending invitation."""
    query = select(TenantInvitation).where(
        TenantInvitation.id == invite_id,
        TenantInvitation.tenant_id == tenant.id
    )
    result = await db.execute(query)
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
        
    if invitation.accepted_at:
        raise HTTPException(status_code=400, detail="Invitation has already been accepted")
        
    await db.delete(invitation)
    await db.commit()
    
    return {"status": "success", "message": "Invitation cancelled"}

@router.post("/invite", response_model=InviteResponse)
async def invite_team_member(
    request: InviteRequest,
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Invite a new team member."""
    # Check if user already exists
    user_query = select(TenantUser).where(
        TenantUser.email == str(request.email),
        TenantUser.tenant_id == tenant.id
    )
    user_result = await db.execute(user_query)
    if user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists."
        )

    # Check if pending invite exists
    invite_query = select(TenantInvitation).where(
        TenantInvitation.email == str(request.email),
        TenantInvitation.tenant_id == tenant.id,
        TenantInvitation.accepted_at.is_(None),
        TenantInvitation.expires_at > datetime.utcnow()
    )
    invite_result = await db.execute(invite_query)
    if invite_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this email."
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    invitation = TenantInvitation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=str(request.email),
        token=token,
        role=request.role,
        permissions=request.permissions,
        invited_by_user_id=tenant.current_user_id,
        expires_at=expires_at
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Send invitation email via tenant's Mailgun/SES
    try:
        # Use existing notification service to send the invite
        notification_service = NotificationService(db)
        
        invite_link = f"{settings.public_base_url}/portal/accept-invite?token={token}"
        
        email_body = f"""
        <html>
            <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
                    <h2 style="color: #0f766e; margin-top: 0;">You've been invited!</h2>
                    <p>Hello,</p>
                    <p>You have been invited to join the <strong>{tenant.name}</strong> team on the Notification Platform as a <strong>{request.role}</strong>.</p>
                    <p>To accept this invitation and set up your account, please click the button below:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{invite_link}" style="background: linear-gradient(135deg, #0f766e 0%, #2563eb 100%); color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Accept Invitation</a>
                    </div>
                    <p style="font-size: 13px; color: #666;">This invitation link will expire in 7 days.</p>
                    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
                    <p style="font-size: 12px; color: #94a3b8;">If you were not expecting this invitation, you can safely ignore this email.</p>
                </div>
            </body>
        </html>
        """
        
        invite_request = SendNotificationRequest(
            recipient=RecipientInfo(
                user_id=f"invite_{invitation.id}",
                email=str(request.email)
            ),
            notification=NotificationData(
                type="team_invitation",
                priority=Priority.HIGH,
                channels=[Channel.EMAIL],
                subject=f"Invitation to join {tenant.name} team",
                body=email_body,
                data={
                    "tenant_name": tenant.name,
                    "role": request.role,
                    "invite_link": invite_link
                }
            )
        )
        
        await notification_service.send_notification(tenant.id, invite_request)
        print(f"Invitation email queued for {request.email}")
        
    except Exception as e:
        # Log error but don't fail the request since invitation record is created
        print(f"Failed to send invitation email: {e}")
        # In a real app, we might want to flag this invite as "delivery_failed"
    
    return InviteResponse(
        invite_id=invitation.id,
        email=invitation.email,
        token=invitation.token,
        expires_at=invitation.expires_at
    )

@router.post("/accept-invite")
async def accept_invitation(
    request: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Finalize account creation from invitation."""
    query = select(TenantInvitation).where(
        TenantInvitation.token == request.token,
        TenantInvitation.accepted_at.is_(None),
        TenantInvitation.expires_at > datetime.utcnow()
    )
    result = await db.execute(query)
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation token."
        )

    # Check if username is taken
    user_query = select(TenantUser).where(TenantUser.username == request.username.lower())
    user_result = await db.execute(user_query)
    if user_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken."
        )

    # Create user
    print(f"Hashing password of length: {len(request.password)}")
    new_user = TenantUser(
        id=uuid.uuid4(),
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        username=request.username.lower(),
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        role=invitation.role,
        permissions=invitation.permissions,
        is_active=True
    )
    db.add(new_user)
    
    # Mark invite as accepted
    invitation.accepted_at = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "Account created successfully. You can now login."}

@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    user_id: uuid.UUID,
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Remove a team member."""
    # Cannot remove yourself
    if user_id == tenant.current_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove yourself from the team."
        )

    # Find user
    user = await db.get(TenantUser, user_id)
    if not user or user.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your team."
        )

    # Cannot remove root users (only one root exists)
    if user.role == 'root':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Root user cannot be removed."
        )

    await db.delete(user)
    await db.commit()
    return None

@router.patch("/members/{user_id}", response_model=TeamMemberResponse)
async def update_team_member(
    user_id: uuid.UUID,
    role: Optional[str] = Query(None, pattern="^(admin|marketing)$"),
    permissions: Optional[Dict] = None,
    is_active: Optional[bool] = None,
    tenant: Tenant = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update team member role or permissions."""
    user = await db.get(TenantUser, user_id)
    if not user or user.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your team."
        )

    if user.role == 'root':
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Root user permissions cannot be modified."
        )

    if role:
        user.role = role
    if permissions is not None:
        user.permissions = permissions
    if is_active is not None:
        user.is_active = is_active

    await db.commit()
    await db.refresh(user)
    return user
