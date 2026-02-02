from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.core.security import get_api_key
from app.core.utils import get_docker_client

router = APIRouter(
    prefix="/networks",
    tags=["networks"],
    dependencies=[Depends(get_api_key)]
)

@router.get("", response_model=List[Dict[str, Any]])
async def list_networks():
    """
    Get a list of all Docker networks.
    """
    client = get_docker_client()
    try:
        networks = client.networks.list()
        result = []
        for net in networks:
            result.append({
                "id": net.id,
                "name": net.name,
                "driver": net.attrs.get("Driver"),
                "short_id": net.short_id,
                "created": net.attrs.get("Created")
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving networks: {str(e)}")
    finally:
        client.close()
