import sys
import asyncio
import os
import aiohttp

async def run_test():
    # Adding src to sys.path to ensure modules load locally if run directly
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
    from src.api.routers.pipeline import onboard_candidate, OnboardCandidateRequest
    
    req = OnboardCandidateRequest(
        client_id=1,
        name="John Doe Test",
        email="john.doe.test@gmail.com",
        phone="+919876543210"
    )
    
    print("Executing onboard_candidate pipeline...")
    try:
        res = await onboard_candidate(req)
        print("PIPELINE RESULT:")
        print(res)
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
