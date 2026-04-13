from typing import Any
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import text

# Try to use existing imports. Since I didn't see the exact session injection, I'll use raw supabase_client for DB calls like existing services.
from src.core import supabase_client
from src.services.intelligent_orchestration_agent import IntelligentOrchestrationAgent

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])
logger = logging.getLogger(__name__)

# Request Model
class OnboardCandidateRequest(BaseModel):
    client_id: int
    name: str
    email: str
    phone: str = ""

@router.post("/onboard-candidate")
async def onboard_candidate(payload: OnboardCandidateRequest) -> dict[str, Any]:
    """
    Executes the 4-step onboarding pipeline sequentially.
    Option 1: Inserts the mock candidate temporarily to allow DB logging to succeed.
    """
    client_id = payload.client_id
    
    # 1. Fetch dynamic HR & IT roles from users table
    users_resp = await supabase_client.select(
        "users", "role, email", 
        filters={"client_id": f"eq.{client_id}", "is_active": "eq.true"}
    )
    
    hr_email = "hr@example.com"
    it_email = "it@example.com"
    
    for user in users_resp:
        r = (user.get("role") or "").lower()
        if r == "hr" and user.get("email"):
            hr_email = user["email"]
        elif r == "it" and user.get("email"):
            it_email = user["email"]

    # 2. Fetch or Insert/Update temporary candidate to DB (True Upsert)
    existing_cand = await supabase_client.select(
        "candidates", "id", 
        filters={"client_id": f"eq.{client_id}", "email": f"eq.{payload.email}"}
    )
    
    candidate_data = {
        "client_id": client_id,
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "language": "en",
    }

    if existing_cand:
        candidate_id = existing_cand[0]["id"]
        # Update existing record to match latest form data (Name/Phone)
        await supabase_client.update(
            "candidates",
            candidate_data,
            filters={"id": f"eq.{candidate_id}"}
        )
    else:
        candidate_resp = await supabase_client.insert("candidates", candidate_data)
        if not candidate_resp:
            raise HTTPException(status_code=500, detail="Failed to create temporary candidate")
        candidate_id = candidate_resp[0]["id"]
    
    # Initialize the Orchestrator service
    orchestrator = IntelligentOrchestrationAgent(client_id=client_id)
    
    # Prepare variables for template placeholders ({{name}}, {{email}}, {{phone}})
    common_vars = {
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "candidate_name": payload.name, # Some templates might use this
    }

    pipeline_results = []

    try:
        # STEP 1: HR -> Candidate (External)
        try:
            logger.info(f"Running Pipeline Step 1 for Candidate {candidate_id}")
            res1 = await orchestrator.orchestrate_send(
                message_content="We are welcoming them and asking for docs.",
                user_id=str(candidate_id),
                recipient_overrides={"email": payload.email, "phone": payload.phone},
                custom_variables={
                    "type": "onboarding", 
                    "sender_email": hr_email,
                    **common_vars
                }
            )
            pipeline_results.append({"step": 1, "result": res1})
        except Exception as e1:
            logger.error(f"Step 1 failed: {e1}")
            pipeline_results.append({"step": 1, "error": str(e1)})
        
        # STEP 2: HR -> IT (Internal - Email)
        try:
            logger.info(f"Running Pipeline Step 2 for Candidate {candidate_id}")
            res2 = await orchestrator.orchestrate_send(
                message_content=f"Requesting IT to process generic laptop and ID card for {payload.name}.",
                user_id=str(candidate_id),
                recipient_overrides={"email": it_email},
                custom_variables={
                    "type": "internal_request", 
                    "sender_email": hr_email,
                    **common_vars
                }
            )
            pipeline_results.append({"step": 2, "result": res2})
        except Exception as e2:
            logger.error(f"Step 2 failed: {e2}")
            pipeline_results.append({"step": 2, "error": str(e2)})
        
        # STEP 3: IT -> HR (Internal - Email)
        try:
            logger.info(f"Running Pipeline Step 3 for Candidate {candidate_id}")
            res3 = await orchestrator.orchestrate_send(
                message_content=f"Confirming equipment setup for {payload.name}.",
                user_id=str(candidate_id),
                recipient_overrides={"email": hr_email},
                custom_variables={
                    "type": "internal_response", 
                    "sender_email": it_email,
                    **common_vars
                }
            )
            pipeline_results.append({"step": 3, "result": res3})
        except Exception as e3:
            logger.error(f"Step 3 failed: {e3}")
            pipeline_results.append({"step": 3, "error": str(e3)})
        
        # STEP 4: HR -> Candidate (External)
        try:
            logger.info(f"Running Pipeline Step 4 for Candidate {candidate_id}")
            res4 = await orchestrator.orchestrate_send(
                message_content="Great news! Your equipment is being prepared.",
                user_id=str(candidate_id),
                recipient_overrides={"email": payload.email, "phone": payload.phone},
                custom_variables={
                    "type": "onboarding_update", 
                    "sender_email": hr_email,
                    **common_vars
                }
            )
            pipeline_results.append({"step": 4, "result": res4})
        except Exception as e4:
            logger.error(f"Step 4 failed: {e4}")
            pipeline_results.append({"step": 4, "error": str(e4)})
            
    except Exception as e:
        logger.error(f"Pipeline error: {str(e)}")
        # You could choose to delete the candidate here if it failed, but keeping them might be fine
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

    return {
        "success": True,
        "message": "Onboarding pipeline completed",
        "candidate_id": candidate_id,
        "hr_email": hr_email,
        "it_email": it_email,
        "results": pipeline_results
    }
