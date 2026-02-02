from fastapi import APIRouter, WebSocket, status, WebSocketDisconnect
from app.services.docker_monitor import manager
from app.core.utils import get_docker_client, get_current_container_id, process_container_summary
from app.db.database import SessionLocal
from app.db.models import APIKeyModel

router = APIRouter(
    prefix="/ws",
    tags=["websockets"]
)

@router.websocket("/containers/summary")
async def websocket_containers_summary(websocket: WebSocket, api_key: str = None):
    """
    WebSocket endpoint to stream container summaries.
    Usage: ws://host:port/ws/containers/summary?api_key=YOUR_KEY
    """
    await websocket.accept()
    
    # Validate API Key
    db = SessionLocal()
    try:
        if not api_key:
             await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid api key")
             return
             
        key_record = db.query(APIKeyModel).filter(APIKeyModel.key == api_key).first()
        if not key_record:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid api key")
            return
    finally:
        db.close()

    client = get_docker_client()
    self_id = get_current_container_id()
    try:
        containers = client.containers.list(all=True)
        for container in containers:
            summary = process_container_summary(container, self_id)
            await websocket.send_json(summary)
        # Close connection normally after sending all data
        await websocket.close()
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {str(e)}")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except:
            pass
    finally:
        client.close()

@router.websocket("/events")
async def websocket_events(websocket: WebSocket, api_key: str = None):
    """
    WebSocket endpoint to stream Docker events in real-time.
    Usage: ws://host:port/ws/events?api_key=YOUR_KEY
    """
    await websocket.accept()
    
    # Validate API Key
    db = SessionLocal()
    try:
        if not api_key:
             await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
             return
             
        key_record = db.query(APIKeyModel).filter(APIKeyModel.key == api_key).first()
        if not key_record:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    finally:
        db.close()

    manager.active_connections.append(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
