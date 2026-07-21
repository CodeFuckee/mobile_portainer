from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import uuid
import requests
from app.core.security import get_api_key, hash_password, verify_admin_credentials
from app.core.config import ADMIN_USER
from app.db.database import get_db
from app.db.models import APIKeyModel, AdminCredentialModel, ClusterNode

router = APIRouter(prefix="/admin", tags=["admin"])


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


@router.post("/login")
def login(request: Request, db: Session = Depends(get_db)):
    admin_user = request.headers.get("X-Admin-User")
    admin_pass = request.headers.get("X-Admin-Pass")
    if not verify_admin_credentials(db, admin_user, admin_pass):
        raise HTTPException(status_code=401, detail="Invalid Admin Credentials")

    # 查找已有的 API key，没有则自动创建
    api_key = db.query(APIKeyModel).first()
    if not api_key:
        new_key_str = str(uuid.uuid4().hex)
        api_key = APIKeyModel(key=new_key_str, note="自动创建")
        db.add(api_key)
        db.commit()
        db.refresh(api_key)

    return {"api_key": api_key.key, "id": api_key.id, "note": api_key.note}


@router.post("/password")
def change_password(data: ChangePasswordRequest, db: Session = Depends(get_db)):
    """校验当前管理员密码后，持久化保存新的密码哈希。"""
    if not verify_admin_credentials(db, ADMIN_USER, data.current_password):
        raise HTTPException(status_code=401, detail="当前密码不正确")

    credential = db.get(AdminCredentialModel, 1)
    password_hash = hash_password(data.new_password)
    if credential:
        credential.password_hash = password_hash
    else:
        db.add(AdminCredentialModel(id=1, password_hash=password_hash))
    db.commit()
    return {"message": "密码修改成功"}


@router.get("/keys", dependencies=[Depends(get_api_key)])
def list_keys(db: Session = Depends(get_db)):
    result = db.query(APIKeyModel).all()
    return result


@router.post("/keys", dependencies=[Depends(get_api_key)])
def add_key(data: Dict[str, Any], db: Session = Depends(get_db)):
    new_key_str = data.get("key") or str(uuid.uuid4().hex)
    existing = db.query(APIKeyModel).filter(APIKeyModel.key == new_key_str).first()
    if existing:
        raise HTTPException(status_code=400, detail="Key already exists")

    new_key = APIKeyModel(key=new_key_str, note=data.get("note"))
    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    targets: Optional[List[str]] = data.get("targets")
    apply_all: bool = bool(data.get("apply_all"))
    if apply_all:
        nodes = db.query(ClusterNode).all()
    elif targets:
        nodes = db.query(ClusterNode).filter(ClusterNode.id.in_(targets)).all()
    else:
        nodes = []

    results: List[Dict[str, Any]] = []
    for n in nodes:
        try:
            r = requests.post(
                f"{n.base_url.rstrip('/')}/admin/keys",
                headers={"X-Admin-User": n.admin_user, "X-Admin-Pass": n.admin_pass},
                json={"key": new_key.key, "note": new_key.note},
                timeout=10,
            )
            results.append({"node": n.name, "status": r.status_code})
        except Exception as e:
            results.append({"node": n.name, "error": str(e)})

    return {"key": new_key, "propagation": results}


@router.delete("/keys/{key_str}", dependencies=[Depends(get_api_key)])
def delete_key(key_str: str, db: Session = Depends(get_db)):
    key = db.query(APIKeyModel).filter(APIKeyModel.key == key_str).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    db.delete(key)
    db.commit()
    return {"status": "deleted"}


@router.delete("/keys/{key_str}/propagate", dependencies=[Depends(get_api_key)])
def delete_key_propagate(
    key_str: str, data: Dict[str, Any], db: Session = Depends(get_db)
):
    targets: Optional[List[str]] = data.get("targets")
    apply_all: bool = bool(data.get("apply_all"))
    if apply_all:
        nodes = db.query(ClusterNode).all()
    elif targets:
        nodes = db.query(ClusterNode).filter(ClusterNode.id.in_(targets)).all()
    else:
        nodes = []

    results: List[Dict[str, Any]] = []
    for n in nodes:
        try:
            r = requests.delete(
                f"{n.base_url.rstrip('/')}/admin/keys/{key_str}",
                headers={"X-Admin-User": n.admin_user, "X-Admin-Pass": n.admin_pass},
                timeout=10,
            )
            results.append({"node": n.name, "status": r.status_code})
        except Exception as e:
            results.append({"node": n.name, "error": str(e)})
    return {"status": "deleted", "propagation": results}


@router.get("/nodes", dependencies=[Depends(get_api_key)])
def list_nodes(db: Session = Depends(get_db)):
    return db.query(ClusterNode).all()


@router.post("/nodes", dependencies=[Depends(get_api_key)])
def add_node(data: Dict[str, Any], db: Session = Depends(get_db)):
    name = data.get("name")
    base_url = data.get("base_url")
    admin_user = data.get("admin_user")
    admin_pass = data.get("admin_pass")
    if not all([name, base_url, admin_user, admin_pass]):
        raise HTTPException(status_code=400, detail="Missing fields")
    existing = db.query(ClusterNode).filter(ClusterNode.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Node name exists")

    node = ClusterNode(
        name=name, base_url=base_url, admin_user=admin_user, admin_pass=admin_pass
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@router.delete("/nodes/{node_id}", dependencies=[Depends(get_api_key)])
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(ClusterNode).filter(ClusterNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    db.delete(node)
    db.commit()
    return {"status": "deleted"}


# HTML Page (We can keep this here or in main.py, but better here for organization)
# However, this endpoint is at root "/" so we should define it in main.py or include it here with prefix=""
# I'll put the admin page in a separate router or just here but with prefix ""
# Let's create a separate router for the UI or just put it in main.py for simplicity as it is the landing page.
# Actually, the user asked to split main.py. So let's put it in a separate file app/routers/web_ui.py
