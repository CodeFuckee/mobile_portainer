from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
import docker
from app.core.security import get_api_key
from app.core.utils import get_docker_client

router = APIRouter(
    prefix="/images",
    tags=["images"],
    dependencies=[Depends(get_api_key)]
)

@router.get("", response_model=List[Dict[str, Any]])
async def list_images():
    """
    Get a list of all Docker images.
    """
    client = get_docker_client()
    try:
        images = client.images.list()
        containers = client.containers.list(all=True)
        used_image_ids = {c.attrs['Image'] for c in containers}

        result = []
        for img in images:
            result.append({
                "id": img.id,
                "tags": img.tags,
                "created": img.attrs.get("Created"),
                "size": img.attrs.get("Size"),
                "labels": img.labels,
                "short_id": img.short_id,
                "in_use": img.id in used_image_ids
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving images: {str(e)}")
    finally:
        client.close()

@router.get("/{image_id}", response_model=Dict[str, Any])
async def get_image_details(image_id: str):
    client = get_docker_client()
    try:
        image = client.images.get(image_id)
        
        # Check if image is in use
        containers = client.containers.list(all=True)
        used_image_ids = {c.attrs['Image'] for c in containers}
        
        data = dict(image.attrs or {})
        data["id"] = image.id
        data["short_id"] = image.short_id
        data["tags"] = image.tags
        data["in_use"] = image.id in used_image_ids
        return data
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving image details: {str(e)}")
    finally:
        client.close()

@router.post("/pull")
async def pull_image(data: Dict[str, str]):
    """
    Pull a Docker image.
    Body: {"image": "image_name", "tag": "latest"}
    """
    image_name = data.get("image")
    tag = data.get("tag")
    if not image_name:
        raise HTTPException(status_code=400, detail="Image name is required")
    
    client = get_docker_client()
    try:
        # Pull image
        image = client.images.pull(image_name, tag=tag)
        return {
            "status": "success",
            "id": image.id,
            "tags": image.tags,
            "message": f"Image {image_name}:{tag or 'latest'} pulled successfully"
        }
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=f"Docker API Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error pulling image: {str(e)}")
    finally:
        client.close()
